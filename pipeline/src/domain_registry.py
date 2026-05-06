"""
Domain plugin registry (Issue #684).

Maps a domain string (e.g. ``"nfl"``, ``"politics.us"``,
``"finance.equities"``) to the ``DomainProtocol`` instance that handles
that domain at the **pipeline-orchestration** layer.

This registry is for the broader ``DomainProtocol`` defined in
``pipeline/src/domain_protocol.py`` (prompt + scoring + resolution
adapter).  The narrower entity-resolution ``DomainPlugin`` ABC from
``pipeline/src/domain_plugin.py`` (issue #685) has its own dispatcher
under that file; the two systems are intentionally decoupled so a
plugin author can adopt either or both without mandatory inheritance.

Usage::

    from src.domain_registry import get_plugin

    plugin = get_plugin("nfl")
    prompt = plugin.extraction_prompt(article)

The registry is built lazily on first access so import-time side effects
in plugin modules (config loading, constant evaluation) are paid only
once and only if the registry is actually used.

Registering additional plugins::

    from src.domain_registry import register
    from my_pkg import MyDomainPlugin

    register(MyDomainPlugin())

``register`` validates the candidate against the ``DomainProtocol``
via ``isinstance`` and against ``validate_testability_weights`` so
misconfigured plugins fail at registration rather than mid-pipeline.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from src.domain_protocol import DomainProtocol, validate_testability_weights

logger = logging.getLogger(__name__)


_registry: dict[str, DomainProtocol] = {}
# Reentrant — ``_ensure_loaded`` holds the lock while calling ``register``,
# which re-acquires it.  RLock makes that recursion safe.
_registry_lock = threading.RLock()
_default_loaded = False


def _load_default_plugins() -> None:
    """Register the plugins that ship with this repo.

    Called lazily by ``_ensure_loaded`` so importing this module is cheap
    even in test environments that mock the registry.
    """
    # Local import to avoid a circular dependency: ``nfl_plugin`` imports
    # from ``domain_protocol``, which is fine, but importing it at module
    # load here would couple every consumer of ``domain_registry`` to the
    # NFL plugin's import surface.
    from src.plugins.nfl_plugin import NFLPlugin

    register(NFLPlugin())


def _ensure_loaded() -> None:
    """Load default plugins on first access; idempotent."""
    global _default_loaded
    if _default_loaded:
        return
    with _registry_lock:
        if _default_loaded:
            return
        _load_default_plugins()
        _default_loaded = True


def register(plugin: DomainProtocol, *, replace: bool = False) -> None:
    """
    Register a plugin.

    Parameters
    ----------
    plugin : DomainProtocol
        Any object satisfying the ``DomainProtocol`` Protocol.
    replace : bool
        If False (default), raises ``ValueError`` when a plugin for the
        same ``domain`` is already registered.  If True, silently
        overwrites — useful for tests.

    Raises
    ------
    TypeError
        If ``plugin`` does not satisfy the ``DomainProtocol``.
    ValueError
        If ``plugin.domain`` is empty, contains whitespace, or collides
        with an existing registration when ``replace=False``.
    """
    if not isinstance(plugin, DomainProtocol):
        raise TypeError(
            f"register: object {type(plugin).__name__!r} does not satisfy "
            "DomainProtocol (missing one of: domain, extraction_prompt, "
            "resolve_entities, claim_categories, resolution_adapter, "
            "testability_weights)"
        )
    domain = getattr(plugin, "domain", "")
    if not domain or not isinstance(domain, str) or domain.strip() != domain:
        raise ValueError(
            f"register: plugin.domain must be a non-empty, non-padded "
            f"string; got {domain!r}"
        )

    # Validate testability_weights eagerly — catches bad plugins at
    # registration rather than at first extraction.
    try:
        weights = plugin.testability_weights()
    except Exception as exc:
        raise ValueError(
            f"register: {domain!r}.testability_weights() raised: {exc}"
        ) from exc
    validate_testability_weights(weights)

    with _registry_lock:
        if domain in _registry and not replace:
            raise ValueError(
                f"register: domain {domain!r} already registered "
                f"(pass replace=True to overwrite)"
            )
        _registry[domain] = plugin
        logger.info(f"Registered DomainProtocol plugin for {domain!r}")


def unregister(domain: str) -> None:
    """Remove a plugin from the registry. No-op if not registered."""
    with _registry_lock:
        _registry.pop(domain, None)


def get_plugin(domain: str) -> DomainProtocol:
    """
    Return the plugin instance for ``domain``.

    Parameters
    ----------
    domain : str
        Domain identifier matching ``plugin.domain``.  Case-sensitive.
        Examples: ``"nfl"``, ``"politics.us"``, ``"finance.equities"``.

    Returns
    -------
    DomainProtocol

    Raises
    ------
    ValueError
        If no plugin is registered for ``domain``.  The error message
        lists the currently registered domains so misconfiguration is
        easy to debug.
    """
    _ensure_loaded()
    plugin = _registry.get(domain)
    if plugin is None:
        known = sorted(_registry.keys())
        raise ValueError(
            f"No DomainProtocol plugin registered for domain {domain!r}. "
            f"Registered domains: {known}"
        )
    return plugin


def list_plugins() -> list[str]:
    """Return the sorted list of registered domain identifiers."""
    _ensure_loaded()
    with _registry_lock:
        return sorted(_registry.keys())


def reset_registry(*, _testing_only: bool = False) -> None:
    """
    Clear the registry.  Test-only — never call from production code.

    The keyword-only ``_testing_only=True`` is required to make accidental
    use obvious in greps.
    """
    if not _testing_only:
        raise RuntimeError(
            "reset_registry must be called with _testing_only=True; "
            "this function is for tests only."
        )
    global _default_loaded
    with _registry_lock:
        _registry.clear()
        _default_loaded = False


def _peek_registry() -> dict[str, DomainProtocol]:
    """Return a shallow copy of the registry. Internal/diagnostic use."""
    _ensure_loaded()
    with _registry_lock:
        return dict(_registry)


# Public re-exports for convenience.
def get_plugin_or_none(domain: str) -> Optional[DomainProtocol]:
    """Return plugin for ``domain`` or ``None`` if not registered."""
    _ensure_loaded()
    return _registry.get(domain)


__all__ = [
    "register",
    "unregister",
    "get_plugin",
    "get_plugin_or_none",
    "list_plugins",
    "reset_registry",
]

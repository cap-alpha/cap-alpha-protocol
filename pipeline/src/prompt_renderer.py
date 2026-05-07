"""
Prompt template renderer (Issue #687).

Renders domain-specific extraction prompts from Jinja2 templates, composing
shared schema sections (testability_schema.jinja, output_format.jinja) with
domain-specific claim categories and examples.

Directory layout:
  pipeline/config/domains/
    _shared/
      testability_schema.jinja   — shared scoring rubric + hedge_level/stance/resolution_condition
      output_format.jinja        — JSON output structure (parameterised by claim_categories)
    nfl/
      extraction_prompt.jinja    — top-level template, {% include 'output_format.jinja' %} etc.
      claim_categories.yaml      — domain-specific category list
      examples.jinja             — domain-specific few-shot examples

Design decisions (see issue #687):
  - Jinja2 for template composition: {% include %} enables shared sections without
    copy-paste duplication across domains.  Python str.format() cannot do cross-file
    includes.
  - Rendering happens at startup (once per domain), cached in _PROMPT_CACHE.
    Per-article variables (text, author, etc.) are injected at call time via
    Jinja2 variables, not .format() — so the full render happens once.
  - Versioning: SHA-256 of the fully-rendered template (before per-article data is
    substituted) is stored as the domain's prompt_version.  Changing any included
    file changes the hash, surfacing the change in the BigQuery raw_utterance rows.
"""

import hashlib
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Root of the domains config directory.
DOMAINS_ROOT = Path(__file__).resolve().parent.parent / "config" / "domains"


def _load_claim_categories(domain: str) -> list[str]:
    """Load claim category list from domains/<domain>/claim_categories.yaml."""
    path = DOMAINS_ROOT / domain / "claim_categories.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"claim_categories.yaml not found for domain {domain!r}: {path}"
        )
    with open(path) as f:
        data = yaml.safe_load(f)
    categories = data.get("categories", [])
    if not isinstance(categories, list) or not categories:
        raise ValueError(
            f"claim_categories.yaml for domain {domain!r} must have a non-empty 'categories' list"
        )
    return categories


def _build_jinja_env(domain: str):
    """
    Build a Jinja2 Environment with two loaders:
      1. domain-specific template dir (e.g. config/domains/nfl/)
      2. shared template dir       (e.g. config/domains/_shared/)

    The ChoiceLoader tries the domain dir first, then _shared, so
    {% include 'testability_schema.jinja' %} (resolves from _shared/) and
    {% include 'examples.jinja' %} (resolves from the domain dir) both work correctly.
    Shared templates are referenced by basename only — no path prefix needed.
    """
    try:
        from jinja2 import ChoiceLoader, Environment, FileSystemLoader
    except ImportError:
        raise ImportError(
            "Jinja2 is required for prompt template rendering. "
            "Install it with: pip install Jinja2>=3.1.0"
        )

    domain_dir = DOMAINS_ROOT / domain
    shared_dir = DOMAINS_ROOT / "_shared"

    if not domain_dir.exists():
        raise FileNotFoundError(f"Domain template directory not found: {domain_dir}")

    loader = ChoiceLoader(
        [
            FileSystemLoader(str(domain_dir)),
            FileSystemLoader(str(shared_dir)),
        ]
    )
    env = Environment(loader=loader, keep_trailing_newline=True, autoescape=False)
    return env


@lru_cache(maxsize=16)
def _render_base_template(domain: str) -> tuple[str, tuple]:
    """
    Compute the prompt version hash and claim categories for a domain.

    Returns (prompt_version_hash: str, claim_categories: tuple).

    Cached indefinitely per process (templates are static at runtime).
    Per-article variables are substituted in render_extraction_prompt().
    """
    env = _build_jinja_env(domain)
    claim_categories = _load_claim_categories(domain)

    template = env.get_template("extraction_prompt.jinja")

    # Render with sentinel values to produce the "structure hash".
    # This hash changes when any template file changes, regardless of article content.
    sentinel_render = template.render(
        sport=domain,
        published_date="__SENTINEL__",
        source_name="__SENTINEL__",
        author="__SENTINEL__",
        title="__SENTINEL__",
        text="__SENTINEL__",
        claim_categories=claim_categories,
    )
    version_hash = hashlib.sha256(sentinel_render.encode("utf-8")).hexdigest()[:8]

    # Return categories as a tuple so the lru_cache can hash it.
    return version_hash, tuple(claim_categories)


def render_extraction_prompt(
    domain: str,
    sport: str,
    published_date: str,
    source_name: str,
    author: str,
    title: str,
    text: str,
    max_text_chars: int = 4000,
) -> tuple[str, str]:
    """
    Render the extraction prompt for a given domain with per-article data.

    Args:
        domain:          Domain key, e.g. "nfl". Maps to config/domains/<domain>/.
        sport:           Human-readable sport label, e.g. "NFL" or "nfl".
        published_date:  ISO date string or "Unknown".
        source_name:     Media source name.
        author:          Author name.
        title:           Article title.
        text:            Article body text (truncated to max_text_chars).
        max_text_chars:  Max chars of article text to include in prompt (default 4000).

    Returns:
        (rendered_prompt: str, prompt_version: str)
        prompt_version is the 8-char SHA-256 hex prefix of the base template
        (changes when any template file changes, not when article content changes).
    """
    # Load claim categories + compute version hash (cached)
    version_hash, claim_categories = _render_base_template(domain)

    # Re-build env (not cached, but cheap) and render with real article data.
    env = _build_jinja_env(domain)
    template = env.get_template("extraction_prompt.jinja")

    rendered = template.render(
        sport=sport,
        published_date=published_date or "Unknown",
        source_name=source_name or "Unknown",
        author=author or "Unknown",
        title=title or "Untitled",
        text=text[:max_text_chars],
        claim_categories=claim_categories,
    )
    return rendered, version_hash


def get_prompt_version(domain: str) -> str:
    """Return the 8-char prompt version hash for a domain (cached)."""
    version_hash, _ = _render_base_template(domain)
    return version_hash

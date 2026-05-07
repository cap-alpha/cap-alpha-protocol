"""
DomainPlugin — abstract base class for multi-domain extraction (Issue #685).

Each domain (NFL, politics, finance, etc.) implements this interface to provide:
  - Entity resolution  (resolve_entities)
  - Domain detection   (matches)
  - Claim category mapping

## Entity resolution strategy — Option C: Cached inline with graceful degradation

Design decision from issue #685:

  We use **cached inline** (Option C) with a per-process LRU dict as the cache
  backend — no Redis required.  The cache is keyed by (domain, raw_name) and
  populated on first access; subsequent lookups within the same extraction run
  (and between runs within the same process lifetime) are instant.

  Rationale:

  * The pipeline is per-article, not streaming.  Each article typically mentions
    a small, overlapping set of entities (the same team, the same player, the
    same politician).  An in-memory cache hits near-100% within a run and
    meaningfully across consecutive runs for top-tier sources.

  * Inline resolution keeps the pipeline single-pass.  Option B (async batch)
    would require a second job, a second BQ write, and a join step that adds
    operational complexity without material throughput gain for the current
    article volume (hundreds/day, not millions).

  * Option A (naive inline, no cache) is untenable for politics: Ballotpedia
    has aggressive rate limits and per-call latency that would multiply
    extraction time 10x per article.

  * No Redis on budget.  The LRU dict is process-scoped and is good enough.
    If a cache miss goes to a slow external API (Ballotpedia), resolve_entities
    MUST return a best-effort result (UNRESOLVED:<name>) on timeout rather than
    blocking or raising.  Callers must never be held up longer than
    ENTITY_RESOLVE_TIMEOUT_S seconds per entity.

  When to switch strategies:

  * Switch to B (async batch) if extraction throughput exceeds ~500 articles/hr
    and profiling shows entity API latency is a bottleneck.
  * Add Redis if cross-process cache sharing becomes valuable (multi-worker
    deployment) or if in-memory cache size becomes problematic.

## Cache contract

  * Cache key  : (domain: str, raw_name: str)  — domain-scoped to avoid
                 collisions (e.g. "Eagles" is a team in NFL and a basketball
                 team in politics-adjacent sports coverage).
  * Cache value: resolved entity_id string, or "UNRESOLVED:<raw_name>".
  * Cache size : MAX_ENTITY_CACHE_SIZE entries per-process (LRU eviction).
  * TTL        : process lifetime (no expiry).  Stale entries are acceptable
                 because entity IDs are stable; new entities appear gradually
                 and the UNRESOLVED fallback means data is never silently
                 dropped.
"""

from __future__ import annotations

import functools
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

# Per-process LRU cache bound.  1 024 entries covers ~10 000 article runs
# comfortably (typical article mentions 3–8 distinct entities).
MAX_ENTITY_CACHE_SIZE = 1_024

# Maximum seconds to wait for a single external entity API call (Ballotpedia,
# SportsDataIO, etc.).  Exceeded calls return UNRESOLVED immediately.
ENTITY_RESOLVE_TIMEOUT_S = float(2.0)


class EntityResolutionResult:
    """
    Lightweight result for a single entity resolution.

    Attributes:
        raw_name:    The original string extracted by the LLM (e.g. "Patrick Mahomes").
        entity_id:   Resolved canonical ID (e.g. "nfl:player:mahomes-patrick-1986"),
                     or "UNRESOLVED:<raw_name>" when resolution failed.
        source:      Where the ID came from: "cache" | "bigquery" | "external_api"
                     | "unresolved".
        confidence:  Float 0–1.  1.0 for exact BQ/cache hits; lower for fuzzy/LLM
                     matches; 0.0 for UNRESOLVED.
    """

    __slots__ = ("raw_name", "entity_id", "source", "confidence")

    def __init__(
        self,
        raw_name: str,
        entity_id: str,
        source: str = "unresolved",
        confidence: float = 0.0,
    ) -> None:
        self.raw_name = raw_name
        self.entity_id = entity_id
        self.source = source
        self.confidence = confidence

    @classmethod
    def unresolved(cls, raw_name: str) -> "EntityResolutionResult":
        return cls(
            raw_name=raw_name,
            entity_id=f"UNRESOLVED:{raw_name}",
            source="unresolved",
            confidence=0.0,
        )

    def is_resolved(self) -> bool:
        return not self.entity_id.startswith("UNRESOLVED:")

    def __repr__(self) -> str:
        return (
            f"EntityResolutionResult(raw={self.raw_name!r}, "
            f"id={self.entity_id!r}, src={self.source!r}, conf={self.confidence:.2f})"
        )


class DomainPlugin(ABC):
    """
    Abstract base class for per-domain extraction behaviour.

    Concrete subclasses:
      - NflDomainPlugin      (pipeline/src/domains/nfl.py, to be created)
      - PoliticsDomainPlugin (pipeline/src/domains/politics.py, to be created)
      - FinanceDomainPlugin  (pipeline/src/domains/finance.py, to be created)

    ### Entity resolution contract (Option C — cached inline)

    ``resolve_entities`` is called **inline** during extraction, immediately
    after the 32B model extracts each utterance batch.  The call MUST:

    1. Check the per-domain in-memory LRU cache first.
    2. On a cache miss, attempt resolution via the domain's canonical data
       source (BQ entity table, SportsDataIO, Ballotpedia, etc.).
    3. Return within ENTITY_RESOLVE_TIMEOUT_S regardless of external API state;
       return EntityResolutionResult.unresolved() on timeout.
    4. Populate the cache with the result (even for UNRESOLVED, to avoid
       hammering the API on repeated lookups of unknown entities).
    5. Never raise — callers (assertion_extractor) catch no entity exceptions.

    The shared ``_entity_cache`` dict is provided on the base class and is
    keyed by ``(domain_key, raw_name)``.  Subclasses MUST use
    ``self._entity_cache`` rather than their own dict so the bound enforced
    by ``MAX_ENTITY_CACHE_SIZE`` is applied globally across all domain plugins
    in the same process.
    """

    # Class-level LRU cache shared across all plugin instances in the process.
    # Key: (domain_key: str, raw_name: str) → EntityResolutionResult
    _entity_cache: dict[tuple[str, str], EntityResolutionResult] = {}

    # --- Abstract properties -------------------------------------------------

    @property
    @abstractmethod
    def domain_key(self) -> str:
        """
        Short lowercase identifier for this domain, e.g. "nfl", "politics",
        "finance".  Used as the first component of the entity cache key.
        """
        ...

    # --- Abstract methods ----------------------------------------------------

    @abstractmethod
    def matches(self, source_id: str, text: str) -> bool:
        """
        Return True if this plugin should handle the given article.

        Called once per article before extraction begins.  Implementations
        should be cheap (keyword match, source_id prefix, config lookup).

        Args:
            source_id: The source identifier from raw_pundit_media.
            text:      Article body text (truncated to first 500 chars is fine).
        """
        ...

    @abstractmethod
    def resolve_entities(
        self,
        raw_names: list[str],
        *,
        db: Optional[object] = None,
        timeout_s: float = ENTITY_RESOLVE_TIMEOUT_S,
    ) -> dict[str, EntityResolutionResult]:
        """
        Resolve a batch of raw entity name strings to canonical entity IDs.

        **Strategy: cached inline (Option C from issue #685).**

        Called inline after the 32B model returns utterances for a single
        article.  Implementations MUST:

        1. Return cache hits immediately without any I/O.
        2. Batch all cache-miss names into a single external request where
           possible (e.g. one BQ query for all player names at once, one
           Ballotpedia bulk call).
        3. Respect ``timeout_s``; return UNRESOLVED entries for any name not
           resolved within the deadline.
        4. Cache all results (including UNRESOLVED) to prevent repeated API
           hits for unknown entities.
        5. Never raise — wrap all I/O in try/except and fall back to
           UNRESOLVED on error.

        Args:
            raw_names:  List of entity name strings as extracted by the LLM.
                        May contain duplicates; callers de-dup before calling.
            db:         Optional DBManager instance for BigQuery lookups.
                        Plugins that only use external APIs may ignore this.
            timeout_s:  Hard deadline in seconds for external API calls.
                        Defaults to ENTITY_RESOLVE_TIMEOUT_S (2.0 s).

        Returns:
            dict mapping each raw_name → EntityResolutionResult.
            Every name in ``raw_names`` MUST have an entry in the result dict;
            names that could not be resolved get EntityResolutionResult.unresolved().

        Example:
            >>> plugin = NflDomainPlugin()
            >>> results = plugin.resolve_entities(
            ...     ["Patrick Mahomes", "Kansas City Chiefs", "UNKNOWN_PLAYER_XYZ"],
            ...     db=db_manager,
            ... )
            >>> results["Patrick Mahomes"].entity_id
            'nfl:player:mahomes-patrick-1986'
            >>> results["UNKNOWN_PLAYER_XYZ"].is_resolved()
            False
        """
        ...

    @abstractmethod
    def valid_claim_categories(self) -> frozenset[str]:
        """
        Return the set of claim_category values valid for this domain.

        Used by the extractor to validate LLM output and reject cross-domain
        category leakage (e.g. an NFL plugin should not accept
        "election_outcome" as a valid category).
        """
        ...

    # --- Concrete helpers shared by all plugins ------------------------------

    def _cache_get(self, raw_name: str) -> Optional[EntityResolutionResult]:
        """Return cached result for (domain_key, raw_name), or None if not cached."""
        return self._entity_cache.get((self.domain_key, raw_name))

    def _cache_put(self, raw_name: str, result: EntityResolutionResult) -> None:
        """
        Store result in the class-level cache, evicting oldest entry if full.

        Eviction is LRU-approximate: when the cache is at capacity we remove
        an arbitrary entry (first key).  A proper LRU via ``functools.lru_cache``
        cannot be used here because the cache is shared state and keyed
        dynamically.  At 1 024 entries and modest article volume the eviction
        policy barely matters.
        """
        key = (self.domain_key, raw_name)
        if key in self._entity_cache:
            # Refresh: move to most-recent by delete-and-reinsert
            del self._entity_cache[key]
        elif len(self._entity_cache) >= MAX_ENTITY_CACHE_SIZE:
            # Evict oldest entry (insertion-order guaranteed in Python 3.7+)
            oldest = next(iter(self._entity_cache))
            del self._entity_cache[oldest]
            logger.debug(
                f"Entity cache evicted {oldest!r} (size={MAX_ENTITY_CACHE_SIZE})"
            )
        self._entity_cache[key] = result

    def cache_stats(self) -> dict[str, int]:
        """
        Return a snapshot of entity cache usage for this domain.

        Returns:
            {"domain": self.domain_key, "entries": N, "capacity": MAX_ENTITY_CACHE_SIZE}
        """
        domain_entries = sum(1 for (d, _) in self._entity_cache if d == self.domain_key)
        return {
            "domain": self.domain_key,
            "entries": domain_entries,
            "capacity": MAX_ENTITY_CACHE_SIZE,
        }

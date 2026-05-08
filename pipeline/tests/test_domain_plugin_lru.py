"""
Regression tests for DomainPlugin LRU eviction behaviour (issue #734).

PR #714 replaced a plain dict with OrderedDict to give correct LRU semantics.
_cache_get promotes a hit to the MRU end via move_to_end; _cache_put evicts
the LRU entry (last=False) when the cache is at capacity.  These tests lock
in that behaviour so a future refactor cannot silently regress to FIFO or
random eviction.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional

import pytest

import src.domain_plugin as _mod
from src.domain_plugin import (
    DomainPlugin,
    EntityResolutionResult,
)


# ---------------------------------------------------------------------------
# Minimal concrete subclass — just enough to instantiate DomainPlugin
# ---------------------------------------------------------------------------


class _TestPlugin(DomainPlugin):
    """Minimal DomainPlugin subclass used only for LRU unit tests."""

    @property
    def domain_key(self) -> str:
        return "test"

    def matches(self, source_id: str, text: str) -> bool:
        return True

    def resolve_entities(
        self,
        raw_names: list[str],
        *,
        db: Optional[object] = None,
        timeout_s: float = 2.0,
    ) -> dict[str, EntityResolutionResult]:
        return {name: EntityResolutionResult.unresolved(name) for name in raw_names}

    def valid_claim_categories(self) -> frozenset[str]:
        return frozenset({"test_category"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(name: str) -> EntityResolutionResult:
    return EntityResolutionResult(
        raw_name=name,
        entity_id=f"test:entity:{name}",
        source="bigquery",
        confidence=1.0,
    )


@pytest.fixture(autouse=True)
def _isolated_cache():
    """
    Wipe the class-level LRU cache before and after every test.

    The cache is shared across all DomainPlugin instances in the process, so
    without this fixture test ordering would affect outcomes.  We also restore
    MAX_ENTITY_CACHE_SIZE in case a test overrides it.
    """
    original_max = _mod.MAX_ENTITY_CACHE_SIZE
    DomainPlugin._entity_cache = OrderedDict()
    yield
    DomainPlugin._entity_cache = OrderedDict()
    _mod.MAX_ENTITY_CACHE_SIZE = original_max


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLruEviction:
    def test_lru_eviction_keeps_recently_used(self) -> None:
        """
        Fill the cache to capacity with a hot key inserted first (making it
        the LRU candidate).  Repeatedly call _cache_get on the hot key to
        promote it to MRU.  Then insert a new key, triggering eviction.

        Assertions:
          (a) hot_key is still present in the cache.
          (b) The oldest cold key (first inserted after hot_key) was evicted.
        """
        # Use a small effective capacity so the test does not insert 1 024 entries.
        _mod.MAX_ENTITY_CACHE_SIZE = 4
        plugin = _TestPlugin()

        # Insert hot_key first — it starts as the LRU candidate.
        plugin._cache_put("hot_key", _make_result("hot_key"))

        # Fill the remaining slots with cold keys.
        cold_keys = ["cold_a", "cold_b", "cold_c"]
        for ck in cold_keys:
            plugin._cache_put(ck, _make_result(ck))

        assert len(DomainPlugin._entity_cache) == 4  # at capacity

        # Promote hot_key to MRU via repeated cache hits.
        for _ in range(5):
            result = plugin._cache_get("hot_key")
            assert result is not None, "_cache_get returned None for an existing key"

        # Insert one more entry — must trigger eviction of the LRU.
        plugin._cache_put("new_key", _make_result("new_key"))

        assert len(DomainPlugin._entity_cache) == 4  # size unchanged

        # (a) hot_key must survive — it was recently used.
        assert plugin._cache_get("hot_key") is not None, (
            "hot_key was evicted even though it was recently accessed"
        )

        # (b) cold_a must have been evicted — it is the oldest untouched entry.
        assert DomainPlugin._entity_cache.get(("test", "cold_a")) is None, (
            "cold_a should have been evicted (oldest LRU entry) but is still in cache"
        )

    def test_lru_promotion_on_hit(self) -> None:
        """
        Insert keys A then B into a capacity-2 cache (so it is immediately full).
        Access A via _cache_get to promote it to MRU — B becomes the LRU.
        Insert C, triggering eviction.

        Assertions:
          - B was evicted (it became the LRU after A was promoted).
          - A is still present (it was promoted to MRU).
          - C is present (it was just inserted).
        """
        _mod.MAX_ENTITY_CACHE_SIZE = 2
        plugin = _TestPlugin()

        # Insert A then B; cache is now full.
        plugin._cache_put("A", _make_result("A"))
        plugin._cache_put("B", _make_result("B"))
        assert len(DomainPlugin._entity_cache) == 2

        # Promote A to MRU — B is now the LRU.
        result_a = plugin._cache_get("A")
        assert result_a is not None, "_cache_get returned None for key A"

        # Insert C — must evict the LRU, which is now B.
        plugin._cache_put("C", _make_result("C"))

        assert DomainPlugin._entity_cache.get(("test", "B")) is None, (
            "B should have been evicted (LRU after A was promoted) but is still present"
        )
        assert DomainPlugin._entity_cache.get(("test", "A")) is not None, (
            "A should still be in cache (it was promoted to MRU) but was evicted"
        )
        assert DomainPlugin._entity_cache.get(("test", "C")) is not None, (
            "C should be in cache but is missing"
        )

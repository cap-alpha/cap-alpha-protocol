"""
Politics DomainProtocol plugin — STUB (Issue #684).

Per the design issue acceptance criteria, this stub exists so the protocol
shape is exercised by something *other* than the NFL implementation.  It
intentionally does NOT define a working extraction prompt or a real
resolution adapter — those land in a follow-up issue once the political
corpus is curated and the entity vocabulary is settled.

What this stub provides today:
    - ``domain = "politics.us"`` (matches ``silver_v2_core.domain_taxonomy``)
    - ``claim_categories()`` returning the agreed enum.
    - ``testability_weights()`` reflecting the design rationale on issue
      #684 (predicate_falsifiability up, resolution_horizon_defined down).
    - ``extraction_prompt()`` raising ``NotImplementedError`` to make
      accidental wiring obvious.
    - ``resolve_entities()`` and ``resolution_adapter()`` returning
      "unresolved" / "pending" placeholders so the plugin can be loaded
      into the registry without crashing the orchestrator.

This stub is NOT registered by default.  Enable it in tests or an
explicit dispatcher config when the politics corpus is ready.
"""

from __future__ import annotations

from src.domain_protocol import ResolutionResult

POLITICS_CLAIM_CATEGORIES: list[str] = [
    "election_outcome",
    "polling_prediction",
    "appointment",
    "legislation",
    "policy_prediction",
]

# Politics-tuned weights (rationale on issue #684):
#   - elections have fixed dates, so resolution_horizon_defined matters less
#   - political language is deliberately vague, so predicate_falsifiability
#     matters more
#   - thresholds are usually expressed as binary win/lose so
#     threshold_concreteness gets the same weight as default
POLITICS_TESTABILITY_WEIGHTS: dict[str, float] = {
    "subject_specificity": 0.20,
    "predicate_falsifiability": 0.40,
    "threshold_concreteness": 0.20,
    "resolution_horizon_defined": 0.05,
    "evidence_accessibility": 0.15,
}


class PoliticsPlugin:
    """Stub politics plugin — see module docstring."""

    domain: str = "politics.us"

    def extraction_prompt(self, article: dict) -> str:
        raise NotImplementedError(
            "PoliticsPlugin.extraction_prompt is not yet implemented. "
            "See issue #684 follow-up for political-corpus prompt design."
        )

    def resolve_entities(self, utterance: dict) -> dict:
        out = dict(utterance)
        out.setdefault("entities", {})
        out["entity_resolved"] = False
        return out

    def claim_categories(self) -> list[str]:
        return list(POLITICS_CLAIM_CATEGORIES)

    def resolution_adapter(self, claim: dict) -> ResolutionResult:
        return ResolutionResult(
            outcome="pending",
            confidence=0.0,
            notes="PoliticsPlugin.resolution_adapter not yet implemented.",
        )

    def testability_weights(self) -> dict[str, float]:
        return dict(POLITICS_TESTABILITY_WEIGHTS)


__all__ = [
    "PoliticsPlugin",
    "POLITICS_CLAIM_CATEGORIES",
    "POLITICS_TESTABILITY_WEIGHTS",
]

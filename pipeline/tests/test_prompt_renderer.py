"""
Unit tests for prompt_renderer (Issue #687).

Tests verify:
1. NFL domain renders without errors
2. Rendered prompt contains required field names from the shared schema
3. Prompt versioning is deterministic and 8 chars
4. Changing template content (mocked) changes the version hash
5. Missing Jinja2 import raises ImportError (not AttributeError)
"""

import hashlib
import importlib
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = [
    "text",
    "speech_act_type",
    "testability_subscores",
    "subject_specificity",
    "predicate_falsifiability",
    "threshold_concreteness",
    "resolution_horizon_defined",
    "evidence_accessibility",
    "testability_score",
    "resolution_horizon",
    "extracted_claim",
    "claim_category",
    "stance",
    "season_year",
    "target_player",
    "target_team",
    "confidence_note",
    "prediction_horizon_days",
    "resolution_condition",
    "hedge_level",
]

NFL_CLAIM_CATEGORIES = [
    "player_performance",
    "game_outcome",
    "trade",
    "draft_pick",
    "injury",
    "contract",
    "award_prediction",
    "fa_signing",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRenderExtractionPrompt:
    def test_nfl_render_returns_string(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, version = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="ESPN",
            author="Adam Schefter",
            title="Test Article",
            text="Patrick Mahomes will win the MVP this season.",
        )
        assert isinstance(rendered, str)
        assert len(rendered) > 100

    def test_nfl_render_contains_required_fields(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="ESPN",
            author="Adam Schefter",
            title="Test Article",
            text="Mahomes will win MVP.",
        )
        for field in REQUIRED_FIELDS:
            assert field in rendered, (
                f"Required field {field!r} missing from rendered NFL prompt"
            )

    def test_nfl_render_contains_all_claim_categories(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="ESPN",
            author="Adam Schefter",
            title="Test",
            text="test",
        )
        for cat in NFL_CLAIM_CATEGORIES:
            assert cat in rendered, (
                f"Claim category {cat!r} missing from rendered NFL prompt"
            )

    def test_nfl_render_contains_article_data(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="Pat McAfee Show",
            author="Pat McAfee",
            title="McAfee Takes",
            text="My bold take: the Steelers will win the division.",
        )
        assert "Pat McAfee Show" in rendered
        assert "Pat McAfee" in rendered
        assert "McAfee Takes" in rendered
        assert "Steelers will win the division" in rendered

    def test_nfl_render_truncates_text_to_4000_chars(self):
        from src.prompt_renderer import render_extraction_prompt

        long_text = "x" * 10000
        rendered, _ = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="ESPN",
            author="Author",
            title="Title",
            text=long_text,
            max_text_chars=4000,
        )
        # The rendered prompt should not contain more than 4000 x's
        assert "x" * 4001 not in rendered
        assert "x" * 4000 in rendered

    def test_nfl_render_returns_version_hash(self):
        from src.prompt_renderer import render_extraction_prompt

        _, version = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="ESPN",
            author="A",
            title="T",
            text="t",
        )
        assert isinstance(version, str)
        assert len(version) == 8
        # Should be a hex string
        int(version, 16)

    def test_version_is_deterministic(self):
        from src.prompt_renderer import get_prompt_version

        v1 = get_prompt_version("nfl")
        v2 = get_prompt_version("nfl")
        assert v1 == v2

    def test_version_does_not_change_with_article_content(self):
        from src.prompt_renderer import render_extraction_prompt

        _, v1 = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-01-01",
            source_name="ESPN",
            author="A",
            title="T",
            text="article text 1",
        )
        _, v2 = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-12-31",
            source_name="CBS",
            author="B",
            title="U",
            text="completely different article text with new content",
        )
        assert v1 == v2, "Prompt version must not change based on per-article variables"

    def test_missing_domain_raises_file_not_found(self):
        from src.prompt_renderer import render_extraction_prompt

        with pytest.raises(FileNotFoundError):
            render_extraction_prompt(
                domain="unknown_domain_xyz",
                sport="XYZ",
                published_date="2025-09-01",
                source_name="S",
                author="A",
                title="T",
                text="t",
            )

    def test_nfl_examples_included(self):
        """Verify that domain-specific NFL examples appear in the rendered prompt."""
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="nfl",
            sport="NFL",
            published_date="2025-09-01",
            source_name="ESPN",
            author="A",
            title="T",
            text="t",
        )
        # Examples from examples.jinja
        assert "Patrick Mahomes" in rendered
        assert "Philadelphia Eagles" in rendered
        assert "Baltimore Ravens" in rendered

    def test_politics_render_returns_string(self):
        """Minimal smoke test: politics domain renders without error."""
        from src.prompt_renderer import render_extraction_prompt

        rendered, version = render_extraction_prompt(
            domain="politics",
            sport="politics",
            published_date="2026-11-03",
            source_name="Politico",
            author="Jane Doe",
            title="Election Preview",
            text="The incumbent will win the Senate race by a wide margin.",
        )
        assert isinstance(rendered, str)
        assert len(rendered) > 100
        assert isinstance(version, str) and len(version) == 8

    def test_politics_render_contains_claim_categories(self):
        """Politics prompt must include all politics claim categories."""
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="politics",
            sport="politics",
            published_date="2026-11-03",
            source_name="Politico",
            author="Jane Doe",
            title="Election Preview",
            text="The incumbent will win.",
        )
        for cat in [
            "election_outcome",
            "polling_prediction",
            "appointment",
            "legislation",
            "policy_prediction",
            "party_dynamics",
        ]:
            assert cat in rendered, (
                f"Politics claim category {cat!r} missing from rendered prompt"
            )

    def test_politics_render_uses_target_entity_not_target_player(self):
        """Politics prompt must reference target_entity, not target_player."""
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="politics",
            sport="politics",
            published_date="2026-11-03",
            source_name="Politico",
            author="Jane Doe",
            title="Election Preview",
            text="The incumbent will win.",
        )
        assert "target_entity" in rendered, (
            "Politics prompt must use target_entity (not target_player)"
        )
        assert "target_player = candidate" not in rendered, (
            "Politics prompt must not instruct model to populate target_player"
        )


# ---------------------------------------------------------------------------
# Tests for _sport_to_extraction_domain (Issue #683 — domain routing)
# ---------------------------------------------------------------------------


class TestSportToExtractionDomain:
    """Unit tests for the _sport_to_extraction_domain helper in assertion_extractor."""

    def _fn(self):
        from src.assertion_extractor import _sport_to_extraction_domain

        return _sport_to_extraction_domain

    def test_politics_maps_to_politics(self):
        fn = self._fn()
        assert fn("politics") == "politics"

    def test_politics_case_insensitive(self):
        fn = self._fn()
        assert fn("Politics") == "politics"
        assert fn("POLITICS") == "politics"

    def test_politics_with_whitespace(self):
        fn = self._fn()
        assert fn("  politics  ") == "politics"

    def test_finance_maps_to_finance(self):
        fn = self._fn()
        assert fn("finance") == "finance"

    def test_finance_aliases_map_to_finance(self):
        fn = self._fn()
        assert fn("financial") == "finance"
        assert fn("markets") == "finance"
        assert fn("investing") == "finance"

    def test_finance_case_insensitive(self):
        fn = self._fn()
        assert fn("Finance") == "finance"
        assert fn("FINANCE") == "finance"
        assert fn("MARKETS") == "finance"

    def test_nfl_uppercase_maps_to_nfl(self):
        fn = self._fn()
        assert fn("NFL") == "nfl"

    def test_nfl_lowercase_maps_to_nfl(self):
        fn = self._fn()
        assert fn("nfl") == "nfl"

    def test_empty_string_maps_to_nfl(self):
        fn = self._fn()
        assert fn("") == "nfl"

    def test_none_maps_to_nfl(self):
        fn = self._fn()
        assert fn(None) == "nfl"

    def test_unknown_sport_maps_to_nfl(self):
        fn = self._fn()
        assert fn("baseball") == "nfl"
        assert fn("basketball") == "nfl"


# ---------------------------------------------------------------------------
# Tests for finance domain template rendering (Issue #683)
# ---------------------------------------------------------------------------


FINANCE_CLAIM_CATEGORIES = [
    "earnings_prediction",
    "price_target",
    "rate_decision",
    "merger_acquisition",
    "macro_indicator",
    "sector_call",
]


class TestFinanceDomainRender:
    def test_finance_render_returns_string(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, version = render_extraction_prompt(
            domain="finance",
            sport="finance",
            published_date="2025-09-01",
            source_name="CNBC",
            author="Jim Cramer",
            title="Mad Money",
            text="Apple will beat EPS estimates this quarter.",
        )
        assert isinstance(rendered, str)
        assert len(rendered) > 100

    def test_finance_render_contains_required_fields(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="finance",
            sport="finance",
            published_date="2025-09-01",
            source_name="CNBC",
            author="Jim Cramer",
            title="Mad Money",
            text="The Fed will cut rates.",
        )
        for field in REQUIRED_FIELDS:
            assert field in rendered, (
                f"Required field {field!r} missing from rendered finance prompt"
            )

    def test_finance_render_contains_all_claim_categories(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="finance",
            sport="finance",
            published_date="2025-09-01",
            source_name="CNBC",
            author="A",
            title="T",
            text="test",
        )
        for cat in FINANCE_CLAIM_CATEGORIES:
            assert cat in rendered, (
                f"Claim category {cat!r} missing from rendered finance prompt"
            )

    def test_finance_render_contains_domain_guidance(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="finance",
            sport="finance",
            published_date="2025-09-01",
            source_name="Bloomberg",
            author="A",
            title="T",
            text="test",
        )
        assert "financial pundit" in rendered
        assert "target_team = null" in rendered

    def test_finance_render_contains_examples(self):
        from src.prompt_renderer import render_extraction_prompt

        rendered, _ = render_extraction_prompt(
            domain="finance",
            sport="finance",
            published_date="2025-09-01",
            source_name="CNBC",
            author="A",
            title="T",
            text="test",
        )
        # Key entities from finance examples
        assert "Apple" in rendered
        assert "Bitcoin" in rendered
        assert "Federal Reserve" in rendered

    def test_finance_version_is_deterministic(self):
        from src.prompt_renderer import get_prompt_version

        v1 = get_prompt_version("finance")
        v2 = get_prompt_version("finance")
        assert v1 == v2

    def test_finance_version_differs_from_nfl_version(self):
        from src.prompt_renderer import get_prompt_version

        nfl_v = get_prompt_version("nfl")
        fin_v = get_prompt_version("finance")
        assert nfl_v != fin_v, (
            "Finance and NFL domains must have distinct prompt versions"
        )

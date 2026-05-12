"""
Unit tests for multi-model entity resolution validation (Issue #824).

Tests _validate_entity_resolution and _should_flag_entity_resolution.
No LLM API or BigQuery calls — all LLM responses are mocked.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.assertion_extractor import (
    _should_flag_entity_resolution,
    _validate_entity_resolution,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_provider():
    """A mock LLMProvider whose classify() can be configured per test."""
    provider = MagicMock()
    provider.model = "mock-7b"
    return provider


def _make_entity_json(name: str, entity_type: str = "player", team: str = None) -> str:
    """Build a target_entity JSON string the same way _build_target_entity does."""
    entity: dict = {"type": entity_type, "name": name, "sport": "NFL"}
    if team:
        entity["team"] = team
    return json.dumps(entity)


def _provider_returns(
    mock_provider, confirmed: bool, confidence: float, alternate=None
):
    """Configure mock_provider.classify() to return a JSON entity-validation response."""
    response = json.dumps(
        {
            "confirmed": confirmed,
            "confidence": confidence,
            "alternate": alternate,
        }
    )
    mock_provider.classify.return_value = response


# ---------------------------------------------------------------------------
# _validate_entity_resolution
# ---------------------------------------------------------------------------


class TestValidateEntityResolution:
    def test_high_confidence_confirmed_returns_clean_result(self, mock_provider):
        _provider_returns(mock_provider, confirmed=True, confidence=0.95)
        entity_json = _make_entity_json("Patrick Mahomes")
        result = _validate_entity_resolution(
            claim_text="Mahomes will win MVP this season",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is True
        assert result["confidence"] == pytest.approx(0.95)
        assert result["alternate"] is None
        mock_provider.classify.assert_called_once()

    def test_low_confidence_returns_low_confidence(self, mock_provider):
        _provider_returns(mock_provider, confirmed=True, confidence=0.55)
        entity_json = _make_entity_json("Josh Allen")
        result = _validate_entity_resolution(
            claim_text="Allen will throw for 4000 yards",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is True
        assert result["confidence"] == pytest.approx(0.55)

    def test_not_confirmed_returns_false(self, mock_provider):
        _provider_returns(
            mock_provider, confirmed=False, confidence=0.85, alternate="Joe Burrow"
        )
        entity_json = _make_entity_json("Joe Allen")
        result = _validate_entity_resolution(
            claim_text="Allen will lead the Bengals to the Super Bowl",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is False
        assert result["alternate"] == "Joe Burrow"

    def test_llm_error_returns_safe_default(self, mock_provider):
        """On any LLM or parse failure, return the safe default (not flagged)."""
        mock_provider.classify.side_effect = RuntimeError("connection refused")
        entity_json = _make_entity_json("Patrick Mahomes")
        result = _validate_entity_resolution(
            claim_text="Mahomes will win MVP",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        # Safe default: confirmed=True, confidence=1.0, alternate=None
        assert result["confirmed"] is True
        assert result["confidence"] == pytest.approx(1.0)
        assert result["alternate"] is None

    def test_malformed_json_response_returns_safe_default(self, mock_provider):
        """Unparseable LLM response returns safe default rather than raising."""
        mock_provider.classify.return_value = "I'm not sure, maybe?"
        entity_json = _make_entity_json("Lamar Jackson")
        result = _validate_entity_resolution(
            claim_text="Jackson will win the MVP award",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is True
        assert result["confidence"] == pytest.approx(1.0)

    def test_confidence_clamped_to_0_1(self, mock_provider):
        """Confidence values outside [0, 1] are clamped."""
        mock_provider.classify.return_value = json.dumps(
            {"confirmed": True, "confidence": 1.5, "alternate": None}
        )
        entity_json = _make_entity_json("Travis Kelce")
        result = _validate_entity_resolution(
            claim_text="Kelce will score 10 TDs",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confidence"] == pytest.approx(1.0)

    def test_alternate_whitespace_stripped(self, mock_provider):
        """Alternate entity names with only whitespace are normalised to None."""
        mock_provider.classify.return_value = json.dumps(
            {"confirmed": False, "confidence": 0.3, "alternate": "   "}
        )
        entity_json = _make_entity_json("Jalen Hurts")
        result = _validate_entity_resolution(
            claim_text="Hurts will rush for 700 yards",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["alternate"] is None

    def test_team_entity_json_handled(self, mock_provider):
        """Works with team-type entity JSON (uses abbrev instead of name)."""
        _provider_returns(mock_provider, confirmed=True, confidence=0.9)
        entity_json = json.dumps({"type": "team", "abbrev": "KC", "sport": "NFL"})
        result = _validate_entity_resolution(
            claim_text="KC will win the Super Bowl",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is True
        # Verify the prompt was built — classify was called
        mock_provider.classify.assert_called_once()

    def test_raw_string_entity_fallback(self, mock_provider):
        """Non-JSON target_entity strings degrade gracefully."""
        _provider_returns(mock_provider, confirmed=True, confidence=0.8)
        result = _validate_entity_resolution(
            claim_text="Mahomes will win MVP",
            target_entity="Patrick Mahomes (plain string)",
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is True

    def test_classify_called_with_claim_truncated(self, mock_provider):
        """The prompt sent to classify should not exceed the 600-char claim limit."""
        _provider_returns(mock_provider, confirmed=True, confidence=0.88)
        long_claim = "X" * 1200
        entity_json = _make_entity_json("Justin Jefferson")
        _validate_entity_resolution(
            claim_text=long_claim,
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        call_args = mock_provider.classify.call_args[0][0]
        # The truncated claim (600 chars) should appear, not the full 1200-char string
        assert long_claim not in call_args
        assert "X" * 600 in call_args

    def test_markdown_fenced_json_parsed(self, mock_provider):
        """JSON wrapped in markdown fences is parsed correctly via _extract_json_from_response."""
        mock_provider.classify.return_value = (
            '```json\n{"confirmed": true, "confidence": 0.82, "alternate": null}\n```'
        )
        entity_json = _make_entity_json("Cooper Kupp")
        result = _validate_entity_resolution(
            claim_text="Kupp will have 1200 receiving yards",
            target_entity=entity_json,
            llm_provider=mock_provider,
        )
        assert result["confirmed"] is True
        assert result["confidence"] == pytest.approx(0.82)


# ---------------------------------------------------------------------------
# _should_flag_entity_resolution
# ---------------------------------------------------------------------------


class TestShouldFlagEntityResolution:
    def test_high_confidence_confirmed_not_flagged(self):
        result = {"confirmed": True, "confidence": 0.95, "alternate": None}
        assert _should_flag_entity_resolution(result) is False

    def test_exactly_at_threshold_not_flagged(self):
        """Confidence at exactly 0.7 should NOT be flagged (threshold is < 0.7)."""
        result = {"confirmed": True, "confidence": 0.7, "alternate": None}
        assert _should_flag_entity_resolution(result) is False

    def test_just_below_threshold_flagged(self):
        result = {"confirmed": True, "confidence": 0.69, "alternate": None}
        assert _should_flag_entity_resolution(result) is True

    def test_zero_confidence_flagged(self):
        result = {"confirmed": True, "confidence": 0.0, "alternate": None}
        assert _should_flag_entity_resolution(result) is True

    def test_not_confirmed_flagged_regardless_of_confidence(self):
        """confirmed=False should always flag even if confidence is high."""
        result = {"confirmed": False, "confidence": 0.9, "alternate": "Joe Burrow"}
        assert _should_flag_entity_resolution(result) is True

    def test_not_confirmed_low_confidence_flagged(self):
        result = {"confirmed": False, "confidence": 0.3, "alternate": None}
        assert _should_flag_entity_resolution(result) is True

    def test_missing_confirmed_defaults_to_true_not_flagged(self):
        """Missing 'confirmed' key defaults to True (safe default)."""
        result = {"confidence": 0.95}
        assert _should_flag_entity_resolution(result) is False

    def test_missing_confidence_defaults_to_1_not_flagged(self):
        """Missing 'confidence' key defaults to 1.0 (safe default)."""
        result = {"confirmed": True}
        assert _should_flag_entity_resolution(result) is False

"""
Unit tests for assertion_quality heuristic scorer.
No BigQuery required — tests the pure scoring logic.
"""

import pytest

from src.assertion_quality import score_prediction, _heuristic_signals


# ---------------------------------------------------------------------------
# Signal detection tests
# ---------------------------------------------------------------------------


class TestHeuristicSignals:
    def test_has_player_name_when_populated(self):
        row = {"extracted_claim": "X will win", "target_player_name": "Patrick Mahomes"}
        signals = _heuristic_signals(row)
        assert signals["has_player_name"] is True

    def test_no_player_name_when_none(self):
        row = {"extracted_claim": "The team will win", "target_player_name": None}
        signals = _heuristic_signals(row)
        assert signals["has_player_name"] is False

    def test_no_player_name_when_string_none(self):
        row = {"extracted_claim": "X", "target_player_name": "None"}
        signals = _heuristic_signals(row)
        assert signals["has_player_name"] is False

    def test_has_specific_number_pick(self):
        row = {"extracted_claim": "Travis Hunter will go 1st overall in the draft"}
        signals = _heuristic_signals(row)
        assert signals["has_specific_number"] is True

    def test_has_specific_number_yards(self):
        row = {"extracted_claim": "Tyreek Hill will surpass 1500 yards"}
        signals = _heuristic_signals(row)
        assert signals["has_specific_number"] is True

    def test_no_specific_number_vague(self):
        row = {"extracted_claim": "The Jets defense will utilize four-down fronts"}
        signals = _heuristic_signals(row)
        assert signals["has_specific_number"] is False

    def test_falsifiable_verb_will(self):
        row = {"extracted_claim": "Mahomes will win the Super Bowl"}
        signals = _heuristic_signals(row)
        assert signals["falsifiable_verb"] is True

    def test_falsifiable_verb_wont(self):
        row = {"extracted_claim": "The Browns won't make the playoffs"}
        signals = _heuristic_signals(row)
        assert signals["falsifiable_verb"] is True

    def test_tautology_might(self):
        row = {"extracted_claim": "He might have a good season"}
        signals = _heuristic_signals(row)
        assert signals["is_tautology"] is True

    def test_tautology_could(self):
        row = {"extracted_claim": "The team could potentially be better"}
        signals = _heuristic_signals(row)
        assert signals["is_tautology"] is True

    def test_claim_length_good(self):
        row = {"extracted_claim": "Patrick Mahomes will win MVP in 2025"}
        signals = _heuristic_signals(row)
        assert signals["claim_length_good"] is True
        assert signals["claim_length_bad"] is False

    def test_claim_length_bad_too_short(self):
        row = {"extracted_claim": "Win"}
        signals = _heuristic_signals(row)
        assert signals["claim_length_bad"] is True

    def test_category_mismatch_draft_pick_no_number(self):
        row = {
            "extracted_claim": "The Jets defense will utilize four-down fronts",
            "claim_category": "draft_pick",
        }
        signals = _heuristic_signals(row)
        assert signals["category_mismatch"] is True

    def test_category_mismatch_draft_pick_with_number(self):
        row = {
            "extracted_claim": "Travis Hunter will be the 1st overall pick",
            "claim_category": "draft_pick",
        }
        signals = _heuristic_signals(row)
        assert signals["category_mismatch"] is False

    def test_category_mismatch_non_draft(self):
        row = {
            "extracted_claim": "Mahomes will win MVP",
            "claim_category": "player_performance",
        }
        signals = _heuristic_signals(row)
        assert signals["category_mismatch"] is False


# ---------------------------------------------------------------------------
# Scoring tests
# ---------------------------------------------------------------------------


class TestScorePrediction:
    def test_high_quality_prediction(self):
        row = {
            "extracted_claim": "Mel Kiper will have Travis Hunter as #1 overall pick in the 2025 NFL Draft",
            "target_player_name": "Travis Hunter",
            "target_team": "JAX",
            "season_year": "2025",
            "claim_category": "draft_pick",
        }
        score, tier, signals = score_prediction(row)
        assert score >= 0.7
        assert tier == "HIGH"

    def test_low_quality_garbage(self):
        row = {
            "extracted_claim": "The Jets defense will utilize four-down fronts",
            "target_player_name": None,
            "target_team": None,
            "season_year": None,
            "claim_category": "draft_pick",  # mismatch too
        }
        score, tier, signals = score_prediction(row)
        assert tier == "LOW"

    def test_tautology_penalized(self):
        row = {
            "extracted_claim": "Patrick Mahomes might win the Super Bowl next year",
            "target_player_name": "Patrick Mahomes",
            "target_team": "KC",
            "season_year": "2025",
            "claim_category": "game_outcome",
        }
        score_with_tautology, _, _ = score_prediction(row)

        row_clean = {
            "extracted_claim": "Patrick Mahomes will win the Super Bowl next year",
            "target_player_name": "Patrick Mahomes",
            "target_team": "KC",
            "season_year": "2025",
            "claim_category": "game_outcome",
        }
        score_clean, _, _ = score_prediction(row_clean)
        assert score_clean > score_with_tautology

    def test_score_clamped_to_unit_interval(self):
        # Even maximally good prediction should be <= 1.0
        row = {
            "extracted_claim": "Patrick Mahomes will win 15 touchdowns in 2025",
            "target_player_name": "Patrick Mahomes",
            "target_team": "KC",
            "season_year": "2025",
            "claim_category": "player_performance",
        }
        score, _, _ = score_prediction(row)
        assert 0.0 <= score <= 1.0

    def test_tier_boundaries(self):
        # HIGH >= 0.7
        row_high = {
            "extracted_claim": "Patrick Mahomes will throw for 4000 yards in 2025",
            "target_player_name": "Patrick Mahomes",
            "target_team": "KC",
            "season_year": "2025",
            "claim_category": "player_performance",
        }
        score, tier, _ = score_prediction(row_high)
        if score >= 0.7:
            assert tier == "HIGH"
        elif score >= 0.4:
            assert tier == "MEDIUM"
        else:
            assert tier == "LOW"

    def test_uses_raw_assertion_text_as_fallback(self):
        row = {
            "extracted_claim": None,
            "raw_assertion_text": "Mahomes will win MVP in the 2025 season",
            "target_player_name": "Patrick Mahomes",
            "target_team": "KC",
            "season_year": "2025",
            "claim_category": "player_performance",
        }
        score, tier, _ = score_prediction(row)
        assert score > 0.0  # Should score based on raw text

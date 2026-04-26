"""Unit tests for historical_resolver.

No network or BigQuery required — PFR fetches and BQ writes are mocked.
"""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest
from src import historical_resolver as hr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _facts_2024() -> hr.SeasonFacts:
    standings = pd.DataFrame(
        [
            {
                "team_label": "Kansas City Chiefs",
                "team_pfr": "KAN",
                "conference": "AFC",
                "division": "AFC West",
                "wins": 15,
                "losses": 2,
                "ties": 0,
                "made_playoffs": True,
            },
            {
                "team_label": "Buffalo Bills",
                "team_pfr": "BUF",
                "conference": "AFC",
                "division": "AFC East",
                "wins": 13,
                "losses": 4,
                "ties": 0,
                "made_playoffs": True,
            },
            {
                "team_label": "Dallas Cowboys",
                "team_pfr": "DAL",
                "conference": "NFC",
                "division": "NFC East",
                "wins": 7,
                "losses": 10,
                "ties": 0,
                "made_playoffs": False,
            },
            {
                "team_label": "Philadelphia Eagles",
                "team_pfr": "PHI",
                "conference": "NFC",
                "division": "NFC East",
                "wins": 14,
                "losses": 3,
                "ties": 0,
                "made_playoffs": True,
            },
            {
                "team_label": "Chicago Bears",
                "team_pfr": "CHI",
                "conference": "NFC",
                "division": "NFC North",
                "wins": 5,
                "losses": 12,
                "ties": 0,
                "made_playoffs": False,
            },
        ]
    )
    return hr.SeasonFacts(
        season=2024,
        standings_url="https://www.pro-football-reference.com/years/2024/",
        standings=standings,
        playoff_teams={"Kansas City Chiefs", "Buffalo Bills", "Philadelphia Eagles"},
        division_winners={
            "AFC East": "Buffalo Bills",
            "AFC West": "Kansas City Chiefs",
            "NFC East": "Philadelphia Eagles",
        },
        super_bowl_winner="Philadelphia Eagles",
        conference_champs={"AFC": "Kansas City Chiefs", "NFC": "Philadelphia Eagles"},
        awards={
            "MVP": "Josh Allen",
            "OPOY": "Saquon Barkley",
            "DPOY": "Patrick Surtain II",
            "OROY": "Jayden Daniels",
            "DROY": "Jared Verse",
            "CPOY": "Joe Burrow",
            "COY": "Kevin O'Connell",
        },
        awards_url="https://www.pro-football-reference.com/awards/awards_2024.htm",
    )


@pytest.fixture(autouse=True)
def _reset_caches():
    hr._SEASON_CACHE.clear()
    hr._PAGE_CACHE.clear()
    yield
    hr._SEASON_CACHE.clear()
    hr._PAGE_CACHE.clear()


@pytest.fixture
def facts_2024(monkeypatch):
    facts = _facts_2024()
    monkeypatch.setattr(hr, "load_season_facts", lambda season: facts)
    return facts


# ---------------------------------------------------------------------------
# Team normalisation
# ---------------------------------------------------------------------------


def test_normalize_team_to_pfr_known_aliases():
    assert hr.normalize_team_to_pfr("the Chiefs will win") == "KAN"
    assert hr.normalize_team_to_pfr("Philadelphia Eagles") == "PHI"
    assert hr.normalize_team_to_pfr("San Francisco 49ers") == "SFO"
    assert hr.normalize_team_to_pfr("KAN") == "KAN"
    assert hr.normalize_team_to_pfr("") is None


# ---------------------------------------------------------------------------
# Win totals
# ---------------------------------------------------------------------------


def test_resolve_win_total_threshold_correct(facts_2024):
    pred = {
        "extracted_claim": "The Chiefs will win at least 12 games in 2024",
        "claim_category": "win_total",
        "target_team": "KAN",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"
    assert result.confidence >= 0.8
    assert result.evidence_url == facts_2024.standings_url


def test_resolve_win_total_threshold_incorrect(facts_2024):
    pred = {
        "extracted_claim": "The Bears will win 11+ wins",
        "claim_category": "win_total",
        "target_team": "CHI",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "incorrect"


def test_resolve_win_total_exact_record(facts_2024):
    pred = {
        "extracted_claim": "Philadelphia goes 14-3",
        "claim_category": "season_record",
        "target_team": "PHI",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


# ---------------------------------------------------------------------------
# Playoff predictions
# ---------------------------------------------------------------------------


def test_resolve_make_playoffs_correct(facts_2024):
    pred = {
        "extracted_claim": "The Chiefs will make the playoffs",
        "claim_category": "playoffs",
        "target_team": "KAN",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


def test_resolve_miss_playoffs_correct(facts_2024):
    pred = {
        "extracted_claim": "Cowboys will miss the playoffs",
        "claim_category": "playoffs",
        "target_team": "DAL",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


def test_resolve_super_bowl_winner(facts_2024):
    pred = {
        "extracted_claim": "The Eagles will win Super Bowl",
        "claim_category": "playoffs",
        "target_team": "PHI",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


def test_resolve_division_winner(facts_2024):
    pred = {
        "extracted_claim": "Buffalo will win the division",
        "claim_category": "playoffs",
        "target_team": "BUF",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


# ---------------------------------------------------------------------------
# Awards
# ---------------------------------------------------------------------------


def test_resolve_award_mvp_correct(facts_2024):
    pred = {
        "extracted_claim": "Josh Allen will win MVP this year",
        "claim_category": "award",
        "target_player": "Josh Allen",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


def test_resolve_award_mvp_incorrect(facts_2024):
    pred = {
        "extracted_claim": "Lamar Jackson will win MVP",
        "claim_category": "award",
        "target_player": "Lamar Jackson",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "incorrect"


def test_resolve_oroy(facts_2024):
    pred = {
        "extracted_claim": "Jayden Daniels wins offensive rookie of the year",
        "claim_category": "award",
        "target_player": "Jayden Daniels",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_route_falls_back_to_keyword(facts_2024):
    pred = {
        "extracted_claim": "Josh Allen is a lock for MVP",
        "claim_category": "player_performance",  # mis-categorised at extraction time
        "target_player": "Josh Allen",
    }
    # The keyword fallback should pick the award resolver, not stat milestone.
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "correct"


def test_route_unknown_returns_unresolvable():
    pred = {
        "extracted_claim": "It will be a great season",
        "claim_category": "vibes",
    }
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "unresolvable"


# ---------------------------------------------------------------------------
# Confidence floor + evidence URL enforcement
# ---------------------------------------------------------------------------


def test_low_confidence_demoted_to_unresolvable(monkeypatch):
    facts = _facts_2024()
    monkeypatch.setattr(hr, "load_season_facts", lambda season: facts)

    def fake_resolver(pred, season):
        return hr.ResolutionResult(
            outcome="correct",
            evidence_url="http://example.com",
            confidence=0.4,
            notes="weak",
        )

    monkeypatch.setitem(hr.CATEGORY_RESOLVERS, "win_total", fake_resolver)
    pred = {"extracted_claim": "x", "claim_category": "win_total"}
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "unresolvable"


def test_missing_evidence_url_demoted(monkeypatch):
    def fake_resolver(pred, season):
        return hr.ResolutionResult(outcome="correct", confidence=0.95, notes="ok")

    monkeypatch.setitem(hr.CATEGORY_RESOLVERS, "win_total", fake_resolver)
    pred = {"extracted_claim": "x", "claim_category": "win_total"}
    result = hr.resolve_prediction(pred, 2024)
    assert result.outcome == "unresolvable"


# ---------------------------------------------------------------------------
# BQ write mapping + batch driver
# ---------------------------------------------------------------------------


def test_outcome_to_status():
    assert hr._outcome_to_status("correct") == "CORRECT"
    assert hr._outcome_to_status("incorrect") == "INCORRECT"
    assert hr._outcome_to_status("partial") == "CORRECT"
    assert hr._outcome_to_status("unresolvable") == "VOID"


def test_run_batch_with_inline_df(facts_2024):
    df = pd.DataFrame(
        [
            {
                "prediction_hash": "h1",
                "extracted_claim": "Chiefs win 12+ games",
                "claim_category": "win_total",
                "season_year": 2024,
                "target_team": "KAN",
                "target_player_id": None,
            },
            {
                "prediction_hash": "h2",
                "extracted_claim": "Josh Allen wins MVP",
                "claim_category": "award",
                "season_year": 2024,
                "target_team": None,
                "target_player_id": "Josh Allen",
            },
            {
                "prediction_hash": "h3",
                "extracted_claim": "Bears make playoffs",
                "claim_category": "playoffs",
                "season_year": 2024,
                "target_team": "CHI",
                "target_player_id": None,
            },
        ]
    )

    with patch.object(hr, "write_to_bq") as mock_write:
        summary = hr.run_batch(season=2024, dry_run=False, predictions_df=df)

    assert summary["attempted"] == 3
    assert summary["correct"] == 2
    assert summary["incorrect"] == 1
    assert summary["unresolvable"] == 0
    assert summary["resolution_rate"] == 1.0
    assert mock_write.call_count == 3


def test_run_batch_dry_run_does_not_write(facts_2024):
    df = pd.DataFrame(
        [
            {
                "prediction_hash": "h1",
                "extracted_claim": "Chiefs win 12+ games",
                "claim_category": "win_total",
                "season_year": 2024,
                "target_team": "KAN",
                "target_player_id": None,
            }
        ]
    )
    with patch("src.resolution_engine.record_resolution") as mock_record:
        summary = hr.run_batch(season=2024, dry_run=True, predictions_df=df)
    assert summary["attempted"] == 1
    assert summary["correct"] == 1
    mock_record.assert_not_called()

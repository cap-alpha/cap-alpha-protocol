"""
Tests for the Accountability Engine (Issue #162).
Unit tests only — no BigQuery or LLM calls required.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from src.accountability_engine import (
    ACCOUNTABILITY_CLASSES,
    DEFAULT_WINDOW_DAYS,
    MIN_CONTENT_CHARS,
    AccountabilityResult,
    _build_content_blob,
    _normalize_class,
    classify_accountability,
    get_accountability_summary,
    get_subsequent_content,
    get_unclassified_incorrect_predictions,
    record_accountability,
    run_accountability_scan,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model = "test-model"
    provider.classify.return_value = "owns_it"
    return provider


@pytest.fixture
def sample_prediction_row():
    return pd.Series(
        {
            "prediction_hash": "a" * 64,
            "pundit_id": "mel_kiper",
            "pundit_name": "Mel Kiper Jr.",
            "extracted_claim": "Travis Hunter will be the #1 overall pick",
            "claim_category": "draft_pick",
            "target_player_name": "Travis Hunter",
            "target_team": None,
            "prediction_ts": "2026-01-15T00:00:00Z",
            "resolved_at": "2026-04-24T22:00:00Z",
        }
    )


@pytest.fixture
def sample_result():
    return AccountabilityResult(
        prediction_hash="a" * 64,
        pundit_id="mel_kiper",
        pundit_name="Mel Kiper Jr.",
        original_claim="Travis Hunter will be the #1 overall pick",
        resolution_status="INCORRECT",
        resolved_at="2026-04-24T22:00:00Z",
        accountability_class="owns_it",
        evidence_url="https://example.com/article",
        evidence_snippet="I got that one wrong — Travis Hunter went #2, not #1.",
        window_days=DEFAULT_WINDOW_DAYS,
        articles_scanned=3,
        llm_model="test-model",
    )


# ---------------------------------------------------------------------------
# _normalize_class
# ---------------------------------------------------------------------------


class TestNormalizeClass:
    def test_exact_match(self):
        for cls in ACCOUNTABILITY_CLASSES:
            assert _normalize_class(cls) == cls

    def test_uppercase_normalized(self):
        assert _normalize_class("OWNS_IT") == "owns_it"

    def test_with_trailing_punctuation(self):
        assert _normalize_class("deflection.") == "deflection"
        assert _normalize_class("revisionism:") == "revisionism"

    def test_with_spaces(self):
        assert _normalize_class("silent burial") == "silent_burial"

    def test_partial_match(self):
        assert _normalize_class("owns_it_clearly") == "owns_it"

    def test_unknown_falls_back(self):
        assert _normalize_class("i_have_no_idea") == "insufficient_data"

    def test_empty_string_falls_back(self):
        assert _normalize_class("") == "insufficient_data"


# ---------------------------------------------------------------------------
# _build_content_blob
# ---------------------------------------------------------------------------


class TestBuildContentBlob:
    def test_empty_df_returns_empty(self):
        blob, url, snippet = _build_content_blob(pd.DataFrame())
        assert blob == ""
        assert url is None
        assert snippet is None

    def test_single_article(self):
        df = pd.DataFrame(
            [
                {
                    "url": "https://example.com/1",
                    "title": "Mel Kiper's Draft Recap",
                    "content_text": "I was wrong about Hunter going first overall.",
                    "published_date": "2026-04-25",
                }
            ]
        )
        blob, url, snippet = _build_content_blob(df)
        assert "Mel Kiper" in blob
        assert url == "https://example.com/1"
        assert snippet is not None
        assert "wrong" in snippet

    def test_multiple_articles_separated(self):
        df = pd.DataFrame(
            [
                {
                    "url": "https://example.com/1",
                    "title": "Article 1",
                    "content_text": "Content 1",
                    "published_date": "2026-04-25",
                },
                {
                    "url": "https://example.com/2",
                    "title": "Article 2",
                    "content_text": "Content 2",
                    "published_date": "2026-04-26",
                },
            ]
        )
        blob, url, snippet = _build_content_blob(df)
        assert "---" in blob
        assert "Article 1" in blob
        assert "Article 2" in blob
        # First article with content is used for evidence
        assert url == "https://example.com/1"

    def test_article_without_url_skipped_for_evidence(self):
        df = pd.DataFrame(
            [
                {
                    "url": None,
                    "title": "No URL",
                    "content_text": "Some content",
                    "published_date": "2026-04-25",
                },
                {
                    "url": "https://example.com/2",
                    "title": "With URL",
                    "content_text": "Content with url",
                    "published_date": "2026-04-26",
                },
            ]
        )
        _, url, _ = _build_content_blob(df)
        assert url == "https://example.com/2"


# ---------------------------------------------------------------------------
# AccountabilityResult
# ---------------------------------------------------------------------------


class TestAccountabilityResult:
    def test_classified_at_auto_set(self):
        result = AccountabilityResult(
            prediction_hash="b" * 64,
            pundit_id="test",
            pundit_name="Test Pundit",
            original_claim="Claim",
            resolution_status="INCORRECT",
            resolved_at="2026-04-01T00:00:00Z",
            accountability_class="deflection",
            evidence_url=None,
            evidence_snippet=None,
            window_days=90,
            articles_scanned=0,
            llm_model="qwen2.5:32b",
        )
        assert result.classified_at != ""
        # Should be a valid ISO timestamp
        datetime.fromisoformat(result.classified_at)

    def test_explicit_classified_at_preserved(self):
        ts = "2026-04-25T12:00:00+00:00"
        result = AccountabilityResult(
            prediction_hash="c" * 64,
            pundit_id="test",
            pundit_name="Test",
            original_claim="Claim",
            resolution_status="INCORRECT",
            resolved_at=None,
            accountability_class="owns_it",
            evidence_url=None,
            evidence_snippet=None,
            window_days=90,
            articles_scanned=1,
            llm_model="test",
            classified_at=ts,
        )
        assert result.classified_at == ts


# ---------------------------------------------------------------------------
# classify_accountability
# ---------------------------------------------------------------------------


class TestClassifyAccountability:
    def test_insufficient_data_when_no_content(
        self, sample_prediction_row, mock_provider, mock_db
    ):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = classify_accountability(
            prediction_row=sample_prediction_row,
            provider=mock_provider,
            db=mock_db,
        )
        assert result.accountability_class == "insufficient_data"
        assert result.articles_scanned == 0
        mock_provider.classify.assert_not_called()

    def test_insufficient_data_when_content_too_short(
        self, sample_prediction_row, mock_provider, mock_db
    ):
        df = pd.DataFrame(
            [
                {
                    "url": "https://example.com/1",
                    "title": "Short",
                    "content_text": "Hi",  # less than MIN_CONTENT_CHARS
                    "published_date": "2026-04-25",
                }
            ]
        )
        mock_db.fetch_df.return_value = df
        result = classify_accountability(
            prediction_row=sample_prediction_row,
            provider=mock_provider,
            db=mock_db,
        )
        assert result.accountability_class == "insufficient_data"
        mock_provider.classify.assert_not_called()

    def test_llm_called_with_sufficient_content(
        self, sample_prediction_row, mock_provider, mock_db
    ):
        df = pd.DataFrame(
            [
                {
                    "url": "https://example.com/1",
                    "title": "Draft Recap",
                    "content_text": "X" * MIN_CONTENT_CHARS,
                    "published_date": "2026-04-25",
                }
            ]
        )
        mock_db.fetch_df.return_value = df
        mock_provider.classify.return_value = "owns_it"

        result = classify_accountability(
            prediction_row=sample_prediction_row,
            provider=mock_provider,
            db=mock_db,
        )

        mock_provider.classify.assert_called_once()
        assert result.accountability_class == "owns_it"
        assert result.articles_scanned == 1

    def test_llm_response_normalized(
        self, sample_prediction_row, mock_provider, mock_db
    ):
        df = pd.DataFrame(
            [
                {
                    "url": "https://example.com/1",
                    "title": "Article",
                    "content_text": "Y" * MIN_CONTENT_CHARS,
                    "published_date": "2026-04-25",
                }
            ]
        )
        mock_db.fetch_df.return_value = df
        mock_provider.classify.return_value = "DOUBLING DOWN"

        result = classify_accountability(
            prediction_row=sample_prediction_row,
            provider=mock_provider,
            db=mock_db,
        )
        assert result.accountability_class == "doubling_down"

    def test_prediction_fields_preserved(
        self, sample_prediction_row, mock_provider, mock_db
    ):
        mock_db.fetch_df.return_value = pd.DataFrame()
        result = classify_accountability(
            prediction_row=sample_prediction_row,
            provider=mock_provider,
            db=mock_db,
        )
        assert result.prediction_hash == "a" * 64
        assert result.pundit_id == "mel_kiper"
        assert result.pundit_name == "Mel Kiper Jr."
        assert result.window_days == DEFAULT_WINDOW_DAYS
        assert result.llm_model == "test-model"

    def test_uses_player_name_for_subject_filter(
        self, sample_prediction_row, mock_provider, mock_db
    ):
        mock_db.fetch_df.return_value = pd.DataFrame()
        classify_accountability(
            prediction_row=sample_prediction_row,
            provider=mock_provider,
            db=mock_db,
        )
        # DB should have been called for subsequent content
        mock_db.fetch_df.assert_called_once()
        call_args = mock_db.fetch_df.call_args[0][0]
        assert "Travis Hunter" in call_args


# ---------------------------------------------------------------------------
# record_accountability
# ---------------------------------------------------------------------------


class TestRecordAccountability:
    def test_merge_sql_called(self, sample_result, mock_db):
        record_accountability(sample_result, db=mock_db)
        mock_db.execute.assert_called_once()
        sql = mock_db.execute.call_args[0][0]
        assert "MERGE" in sql
        assert "accountability_ledger" in sql
        assert sample_result.prediction_hash in sql
        assert "owns_it" in sql

    def test_null_evidence_handled(self, mock_db):
        result = AccountabilityResult(
            prediction_hash="d" * 64,
            pundit_id="pundit",
            pundit_name=None,
            original_claim=None,
            resolution_status="INCORRECT",
            resolved_at=None,
            accountability_class="insufficient_data",
            evidence_url=None,
            evidence_snippet=None,
            window_days=90,
            articles_scanned=0,
            llm_model="qwen2.5:32b",
        )
        record_accountability(result, db=mock_db)
        sql = mock_db.execute.call_args[0][0]
        assert "NULL" in sql


# ---------------------------------------------------------------------------
# get_unclassified_incorrect_predictions
# ---------------------------------------------------------------------------


class TestGetUnclassifiedIncorrectPredictions:
    def test_returns_dataframe(self, mock_db):
        expected = pd.DataFrame(
            [{"prediction_hash": "a" * 64, "pundit_id": "mel_kiper"}]
        )
        mock_db.fetch_df.return_value = expected
        result = get_unclassified_incorrect_predictions(db=mock_db)
        assert len(result) == 1

    def test_limit_applied(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unclassified_incorrect_predictions(limit=5, db=mock_db)
        sql = mock_db.fetch_df.call_args[0][0]
        assert "LIMIT 5" in sql

    def test_no_limit_when_none(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_unclassified_incorrect_predictions(limit=None, db=mock_db)
        sql = mock_db.fetch_df.call_args[0][0]
        assert "LIMIT" not in sql


# ---------------------------------------------------------------------------
# run_accountability_scan
# ---------------------------------------------------------------------------


class TestRunAccountabilityScan:
    def test_empty_pending_returns_empty(self, mock_db, mock_provider):
        mock_db.fetch_df.return_value = pd.DataFrame()
        with patch(
            "src.accountability_engine.get_provider", return_value=mock_provider
        ):
            results = run_accountability_scan(db=mock_db)
        assert results == []

    def test_dry_run_does_not_write(self, mock_db, mock_provider):
        pending = pd.DataFrame(
            [
                {
                    "prediction_hash": "a" * 64,
                    "pundit_id": "mel_kiper",
                    "pundit_name": "Mel Kiper Jr.",
                    "extracted_claim": "Claim",
                    "claim_category": "draft_pick",
                    "target_player_name": None,
                    "target_team": None,
                    "prediction_ts": "2026-01-01T00:00:00Z",
                    "resolved_at": "2026-04-01T00:00:00Z",
                }
            ]
        )
        # First call returns pending predictions; second call returns empty content
        mock_db.fetch_df.side_effect = [pending, pd.DataFrame()]

        with patch(
            "src.accountability_engine.get_provider", return_value=mock_provider
        ):
            results = run_accountability_scan(dry_run=True, db=mock_db)

        assert len(results) == 1
        mock_db.execute.assert_not_called()

    def test_errors_per_prediction_do_not_abort_scan(self, mock_db, mock_provider):
        pending = pd.DataFrame(
            [
                {
                    "prediction_hash": "a" * 64,
                    "pundit_id": "p1",
                    "pundit_name": "Pundit 1",
                    "extracted_claim": "Claim 1",
                    "claim_category": "draft_pick",
                    "target_player_name": None,
                    "target_team": None,
                    "prediction_ts": "2026-01-01T00:00:00Z",
                    "resolved_at": "2026-04-01T00:00:00Z",
                },
                {
                    "prediction_hash": "b" * 64,
                    "pundit_id": "p2",
                    "pundit_name": "Pundit 2",
                    "extracted_claim": "Claim 2",
                    "claim_category": "game_outcome",
                    "target_player_name": None,
                    "target_team": None,
                    "prediction_ts": "2026-01-02T00:00:00Z",
                    "resolved_at": "2026-04-02T00:00:00Z",
                },
            ]
        )
        # pending df, then raise on first content fetch, then empty for second
        mock_db.fetch_df.side_effect = [pending, Exception("BQ error"), pd.DataFrame()]
        mock_provider.classify.return_value = "owns_it"

        with patch(
            "src.accountability_engine.get_provider", return_value=mock_provider
        ):
            results = run_accountability_scan(dry_run=True, db=mock_db)

        # Second prediction should still be processed
        assert any(r.prediction_hash == "b" * 64 for r in results)


# ---------------------------------------------------------------------------
# get_accountability_summary
# ---------------------------------------------------------------------------


class TestGetAccountabilitySummary:
    def test_returns_dataframe(self, mock_db):
        expected = pd.DataFrame(
            [
                {
                    "pundit_id": "mel_kiper",
                    "pundit_name": "Mel Kiper Jr.",
                    "accountability_class": "owns_it",
                    "count": 3,
                    "pct": 75.0,
                }
            ]
        )
        mock_db.fetch_df.return_value = expected
        result = get_accountability_summary(db=mock_db)
        assert len(result) == 1
        assert result.iloc[0]["accountability_class"] == "owns_it"

    def test_excludes_insufficient_data(self, mock_db):
        mock_db.fetch_df.return_value = pd.DataFrame()
        get_accountability_summary(db=mock_db)
        sql = mock_db.fetch_df.call_args[0][0]
        assert "insufficient_data" in sql
        assert "!=" in sql


# ---------------------------------------------------------------------------
# ACCOUNTABILITY_CLASSES completeness
# ---------------------------------------------------------------------------


class TestAccountabilityClassesDefinition:
    def test_all_expected_classes_defined(self):
        expected = {
            "owns_it",
            "silent_burial",
            "revisionism",
            "doubling_down",
            "deflection",
            "insufficient_data",
        }
        assert set(ACCOUNTABILITY_CLASSES.keys()) == expected

    def test_all_classes_have_descriptions(self):
        for cls, desc in ACCOUNTABILITY_CLASSES.items():
            assert desc, f"Missing description for {cls}"

"""
Tests for extraction provenance tracking (Issue #247).

Covers:
  - PunditPrediction has prompt_version / llm_provider / llm_model fields
  - PROMPT_VERSION is a stable 8-char hex string
  - run_extraction populates provenance fields on every PunditPrediction
  - _build_pundit_predictions (local_rag_pipeline) passes provenance through
  - ingest_batch includes provenance columns in the row dict
  - extraction_quality.run_report handles an empty ledger gracefully
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    PROMPT_VERSION,
    ExtractionResult,
    run_extraction,
)
from src.cryptographic_ledger import PunditPrediction, ingest_batch
from src.local_rag_pipeline import _build_pundit_predictions
from src.team_batcher import BATCH_PROMPT_VERSION, ArticleRecord


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
    provider.model = "test-model-7b"
    provider.extract_predictions.return_value = []
    return provider


def make_raw_media_df():
    return pd.DataFrame(
        [
            {
                "content_hash": "abc123",
                "source_id": "espn_nfl",
                "title": "Mock Article",
                "raw_text": "Chiefs will win the Super Bowl this season.",
                "source_url": "https://espn.com/1",
                "author": "Adam Schefter",
                "matched_pundit_id": "adam_schefter",
                "matched_pundit_name": "Adam Schefter",
                "published_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
            }
        ]
    )


# ---------------------------------------------------------------------------
# PunditPrediction dataclass fields
# ---------------------------------------------------------------------------


class TestPunditPredictionProvenanceFields:
    def test_new_fields_default_to_none(self):
        p = PunditPrediction(
            pundit_id="test",
            pundit_name="Test Pundit",
            source_url="https://example.com",
            raw_assertion_text="Some prediction",
        )
        assert p.prompt_version is None
        assert p.llm_provider is None
        assert p.llm_model is None

    def test_fields_accept_values(self):
        p = PunditPrediction(
            pundit_id="test",
            pundit_name="Test Pundit",
            source_url="https://example.com",
            raw_assertion_text="Some prediction",
            prompt_version="a1b2c3d4",
            llm_provider="ollama",
            llm_model="qwen2.5:32b",
        )
        assert p.prompt_version == "a1b2c3d4"
        assert p.llm_provider == "ollama"
        assert p.llm_model == "qwen2.5:32b"


# ---------------------------------------------------------------------------
# PROMPT_VERSION constant
# ---------------------------------------------------------------------------


class TestPromptVersion:
    def test_is_8_char_hex(self):
        assert len(PROMPT_VERSION) == 8
        int(PROMPT_VERSION, 16)  # raises ValueError if not valid hex

    def test_batch_prompt_version_is_8_char_hex(self):
        assert len(BATCH_PROMPT_VERSION) == 8
        int(BATCH_PROMPT_VERSION, 16)

    def test_versions_are_different(self):
        # The single-article and batch prompts should version independently.
        assert PROMPT_VERSION != BATCH_PROMPT_VERSION


# ---------------------------------------------------------------------------
# run_extraction populates provenance on PunditPredictions
# ---------------------------------------------------------------------------


class TestRunExtractionProvenance:
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_provenance_fields_set_on_predictions(
        self, mock_extract, mock_ingest, mock_db, mock_provider
    ):
        mock_db.fetch_df.return_value = make_raw_media_df()
        mock_extract.return_value = ExtractionResult(
            content_hash="abc123",
            predictions=[
                {
                    "extracted_claim": "Chiefs win Super Bowl",
                    "claim_category": "game_outcome",
                    "season_year": 2026,
                    "stance": "bullish",
                }
            ],
        )
        mock_ingest.return_value = ["hash1"]

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert mock_ingest.called
        predictions_arg = mock_ingest.call_args[0][0]
        assert len(predictions_arg) == 1
        pred = predictions_arg[0]

        assert pred.prompt_version == PROMPT_VERSION
        assert (
            pred.llm_provider
            == type(mock_provider).__name__.replace("Provider", "").lower()
        )
        assert pred.llm_model == "test-model-7b"

    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_provider_type_derived_from_class_name(
        self, mock_extract, mock_ingest, mock_db
    ):
        """Provider type uses the class name with 'Provider' stripped."""
        from unittest.mock import MagicMock

        class GeminiProvider:
            model = "gemini-2.5-flash"
            extract_predictions = MagicMock(return_value=[])

        gemini = GeminiProvider()
        mock_db.fetch_df.return_value = make_raw_media_df()
        mock_extract.return_value = ExtractionResult(
            content_hash="abc123",
            predictions=[
                {
                    "extracted_claim": "Chiefs win Super Bowl",
                    "claim_category": "game_outcome",
                    "stance": "bullish",
                    "season_year": 2026,
                }
            ],
        )
        mock_ingest.return_value = ["hash1"]

        run_extraction(limit=10, db=mock_db, provider=gemini)

        pred = mock_ingest.call_args[0][0][0]
        assert pred.llm_provider == "gemini"
        assert pred.llm_model == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# _build_pundit_predictions (local_rag_pipeline) passes provenance through
# ---------------------------------------------------------------------------


class TestBuildPunditPredictionsProvenance:
    def _make_article(self):
        return ArticleRecord(
            content_hash="art123",
            raw_text="The Chiefs will win it all.",
            title="Mock Article",
            pundit_name="Pat McAfee",
            source_name="pat_mcafee_show",
            published_date="2026-04-01",
        )

    def test_provenance_passed_to_predictions(self):
        predictions = [
            {
                "extracted_claim": "Chiefs win Super Bowl",
                "claim_category": "game_outcome",
            }
        ]
        article = self._make_article()
        result = _build_pundit_predictions(
            predictions,
            article,
            pundit_id="pat_mcafee",
            source_url="https://mcafee.com/1",
            prompt_version="b4a3f1c2",
            llm_provider="ollama",
            llm_model="qwen2.5:32b",
        )

        assert len(result) == 1
        assert result[0].prompt_version == "b4a3f1c2"
        assert result[0].llm_provider == "ollama"
        assert result[0].llm_model == "qwen2.5:32b"

    def test_defaults_to_none_when_not_provided(self):
        predictions = [
            {
                "extracted_claim": "Bears make playoffs",
                "claim_category": "game_outcome",
            }
        ]
        article = self._make_article()
        result = _build_pundit_predictions(
            predictions,
            article,
            pundit_id="cowherd",
            source_url="https://cowherd.com/1",
        )

        assert result[0].prompt_version is None
        assert result[0].llm_provider is None
        assert result[0].llm_model is None


# ---------------------------------------------------------------------------
# ingest_batch includes provenance in row dict
# ---------------------------------------------------------------------------


class TestIngestBatchProvenance:
    @patch("src.cryptographic_ledger._append_to_ledger")
    @patch("src.cryptographic_ledger.get_latest_chain_hash", return_value="")
    def test_provenance_columns_in_row(self, mock_chain, mock_append, mock_db):
        predictions = [
            PunditPrediction(
                pundit_id="test",
                pundit_name="Test",
                source_url="https://x.com",
                raw_assertion_text="Some claim",
                prompt_version="a1b2c3d4",
                llm_provider="ollama",
                llm_model="qwen2.5:32b",
            )
        ]
        ingest_batch(predictions, db=mock_db)

        assert mock_append.called
        df_arg = mock_append.call_args[0][0]
        assert "prompt_version" in df_arg.columns
        assert "llm_provider" in df_arg.columns
        assert "llm_model" in df_arg.columns
        assert df_arg.iloc[0]["prompt_version"] == "a1b2c3d4"
        assert df_arg.iloc[0]["llm_provider"] == "ollama"
        assert df_arg.iloc[0]["llm_model"] == "qwen2.5:32b"

    @patch("src.cryptographic_ledger._append_to_ledger")
    @patch("src.cryptographic_ledger.get_latest_chain_hash", return_value="")
    def test_null_provenance_written_as_none(self, mock_chain, mock_append, mock_db):
        predictions = [
            PunditPrediction(
                pundit_id="test",
                pundit_name="Test",
                source_url="https://x.com",
                raw_assertion_text="Some claim",
            )
        ]
        ingest_batch(predictions, db=mock_db)

        df_arg = mock_append.call_args[0][0]
        assert pd.isna(df_arg.iloc[0]["prompt_version"])
        assert pd.isna(df_arg.iloc[0]["llm_provider"])
        assert pd.isna(df_arg.iloc[0]["llm_model"])


# ---------------------------------------------------------------------------
# extraction_quality CLI — unit tests (no BQ)
# ---------------------------------------------------------------------------


class TestExtractionQualityReport:
    def test_run_report_handles_empty_ledger(self, mock_db, capsys):
        mock_db.fetch_df.return_value = pd.DataFrame()

        from src.extraction_quality import run_report

        run_report(compare_versions=True, db=mock_db)
        out = capsys.readouterr().out
        assert "No predictions found" in out

    def test_run_report_prints_version_table(self, mock_db, capsys):
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "prompt_version": "a1b2c3d4",
                    "llm_provider": "ollama",
                    "llm_model": "qwen2.5:32b",
                    "total_predictions": 50,
                    "correct": 30,
                    "incorrect": 10,
                    "pending": 10,
                    "resolved": 40,
                    "precision": 0.75,
                }
            ]
        )

        from src.extraction_quality import run_report

        run_report(compare_versions=True, db=mock_db)
        out = capsys.readouterr().out
        assert "prompt_version" in out.lower() or "Prompt Version" in out

    def test_run_report_defaults_to_versions_when_no_flags(self, mock_db, capsys):
        mock_db.fetch_df.return_value = pd.DataFrame()

        from src.extraction_quality import run_report

        # All flags False → should still run (defaults to versions)
        run_report(
            compare_versions=False,
            compare_providers=False,
            compare_models=False,
            db=mock_db,
        )
        out = capsys.readouterr().out
        # Should not raise and should produce some output
        assert out  # non-empty

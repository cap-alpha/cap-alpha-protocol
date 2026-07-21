"""
Tests for speech-act authorship classification (Issue #366).

Covers the three authorship speech acts:
  authored   — speaker makes the claim directly
  quoted     — speaker transmits another person's claim; score routes to originating_speaker
  commentary — speaker reacts to / agrees or disagrees with a claim; treated as a new
               authored claim by the current speaker

Complements test_extraction_speech_act.py (which covers speech_act_type / testability).
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    DEFAULT_SPEECH_ACT,
    VALID_SPEECH_ACTS,
    ExtractionResult,
    extract_assertions,
    run_extraction,
    write_raw_utterances,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_utterance(
    text: str = "Mahomes will win MVP",
    speech_act_type: str = "assertion",
    speech_act: str = "authored",
    originating_speaker: str = None,
    testability_score: float = 0.85,
    extracted_claim: str = None,
    season_year: int = 2026,
    **kwargs,
) -> dict:
    if extracted_claim is None:
        extracted_claim = text
    return {
        "text": text,
        "speech_act_type": speech_act_type,
        "speech_act": speech_act,
        "originating_speaker": originating_speaker,
        "testability_score": testability_score,
        "testability_subscores": {
            "subject_specificity": testability_score,
            "predicate_falsifiability": testability_score,
            "threshold_concreteness": testability_score,
            "resolution_horizon_defined": testability_score,
            "evidence_accessibility": testability_score,
        },
        "extracted_claim": extracted_claim,
        "claim_category": kwargs.get("claim_category", "player_performance"),
        "stance": kwargs.get("stance", "bullish"),
        "season_year": season_year,
        "target_player": kwargs.get("target_player"),
        "target_team": kwargs.get("target_team"),
        "confidence_note": "strong",
        "prediction_horizon_days": 90,
        "resolution_horizon": None,
        "predicate": "will_win",
        "subject": "Patrick Mahomes",
        "predicate_args": {},
    }


def make_raw_media_df(n: int = 1) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "content_hash": f"hash_{i}",
                "source_id": "espn_nfl",
                "title": f"Article {i}",
                "raw_text": (
                    "Patrick Mahomes will definitely win the NFL MVP award this season without question. "
                    "The Kansas City Chiefs offense has been completely unstoppable all year long. "
                    "Nobody in the entire NFL can match his incredible playmaking ability and arm strength. "
                    "The Super Bowl is absolutely well within reach for the Chiefs this season."
                ),
                "source_url": f"https://espn.com/article/{i}",
                "author": "Adam Schefter",
                "matched_pundit_id": "adam_schefter",
                "matched_pundit_name": "Adam Schefter",
                "published_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    db.client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    # write_raw_utterances routes through db.append_dataframe_to_table (#1124),
    # not db.client.load_table_from_dataframe directly — delegate so existing
    # assertions on db.client.load_table_from_dataframe.call_args still work.
    db.append_dataframe_to_table.side_effect = lambda df, table_name: (
        db.client.load_table_from_dataframe(df, table_name, job_config=None)
    )
    return db


@pytest.fixture
def mock_provider():
    p = MagicMock()
    p.model = "mock-model"
    p.extract_predictions.return_value = []
    return p


# ---------------------------------------------------------------------------
# VALID_SPEECH_ACTS constant
# ---------------------------------------------------------------------------


class TestValidSpeechActs:
    def test_exactly_three_values(self):
        assert VALID_SPEECH_ACTS == {"authored", "quoted", "commentary"}

    def test_default_is_authored(self):
        assert DEFAULT_SPEECH_ACT == "authored"


# ---------------------------------------------------------------------------
# write_raw_utterances — new fields persisted to BQ
# ---------------------------------------------------------------------------


class TestWriteRawUtterancesNewFields:
    def test_authored_speech_act_written(self, mock_db):
        utterances = [make_utterance(speech_act="authored")]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert df.iloc[0]["speech_act"] == "authored"
        val = df.iloc[0]["originating_speaker"]
        assert val is None or val == "None" or pd.isna(val)

    def test_quoted_speech_act_written_with_originating_speaker(self, mock_db):
        utterances = [
            make_utterance(
                speech_act="quoted",
                originating_speaker="Adam Schefter",
                extracted_claim="Cowboys will cut Dak Prescott (per Schefter)",
            )
        ]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert df.iloc[0]["speech_act"] == "quoted"
        assert df.iloc[0]["originating_speaker"] == "Adam Schefter"

    def test_commentary_speech_act_written(self, mock_db):
        utterances = [
            make_utterance(
                speech_act="commentary",
                originating_speaker="Colin Cowherd",
                extracted_claim="agree: Mahomes wins 4th Super Bowl",
            )
        ]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert df.iloc[0]["speech_act"] == "commentary"
        assert df.iloc[0]["originating_speaker"] == "Colin Cowherd"

    def test_unknown_speech_act_defaults_to_authored(self, mock_db):
        utterances = [make_utterance(speech_act="invented_type")]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert df.iloc[0]["speech_act"] == "authored"

    def test_missing_speech_act_defaults_to_authored(self, mock_db):
        u = make_utterance()
        del u["speech_act"]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=[u],
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert df.iloc[0]["speech_act"] == "authored"

    def test_empty_originating_speaker_stored_as_none(self, mock_db):
        utterances = [make_utterance(speech_act="authored", originating_speaker="")]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        # Empty string coerced to None in rows dict. After object→str cast in the
        # BQ write path, None becomes "None". Both represent a null speaker.
        val = df.iloc[0]["originating_speaker"]
        assert val is None or val == "None" or pd.isna(val)

    def test_schema_includes_new_columns(self, mock_db):
        utterances = [make_utterance()]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="doc1",
                speaker_entity_id="ent1",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert "speech_act" in df.columns
        assert "originating_speaker" in df.columns


# ---------------------------------------------------------------------------
# Scoring routing — run_extraction routes quoted claims to originating_speaker
# ---------------------------------------------------------------------------


class TestScoringRouting:
    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_authored_claim_attributed_to_speaker(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        pred = make_utterance(
            speech_act="authored",
            extracted_claim="Mahomes will win MVP in 2026",
        )
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[pred], utterances=[pred]
        )
        mock_ingest.return_value = ["h1"]
        mock_write.return_value = (1, {})

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        ingested = mock_ingest.call_args[0][0]
        assert len(ingested) == 1
        assert ingested[0].pundit_id == "adam_schefter"
        assert ingested[0].pundit_name == "Adam Schefter"

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_quoted_claim_routed_to_originating_speaker(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """When speech_act=quoted, the PunditPrediction must credit the originating_speaker."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        pred = make_utterance(
            speech_act="quoted",
            originating_speaker="Ian Rapoport",
            extracted_claim="Chiefs extend Mahomes by 3 years (per Rapoport)",
        )
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[pred], utterances=[pred]
        )
        mock_ingest.return_value = ["h1"]
        mock_write.return_value = (1, {})

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        ingested = mock_ingest.call_args[0][0]
        assert len(ingested) == 1
        # Score credited to originating_speaker, not the transmitter
        assert ingested[0].pundit_name == "Ian Rapoport"
        assert "ian_rapoport" in ingested[0].pundit_id

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_quoted_without_originating_speaker_falls_back_to_current_speaker(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """speech_act=quoted with no originating_speaker must NOT crash; fall back to current speaker."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        pred = make_utterance(
            speech_act="quoted",
            originating_speaker=None,
            extracted_claim="Someone reported Mahomes trade",
        )
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[pred], utterances=[pred]
        )
        mock_ingest.return_value = ["h1"]
        mock_write.return_value = (1, {})

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        ingested = mock_ingest.call_args[0][0]
        assert len(ingested) == 1
        assert ingested[0].pundit_id == "adam_schefter"

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_commentary_claim_attributed_to_current_speaker(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """commentary claims are authored by the current speaker (their agree/disagree opinion)."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        pred = make_utterance(
            speech_act="commentary",
            originating_speaker="Colin Cowherd",
            extracted_claim="agree: Mahomes wins 4th Super Bowl",
        )
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0", predictions=[pred], utterances=[pred]
        )
        mock_ingest.return_value = ["h1"]
        mock_write.return_value = (1, {})

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        ingested = mock_ingest.call_args[0][0]
        assert len(ingested) == 1
        # Commentary: attribution stays with current speaker (they own the agree/disagree)
        assert ingested[0].pundit_id == "adam_schefter"
        assert ingested[0].pundit_name == "Adam Schefter"

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_mixed_speech_acts_routed_correctly(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """authored + quoted in same article: authored → current speaker, quoted → originating_speaker."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)
        authored_pred = make_utterance(
            text="Eagles win 12 games",
            speech_act="authored",
            extracted_claim="Eagles win 12 games in 2026",
        )
        quoted_pred = make_utterance(
            text="Pelissero says Eagles will trade Slay",
            speech_act="quoted",
            originating_speaker="Tom Pelissero",
            extracted_claim="Eagles will trade Slay (per Pelissero)",
            claim_category="trade",
        )
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[authored_pred, quoted_pred],
            utterances=[authored_pred, quoted_pred],
        )
        mock_ingest.return_value = ["h1", "h2"]
        mock_write.return_value = (2, {})

        run_extraction(limit=10, db=mock_db, provider=mock_provider)

        ingested = mock_ingest.call_args[0][0]
        assert len(ingested) == 2

        by_claim = {p.extracted_claim: p for p in ingested}
        assert by_claim["Eagles win 12 games in 2026"].pundit_id == "adam_schefter"
        assert (
            by_claim["Eagles will trade Slay (per Pelissero)"].pundit_name
            == "Tom Pelissero"
        )


# ---------------------------------------------------------------------------
# extract_assertions — speech_act field propagated to utterances
# ---------------------------------------------------------------------------


class TestExtractAssertionsSpeechActField:
    def test_authored_utterance_preserved(self, mock_provider):
        mock_provider.extract_predictions.return_value = [
            make_utterance(speech_act="authored")
        ]
        result = extract_assertions(
            content_hash="abc123", text="...", provider=mock_provider
        )
        assert result.utterances[0]["speech_act"] == "authored"

    def test_quoted_utterance_preserved(self, mock_provider):
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                speech_act="quoted",
                originating_speaker="Ian Rapoport",
                extracted_claim="Chiefs cut Hill (per Rapoport)",
            )
        ]
        result = extract_assertions(
            content_hash="abc123", text="...", provider=mock_provider
        )
        assert result.utterances[0]["speech_act"] == "quoted"
        assert result.utterances[0]["originating_speaker"] == "Ian Rapoport"

    def test_commentary_utterance_preserved(self, mock_provider):
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                speech_act="commentary",
                originating_speaker="Colin Cowherd",
                extracted_claim="agree: Mahomes wins 4th Super Bowl",
            )
        ]
        result = extract_assertions(
            content_hash="abc123", text="...", provider=mock_provider
        )
        assert result.utterances[0]["speech_act"] == "commentary"
        assert result.utterances[0]["originating_speaker"] == "Colin Cowherd"

    def test_speech_act_absent_in_legacy_response(self, mock_provider):
        """LLM responses without speech_act field are tolerated."""
        u = make_utterance()
        del u["speech_act"]
        del u["originating_speaker"]
        mock_provider.extract_predictions.return_value = [u]
        result = extract_assertions(
            content_hash="abc123", text="...", provider=mock_provider
        )
        # Field absent in utterances dict — should not raise
        assert len(result.utterances) == 1

    def test_all_three_speech_acts_in_same_article(self, mock_provider):
        mock_provider.extract_predictions.return_value = [
            make_utterance(speech_act="authored", text="Eagles win 12"),
            make_utterance(
                speech_act="quoted",
                text="Schefter says Eagles cut Slay",
                originating_speaker="Adam Schefter",
                extracted_claim="Eagles cut Slay (per Schefter)",
            ),
            make_utterance(
                speech_act="commentary",
                text="I agree with Schefter on this one",
                originating_speaker="Adam Schefter",
                extracted_claim="agree: Eagles cut Slay",
            ),
        ]
        result = extract_assertions(
            content_hash="abc123", text="...", provider=mock_provider
        )
        acts = [u["speech_act"] for u in result.utterances]
        assert "authored" in acts
        assert "quoted" in acts
        assert "commentary" in acts

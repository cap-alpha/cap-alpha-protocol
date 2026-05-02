"""
Phase C — speech_act_type + testability_score extraction tests (Issue #555).

Tests cover:
- Speech-act classification: rhetorical questions NOT promoted, assertions promoted
- testability_score averaging of 5 sub-scores
- Promotion logic: testability_score < 0.6 → raw_utterance only, NOT ledger
- TESTABILITY_THRESHOLD=0.0 backward-compat mode → everything promoted
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    ExtractionResult,
    PROMOTABLE_SPEECH_ACTS,
    VALID_SPEECH_ACT_TYPES,
    _is_promotable,
    compute_testability_score,
    extract_assertions,
    get_testability_threshold,
    run_extraction,
    write_raw_utterances,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    # Simulate BQ client for write_raw_utterances
    db.client = MagicMock()
    mock_job = MagicMock()
    mock_job.result.return_value = None
    db.client.load_table_from_dataframe.return_value = mock_job
    return db


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model = "mock-model"
    provider.extract_predictions.return_value = []
    return provider


def make_utterance(
    text: str = "Mahomes will win MVP",
    speech_act_type: str = "assertion",
    testability_score: float = 0.8,
    subscores: dict = None,
    extracted_claim: str = "",
    **kwargs,
) -> dict:
    """Helper to build a minimal utterance dict."""
    if extracted_claim == "" and speech_act_type in PROMOTABLE_SPEECH_ACTS:
        extracted_claim = text
    return {
        "text": text,
        "speech_act_type": speech_act_type,
        "testability_score": testability_score,
        "testability_subscores": subscores
        or {
            "subject_specificity": testability_score,
            "predicate_falsifiability": testability_score,
            "threshold_concreteness": testability_score,
            "resolution_horizon_defined": testability_score,
            "evidence_accessibility": testability_score,
        },
        "extracted_claim": extracted_claim,
        "claim_category": kwargs.get("claim_category", "player_performance"),
        "stance": kwargs.get("stance", "bullish"),
        "season_year": kwargs.get("season_year", 2026),
        "target_player": kwargs.get("target_player", None),
        "target_team": kwargs.get("target_team", None),
        "confidence_note": kwargs.get("confidence_note", "strong"),
        "prediction_horizon_days": kwargs.get("prediction_horizon_days", 90),
        "resolution_horizon": kwargs.get("resolution_horizon", None),
        "predicate": kwargs.get("predicate", "will_win"),
        "subject": kwargs.get("subject", "Patrick Mahomes"),
        "predicate_args": kwargs.get("predicate_args", {}),
    }


def make_raw_media_df(n: int = 1) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "content_hash": f"hash_{i}",
                "source_id": "espn_nfl",
                "title": f"Article {i}",
                "raw_text": "Mahomes will win MVP this season. Can anyone stop him?",
                "source_url": f"https://espn.com/article/{i}",
                "author": "Adam Schefter",
                "matched_pundit_id": "adam_schefter",
                "matched_pundit_name": "Adam Schefter",
                "published_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
                "sport": "NFL",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# compute_testability_score
# ---------------------------------------------------------------------------


class TestComputeTestabilityScore:
    def test_averages_five_subscores(self):
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 0.8,
            "threshold_concreteness": 0.6,
            "resolution_horizon_defined": 0.4,
            "evidence_accessibility": 0.2,
        }
        score = compute_testability_score(subscores)
        assert score == pytest.approx((1.0 + 0.8 + 0.6 + 0.4 + 0.2) / 5, abs=1e-3)

    def test_all_ones_returns_one(self):
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 1.0,
            "resolution_horizon_defined": 1.0,
            "evidence_accessibility": 1.0,
        }
        assert compute_testability_score(subscores) == 1.0

    def test_all_zeros_returns_zero(self):
        subscores = {
            "subject_specificity": 0.0,
            "predicate_falsifiability": 0.0,
            "threshold_concreteness": 0.0,
            "resolution_horizon_defined": 0.0,
            "evidence_accessibility": 0.0,
        }
        assert compute_testability_score(subscores) == 0.0

    def test_missing_subscore_defaults_to_zero(self):
        # 4 of 5 subscores present at 1.0; missing one defaults to 0.0 → avg 0.8
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 1.0,
            "resolution_horizon_defined": 1.0,
            # evidence_accessibility missing
        }
        score = compute_testability_score(subscores)
        assert score == pytest.approx(0.8, abs=1e-3)

    def test_empty_subscores_returns_zero(self):
        assert compute_testability_score({}) == 0.0

    def test_none_subscores_returns_zero(self):
        assert compute_testability_score(None) == 0.0

    def test_clamps_out_of_range_values(self):
        """Values > 1.0 or < 0.0 should be clamped."""
        subscores = {
            "subject_specificity": 2.0,  # clamped to 1.0
            "predicate_falsifiability": -0.5,  # clamped to 0.0
            "threshold_concreteness": 0.5,
            "resolution_horizon_defined": 0.5,
            "evidence_accessibility": 0.5,
        }
        score = compute_testability_score(subscores)
        # (1.0 + 0.0 + 0.5 + 0.5 + 0.5) / 5 = 0.5
        assert score == pytest.approx(0.5, abs=1e-3)

    def test_rhetorical_question_low_score(self):
        """A typical rhetorical question should score well below 0.6."""
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 0.1,
            "threshold_concreteness": 0.0,
            "resolution_horizon_defined": 0.0,
            "evidence_accessibility": 0.2,
        }
        score = compute_testability_score(subscores)
        assert score < 0.6

    def test_assertion_high_score(self):
        """A concrete numeric assertion should score well above 0.6."""
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 1.0,
            "resolution_horizon_defined": 0.8,
            "evidence_accessibility": 1.0,
        }
        score = compute_testability_score(subscores)
        assert score >= 0.6


# ---------------------------------------------------------------------------
# get_testability_threshold
# ---------------------------------------------------------------------------


class TestGetTestabilityThreshold:
    def test_default_is_0_6(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TESTABILITY_THRESHOLD", None)
            assert get_testability_threshold() == 0.6

    def test_env_override(self):
        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.3"}):
            assert get_testability_threshold() == 0.3

    def test_zero_allows_everything(self):
        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.0"}):
            assert get_testability_threshold() == 0.0

    def test_one_blocks_everything(self):
        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "1.0"}):
            assert get_testability_threshold() == 1.0

    def test_out_of_range_uses_default(self):
        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "1.5"}):
            assert get_testability_threshold() == 0.6

    def test_non_float_uses_default(self):
        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "high"}):
            assert get_testability_threshold() == 0.6


# ---------------------------------------------------------------------------
# _is_promotable
# ---------------------------------------------------------------------------


class TestIsPromotable:
    def test_assertion_above_threshold_promoted(self):
        u = make_utterance(speech_act_type="assertion", testability_score=0.8)
        assert _is_promotable(u, threshold=0.6) is True

    def test_conditional_above_threshold_promoted(self):
        u = make_utterance(speech_act_type="conditional", testability_score=0.7)
        assert _is_promotable(u, threshold=0.6) is True

    def test_recall_above_threshold_promoted(self):
        u = make_utterance(speech_act_type="recall", testability_score=0.65)
        assert _is_promotable(u, threshold=0.6) is True

    def test_rhetorical_question_never_promoted(self):
        """Rhetorical questions must NEVER be promoted, even with high testability_score."""
        u = make_utterance(
            text="Can anyone stop this offense?",
            speech_act_type="rhetorical_question",
            testability_score=0.9,
            extracted_claim="Can anyone stop this offense?",
        )
        assert _is_promotable(u, threshold=0.6) is False

    def test_hedge_never_promoted(self):
        u = make_utterance(
            text="I think he might win MVP",
            speech_act_type="hedge",
            testability_score=0.9,
            extracted_claim="he might win MVP",
        )
        assert _is_promotable(u, threshold=0.6) is False

    def test_commentary_never_promoted(self):
        u = make_utterance(
            speech_act_type="commentary",
            testability_score=0.9,
            extracted_claim="Their run game is the key",
        )
        assert _is_promotable(u, threshold=0.6) is False

    def test_opinion_never_promoted(self):
        u = make_utterance(
            speech_act_type="opinion",
            testability_score=0.9,
            extracted_claim="He's the best QB ever",
        )
        assert _is_promotable(u, threshold=0.6) is False

    def test_analogy_never_promoted(self):
        u = make_utterance(
            speech_act_type="analogy",
            testability_score=0.9,
            extracted_claim="like Jordan in the clutch",
        )
        assert _is_promotable(u, threshold=0.6) is False

    def test_joke_never_promoted(self):
        u = make_utterance(
            speech_act_type="joke",
            testability_score=0.9,
            extracted_claim="they'll win by infinity",
        )
        assert _is_promotable(u, threshold=0.6) is False

    def test_assertion_below_threshold_not_promoted(self):
        """Assertion with testability_score < threshold should NOT be promoted."""
        u = make_utterance(speech_act_type="assertion", testability_score=0.4)
        assert _is_promotable(u, threshold=0.6) is False

    def test_assertion_at_threshold_promoted(self):
        """Exactly at the threshold should be promoted."""
        u = make_utterance(speech_act_type="assertion", testability_score=0.6)
        assert _is_promotable(u, threshold=0.6) is True

    def test_empty_claim_not_promoted(self):
        """Even valid speech_act + high score is not promoted if extracted_claim is empty."""
        # Build the utterance directly — bypassing the make_utterance helper which
        # auto-fills extracted_claim for promotable types.
        u = {
            "text": "Some text",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "testability_subscores": {},
            "extracted_claim": "",  # explicitly empty
            "claim_category": "player_performance",
            "stance": "bullish",
            "season_year": 2026,
        }
        assert _is_promotable(u, threshold=0.6) is False

    def test_threshold_zero_promotes_all_speech_acts(self):
        """With threshold=0.0, all assertion/conditional/recall should be promoted
        as long as extracted_claim is non-empty."""
        for sat in ("assertion", "conditional", "recall"):
            u = make_utterance(speech_act_type=sat, testability_score=0.0)
            assert _is_promotable(u, threshold=0.0) is True, f"failed for {sat}"

    def test_threshold_zero_still_blocks_non_promotable(self):
        """threshold=0.0 only promotes assertion/conditional/recall — not rhetorical_question etc."""
        for sat in (
            "rhetorical_question",
            "hedge",
            "commentary",
            "opinion",
            "analogy",
            "joke",
        ):
            u = make_utterance(
                speech_act_type=sat, testability_score=0.0, extracted_claim="some text"
            )
            assert _is_promotable(u, threshold=0.0) is False, (
                f"should not promote {sat}"
            )


# ---------------------------------------------------------------------------
# extract_assertions — Phase C
# ---------------------------------------------------------------------------


class TestExtractAssertionsSpeechAct:
    def test_rhetorical_question_not_in_predictions(self, mock_provider):
        """Rhetorical questions must not appear in result.predictions."""
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                text="Can anyone stop Mahomes?",
                speech_act_type="rhetorical_question",
                testability_score=0.2,
                extracted_claim="",
            ),
            make_utterance(
                text="Mahomes will win MVP in 2026",
                speech_act_type="assertion",
                testability_score=0.85,
                extracted_claim="Mahomes will win MVP in 2026",
                season_year=2026,
            ),
        ]

        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.6"}):
            result = extract_assertions(
                content_hash="abc123",
                text="...",
                provider=mock_provider,
            )

        assert len(result.predictions) == 1
        assert "Mahomes will win MVP" in result.predictions[0]["extracted_claim"]

    def test_rhetorical_question_in_utterances(self, mock_provider):
        """Rhetorical questions should appear in result.utterances (full audit trail)."""
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                text="Can anyone stop Mahomes?",
                speech_act_type="rhetorical_question",
                testability_score=0.2,
                extracted_claim="",
            ),
            make_utterance(
                text="Mahomes will win MVP in 2026",
                speech_act_type="assertion",
                testability_score=0.85,
                extracted_claim="Mahomes will win MVP in 2026",
                season_year=2026,
            ),
        ]

        result = extract_assertions(
            content_hash="abc123",
            text="...",
            provider=mock_provider,
        )

        assert len(result.utterances) == 2
        types = {u["speech_act_type"] for u in result.utterances}
        assert "rhetorical_question" in types
        assert "assertion" in types

    def test_low_testability_assertion_not_promoted(self, mock_provider):
        """An assertion below the testability threshold must not reach predictions."""
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                text="He will probably do okay",
                speech_act_type="assertion",
                testability_score=0.3,  # below default threshold 0.6
                extracted_claim="He will do okay",
            ),
        ]

        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.6"}):
            result = extract_assertions(
                content_hash="abc123",
                text="...",
                provider=mock_provider,
            )

        assert len(result.predictions) == 0
        assert len(result.utterances) == 1  # still captured

    def test_low_testability_assertion_in_utterances(self, mock_provider):
        """Low-testability utterances must still appear in result.utterances."""
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                text="He will probably struggle",
                speech_act_type="assertion",
                testability_score=0.25,
                extracted_claim="He will struggle",
            ),
        ]

        result = extract_assertions(
            content_hash="abc123",
            text="...",
            provider=mock_provider,
        )

        assert len(result.utterances) == 1
        assert result.utterances[0]["text"] == "He will probably struggle"

    def test_testability_score_recomputed_from_subscores(self, mock_provider):
        """When subscores are present, the score should be recomputed by the pipeline."""
        subscores = {
            "subject_specificity": 1.0,
            "predicate_falsifiability": 1.0,
            "threshold_concreteness": 1.0,
            "resolution_horizon_defined": 1.0,
            "evidence_accessibility": 1.0,
        }
        mock_provider.extract_predictions.return_value = [
            {
                "text": "Eagles win 12+ games",
                "speech_act_type": "assertion",
                "testability_subscores": subscores,
                "testability_score": 0.1,  # deliberately wrong — should be overwritten
                "extracted_claim": "Eagles win 12+ games",
                "claim_category": "game_outcome",
                "stance": "bullish",
                "season_year": 2026,
                "target_player": None,
                "target_team": "PHI",
                "confidence_note": "strong",
                "prediction_horizon_days": 90,
                "resolution_horizon": None,
                "predicate": "will_win_at_least",
                "subject": "Philadelphia Eagles",
                "predicate_args": {},
            }
        ]

        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.6"}):
            result = extract_assertions(
                content_hash="abc123",
                text="...",
                provider=mock_provider,
            )

        # Score should have been recomputed to 1.0, so it IS promoted
        assert len(result.predictions) == 1
        # Confirm recomputed score in utterances
        assert result.utterances[0]["testability_score"] == 1.0

    def test_conditional_promoted(self, mock_provider):
        """Conditionals above threshold are promoted."""
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                text="If the OL stays healthy, Ravens reach AFC Championship",
                speech_act_type="conditional",
                testability_score=0.88,
                extracted_claim="Ravens reach AFC Championship (conditional on OL health)",
                season_year=2026,
            ),
        ]

        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.6"}):
            result = extract_assertions(
                content_hash="abc123",
                text="...",
                provider=mock_provider,
            )

        assert len(result.predictions) == 1
        assert "Ravens" in result.predictions[0]["extracted_claim"]

    def test_threshold_zero_promotes_everything(self, mock_provider):
        """TESTABILITY_THRESHOLD=0.0 — all utterances with non-empty claim promoted."""
        mock_provider.extract_predictions.return_value = [
            make_utterance(
                text="Can anyone stop Mahomes?",
                speech_act_type="rhetorical_question",
                testability_score=0.1,
                extracted_claim="",  # empty → still not promoted (no claim text)
            ),
            make_utterance(
                text="He will be okay",
                speech_act_type="assertion",
                testability_score=0.05,
                extracted_claim="He will be okay",
                season_year=2026,
            ),
            make_utterance(
                text="If healthy, he wins",
                speech_act_type="conditional",
                testability_score=0.05,
                extracted_claim="If healthy, he wins",
                season_year=2026,
            ),
        ]

        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.0"}):
            result = extract_assertions(
                content_hash="abc123",
                text="...",
                provider=mock_provider,
            )

        # rhetorical_question has empty claim → not promoted even at threshold=0
        # The other two (assertion, conditional) should be promoted
        assert len(result.predictions) == 2
        types = {p["speech_act_type"] for p in result.predictions}
        assert "assertion" in types
        assert "conditional" in types


# ---------------------------------------------------------------------------
# write_raw_utterances
# ---------------------------------------------------------------------------


class TestWriteRawUtterances:
    def test_writes_all_utterances(self, mock_db):
        utterances = [
            make_utterance(speech_act_type="assertion", testability_score=0.8),
            make_utterance(
                text="Can anyone stop this?",
                speech_act_type="rhetorical_question",
                testability_score=0.2,
                extracted_claim="",
            ),
        ]

        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            n = write_raw_utterances(
                utterances=utterances,
                source_doc_id="hash_abc",
                speaker_entity_id="entity_123",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )

        assert n == 2
        mock_db.client.load_table_from_dataframe.assert_called_once()
        df_written = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert len(df_written) == 2
        assert set(df_written.columns) >= {
            "utterance_id",
            "source_doc_id",
            "speaker_entity_id",
            "uttered_at",
            "text",
            "speech_act_type",
            "testability_score",
            "domain",
            "extraction_confidence",
            "created_at",
        }

    def test_returns_zero_on_empty_list(self, mock_db):
        n = write_raw_utterances(
            utterances=[],
            source_doc_id="hash_abc",
            speaker_entity_id="entity_123",
            uttered_at=datetime.now(timezone.utc),
            domain="nfl",
            db=mock_db,
        )
        assert n == 0
        mock_db.client.load_table_from_dataframe.assert_not_called()

    def test_recomputes_score_from_subscores(self, mock_db):
        """Subscores present → score should be recomputed before writing."""
        utterances = [
            {
                "text": "Eagles win 11+",
                "speech_act_type": "assertion",
                "testability_score": 0.1,  # wrong — should be overwritten
                "testability_subscores": {
                    "subject_specificity": 1.0,
                    "predicate_falsifiability": 1.0,
                    "threshold_concreteness": 1.0,
                    "resolution_horizon_defined": 1.0,
                    "evidence_accessibility": 1.0,
                },
                "extracted_claim": "Eagles win 11+",
                "resolution_horizon": None,
            }
        ]

        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="h",
                speaker_entity_id="e",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )

        df_written = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert float(df_written.iloc[0]["testability_score"]) == pytest.approx(1.0)

    def test_coerces_invalid_speech_act_type(self, mock_db):
        """Unknown speech_act_type values are coerced to 'commentary'."""
        utterances = [
            make_utterance(speech_act_type="unknown_type", testability_score=0.5)
        ]
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            write_raw_utterances(
                utterances=utterances,
                source_doc_id="h",
                speaker_entity_id="e",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        df_written = mock_db.client.load_table_from_dataframe.call_args[0][0]
        assert df_written.iloc[0]["speech_act_type"] == "commentary"

    def test_continues_on_write_failure(self, mock_db):
        """write_raw_utterances should NOT raise on BQ write failure — just return 0."""
        mock_db.client.load_table_from_dataframe.side_effect = Exception(
            "BQ unavailable"
        )
        utterances = [make_utterance()]

        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            n = write_raw_utterances(
                utterances=utterances,
                source_doc_id="h",
                speaker_entity_id="e",
                uttered_at=datetime.now(timezone.utc),
                domain="nfl",
                db=mock_db,
            )
        assert n == 0  # soft failure


# ---------------------------------------------------------------------------
# run_extraction — Phase C integration
# ---------------------------------------------------------------------------


class TestRunExtractionSpeechAct:
    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_utterances_written_to_raw_utterance(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """run_extraction must call write_raw_utterances for the extracted utterances."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)

        all_utterances = [
            make_utterance(
                speech_act_type="rhetorical_question",
                testability_score=0.2,
                extracted_claim="",
            ),
            make_utterance(
                speech_act_type="assertion",
                testability_score=0.85,
                extracted_claim="Mahomes wins MVP in 2026",
                season_year=2026,
            ),
        ]
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[all_utterances[1]],
            utterances=all_utterances,
        )
        mock_ingest.return_value = ["pred_hash_1"]
        mock_write.return_value = 2

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        mock_write.assert_called_once()
        assert summary["utterances_written"] == 2
        assert summary["predictions_extracted"] == 1

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_suppressed_count_tracked(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """Suppressed utterances (not promoted) should be reflected in summary."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)

        all_utterances = [
            make_utterance(
                speech_act_type="rhetorical_question",
                testability_score=0.1,
                extracted_claim="",
            ),
            make_utterance(
                speech_act_type="hedge", testability_score=0.3, extracted_claim=""
            ),
            make_utterance(
                speech_act_type="assertion",
                testability_score=0.9,
                extracted_claim="Eagles win 12+ games",
                season_year=2026,
            ),
        ]
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[all_utterances[2]],
            utterances=all_utterances,
        )
        mock_ingest.return_value = ["pred_hash_1"]
        mock_write.return_value = 3

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["suppressed"] == 2  # 2 utterances not promoted
        assert summary["utterances_written"] == 3

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.extract_assertions")
    def test_low_testability_not_in_ledger(
        self, mock_extract, mock_write, mock_db, mock_provider
    ):
        """Utterances below testability threshold are NOT passed to ingest_batch."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)

        # Prediction list is empty because all utterances scored below threshold
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=[],
            utterances=[
                make_utterance(
                    speech_act_type="assertion",
                    testability_score=0.3,
                    extracted_claim="He will be fine",
                )
            ],
        )
        mock_write.return_value = 1

        with patch("src.assertion_extractor.ingest_batch") as mock_ingest:
            summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        mock_ingest.assert_not_called()
        assert summary["predictions_extracted"] == 0
        assert summary["utterances_written"] == 1

    @patch("src.assertion_extractor.write_raw_utterances")
    @patch("src.assertion_extractor.ingest_batch")
    @patch("src.assertion_extractor.extract_assertions")
    def test_threshold_zero_promotes_all_assertions(
        self, mock_extract, mock_ingest, mock_write, mock_db, mock_provider
    ):
        """TESTABILITY_THRESHOLD=0.0 — all assertion/conditional utterances get promoted."""
        mock_db.fetch_df.return_value = make_raw_media_df(1)

        low_score_assertions = [
            make_utterance(
                speech_act_type="assertion",
                testability_score=0.1,
                extracted_claim="He will do okay",
                season_year=2026,
            ),
            make_utterance(
                speech_act_type="conditional",
                testability_score=0.05,
                extracted_claim="If healthy, he wins",
                season_year=2026,
            ),
        ]
        mock_extract.return_value = ExtractionResult(
            content_hash="hash_0",
            predictions=low_score_assertions,
            utterances=low_score_assertions,
        )
        mock_ingest.return_value = ["h1", "h2"]
        mock_write.return_value = 2

        with patch.dict(os.environ, {"TESTABILITY_THRESHOLD": "0.0"}):
            summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert summary["predictions_extracted"] == 2
        assert summary["predictions_ingested"] == 2

    def test_summary_includes_phase_c_fields(self, mock_db, mock_provider):
        """run_extraction summary must include Phase C observability fields."""
        mock_db.fetch_df.return_value = pd.DataFrame()

        summary = run_extraction(limit=10, db=mock_db, provider=mock_provider)

        assert "utterances_written" in summary
        assert "suppressed" in summary
        assert "testability_threshold" in summary
        assert isinstance(summary["testability_threshold"], float)


# ---------------------------------------------------------------------------
# VALID_SPEECH_ACT_TYPES coverage
# ---------------------------------------------------------------------------


class TestSpeechActTypeTaxonomy:
    def test_promotable_types_are_subset_of_valid(self):
        """PROMOTABLE_SPEECH_ACTS must be a subset of VALID_SPEECH_ACT_TYPES."""
        assert PROMOTABLE_SPEECH_ACTS.issubset(VALID_SPEECH_ACT_TYPES)

    def test_non_promotable_types_defined(self):
        """All non-promotable types are in VALID_SPEECH_ACT_TYPES."""
        non_promotable = {
            "rhetorical_question",
            "hedge",
            "commentary",
            "opinion",
            "analogy",
            "joke",
        }
        assert non_promotable.issubset(VALID_SPEECH_ACT_TYPES)

    def test_exactly_nine_types_defined(self):
        assert len(VALID_SPEECH_ACT_TYPES) == 9

    def test_exactly_three_promotable_types(self):
        assert len(PROMOTABLE_SPEECH_ACTS) == 3
        assert PROMOTABLE_SPEECH_ACTS == {"assertion", "conditional", "recall"}

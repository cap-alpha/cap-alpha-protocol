"""
Sport Field Unit Tests (Issue #120)

Verifies that the sport field flows correctly end-to-end through every
pipeline component: PunditPrediction → ingest → assertion extractor →
media ingestor → resolution engine.

No BigQuery or LLM API required — all mocked.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.assertion_extractor import (
    EXTRACTION_PROMPT,
    extract_assertions,
    run_extraction,
)
from src.cryptographic_ledger import PunditPrediction, ingest_batch, ingest_prediction
from src.media_ingestor import MediaItem, fetch_rss, ingest_source
from src.resolution_engine import get_pending_predictions, get_pundit_accuracy_summary

# ---------------------------------------------------------------------------
# PunditPrediction dataclass
# ---------------------------------------------------------------------------


class TestPunditPredictionSport:
    def test_default_sport_is_nfl(self):
        p = PunditPrediction(
            pundit_id="test",
            pundit_name="Test Pundit",
            source_url="https://x.com/test/1",
            raw_assertion_text="Mahomes wins MVP",
        )
        assert p.sport == "NFL"

    def test_sport_can_be_set_explicitly(self):
        p = PunditPrediction(
            pundit_id="test",
            pundit_name="Test Pundit",
            source_url="https://x.com/test/1",
            raw_assertion_text="Ohtani wins Cy Young",
            sport="MLB",
        )
        assert p.sport == "MLB"

    def test_all_sport_values_accepted(self):
        for sport in ["NFL", "MLB", "NBA", "NHL", "NCAAF", "NCAAB"]:
            p = PunditPrediction(
                pundit_id="test",
                pundit_name="Test",
                source_url="https://x.com/test/1",
                raw_assertion_text="some claim",
                sport=sport,
            )
            assert p.sport == sport


# ---------------------------------------------------------------------------
# ingest_prediction — sport written to BQ row
# ---------------------------------------------------------------------------


class TestIngestPredictionSport:
    def _make_mock_db(self):
        db = MagicMock()
        db.fetch_df.return_value = pd.DataFrame()  # empty → seed chain hash
        mock_job = MagicMock()
        mock_job.result.return_value = None
        db.client.load_table_from_dataframe.return_value = mock_job
        return db

    def test_ingest_prediction_writes_sport_nfl(self):
        db = self._make_mock_db()
        p = PunditPrediction(
            pundit_id="adam_schefter",
            pundit_name="Adam Schefter",
            source_url="https://x.com/schefter/1",
            raw_assertion_text="Chiefs win Super Bowl",
            sport="NFL",
        )
        ingest_prediction(p, db=db)
        df_written = db.client.load_table_from_dataframe.call_args[0][0]
        assert "sport" in df_written.columns
        assert df_written.iloc[0]["sport"] == "NFL"

    def test_ingest_prediction_writes_sport_mlb(self):
        db = self._make_mock_db()
        p = PunditPrediction(
            pundit_id="ken_rosenthal",
            pundit_name="Ken Rosenthal",
            source_url="https://x.com/rosenthal/1",
            raw_assertion_text="Ohtani wins World Series MVP",
            sport="MLB",
        )
        ingest_prediction(p, db=db)
        df_written = db.client.load_table_from_dataframe.call_args[0][0]
        assert df_written.iloc[0]["sport"] == "MLB"

    def test_ingest_batch_writes_sport_per_prediction(self):
        db = self._make_mock_db()
        preds = [
            PunditPrediction(
                pundit_id="p1",
                pundit_name="Pundit 1",
                source_url="https://x.com/p1/1",
                raw_assertion_text="NFL claim",
                sport="NFL",
            ),
            PunditPrediction(
                pundit_id="p2",
                pundit_name="Pundit 2",
                source_url="https://x.com/p2/1",
                raw_assertion_text="MLB claim",
                sport="MLB",
            ),
        ]
        ingest_batch(preds, db=db)
        df_written = db.client.load_table_from_dataframe.call_args[0][0]
        sports = df_written["sport"].tolist()
        assert sports == ["NFL", "MLB"]


# ---------------------------------------------------------------------------
# EXTRACTION_PROMPT — parameterized with sport
# ---------------------------------------------------------------------------


class TestExtractionPromptSport:
    def test_prompt_contains_sport_placeholder(self):
        assert "{sport}" in EXTRACTION_PROMPT

    def test_prompt_renders_nfl(self):
        rendered = EXTRACTION_PROMPT.format(
            sport="NFL",
            published_date="2025-01-01",
            source_name="ESPN",
            author="Adam Schefter",
            title="Test",
            text="some text",
        )
        assert "NFL" in rendered
        assert "{sport}" not in rendered

    def test_prompt_renders_mlb(self):
        rendered = EXTRACTION_PROMPT.format(
            sport="MLB",
            published_date="2025-01-01",
            source_name="MLB.com",
            author="Ken Rosenthal",
            title="Test",
            text="some text",
        )
        assert "MLB" in rendered
        assert "{sport}" not in rendered


# ---------------------------------------------------------------------------
# extract_assertions — sport passed through
# ---------------------------------------------------------------------------


class TestExtractAssertionsSport:
    def _make_mock_provider(self):
        provider = MagicMock()
        provider.model = "mock-model"
        provider.extract_predictions.return_value = []
        return provider

    def test_default_sport_is_nfl_in_prompt(self):
        provider = self._make_mock_provider()
        extract_assertions("abc123", "some text", provider=provider)
        prompt_used = provider.extract_predictions.call_args[0][0]
        assert "NFL" in prompt_used

    def test_mlb_sport_in_prompt(self):
        provider = self._make_mock_provider()
        extract_assertions("abc123", "some text", sport="MLB", provider=provider)
        prompt_used = provider.extract_predictions.call_args[0][0]
        assert "MLB" in prompt_used

    def test_nba_sport_in_prompt(self):
        provider = self._make_mock_provider()
        extract_assertions("abc123", "some text", sport="NBA", provider=provider)
        prompt_used = provider.extract_predictions.call_args[0][0]
        assert "NBA" in prompt_used


# ---------------------------------------------------------------------------
# run_extraction — sport threads to PunditPrediction
# ---------------------------------------------------------------------------


class TestRunExtractionSport:
    def _make_media_row(self, sport="NFL"):
        return {
            "content_hash": "abc" * 20 + "ab",
            "source_id": "espn_nfl",
            "title": "Test Article",
            "raw_text": "Mahomes will win MVP this season.",
            "source_url": "https://espn.com/test",
            "author": "Adam Schefter",
            "matched_pundit_id": "adam_schefter",
            "matched_pundit_name": "Adam Schefter",
            "published_at": None,
            "sport": sport,
        }

    def _make_mock_provider(self, predictions):
        provider = MagicMock()
        provider.model = "mock-model"
        provider.extract_predictions.return_value = predictions
        return provider

    def test_sport_from_media_row_is_passed_to_prediction(self):
        """sport from raw_pundit_media row is set on PunditPrediction."""
        ingested = []

        def fake_ingest_batch(predictions, db):
            ingested.extend(predictions)
            return ["hash_" + str(i) for i in range(len(predictions))]

        provider = self._make_mock_provider(
            [
                {
                    "extracted_claim": "Mahomes wins MVP",
                    "claim_category": "player_performance",
                    "season_year": 2025,
                    "target_player": "P. Mahomes",
                    "target_team": "KC",
                    "confidence_note": "strong",
                }
            ]
        )

        mock_db = MagicMock()
        mock_db.fetch_df.return_value = pd.DataFrame(
            [self._make_media_row(sport="NFL")]
        )

        with patch(
            "src.assertion_extractor.ingest_batch", side_effect=fake_ingest_batch
        ):
            with patch("src.assertion_extractor.mark_as_processed"):
                run_extraction(limit=1, sport="NFL", db=mock_db, provider=provider)

        assert len(ingested) == 1
        assert ingested[0].sport == "NFL"

    def test_default_sport_nfl_when_row_has_no_sport(self):
        """Fallback: if row has no sport column, uses the run_extraction default."""
        ingested = []

        def fake_ingest_batch(predictions, db):
            ingested.extend(predictions)
            return []

        row = self._make_media_row()
        del row["sport"]  # simulate missing sport column on old rows

        provider = self._make_mock_provider(
            [
                {
                    "extracted_claim": "Chiefs win",
                    "claim_category": "game_outcome",
                    "season_year": 2025,
                    "target_player": None,
                    "target_team": "KC",
                    "confidence_note": "strong",
                }
            ]
        )

        mock_db = MagicMock()
        mock_db.fetch_df.return_value = pd.DataFrame([row])

        with patch(
            "src.assertion_extractor.ingest_batch", side_effect=fake_ingest_batch
        ):
            with patch("src.assertion_extractor.mark_as_processed"):
                run_extraction(limit=1, sport="NFL", db=mock_db, provider=provider)

        assert len(ingested) == 1
        assert ingested[0].sport == "NFL"


# ---------------------------------------------------------------------------
# MediaItem dataclass
# ---------------------------------------------------------------------------


class TestMediaItemSport:
    def test_default_sport_is_nfl(self):
        item = MediaItem(
            content_hash="abc",
            source_id="espn_nfl",
            title="Test",
            raw_text="text",
            source_url="https://espn.com/test",
            author="Schefter",
            matched_pundit_id="adam_schefter",
            matched_pundit_name="Adam Schefter",
            published_at=None,
            ingested_at=datetime.now(timezone.utc),
            content_type="article",
            fetch_source_type="rss",
        )
        assert item.sport == "NFL"

    def test_sport_can_be_set_explicitly(self):
        item = MediaItem(
            content_hash="abc",
            source_id="mlb_news",
            title="Test",
            raw_text="text",
            source_url="https://mlb.com/test",
            author="Ken Rosenthal",
            matched_pundit_id="ken_rosenthal",
            matched_pundit_name="Ken Rosenthal",
            published_at=None,
            ingested_at=datetime.now(timezone.utc),
            content_type="article",
            fetch_source_type="rss",
            sport="MLB",
        )
        assert item.sport == "MLB"


# ---------------------------------------------------------------------------
# fetch_rss — reads sport from source config
# ---------------------------------------------------------------------------


class TestFetchRSSSport:
    def _make_feed_entry(self, title="Test", link="https://espn.com/1"):
        entry = MagicMock()
        entry.get = lambda k, d=None: {
            "title": title,
            "link": link,
            "author": None,
        }.get(k, d)
        entry.published_parsed = None
        entry.summary = "Some article text"
        return entry

    def _mock_feed(self, entries):
        feed = MagicMock()
        feed.bozo = False
        feed.entries = entries
        return feed

    def test_sport_from_source_config_nfl(self):
        source = {
            "id": "espn_nfl",
            "name": "ESPN NFL",
            "type": "rss",
            "url": "https://espn.com/rss",
            "sport": "NFL",
            "pundits": [],
        }
        with patch("src.media_ingestor.feedparser.parse") as mock_parse:
            mock_parse.return_value = self._mock_feed([self._make_feed_entry()])
            items = fetch_rss(
                source, {"max_items_per_feed": 50, "fetch_timeout_seconds": 30}
            )
        assert all(item.sport == "NFL" for item in items)

    def test_sport_from_source_config_mlb(self):
        source = {
            "id": "mlb_news",
            "name": "MLB News",
            "type": "rss",
            "url": "https://mlb.com/rss",
            "sport": "MLB",
            "pundits": [],
        }
        with patch("src.media_ingestor.feedparser.parse") as mock_parse:
            mock_parse.return_value = self._mock_feed([self._make_feed_entry()])
            items = fetch_rss(
                source, {"max_items_per_feed": 50, "fetch_timeout_seconds": 30}
            )
        assert all(item.sport == "MLB" for item in items)

    def test_sport_defaults_to_nfl_when_absent_from_config(self):
        source = {
            "id": "some_source",
            "name": "Some Source",
            "type": "rss",
            "url": "https://example.com/rss",
            "pundits": [],  # no sport key
        }
        with patch("src.media_ingestor.feedparser.parse") as mock_parse:
            mock_parse.return_value = self._mock_feed([self._make_feed_entry()])
            items = fetch_rss(
                source, {"max_items_per_feed": 50, "fetch_timeout_seconds": 30}
            )
        assert all(item.sport == "NFL" for item in items)


# ---------------------------------------------------------------------------
# ingest_source — sport written to BQ row
# ---------------------------------------------------------------------------


class TestIngestSourceSport:
    def test_sport_written_to_bq_row(self):
        source = {
            "id": "espn_nfl",
            "name": "ESPN NFL",
            "type": "rss",
            "url": "https://espn.com/rss",
            "sport": "NFL",
            "pundits": [],
        }
        defaults = {
            "max_retries": 1,
            "retry_backoff_seconds": 0,
            "dedup_window_days": 7,
            "max_items_per_feed": 10,
            "fetch_timeout_seconds": 30,
        }
        mock_db = MagicMock()
        mock_db.fetch_df.return_value = pd.DataFrame()  # no existing hashes

        fake_item = MediaItem(
            content_hash="abc123",
            source_id="espn_nfl",
            title="Test",
            raw_text="text",
            source_url="https://espn.com/1",
            author=None,
            matched_pundit_id=None,
            matched_pundit_name=None,
            published_at=None,
            ingested_at=datetime.now(timezone.utc),
            content_type="article",
            fetch_source_type="rss",
            sport="NFL",
        )

        with patch("src.media_ingestor.FETCHERS", {"rss": lambda s, d: [fake_item]}):
            ingest_source(source, defaults, mock_db)

        df_written = mock_db.append_dataframe_to_table.call_args[0][0]
        assert "sport" in df_written.columns
        assert df_written.iloc[0]["sport"] == "NFL"


# ---------------------------------------------------------------------------
# resolution_engine — sport filter in SQL queries
# ---------------------------------------------------------------------------


class TestResolutionEngineSportFilter:
    def _make_mock_db(self, return_df=None):
        db = MagicMock()
        db.fetch_df.return_value = (
            return_df if return_df is not None else pd.DataFrame()
        )
        return db

    def test_get_pending_no_sport_filter(self):
        db = self._make_mock_db()
        get_pending_predictions(db=db)
        query = db.fetch_df.call_args[0][0]
        assert (
            "sport" not in query.lower().split("where")[1]
            if "where" in query.lower()
            else True
        )

    def test_get_pending_with_nfl_filter(self):
        db = self._make_mock_db()
        get_pending_predictions(sport="NFL", db=db)
        query = db.fetch_df.call_args[0][0]
        assert "NFL" in query

    def test_get_pending_with_mlb_filter(self):
        db = self._make_mock_db()
        get_pending_predictions(sport="MLB", db=db)
        query = db.fetch_df.call_args[0][0]
        assert "MLB" in query

    def test_get_accuracy_summary_no_sport_filter(self):
        db = self._make_mock_db()
        get_pundit_accuracy_summary(db=db)
        query = db.fetch_df.call_args[0][0]
        # No WHERE clause when sport not specified
        assert "MLB" not in query and "NBA" not in query

    def test_get_accuracy_summary_with_nfl_filter(self):
        db = self._make_mock_db()
        get_pundit_accuracy_summary(sport="NFL", db=db)
        query = db.fetch_df.call_args[0][0]
        assert "NFL" in query

    def test_get_accuracy_summary_returns_sport_column(self):
        """Verifies sport is in the SELECT clause of the summary query."""
        db = self._make_mock_db()
        get_pundit_accuracy_summary(db=db)
        query = db.fetch_df.call_args[0][0]
        assert "sport" in query.lower()

    def test_get_pending_returns_sport_column(self):
        """Verifies sport is in the SELECT clause of the pending query."""
        db = self._make_mock_db()
        get_pending_predictions(db=db)
        query = db.fetch_df.call_args[0][0]
        assert "sport" in query.lower()

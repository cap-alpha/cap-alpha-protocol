"""
Tests for full article text scraping (Issue #127).
Unit tests — no network access required. All HTTP calls are mocked.
"""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.media_ingestor import (
    MediaItem,
    _enrich_with_full_text,
    _scrape_article_text,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_HTML = """
<html>
<head><title>NFL Trade Analysis</title></head>
<body>
<nav>Navigation stuff</nav>
<article>
<h1>Breaking: Major Trade Prediction</h1>
<p>Adam Schefter predicts the Bears will trade their first-round pick to move up
in the draft. This is a bold prediction that could reshape the NFC North for
years to come. The analysis below breaks down the cap implications.</p>
<p>Looking at the salary cap numbers, Chicago has approximately $35 million in
available space, which gives them flexibility to absorb a large contract in any
trade scenario. Multiple sources confirm discussions are ongoing.</p>
</article>
<footer>Footer stuff</footer>
</body>
</html>
"""

SHORT_HTML = """
<html><body><p>Too short</p></body></html>
"""


def _make_item(source_url="https://example.com/article/1", raw_text="RSS summary"):
    now = datetime.now(timezone.utc)
    return MediaItem(
        content_hash="abc123",
        source_id="test_feed",
        title="Test Article",
        raw_text=raw_text,
        source_url=source_url,
        author="Adam Schefter",
        matched_pundit_id="adam_schefter",
        matched_pundit_name="Adam Schefter",
        published_at=now,
        ingested_at=now,
        content_type="article",
        fetch_source_type="rss",
    )


# ---------------------------------------------------------------------------
# _scrape_article_text
# ---------------------------------------------------------------------------


class TestScrapeArticleText:
    @patch("src.media_ingestor.requests.get")
    def test_extracts_article_text(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _scrape_article_text("https://example.com/article/1")

        assert result is not None
        assert len(result) > 100
        assert "trade" in result.lower() or "prediction" in result.lower()
        mock_get.assert_called_once_with(
            "https://example.com/article/1",
            timeout=15,
            headers={"User-Agent": "PunditLedger/1.0"},
        )

    @patch("src.media_ingestor.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_resp

        result = _scrape_article_text("https://example.com/missing")
        assert result is None

    @patch("src.media_ingestor.requests.get")
    def test_returns_none_on_connection_error(self, mock_get):
        mock_get.side_effect = ConnectionError("Connection refused")

        result = _scrape_article_text("https://example.com/down")
        assert result is None

    @patch("src.media_ingestor.requests.get")
    def test_returns_none_when_text_too_short(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = SHORT_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = _scrape_article_text("https://example.com/short")
        assert result is None

    @patch("src.media_ingestor.requests.get")
    def test_respects_timeout_parameter(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.text = SAMPLE_HTML
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        _scrape_article_text("https://example.com/article", timeout=5)
        mock_get.assert_called_once_with(
            "https://example.com/article",
            timeout=5,
            headers={"User-Agent": "PunditLedger/1.0"},
        )


# ---------------------------------------------------------------------------
# _enrich_with_full_text
# ---------------------------------------------------------------------------


class TestEnrichWithFullText:
    @patch("src.media_ingestor._scrape_article_text")
    def test_replaces_raw_text_when_scrape_succeeds(self, mock_scrape):
        mock_scrape.return_value = (
            "Full article text from the website with enough content."
        )
        item = _make_item(raw_text="Short RSS summary")
        source = {"scrape_full_text": True, "scrape_delay_seconds": 0}

        enriched = _enrich_with_full_text([item], source)

        assert len(enriched) == 1
        assert (
            enriched[0].raw_text
            == "Full article text from the website with enough content."
        )
        mock_scrape.assert_called_once_with(item.source_url)

    @patch("src.media_ingestor._scrape_article_text")
    def test_keeps_original_text_when_scrape_fails(self, mock_scrape):
        mock_scrape.return_value = None
        item = _make_item(raw_text="Original RSS summary")
        source = {"scrape_full_text": True, "scrape_delay_seconds": 0}

        enriched = _enrich_with_full_text([item], source)

        assert len(enriched) == 1
        assert enriched[0].raw_text == "Original RSS summary"

    @patch("src.media_ingestor._scrape_article_text")
    def test_skips_scraping_when_flag_is_false(self, mock_scrape):
        item = _make_item()
        source = {"scrape_full_text": False}

        enriched = _enrich_with_full_text([item], source)

        assert len(enriched) == 1
        assert enriched[0].raw_text == "RSS summary"
        mock_scrape.assert_not_called()

    @patch("src.media_ingestor._scrape_article_text")
    def test_skips_scraping_when_flag_absent(self, mock_scrape):
        item = _make_item()
        source = {"id": "test_feed", "type": "rss"}

        enriched = _enrich_with_full_text([item], source)

        assert len(enriched) == 1
        mock_scrape.assert_not_called()

    @patch("src.media_ingestor.time.sleep")
    @patch("src.media_ingestor._scrape_article_text")
    def test_rate_limiting_between_requests(self, mock_scrape, mock_sleep):
        mock_scrape.return_value = (
            "Full text content that is long enough to pass validation."
        )
        items = [_make_item(source_url=f"https://example.com/{i}") for i in range(3)]
        source = {"scrape_full_text": True, "scrape_delay_seconds": 1.5}

        _enrich_with_full_text(items, source)

        assert mock_scrape.call_count == 3
        # Sleep called between items, not after the last one
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(1.5)

    @patch("src.media_ingestor.time.sleep")
    @patch("src.media_ingestor._scrape_article_text")
    def test_default_delay_is_half_second(self, mock_scrape, mock_sleep):
        mock_scrape.return_value = "Full text content."
        items = [_make_item(source_url=f"https://example.com/{i}") for i in range(2)]
        source = {"scrape_full_text": True}  # no scrape_delay_seconds

        _enrich_with_full_text(items, source)

        mock_sleep.assert_called_once_with(0.5)

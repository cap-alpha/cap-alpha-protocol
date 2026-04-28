"""
Unit tests for url_ingestor.py (Issue #300).
No network or BigQuery access — all HTTP/DB calls are mocked.
"""

import io
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.url_ingestor import discover_articles, fetch_article_text, ingest_from_urls


# ---------------------------------------------------------------------------
# fetch_article_text
# ---------------------------------------------------------------------------


def _make_response(html: str, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    resp.raise_for_status = MagicMock()
    return resp


SIMPLE_HTML = """
<html>
<head>
  <meta name="author" content="Mel Kiper" />
  <meta property="article:published_time" content="2025-04-15T10:00:00Z" />
  <title>2025 NFL Mock Draft</title>
</head>
<body><p>This is a long article about NFL draft picks and prospects.</p></body>
</html>
"""

JSON_LD_HTML = """
<html>
<head>
  <script type="application/ld+json">
  {"@type": "NewsArticle", "author": {"@type": "Person", "name": "Todd McShay"}}
  </script>
</head>
<body><p>Mock draft analysis for 2025.</p></body>
</html>
"""

JSON_LD_LIST_AUTHOR_HTML = """
<html>
<head>
  <script type="application/ld+json">
  {"@type": "NewsArticle", "author": [{"@type": "Person", "name": "Daniel Jeremiah"}]}
  </script>
</head>
<body><p>Draft board rankings for 2025 season.</p></body>
</html>
"""


@patch("src.url_ingestor.requests.get")
def test_fetch_article_text_meta_author(mock_get):
    mock_get.return_value = _make_response(SIMPLE_HTML)
    result = fetch_article_text("https://example.com/draft")
    assert result["author"] == "Mel Kiper"
    assert result["url"] == "https://example.com/draft"
    assert isinstance(result["published_at"], datetime)


@patch("src.url_ingestor.requests.get")
def test_fetch_article_text_json_ld_dict_author(mock_get):
    mock_get.return_value = _make_response(JSON_LD_HTML)
    result = fetch_article_text("https://example.com/mcshay")
    assert result["author"] == "Todd McShay"


@patch("src.url_ingestor.requests.get")
def test_fetch_article_text_json_ld_list_author(mock_get):
    mock_get.return_value = _make_response(JSON_LD_LIST_AUTHOR_HTML)
    result = fetch_article_text("https://example.com/jeremiah")
    assert result["author"] == "Daniel Jeremiah"


@patch("src.url_ingestor.requests.get")
def test_fetch_article_text_no_author(mock_get):
    mock_get.return_value = _make_response(
        "<html><body><p>Some article without author info.</p></body></html>"
    )
    result = fetch_article_text("https://example.com/noauthor")
    assert result["author"] is None


# ---------------------------------------------------------------------------
# discover_articles — empty YAML safe_load
# ---------------------------------------------------------------------------


def test_discover_articles_empty_yaml(tmp_path):
    """yaml.safe_load returns None for empty file — must not raise."""
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("")

    with patch("src.url_ingestor.DDGS") as mock_ddgs:
        mock_ddgs.return_value.__enter__.return_value.text.return_value = []
        result = discover_articles(config_path=str(config_file))

    assert result == []


def test_discover_articles_filters_by_keyword(tmp_path):
    """Articles without draft/mock/pick/prediction/prospect in title are excluded."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text("search_queries:\n  - nfl draft 2025\n")

    search_results = [
        {"href": "https://example.com/a", "title": "NFL Mock Draft 2025 top picks"},
        {"href": "https://example.com/b", "title": "Unrelated sports news story"},
    ]

    with (
        patch("src.url_ingestor.DDGS") as mock_ddgs,
        patch("src.url_ingestor.time.sleep"),
    ):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = search_results
        result = discover_articles(config_path=str(config_file))

    assert len(result) == 1
    assert result[0]["url"] == "https://example.com/a"


def test_discover_articles_deduplicates_urls(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "search_queries:\n  - nfl draft 2025\n  - mock draft picks\n"
    )

    same_result = [{"href": "https://example.com/draft", "title": "NFL Mock Draft"}]

    with (
        patch("src.url_ingestor.DDGS") as mock_ddgs,
        patch("src.url_ingestor.time.sleep"),
    ):
        mock_ddgs.return_value.__enter__.return_value.text.return_value = same_result
        result = discover_articles(config_path=str(config_file))

    assert len(result) == 1


# ---------------------------------------------------------------------------
# ingest_from_urls — nullable columns preserved as NULL, not "None"
# ---------------------------------------------------------------------------


@patch("src.url_ingestor.fetch_article_text")
def test_ingest_nullable_cols_not_string_none(mock_fetch):
    """matched_pundit_id / matched_pundit_name must be pd.NA, not 'None', after astype('string')."""
    mock_fetch.return_value = {
        "title": "2025 NFL Draft Preview",
        "text": "A" * 200,
        "author": None,
        "published_at": None,
        "url": "https://example.com/draft",
    }

    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()

    captured_df = {}

    def capture_df(df, table):
        captured_df["df"] = df.copy()

    db.append_dataframe_to_table.side_effect = capture_df

    url_configs = [
        {
            "url": "https://example.com/draft",
            "source_id": "web_search",
            # no pundit_name / pundit_id — should be NULL
        }
    ]

    ingest_from_urls(url_configs, db)

    df = captured_df["df"]
    assert "matched_pundit_id" in df.columns
    assert "matched_pundit_name" in df.columns

    # Values must be NA, not the string "None"
    assert df["matched_pundit_id"].dtype == pd.StringDtype()
    assert pd.isna(df["matched_pundit_id"].iloc[0])
    assert pd.isna(df["matched_pundit_name"].iloc[0])


@patch("src.url_ingestor.fetch_article_text")
def test_ingest_dry_run_skips_db(mock_fetch):
    mock_fetch.return_value = {
        "title": "Mock Draft 2025",
        "text": "B" * 200,
        "author": "Mel Kiper",
        "published_at": None,
        "url": "https://example.com/mock",
    }

    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()

    result = ingest_from_urls(
        [{"url": "https://example.com/mock", "source_id": "espn"}], db, dry_run=True
    )

    db.append_dataframe_to_table.assert_not_called()
    assert result["new"] == 1


@patch("src.url_ingestor.fetch_article_text")
def test_ingest_dedup_skips_existing_hash(mock_fetch):
    from src.media_ingestor import compute_content_hash

    url = "https://example.com/existing"
    title = "Existing Draft Article"
    existing_hash = compute_content_hash(url, title)

    mock_fetch.return_value = {
        "title": title,
        "text": "C" * 200,
        "author": "Todd McShay",
        "published_at": None,
        "url": url,
    }

    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame({"content_hash": [existing_hash]})

    result = ingest_from_urls([{"url": url, "source_id": "espn"}], db)

    db.append_dataframe_to_table.assert_not_called()
    assert result["skipped"] == 1
    assert result["new"] == 0


@patch("src.url_ingestor.fetch_article_text")
def test_ingest_short_article_skipped(mock_fetch):
    mock_fetch.return_value = {
        "title": "Short Article",
        "text": "Too short",
        "author": None,
        "published_at": None,
        "url": "https://example.com/short",
    }

    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()

    result = ingest_from_urls(
        [{"url": "https://example.com/short", "source_id": "web"}], db
    )

    db.append_dataframe_to_table.assert_not_called()
    assert result["skipped"] == 1


@patch("src.url_ingestor.fetch_article_text")
def test_ingest_fetch_error_counted(mock_fetch):
    mock_fetch.side_effect = Exception("connection refused")

    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()

    result = ingest_from_urls(
        [{"url": "https://example.com/bad", "source_id": "web"}], db
    )

    assert result["errors"] == 1
    assert result["new"] == 0


# ---------------------------------------------------------------------------
# fetch_source_type — must be web_scrape (not url_seed)
# ---------------------------------------------------------------------------


@patch("src.url_ingestor.fetch_article_text")
def test_ingest_fetch_source_type_is_web_scrape(mock_fetch):
    mock_fetch.return_value = {
        "title": "NFL Draft Predictions 2025",
        "text": "D" * 200,
        "author": "Adam Schefter",
        "published_at": None,
        "url": "https://example.com/preds",
    }

    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()

    captured_df = {}

    def capture_df(df, table):
        captured_df["df"] = df.copy()

    db.append_dataframe_to_table.side_effect = capture_df

    ingest_from_urls([{"url": "https://example.com/preds", "source_id": "espn"}], db)

    df = captured_df["df"]
    assert df["fetch_source_type"].iloc[0] == "web_scrape"

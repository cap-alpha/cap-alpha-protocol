"""
Tests for post_event_filter.py (Issue #996).

Covers:
  - URL-pattern detection: draft-tracker, live-draft-grades, pick-N slugs
  - Title-pattern detection: "<Team> selects/drafts/picks <Player>"
  - Date-window guard: published after known event close, source-scoped
  - Combined short-circuit (URL match trumps other checks)
  - False-positive guard: normal prediction articles must NOT fire

Unit tests — no BigQuery, no LLM calls required.
"""

from datetime import datetime, timezone

import pytest

from src.post_event_filter import (
    _matches_date_window,
    _matches_title_pattern,
    _matches_url_pattern,
    is_post_event_article,
)


# ---------------------------------------------------------------------------
# Layer 1 — URL patterns
# ---------------------------------------------------------------------------


class TestUrlPatterns:
    def test_draft_tracker_url(self):
        assert _matches_url_pattern(
            "https://profootballtalk.nbcsports.com/2026/04/24/live-draft-tracker-2026/"
        )

    def test_live_draft_grades_url(self):
        assert _matches_url_pattern(
            "https://www.nfl.com/news/live-draft-grades-2026-nfl-draft"
        )

    def test_athletic_pick_n_url(self):
        assert _matches_url_pattern(
            "https://theathletic.com/chiefs-nfl-draft-pick-32-2026/"
        )

    def test_athletic_pick_n_url_large_number(self):
        assert _matches_url_pattern(
            "https://theathletic.com/bears-nfl-draft-pick-257-2025/"
        )

    def test_draft_results_url(self):
        assert _matches_url_pattern(
            "https://www.espn.com/nfl/story/_/id/123/2026-nfl-draft-results-all-picks"
        )

    def test_selected_by_slug(self):
        assert _matches_url_pattern(
            "https://theathletic.com/travis-hunter-selected-by-jaguars-2026/"
        )

    def test_nfl_draft_grades_slug(self):
        assert _matches_url_pattern(
            "https://bleacherreport.com/articles/nfl-draft-grades-2026-every-team"
        )

    def test_live_draft_generic(self):
        assert _matches_url_pattern(
            "https://si.com/nfl/2026/04/24/live-draft-updates-round-1"
        )

    # Negative cases — normal prediction articles
    def test_normal_prediction_article(self):
        assert not _matches_url_pattern(
            "https://www.espn.com/nfl/story/_/id/999/who-will-win-super-bowl-2026"
        )

    def test_normal_mock_draft_article(self):
        # Mock draft analysis BEFORE the event is not a post-event report
        assert not _matches_url_pattern(
            "https://theathletic.com/2026-nfl-mock-draft-mel-kiper-projections/"
        )

    def test_normal_free_agency_prediction(self):
        assert not _matches_url_pattern(
            "https://pff.com/news/nfl-free-agency-2026-best-available-players"
        )

    def test_case_insensitive(self):
        assert _matches_url_pattern("https://example.com/DRAFT-TRACKER-2026-LIVE")


# ---------------------------------------------------------------------------
# Layer 2 — Title patterns
# ---------------------------------------------------------------------------


class TestTitlePatterns:
    # Positive cases
    def test_city_selects(self):
        assert _matches_title_pattern("Kansas City selects Travis Hunter with pick 32")

    def test_nickname_drafts(self):
        assert _matches_title_pattern("Eagles draft Tetairoa McMillan in Round 1")

    def test_city_picks(self):
        assert _matches_title_pattern("Buffalo picks Shedeur Sanders at No. 5")

    def test_city_takes(self):
        assert _matches_title_pattern("Seattle takes offensive tackle in Round 2")

    def test_past_tense_selected(self):
        assert _matches_title_pattern("Dallas selected cornerback Josh Simmons")

    def test_past_tense_drafted(self):
        assert _matches_title_pattern("New England drafted their future franchise QB")

    def test_past_tense_chose(self):
        assert _matches_title_pattern("San Francisco chose pass rusher with first pick")

    def test_multi_word_city(self):
        assert _matches_title_pattern(
            "New Orleans selects wide receiver in second round"
        )

    def test_nickname_only_chiefs(self):
        assert _matches_title_pattern("Chiefs select Travis Hunter")

    def test_nickname_49ers(self):
        assert _matches_title_pattern("49ers draft first-round linebacker")

    # Negative cases
    def test_prediction_article(self):
        assert not _matches_title_pattern(
            "Who will the Chiefs select with the 5th overall pick?"
        )

    def test_mock_draft_headline(self):
        assert not _matches_title_pattern(
            "2026 NFL Mock Draft: Mel Kiper's latest three-round projections"
        )

    def test_analysis_headline(self):
        assert not _matches_title_pattern(
            "Breaking down Seattle's options in the first round"
        )

    def test_rumor_headline(self):
        assert not _matches_title_pattern(
            "Patriots reportedly interested in trading up for QB"
        )

    def test_player_signed_headline(self):
        # "signed" is not one of the pick verbs
        assert not _matches_title_pattern("Cowboys signed wide receiver Davante Adams")

    def test_title_none_returns_false(self):
        # Called with None title — layer skips cleanly
        assert not _matches_title_pattern("")

    def test_case_insensitive_verb(self):
        assert _matches_title_pattern("SEAHAWKS SELECTS QB in first round")


# ---------------------------------------------------------------------------
# Layer 3 — Date-window guard
# ---------------------------------------------------------------------------


class TestDateWindowGuard:
    # ── 2026 NFL Draft window ──────────────────────────────────────────────
    def test_published_day_after_2026_draft_close(self):
        """Published April 26 2026 (day draft ended) — inside window."""
        dt = datetime(2026, 4, 26, 12, 0, tzinfo=timezone.utc)
        assert _matches_date_window(dt, source_id="pft_staff")

    def test_published_week_after_2026_draft(self):
        dt = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
        assert _matches_date_window(dt, source_id="athletic_nfl_staff")

    def test_published_at_2026_draft_close_boundary(self):
        """Exactly at event_close (2026-04-26 00:00 UTC) — inside window."""
        dt = datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc)
        assert _matches_date_window(dt, source_id="pft_staff")

    def test_published_just_before_2026_draft_close(self):
        """1 second before event_close — should NOT fire (pre-event)."""
        dt = datetime(2026, 4, 25, 23, 59, 59, tzinfo=timezone.utc)
        assert not _matches_date_window(dt, source_id="pft_staff")

    def test_published_past_2026_window_end(self):
        """After window_end (May 17 2026) — suppression lifted."""
        dt = datetime(2026, 5, 18, 0, 0, tzinfo=timezone.utc)
        assert not _matches_date_window(dt, source_id="pft_staff")

    # ── 2025 NFL Draft window ──────────────────────────────────────────────
    def test_published_day_after_2025_draft_close(self):
        dt = datetime(2025, 4, 28, 0, 0, tzinfo=timezone.utc)
        assert _matches_date_window(dt, source_id="pft_staff")

    # ── Source-scoping ─────────────────────────────────────────────────────
    def test_non_tracker_source_not_flagged(self):
        """An editorial source (e.g. profootball_focus) should NOT trigger date guard."""
        dt = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
        assert not _matches_date_window(dt, source_id="profootball_focus")

    def test_none_source_id_not_flagged(self):
        """source_id=None means unknown source — date guard skips."""
        dt = datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc)
        assert not _matches_date_window(dt, source_id=None)

    def test_none_published_at_returns_false(self):
        assert not _matches_date_window(None, source_id="pft_staff")

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetimes (no tzinfo) should be treated as UTC."""
        dt = datetime(2026, 4, 26, 12, 0)  # no tzinfo
        assert _matches_date_window(dt, source_id="pft_staff")


# ---------------------------------------------------------------------------
# Public API: is_post_event_article
# ---------------------------------------------------------------------------


class TestIsPostEventArticle:
    # ── Short-circuit on URL ───────────────────────────────────────────────
    def test_url_match_short_circuits(self):
        result = is_post_event_article(
            url="https://profootballtalk.nbcsports.com/live-draft-tracker/",
            title="Who will the Bears pick?",  # prediction-style title
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),  # outside windows
        )
        assert result is True

    # ── Title match ────────────────────────────────────────────────────────
    def test_title_match_fires_when_url_clean(self):
        result = is_post_event_article(
            url="https://theathletic.com/nfl-draft-2026-recap/",
            title="Seahawks select Travis Hunter with pick 5",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        assert result is True

    # ── Date-window match ──────────────────────────────────────────────────
    def test_date_window_fires_when_url_and_title_clean(self):
        result = is_post_event_article(
            url="https://pft.nbcsports.com/2026/04/27/colts-sign-edge-rusher/",
            title="Colts sign edge rusher in free agency",
            published_at=datetime(2026, 4, 27, 0, 0, tzinfo=timezone.utc),
            source_id="pft_staff",
        )
        assert result is True

    # ── False positives ────────────────────────────────────────────────────
    def test_clean_prediction_article_not_flagged(self):
        result = is_post_event_article(
            url="https://www.espn.com/nfl/story/_/id/999/super-bowl-predictions-2026",
            title="Super Bowl 2026 predictions: Who wins it all?",
            published_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
            source_id="espn_nfl",
        )
        assert result is False

    def test_mock_draft_analysis_not_flagged(self):
        result = is_post_event_article(
            url="https://theathletic.com/2026-nfl-mock-draft-two-round-projection/",
            title="2026 NFL Mock Draft: Full two-round projection",
            published_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
            source_id="athletic_nfl_staff",
        )
        assert result is False

    def test_rumor_article_not_flagged(self):
        result = is_post_event_article(
            url="https://pft.nbcsports.com/2026/03/01/patriots-reportedly-targeting-qb/",
            title="Patriots reportedly targeting QB in free agency",
            published_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
            source_id="pft_staff",
        )
        assert result is False

    # ── None / missing optional args ───────────────────────────────────────
    def test_no_title_no_date(self):
        """Minimal call — only URL check runs."""
        result = is_post_event_article(
            url="https://espn.com/nfl/preview-2026",
        )
        assert result is False

    def test_post_event_url_with_no_title_or_date(self):
        result = is_post_event_article(
            url="https://example.com/nfl-draft-grades-2026/",
        )
        assert result is True


# ---------------------------------------------------------------------------
# Integration: assertion_extractor SQL contains post-event filter
# ---------------------------------------------------------------------------


class TestExtractorSqlFilter:
    """Ensure get_unprocessed_media queries include the is_post_event guard.

    This test verifies the SQL string built by get_unprocessed_media, not a
    real BigQuery call.  No LLM call required.
    """

    def test_primary_query_excludes_post_event(self):
        """Primary query must filter out is_post_event = TRUE rows."""
        from unittest.mock import MagicMock

        import pandas as pd

        from src.assertion_extractor import get_unprocessed_media

        mock_db = MagicMock()
        mock_db.fetch_df.return_value = pd.DataFrame()

        get_unprocessed_media(mock_db, limit=10)

        query = mock_db.fetch_df.call_args[0][0]
        # Both forms acceptable: IS NULL OR = FALSE, or NOT TRUE
        assert "is_post_event" in query.lower(), (
            "Primary extraction query must reference is_post_event column"
        )

    def test_fallback_query_excludes_post_event(self):
        """Fallback query (no tracking table) must also filter post-event rows."""
        from unittest.mock import MagicMock

        import pandas as pd
        from google.api_core.exceptions import NotFound

        from src.assertion_extractor import get_unprocessed_media

        mock_db = MagicMock()
        mock_db.fetch_df.side_effect = [
            NotFound("processed_media_hashes"),
            pd.DataFrame(),
        ]

        get_unprocessed_media(mock_db, limit=10)

        fallback_query = mock_db.fetch_df.call_args_list[1][0][0]
        assert "is_post_event" in fallback_query.lower(), (
            "Fallback extraction query must reference is_post_event column"
        )

"""
Post-Event Article Filter (Issue #996)

Heuristic classifier that detects articles describing events that have already
completed — e.g. "Seahawks select <Player> with the 5th overall pick" published
after the NFL Draft ended.

The LLM extraction layer treats these as forward-looking predictions, silently
contaminating the Pundit Prediction Ledger with 100% report-of-fact rows that
can never be falsified (they already happened).

Three detection layers, applied in order:
    1. URL-pattern matching  — draft tracker slugs, live-grades URLs, pick-N slugs
    2. Title-pattern matching — "<Team> selects/drafts/picks <Player>"
    3. Date-window guard     — article published after a known event-close timestamp

Usage::

    from src.post_event_filter import is_post_event_article

    flagged = is_post_event_article(
        url="https://theathletic.com/chiefs-nfl-draft-pick-5-2026/",
        title="Chiefs select Shedeur Sanders at pick 5",
        published_at=datetime(2026, 4, 24, tzinfo=timezone.utc),
    )
    # → True
"""

import re
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Layer 1 — URL patterns
# ---------------------------------------------------------------------------

# Slugs that reliably appear in post-event draft-tracker / live-blog articles.
# Each pattern is tested against LOWER(url).
_URL_PATTERNS: list[re.Pattern] = [
    re.compile(r"draft-tracker"),
    re.compile(r"live-draft-grades"),
    re.compile(r"live-draft"),
    re.compile(r"-nfl-draft-pick-\d+"),
    re.compile(r"draft-results"),
    re.compile(r"-selected-by-"),
    re.compile(r"nfl-draft-grades"),
    re.compile(r"draft-order-by-pick"),
]


def _matches_url_pattern(url: str) -> bool:
    """Return True if any URL pattern fires."""
    lowered = url.lower()
    return any(p.search(lowered) for p in _URL_PATTERNS)


# ---------------------------------------------------------------------------
# Layer 2 — Title patterns
# ---------------------------------------------------------------------------

# NFL franchise city / nickname prefixes (both forms accepted).
_TEAM_PREFIXES = (
    "arizona",
    "atlanta",
    "baltimore",
    "buffalo",
    "carolina",
    "chicago",
    "cincinnati",
    "cleveland",
    "dallas",
    "denver",
    "detroit",
    "green bay",
    "houston",
    "indianapolis",
    "jacksonville",
    "kansas city",
    "las vegas",
    "los angeles",
    "miami",
    "minnesota",
    "new england",
    "new orleans",
    "new york",
    "philadelphia",
    "pittsburgh",
    "san francisco",
    "seattle",
    "tampa bay",
    "tennessee",
    "washington",
    # Nickname-only forms that commonly appear as title starters
    "cardinals",
    "falcons",
    "ravens",
    "bills",
    "panthers",
    "bears",
    "bengals",
    "browns",
    "cowboys",
    "broncos",
    "lions",
    "packers",
    "texans",
    "colts",
    "jaguars",
    "chiefs",
    "raiders",
    "rams",
    "chargers",
    "dolphins",
    "vikings",
    "patriots",
    "saints",
    "giants",
    "jets",
    "eagles",
    "steelers",
    "49ers",
    "seahawks",
    "buccaneers",
    "titans",
    "commanders",
)

# Past-tense or present-tense pick verbs that indicate a completed action.
_PICK_VERBS = (
    "selects",
    "select",
    "selected",
    "drafts",
    "draft",
    "drafted",
    "picks",
    "pick",
    "picked",
    "takes",
    "take",
    "took",
    "chooses",
    "choose",
    "chose",
)

# Build a compiled regex: ^(team ...) (verb) \b
_TEAM_PATTERN = "|".join(
    re.escape(t) for t in sorted(_TEAM_PREFIXES, key=len, reverse=True)
)
_VERB_PATTERN = "|".join(re.escape(v) for v in _PICK_VERBS)
_TITLE_RE = re.compile(
    rf"^(?:{_TEAM_PATTERN})\b.{{0,40}}\b(?:{_VERB_PATTERN})\b",
    re.IGNORECASE,
)


def _matches_title_pattern(title: str) -> bool:
    """Return True if the title looks like a team-selection announcement."""
    return bool(_TITLE_RE.match(title.strip()))


# ---------------------------------------------------------------------------
# Layer 3 — Date-window guard
# ---------------------------------------------------------------------------

# Known event windows: (event_name, event_close_utc, window_end_utc)
# The guard fires when:
#   event_close_utc <= published_at < window_end_utc
#
# window_end_utc is set conservatively (3 weeks after the event) to catch
# retroactive analysis pieces that still describe completed actions.
_EVENT_WINDOWS: list[tuple[str, datetime, datetime]] = [
    # 2025 NFL Draft — Cleveland, April 24-26 2025
    (
        "nfl_draft_2025",
        datetime(2025, 4, 27, 0, 0, tzinfo=timezone.utc),
        datetime(2025, 5, 18, 0, 0, tzinfo=timezone.utc),
    ),
    # 2026 NFL Draft — Green Bay, April 23-25 2026
    (
        "nfl_draft_2026",
        datetime(2026, 4, 26, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 17, 0, 0, tzinfo=timezone.utc),
    ),
    # 2025 NFL Free Agency window (opened March 12, wire requests / confirmed signings)
    (
        "nfl_free_agency_2025",
        datetime(2025, 3, 12, 16, 0, tzinfo=timezone.utc),  # 12:00 ET = 16:00 UTC
        datetime(2025, 4, 1, 0, 0, tzinfo=timezone.utc),
    ),
    # 2026 NFL Free Agency window
    (
        "nfl_free_agency_2026",
        datetime(2026, 3, 11, 16, 0, tzinfo=timezone.utc),
        datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
    ),
]

# Source IDs known to publish live-tracker / wire-report content during events.
# Only these sources trigger the date-window guard to avoid false positives on
# editorial sources that write analysis after events.
_DATE_GUARD_SOURCE_IDS: frozenset[str] = frozenset(
    [
        "pft_staff",
        "athletic_nfl_staff",
        "nfl_com_news",
        "nfl_transactions",
    ]
)


def _matches_date_window(
    published_at: Optional[datetime], source_id: Optional[str] = None
) -> bool:
    """Return True if published_at falls inside a post-event suppression window.

    Only fires when source_id is in the known live-tracker source list to avoid
    over-suppressing editorial analysis that legitimately discusses completed events.
    """
    if published_at is None:
        return False
    # Date-window guard is source-scoped: only fire for known live-tracker source IDs.
    # If source_id is None (unknown) or not in the allowlist, skip this guard entirely
    # to avoid over-suppressing editorial content from unrecognised sources.
    if not source_id or source_id not in _DATE_GUARD_SOURCE_IDS:
        return False
    # Ensure timezone-aware comparison
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    for _name, event_close, window_end in _EVENT_WINDOWS:
        if event_close <= published_at < window_end:
            return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_post_event_article(
    url: str,
    title: Optional[str] = None,
    published_at: Optional[datetime] = None,
    source_id: Optional[str] = None,
) -> bool:
    """Return True if the article is a post-event report, not a forward-looking prediction.

    Checks are applied in cheapest-first order and short-circuit on the first match:
      1. URL-pattern heuristic (regex on slug, O(k) where k = # patterns)
      2. Title-pattern heuristic ("<Team> selects/drafts/picks ...")
      3. Date-window guard (published after known event close, for tracker sources only)

    Args:
        url:          Canonical article URL (required).
        title:        Article headline (optional; layer 2 skipped if None).
        published_at: Publication timestamp (optional; layer 3 skipped if None).
        source_id:    Source identifier from media_sources.yaml (optional; scopes layer 3).

    Returns:
        True  → article should be tagged is_post_event=TRUE and skipped by the extractor.
        False → treat as normal forward-looking content.
    """
    # Layer 1 — URL patterns (fastest, no external data needed)
    if _matches_url_pattern(url):
        return True

    # Layer 2 — Title patterns
    if title and _matches_title_pattern(title):
        return True

    # Layer 3 — Date-window guard (source-scoped)
    if _matches_date_window(published_at, source_id=source_id):
        return True

    return False

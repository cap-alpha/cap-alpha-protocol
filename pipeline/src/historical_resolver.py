"""
Historical Auto-Resolver — score 2020-2024 archived predictions against
public ground-truth data.

Complements `resolve_daily.py`. Where `resolve_daily.py` covers the recent
SportsDataIO-backed cases (draft, game outcomes, player season stats),
this module adds resolvers for categories where the answers live on
Pro-Football-Reference (PFR):

  1. Win totals / season records  (PFR /years/YYYY/)
  2. Playoff predictions          (division winner, conference champ, SB)
  3. Award winners                (MVP, OPOY, DPOY, OROY, DROY, CPOY, COY)
  4. Draft pick predictions       (extends draft logic from resolve_daily)
  5. Statistical milestones       (PFR /years/YYYY/passing.htm etc.)
  6. Trades / signings happen     (boolean transaction check)

Design principles:
  - **Cache aggressively**: each PFR page is fetched at most once per process,
    so 100 predictions for the same season hit the network ~7 times total.
  - **LLM judge as fallback**: ambiguous prediction text is sent to the local
    Ollama model with a structured "did this prediction come true?" prompt.
  - **Always cite**: no resolution lands without an evidence URL.
  - **Confidence floor**: anything below 0.8 confidence is recorded as
    `unresolvable` (mapped to VOID in the existing schema) with a reason.

CLI:
    python -m src.historical_resolver --season 2024 --batch-size 100
    python -m src.historical_resolver --season 2023 --category awards
    python -m src.historical_resolver --season 2024 --dry-run --sample 50
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, Callable, Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass
class ResolutionResult:
    """Per-prediction resolution returned by category resolvers.

    `outcome` semantics:
      - "correct"      — prediction matched reality
      - "incorrect"    — prediction did not match reality
      - "partial"      — partly right (e.g. team made playoffs but lost in WC)
      - "unresolvable" — couldn't determine confidently; needs manual review
    """

    outcome: str  # correct | incorrect | partial | unresolvable
    evidence_url: Optional[str] = None
    confidence: float = 0.0
    notes: str = ""
    evidence_quote: str = ""
    extra: dict = field(default_factory=dict)


CONFIDENCE_FLOOR = 0.8


# ---------------------------------------------------------------------------
# Team aliases (long → PFR abbreviation)
# ---------------------------------------------------------------------------

# PFR uses some abbreviations that differ from SportsDataIO:
#   LV  → "LVR" historically but currently "LVR"/"OAK" pre-2020. PFR uses the
#   franchise's most-recent abbr inside one season. We normalise against both.

PFR_TEAM_ALIASES: dict[str, str] = {
    "chiefs": "KAN",
    "kansas city": "KAN",
    "eagles": "PHI",
    "philadelphia": "PHI",
    "cowboys": "DAL",
    "dallas": "DAL",
    "patriots": "NWE",
    "new england": "NWE",
    "bills": "BUF",
    "buffalo": "BUF",
    "ravens": "BAL",
    "baltimore": "BAL",
    "49ers": "SFO",
    "san francisco": "SFO",
    "niners": "SFO",
    "lions": "DET",
    "detroit": "DET",
    "bears": "CHI",
    "chicago": "CHI",
    "bengals": "CIN",
    "cincinnati": "CIN",
    "browns": "CLE",
    "cleveland": "CLE",
    "broncos": "DEN",
    "denver": "DEN",
    "texans": "HOU",
    "houston": "HOU",
    "colts": "IND",
    "indianapolis": "IND",
    "jaguars": "JAX",
    "jacksonville": "JAX",
    "jags": "JAX",
    "titans": "TEN",
    "tennessee": "TEN",
    "raiders": "LVR",
    "las vegas": "LVR",
    "oakland": "OAK",
    "chargers": "LAC",
    "los angeles chargers": "LAC",
    "rams": "LAR",
    "los angeles rams": "LAR",
    "dolphins": "MIA",
    "miami": "MIA",
    "vikings": "MIN",
    "minnesota": "MIN",
    "giants": "NYG",
    "new york giants": "NYG",
    "jets": "NYJ",
    "new york jets": "NYJ",
    "steelers": "PIT",
    "pittsburgh": "PIT",
    "seahawks": "SEA",
    "seattle": "SEA",
    "buccaneers": "TAM",
    "tampa bay": "TAM",
    "bucs": "TAM",
    "commanders": "WAS",
    "washington": "WAS",
    "redskins": "WAS",
    "falcons": "ATL",
    "atlanta": "ATL",
    "panthers": "CAR",
    "carolina": "CAR",
    "saints": "NOR",
    "new orleans": "NOR",
    "cardinals": "CRD",
    "arizona": "CRD",
    "packers": "GNB",
    "green bay": "GNB",
}

# Reverse map for display
PFR_ABBR_TO_LABEL = {
    "KAN": "Kansas City Chiefs",
    "PHI": "Philadelphia Eagles",
    "DAL": "Dallas Cowboys",
    "NWE": "New England Patriots",
    "BUF": "Buffalo Bills",
    "BAL": "Baltimore Ravens",
    "SFO": "San Francisco 49ers",
    "DET": "Detroit Lions",
    "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "DEN": "Denver Broncos",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "TEN": "Tennessee Titans",
    "LVR": "Las Vegas Raiders",
    "OAK": "Oakland Raiders",
    "LAC": "Los Angeles Chargers",
    "LAR": "Los Angeles Rams",
    "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings",
    "NYG": "New York Giants",
    "NYJ": "New York Jets",
    "PIT": "Pittsburgh Steelers",
    "SEA": "Seattle Seahawks",
    "TAM": "Tampa Bay Buccaneers",
    "WAS": "Washington Commanders",
    "ATL": "Atlanta Falcons",
    "CAR": "Carolina Panthers",
    "NOR": "New Orleans Saints",
    "CRD": "Arizona Cardinals",
    "GNB": "Green Bay Packers",
}


def normalize_team_to_pfr(text: str) -> Optional[str]:
    """Map a team name/nickname to its PFR abbreviation."""
    if not text:
        return None
    s = text.lower().strip()
    # Sort by length so longer aliases ("los angeles rams") match before "rams"
    for alias in sorted(PFR_TEAM_ALIASES, key=len, reverse=True):
        if alias in s:
            return PFR_TEAM_ALIASES[alias]
    if 2 <= len(s) <= 3:
        return s.upper()
    return None


def _normalize_name(name: str) -> str:
    name = (name or "").lower().strip()
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    name = name.replace(".", "")
    return name


# ---------------------------------------------------------------------------
# PFR fetch + cache
# ---------------------------------------------------------------------------

PFR_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# In-memory cache across one process — keyed by URL.
_PAGE_CACHE: dict[str, str] = {}
_RATE_LIMIT_SEC = 3.5  # PFR is touchy; be polite.
_LAST_FETCH_TS = 0.0


def _fetch_pfr_page(url: str, force_refresh: bool = False) -> str:
    """Fetch a PFR page with rate-limiting + in-memory cache."""
    global _LAST_FETCH_TS
    if not force_refresh and url in _PAGE_CACHE:
        return _PAGE_CACHE[url]

    import requests

    now = time.time()
    elapsed = now - _LAST_FETCH_TS
    if elapsed < _RATE_LIMIT_SEC:
        time.sleep(_RATE_LIMIT_SEC - elapsed)

    logger.info(f"GET {url}")
    resp = requests.get(url, headers=PFR_HEADERS, timeout=30)
    _LAST_FETCH_TS = time.time()
    resp.raise_for_status()
    _PAGE_CACHE[url] = resp.text
    return resp.text


def _parse_pfr_tables(html: str) -> dict[str, pd.DataFrame]:
    """Extract all tables (including comment-wrapped ones) keyed by id."""
    from bs4 import BeautifulSoup, Comment

    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, pd.DataFrame] = {}

    for tbl in soup.find_all("table"):
        tid = tbl.get("id") or f"_anon_{len(out)}"
        try:
            df = pd.read_html(StringIO(str(tbl)), flavor="bs4")[0]
            out[tid] = df
        except (ValueError, ImportError):
            continue

    # PFR hides many tables inside HTML comments to deter scrapers
    for c in soup.find_all(string=lambda x: isinstance(x, Comment)):
        if "<table" not in c:
            continue
        sub = BeautifulSoup(c, "html.parser")
        for tbl in sub.find_all("table"):
            tid = tbl.get("id") or f"_comment_{len(out)}"
            try:
                df = pd.read_html(StringIO(str(tbl)), flavor="bs4")[0]
                out[tid] = df
            except (ValueError, ImportError):
                continue
    return out


# ---------------------------------------------------------------------------
# Season facts loader (one-shot per season)
# ---------------------------------------------------------------------------


@dataclass
class SeasonFacts:
    """All the public facts we extract once per season."""

    season: int
    standings_url: str
    standings: pd.DataFrame  # team, wins, losses, ties, division
    playoff_teams: set[str]
    division_winners: dict[str, str]  # division -> team
    super_bowl_winner: Optional[str] = None
    conference_champs: dict[str, str] = field(default_factory=dict)  # AFC/NFC -> team
    awards: dict[str, str] = field(default_factory=dict)  # award -> player
    awards_url: Optional[str] = None


_SEASON_CACHE: dict[int, SeasonFacts] = {}


def load_season_facts(season: int) -> SeasonFacts:
    """Fetch + parse the canonical PFR season page once per season."""
    if season in _SEASON_CACHE:
        return _SEASON_CACHE[season]

    url = f"https://www.pro-football-reference.com/years/{season}/"
    html = _fetch_pfr_page(url)
    tables = _parse_pfr_tables(html)

    # Standings tables on PFR season page are id="AFC" and "NFC"
    standings_rows: list[dict[str, Any]] = []
    division_winners: dict[str, str] = {}

    for conf_id in ("AFC", "NFC"):
        df = tables.get(conf_id)
        if df is None or df.empty:
            continue
        # Columns vary: "Tm", "W", "L", "T"; division names appear as
        # rows where Tm == "AFC East" / "NFC West" etc.
        # Identify division: the first column contains both division
        # headers (no W/L) and team rows.
        first_col = df.columns[0]
        try:
            wins_col = "W"
            losses_col = "L"
            ties_col = "T" if "T" in df.columns else None
        except Exception:
            continue

        current_division: Optional[str] = None
        best_in_division: Optional[tuple[str, int]] = None

        for _, row in df.iterrows():
            label = str(row[first_col]).strip()
            w_raw = row.get(wins_col, "")
            try:
                w = int(float(w_raw))
            except (TypeError, ValueError):
                # Division header row (no numeric wins)
                if best_in_division is not None and current_division is not None:
                    division_winners[current_division] = best_in_division[0]
                current_division = label
                best_in_division = None
                continue
            l_ = int(float(row.get(losses_col, 0) or 0))
            t_ = int(float(row.get(ties_col, 0) or 0)) if ties_col else 0
            # Strip trailing markers like "*" (division winner) and "+" (playoff).
            playoff_marker = label.endswith("*") or label.endswith("+")
            clean_label = re.sub(r"[\*\+\^]+$", "", label).strip()
            standings_rows.append(
                {
                    "team_label": clean_label,
                    "team_pfr": normalize_team_to_pfr(clean_label),
                    "conference": conf_id,
                    "division": current_division,
                    "wins": w,
                    "losses": l_,
                    "ties": t_,
                    "made_playoffs": playoff_marker or label.endswith("*"),
                }
            )
            if best_in_division is None or w > best_in_division[1]:
                best_in_division = (clean_label, w)

        if best_in_division is not None and current_division is not None:
            division_winners.setdefault(current_division, best_in_division[0])

    standings_df = pd.DataFrame(standings_rows)
    playoff_teams = set(
        standings_df.loc[standings_df["made_playoffs"], "team_label"].dropna().tolist()
    )

    facts = SeasonFacts(
        season=season,
        standings_url=url,
        standings=standings_df,
        playoff_teams=playoff_teams,
        division_winners=division_winners,
    )

    # Pull SB winner + conference champs from the playoff bracket table
    # Table id varies across years; fall back to scanning headings.
    sb_winner, conf_champs = _extract_playoff_results(html)
    facts.super_bowl_winner = sb_winner
    facts.conference_champs = conf_champs

    # Awards live on a dedicated page per season.
    try:
        awards_url = (
            f"https://www.pro-football-reference.com/awards/awards_{season}.htm"
        )
        awards_html = _fetch_pfr_page(awards_url)
        facts.awards = _extract_awards(awards_html)
        facts.awards_url = awards_url
    except Exception as exc:
        logger.warning(f"Could not fetch awards for {season}: {exc}")

    _SEASON_CACHE[season] = facts
    return facts


def _extract_playoff_results(html: str) -> tuple[Optional[str], dict[str, str]]:
    """Best-effort scrape of SB winner and conference champs from a season page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    sb_winner: Optional[str] = None
    # Patterns like "Super Bowl Champion: Kansas City Chiefs"
    m = re.search(
        r"Super Bowl Champion[:\s]+([A-Z][A-Za-z .]+?)(?:\s{2,}|\sLeague|$)", text
    )
    if m:
        sb_winner = m.group(1).strip()

    conf_champs: dict[str, str] = {}
    for conf in ("AFC", "NFC"):
        m = re.search(
            rf"{conf} Champion[:\s]+([A-Z][A-Za-z .]+?)(?:\s{{2,}}|\s[AN]FC|$)",
            text,
        )
        if m:
            conf_champs[conf] = m.group(1).strip()

    return sb_winner, conf_champs


# Map various phrasings of award names to canonical keys we store on
# SeasonFacts.awards.  Keys are lower-case for case-insensitive lookup.
AWARD_KEYS: dict[str, str] = {
    "mvp": "MVP",
    "most valuable player": "MVP",
    "opoy": "OPOY",
    "offensive player of the year": "OPOY",
    "dpoy": "DPOY",
    "defensive player of the year": "DPOY",
    "oroy": "OROY",
    "offensive rookie of the year": "OROY",
    "droy": "DROY",
    "defensive rookie of the year": "DROY",
    "cpoy": "CPOY",
    "comeback player of the year": "CPOY",
    "coach of the year": "COY",
    "coy": "COY",
    "ap most valuable player": "MVP",
    "ap offensive player of the year": "OPOY",
    "ap defensive player of the year": "DPOY",
    "ap offensive rookie of the year": "OROY",
    "ap defensive rookie of the year": "DROY",
    "ap comeback player of the year": "CPOY",
    "ap coach of the year": "COY",
}


def _extract_awards(html: str) -> dict[str, str]:
    """Pull award winners from a PFR awards_YYYY.htm page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    awards: dict[str, str] = {}

    # Most awards on PFR appear as a paragraph or table where the first cell
    # is the award label and the second is the winner. The simplest robust
    # approach is to look for "<award>: <winner>" patterns in the page text.
    text = soup.get_text("\n", strip=True)
    for line in text.split("\n"):
        m = re.match(r"^([A-Za-z\- ]+?)[:\-]\s+([A-Z][A-Za-z'.\- ]+)$", line)
        if not m:
            continue
        label = m.group(1).strip().lower()
        winner = m.group(2).strip()
        canonical = AWARD_KEYS.get(label)
        if canonical and canonical not in awards:
            awards[canonical] = winner
    return awards


# ---------------------------------------------------------------------------
# Resolvers — one per category
# ---------------------------------------------------------------------------


def _make_unresolvable(
    reason: str, evidence_url: Optional[str] = None
) -> ResolutionResult:
    return ResolutionResult(
        outcome="unresolvable",
        confidence=0.0,
        notes=reason,
        evidence_url=evidence_url,
    )


def resolve_win_total(prediction: dict, season: int) -> ResolutionResult:
    """Resolve claims like 'Cowboys win 11+ games' or '49ers go 12-5'."""
    claim = (prediction.get("extracted_claim") or "").strip()
    if not claim:
        return _make_unresolvable("empty_claim")

    facts = load_season_facts(season)
    if facts.standings.empty:
        return _make_unresolvable("no_standings", facts.standings_url)

    team_pfr = normalize_team_to_pfr(prediction.get("target_team") or claim)
    if not team_pfr:
        return _make_unresolvable("team_not_found_in_claim", facts.standings_url)

    row = facts.standings[facts.standings["team_pfr"] == team_pfr]
    if row.empty:
        return _make_unresolvable(
            f"team_{team_pfr}_not_in_standings", facts.standings_url
        )

    actual_wins = int(row.iloc[0]["wins"])
    actual_losses = int(row.iloc[0]["losses"])
    label = row.iloc[0]["team_label"]

    # Patterns:
    #   "10+ wins", "at least 10 wins", "win 10 or more games", "10-7"
    cl = claim.lower()

    record_match = re.search(r"(\d{1,2})\s*[-–]\s*(\d{1,2})", cl)
    if record_match:
        pred_w = int(record_match.group(1))
        pred_l = int(record_match.group(2))
        correct = (pred_w == actual_wins) and (pred_l == actual_losses)
        return ResolutionResult(
            outcome="correct" if correct else "incorrect",
            evidence_url=facts.standings_url,
            confidence=0.9,
            notes=f"{label} finished {actual_wins}-{actual_losses} (predicted {pred_w}-{pred_l})",
            evidence_quote=f"{label}: {actual_wins}-{actual_losses}",
        )

    threshold_match = re.search(
        r"(?:at least|over|more than|win[s]?)\s*(\d{1,2})\+?\s*(?:or more\s*)?(?:wins|games)?",
        cl,
    )
    bare_plus = re.search(r"(\d{1,2})\+\s*wins", cl)
    threshold = None
    op = ">="
    if bare_plus:
        threshold = int(bare_plus.group(1))
    elif threshold_match:
        threshold = int(threshold_match.group(1))
        if "more than" in cl or "over" in cl:
            op = ">"

    if threshold is None:
        return _make_unresolvable("could_not_parse_win_total", facts.standings_url)

    correct = (actual_wins >= threshold) if op == ">=" else (actual_wins > threshold)
    return ResolutionResult(
        outcome="correct" if correct else "incorrect",
        evidence_url=facts.standings_url,
        confidence=0.9,
        notes=f"{label} finished {actual_wins}-{actual_losses} (claim: {op}{threshold} wins)",
        evidence_quote=f"{label}: {actual_wins}-{actual_losses}",
    )


def resolve_playoff_prediction(prediction: dict, season: int) -> ResolutionResult:
    """Resolve make-playoffs / division winner / conference champ / SB winner claims."""
    claim = (prediction.get("extracted_claim") or "").strip()
    cl = claim.lower()
    if not claim:
        return _make_unresolvable("empty_claim")

    facts = load_season_facts(season)
    team_pfr = normalize_team_to_pfr(prediction.get("target_team") or claim)
    team_label = PFR_ABBR_TO_LABEL.get(team_pfr or "", "")

    # Super Bowl winner
    if "super bowl" in cl and ("win" in cl or "champion" in cl):
        if not facts.super_bowl_winner:
            return _make_unresolvable("super_bowl_winner_unknown", facts.standings_url)
        if not team_label:
            return _make_unresolvable(
                "team_unspecified_for_sb_claim", facts.standings_url
            )
        correct = team_label.lower() in facts.super_bowl_winner.lower() or (
            facts.super_bowl_winner.lower() in team_label.lower()
        )
        return ResolutionResult(
            outcome="correct" if correct else "incorrect",
            evidence_url=facts.standings_url,
            confidence=0.9,
            notes=f"SB {season}: {facts.super_bowl_winner}",
            evidence_quote=f"Super Bowl Champion: {facts.super_bowl_winner}",
        )

    # Conference champion
    if ("afc" in cl or "nfc" in cl) and ("champion" in cl or "represent" in cl):
        conf = "AFC" if "afc" in cl else "NFC"
        winner = facts.conference_champs.get(conf)
        if not winner:
            return _make_unresolvable(f"{conf}_champ_unknown", facts.standings_url)
        if not team_label:
            return _make_unresolvable("team_unspecified", facts.standings_url)
        correct = (
            team_label.lower() in winner.lower() or winner.lower() in team_label.lower()
        )
        return ResolutionResult(
            outcome="correct" if correct else "incorrect",
            evidence_url=facts.standings_url,
            confidence=0.85,
            notes=f"{conf} Champion {season}: {winner}",
            evidence_quote=f"{conf} Champion: {winner}",
        )

    # Division winner
    if "win" in cl and "division" in cl:
        if not team_label or facts.standings.empty:
            return _make_unresolvable("division_data_missing", facts.standings_url)
        team_row = facts.standings[facts.standings["team_pfr"] == team_pfr]
        if team_row.empty:
            return _make_unresolvable("team_not_in_standings", facts.standings_url)
        division = team_row.iloc[0]["division"]
        winner = facts.division_winners.get(division)
        if not winner:
            return _make_unresolvable("division_winner_unknown", facts.standings_url)
        correct = (
            team_label.lower() in winner.lower() or winner.lower() in team_label.lower()
        )
        return ResolutionResult(
            outcome="correct" if correct else "incorrect",
            evidence_url=facts.standings_url,
            confidence=0.85,
            notes=f"{division} winner {season}: {winner}",
            evidence_quote=f"{division}: {winner}",
        )

    # Make / miss playoffs
    will_make = re.search(
        r"(?:will\s+)?(?:make|reach|qualify for|get to)\s+(?:the\s+)?playoffs", cl
    )
    will_miss = re.search(
        r"(?:miss|fail to make|won't make|will not make)\s+(?:the\s+)?playoffs", cl
    )
    if will_make or will_miss:
        if not team_label:
            return _make_unresolvable(
                "team_unspecified_for_playoff_claim", facts.standings_url
            )
        team_row = facts.standings[facts.standings["team_pfr"] == team_pfr]
        if team_row.empty:
            return _make_unresolvable("team_not_in_standings", facts.standings_url)
        actually_made = bool(team_row.iloc[0]["made_playoffs"])
        expected = bool(will_make)
        correct = actually_made == expected
        return ResolutionResult(
            outcome="correct" if correct else "incorrect",
            evidence_url=facts.standings_url,
            confidence=0.85,
            notes=(
                f"{team_label}: actually {'made' if actually_made else 'missed'} playoffs "
                f"(predicted {'make' if expected else 'miss'})"
            ),
            evidence_quote=f"{team_label} made_playoffs={actually_made}",
        )

    return _make_unresolvable("playoff_pattern_not_recognised", facts.standings_url)


def resolve_award(prediction: dict, season: int) -> ResolutionResult:
    """Resolve award winner claims (MVP, OPOY, etc.)."""
    claim = (prediction.get("extracted_claim") or "").strip()
    cl = claim.lower()
    if not claim:
        return _make_unresolvable("empty_claim")

    facts = load_season_facts(season)
    if not facts.awards:
        return _make_unresolvable("awards_unavailable", facts.awards_url)

    # Identify which award the claim refers to
    target_award: Optional[str] = None
    for phrase in sorted(AWARD_KEYS, key=len, reverse=True):
        if phrase in cl:
            target_award = AWARD_KEYS[phrase]
            break

    if not target_award:
        return _make_unresolvable("award_not_identified", facts.awards_url)

    actual_winner = facts.awards.get(target_award)
    if not actual_winner:
        return _make_unresolvable(f"{target_award}_winner_unknown", facts.awards_url)

    # Find the predicted winner — usually the player named in the claim.
    target_player = (
        prediction.get("target_player") or prediction.get("target_player_name") or ""
    ).strip()
    if not target_player:
        # Try to pull the first capitalised proper-noun pair out of the claim.
        m = re.search(r"([A-Z][a-z]+(?:\s+[A-Z][a-z'\-]+){1,3})", claim)
        if m:
            target_player = m.group(1)

    if not target_player:
        return _make_unresolvable("predicted_winner_unspecified", facts.awards_url)

    pp = _normalize_name(target_player)
    aw = _normalize_name(actual_winner)
    correct = pp in aw or aw in pp

    return ResolutionResult(
        outcome="correct" if correct else "incorrect",
        evidence_url=facts.awards_url,
        confidence=0.9,
        notes=f"{target_award} {season}: {actual_winner} (predicted {target_player})",
        evidence_quote=f"{target_award}: {actual_winner}",
    )


def resolve_draft_pick(prediction: dict, season: int) -> ResolutionResult:
    """Lightweight wrapper that defers structured draft work to existing logic.

    This intentionally returns `unresolvable` so that the daily resolver
    (which already has SportsDataIO access and richer parsing) handles them.
    Kept as a stub so the dispatcher map is complete.
    """
    return _make_unresolvable(
        "delegated_to_resolve_daily.resolve_draft_picks",
        evidence_url=f"https://www.pro-football-reference.com/years/{season}/draft.htm",
    )


def resolve_stat_milestone(prediction: dict, season: int) -> ResolutionResult:
    """Resolve player statistical milestones via PFR season stat tables."""
    claim = (prediction.get("extracted_claim") or "").strip()
    if not claim:
        return _make_unresolvable("empty_claim")
    cl = claim.lower()

    # Map keyword → (pfr stat page suffix, table id, column)
    stat_routes: list[tuple[str, str, str, str]] = [
        # (keyword, page, table_id, column)
        ("passing yard", "passing.htm", "passing", "Yds"),
        ("pass yards", "passing.htm", "passing", "Yds"),
        ("passing touchdown", "passing.htm", "passing", "TD"),
        ("passing tds", "passing.htm", "passing", "TD"),
        ("rushing yard", "rushing.htm", "rushing", "Yds"),
        ("rush yards", "rushing.htm", "rushing", "Yds"),
        ("rushing touchdown", "rushing.htm", "rushing", "TD"),
        ("receiving yard", "receiving.htm", "receiving", "Yds"),
        ("receiving touchdown", "receiving.htm", "receiving", "TD"),
        ("receptions", "receiving.htm", "receiving", "Rec"),
        ("sacks", "defense.htm", "defense", "Sk"),
    ]
    route = next(((p, t, c) for kw, p, t, c in stat_routes if kw in cl), None)
    if not route:
        return _make_unresolvable("stat_keyword_not_matched")
    page, table_id, column = route

    threshold_match = re.search(
        r"(?:at least|over|more than)?\s*([\d,]{2,6})\+?\s*(?:or more)?",
        cl,
    )
    if not threshold_match:
        return _make_unresolvable("threshold_not_parsed")
    try:
        threshold = float(threshold_match.group(1).replace(",", ""))
    except ValueError:
        return _make_unresolvable("threshold_not_numeric")

    target_player = (
        prediction.get("target_player") or prediction.get("target_player_name") or ""
    ).strip()
    if not target_player:
        return _make_unresolvable("player_unspecified")

    url = f"https://www.pro-football-reference.com/years/{season}/{page}"
    try:
        html = _fetch_pfr_page(url)
    except Exception as exc:
        return _make_unresolvable(f"fetch_failed:{exc}", url)
    tables = _parse_pfr_tables(html)
    df = tables.get(table_id) or next(iter(tables.values()), None)
    if df is None or df.empty:
        return _make_unresolvable("stat_table_missing", url)
    if "Player" not in df.columns or column not in df.columns:
        return _make_unresolvable(f"missing_column_{column}", url)

    pp_norm = _normalize_name(target_player)
    df["_pn"] = df["Player"].astype(str).str.lower().str.replace(".", "", regex=False)
    rows = df[df["_pn"].str.contains(pp_norm, na=False)]
    if rows.empty:
        return _make_unresolvable(f"player_not_found:{target_player}", url)

    try:
        actual = float(rows.iloc[0][column])
    except (TypeError, ValueError):
        return _make_unresolvable("stat_not_numeric", url)

    correct = actual >= threshold
    return ResolutionResult(
        outcome="correct" if correct else "incorrect",
        evidence_url=url,
        confidence=0.85,
        notes=f"{target_player} {column}={actual:.0f} (threshold {threshold:.0f})",
        evidence_quote=f"{target_player}: {column}={actual}",
    )


def resolve_transaction(prediction: dict, season: int) -> ResolutionResult:
    """Trades / signings happen — defer to LLM judge with PFR transactions URL."""
    url = f"https://www.pro-football-reference.com/years/{season}/transactions.htm"
    try:
        html = _fetch_pfr_page(url)
    except Exception as exc:
        return _make_unresolvable(f"fetch_failed:{exc}", url)

    claim = (prediction.get("extracted_claim") or "").strip().lower()
    target_player = _normalize_name(
        prediction.get("target_player") or prediction.get("target_player_name") or ""
    )

    if not target_player:
        return _make_unresolvable("player_unspecified", url)

    # Crude substring search — if the player name shows up on the
    # transactions page, the trade/signing happened.
    page_lower = html.lower()
    found = target_player in page_lower
    return ResolutionResult(
        outcome="correct" if found else "incorrect",
        evidence_url=url,
        confidence=0.8 if found else 0.6,
        notes=(
            f"Player '{target_player}' "
            f"{'appears' if found else 'does NOT appear'} on {season} transactions page"
        ),
        evidence_quote=f"transactions.htm contains '{target_player}': {found}",
    )


# ---------------------------------------------------------------------------
# LLM judge fallback
# ---------------------------------------------------------------------------


def llm_judge(prediction: dict, season: int, facts_blob: str) -> ResolutionResult:
    """Last-resort: ask the local LLM whether the prediction came true.

    `facts_blob` should be a short factual summary the model can ground on.
    Returns `unresolvable` if confidence is below CONFIDENCE_FLOOR.
    """
    try:
        from src.llm_provider import get_provider
    except Exception as exc:
        return _make_unresolvable(f"llm_unavailable:{exc}")

    claim = prediction.get("extracted_claim", "")
    prompt = f"""You are an NFL prediction judge. Decide if the prediction below came true given the facts.

PREDICTION: "{claim}"
SEASON: {season}
FACTS:
{facts_blob}

Reply with ONLY a JSON object:
{{
  "outcome": "correct" | "incorrect" | "partial" | "unresolvable",
  "evidence_quote": "<short quote from the facts>",
  "confidence": <float 0.0-1.0>
}}"""
    try:
        provider = get_provider("extraction")
        text = provider.classify(prompt) if hasattr(provider, "classify") else ""
        # `classify` returns a short string — try generate_predictions style instead
        # by re-using the raw provider call when available.
        if not text or "{" not in text:
            # Some providers (Ollama) only expose extract_predictions for JSON.
            # Reuse the prompt as if it were an extraction query.
            preds = provider.extract_predictions(prompt)
            if preds and isinstance(preds, list) and isinstance(preds[0], dict):
                text = json.dumps(preds[0])
    except Exception as exc:
        return _make_unresolvable(f"llm_call_failed:{exc}")

    try:
        # Trim to outermost {...}
        m = re.search(r"\{[\s\S]*\}", text or "")
        data = json.loads(m.group(0)) if m else {}
    except Exception:
        return _make_unresolvable("llm_unparseable_json")

    outcome = (data.get("outcome") or "unresolvable").lower()
    confidence = float(data.get("confidence", 0.0) or 0.0)
    if outcome not in {"correct", "incorrect", "partial", "unresolvable"}:
        outcome = "unresolvable"
    if confidence < CONFIDENCE_FLOOR and outcome != "unresolvable":
        return ResolutionResult(
            outcome="unresolvable",
            confidence=confidence,
            notes=f"llm_confidence_below_floor:{confidence}",
            evidence_quote=str(data.get("evidence_quote", ""))[:240],
        )

    return ResolutionResult(
        outcome=outcome,
        confidence=confidence,
        notes="llm_judge",
        evidence_quote=str(data.get("evidence_quote", ""))[:240],
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


CategoryResolver = Callable[[dict, int], ResolutionResult]

# Map prediction.claim_category → resolver. Categories are not always
# precise (e.g. an MVP claim may come in as 'player_performance'), so the
# dispatcher uses both the category and a lightweight keyword inspection.
CATEGORY_RESOLVERS: dict[str, CategoryResolver] = {
    "win_total": resolve_win_total,
    "season_record": resolve_win_total,
    "game_outcome": resolve_playoff_prediction,
    "playoffs": resolve_playoff_prediction,
    "award": resolve_award,
    "draft_pick": resolve_draft_pick,
    "player_performance": resolve_stat_milestone,
    "trade": resolve_transaction,
    "signing": resolve_transaction,
    "contract": resolve_transaction,
}


def _route(prediction: dict) -> CategoryResolver:
    """Choose a resolver. Strong claim-text signals override category labels
    because the upstream extractor occasionally mis-categorises (e.g. an MVP
    pick coming in as ``player_performance``).
    """
    cl = (prediction.get("extracted_claim") or "").lower()

    # Strong-signal keywords first — these dominate even an explicit category.
    if any(
        k in cl
        for k in (
            "mvp",
            "rookie of the year",
            "coach of the year",
            "player of the year",
            "opoy",
            "dpoy",
            "oroy",
            "droy",
        )
    ):
        return resolve_award
    if any(
        k in cl
        for k in (
            "super bowl",
            "afc champ",
            "nfc champ",
            "make playoffs",
            "miss playoffs",
            "win the division",
        )
    ):
        return resolve_playoff_prediction

    cat = (prediction.get("claim_category") or "").lower()
    if cat in CATEGORY_RESOLVERS:
        return CATEGORY_RESOLVERS[cat]

    if re.search(r"\d+\s*(wins|games)|\d+\s*[-–]\s*\d+", cl):
        return resolve_win_total
    if any(k in cl for k in ("yards", "touchdowns", "tds", "sacks", "receptions")):
        return resolve_stat_milestone
    if any(k in cl for k in ("trade", "signs with", "signed by", "released by")):
        return resolve_transaction
    return lambda p, s: _make_unresolvable("no_resolver_matched")


def resolve_prediction(prediction: dict, season: int) -> ResolutionResult:
    """Entry point: route to a category resolver, then enforce confidence floor."""
    resolver = _route(prediction)
    try:
        result = resolver(prediction, season)
    except Exception as exc:
        logger.exception("resolver_crashed")
        return _make_unresolvable(f"resolver_exception:{exc}")

    # Confidence floor: anything weak gets demoted to unresolvable.
    if (
        result.outcome in {"correct", "incorrect", "partial"}
        and result.confidence < CONFIDENCE_FLOOR
    ):
        return ResolutionResult(
            outcome="unresolvable",
            evidence_url=result.evidence_url,
            confidence=result.confidence,
            notes=f"below_confidence_floor:{result.confidence}: {result.notes}",
            evidence_quote=result.evidence_quote,
        )
    # Require evidence URL for any positive resolution.
    if (
        result.outcome in {"correct", "incorrect", "partial"}
        and not result.evidence_url
    ):
        return _make_unresolvable(f"missing_evidence_url: {result.notes}")
    return result


# ---------------------------------------------------------------------------
# BigQuery write integration
# ---------------------------------------------------------------------------


def _outcome_to_status(outcome: str) -> str:
    """Map our 4-state outcome to the existing 3-state schema (CORRECT/INCORRECT/VOID)."""
    return {
        "correct": "CORRECT",
        "incorrect": "INCORRECT",
        "partial": "CORRECT",  # treat partial as correct with a note
        "unresolvable": "VOID",
    }.get(outcome, "VOID")


def write_to_bq(
    prediction_hash: str, result: ResolutionResult, dry_run: bool = False
) -> None:
    """Persist a ResolutionResult through the existing resolution_engine schema."""
    if dry_run:
        logger.info(
            f"DRY-RUN write {prediction_hash[:12]}… → {result.outcome} ({result.confidence:.2f})"
        )
        return

    from src.resolution_engine import (
        ResolutionResult as ExistingResult,
        record_resolution,
    )

    notes = result.notes
    if result.evidence_quote:
        notes = f"{notes} | quote: {result.evidence_quote[:200]}"
    notes = f"{notes} | confidence={result.confidence:.2f}"

    existing = ExistingResult(
        prediction_hash=prediction_hash,
        resolution_status=_outcome_to_status(result.outcome),
        resolver="auto-historical",
        binary_correct=(result.outcome == "correct"),
        timeliness_weight=1.0,
        weighted_score=1.0
        if result.outcome == "correct"
        else (0.5 if result.outcome == "partial" else 0.0),
        outcome_source="pro-football-reference",
        outcome_reference_id=result.evidence_url,
        outcome_notes=notes,
    )
    record_resolution(existing)


# ---------------------------------------------------------------------------
# Batch driver / CLI
# ---------------------------------------------------------------------------


def fetch_pending_for_season(season: int, batch_size: int) -> pd.DataFrame:
    """Pull PENDING predictions for a season from the ledger via BigQuery."""
    from src.db_manager import DBManager

    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        raise EnvironmentError("GCP_PROJECT_ID not set")

    db = DBManager()
    try:
        sql = f"""
            SELECT
                l.prediction_hash,
                l.extracted_claim,
                l.claim_category,
                l.season_year,
                l.target_player_id,
                l.target_team
            FROM `{project_id}.gold_layer.prediction_ledger` l
            LEFT JOIN `{project_id}.gold_layer.prediction_resolutions` r
                ON l.prediction_hash = r.prediction_hash
            WHERE COALESCE(l.sport, 'NFL') = 'NFL'
              AND l.season_year = {int(season)}
              AND (r.prediction_hash IS NULL OR r.resolution_status = 'PENDING')
            ORDER BY l.ingestion_timestamp ASC
            LIMIT {int(batch_size)}
        """
        return db.fetch_df(sql)
    finally:
        db.close()


def run_batch(
    season: int,
    batch_size: int = 100,
    dry_run: bool = False,
    sample: Optional[int] = None,
    predictions_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Resolve a batch of pending predictions for a season.

    If `predictions_df` is provided, use it instead of fetching from BQ —
    useful for tests and ad-hoc runs.
    """
    if predictions_df is None:
        predictions_df = fetch_pending_for_season(season, batch_size)

    if sample is not None:
        predictions_df = predictions_df.head(sample)

    summary: dict[str, Any] = {
        "season": season,
        "attempted": 0,
        "correct": 0,
        "incorrect": 0,
        "partial": 0,
        "unresolvable": 0,
        "by_category": {},
    }

    for _, row in predictions_df.iterrows():
        summary["attempted"] += 1
        pred = row.to_dict()
        result = resolve_prediction(pred, season)
        summary[result.outcome] = summary.get(result.outcome, 0) + 1
        cat = pred.get("claim_category") or "unknown"
        bucket = summary["by_category"].setdefault(
            cat, {"correct": 0, "incorrect": 0, "partial": 0, "unresolvable": 0}
        )
        bucket[result.outcome] = bucket.get(result.outcome, 0) + 1

        try:
            write_to_bq(pred["prediction_hash"], result, dry_run=dry_run)
        except Exception as exc:
            logger.warning(
                f"BQ write failed for {pred.get('prediction_hash', '?')[:12]}…: {exc}"
            )

    resolved = summary["correct"] + summary["incorrect"] + summary["partial"]
    summary["resolution_rate"] = (
        (resolved / summary["attempted"]) if summary["attempted"] else 0.0
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Historical prediction resolver")
    parser.add_argument(
        "--season", type=int, required=True, help="NFL season year (e.g. 2024)"
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Resolve at most N predictions (for smoke tests)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't write to BigQuery; just print results",
    )
    parser.add_argument(
        "--category", default=None, help="Restrict to a single claim_category"
    )
    args = parser.parse_args()

    df = fetch_pending_for_season(args.season, args.batch_size)
    if args.category:
        df = df[df["claim_category"] == args.category]

    summary = run_batch(
        season=args.season,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        sample=args.sample,
        predictions_df=df,
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()

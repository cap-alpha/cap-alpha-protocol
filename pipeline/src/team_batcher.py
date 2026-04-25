"""
Team-Batching Pre-Processor (Issue #181)

Groups raw media articles by mentioned NFL team before LLM extraction,
reducing round-trips by 3-5x and giving the model cross-article context
to identify consensus vs contrarian pundit takes.

Usage:
    from src.team_batcher import batch_articles_by_team, build_batched_prompt

    batches = batch_articles_by_team(articles, max_per_batch=5)
    for team, batch in batches.items():
        prompt = build_batched_prompt(team, batch)
        predictions = provider.extract_predictions(prompt)
"""

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

# Canonical marker for the batched prompt structure.
# Update this string (not the hash) when the prompt instructions change significantly.
_BATCH_PROMPT_STRUCTURE = (
    "batched-extraction-v1|"
    "fields:extracted_claim,pundit_name,claim_category,season_year,"
    "target_player_name,target_team,consensus_note|"
    "categories:player_performance,game_outcome,trade,draft_pick,injury,contract,other"
)
BATCH_PROMPT_VERSION = hashlib.sha256(_BATCH_PROMPT_STRUCTURE.encode()).hexdigest()[:8]

# ---------------------------------------------------------------------------
# Team name / alias → abbreviation mapping (all 32 NFL teams)
# ---------------------------------------------------------------------------

NFL_TEAMS: dict[str, str] = {
    # AFC East
    "buffalo bills": "BUF",
    "bills": "BUF",
    "buf": "BUF",
    "miami dolphins": "MIA",
    "dolphins": "MIA",
    "mia": "MIA",
    "new england patriots": "NE",
    "patriots": "NE",
    "ne patriots": "NE",
    "pats": "NE",
    "new york jets": "NYJ",
    "jets": "NYJ",
    "nyj": "NYJ",
    # AFC North
    "baltimore ravens": "BAL",
    "ravens": "BAL",
    "bal": "BAL",
    "cincinnati bengals": "CIN",
    "bengals": "CIN",
    "cin": "CIN",
    "cleveland browns": "CLE",
    "browns": "CLE",
    "cle": "CLE",
    "pittsburgh steelers": "PIT",
    "steelers": "PIT",
    "pit": "PIT",
    # AFC South
    "houston texans": "HOU",
    "texans": "HOU",
    "hou": "HOU",
    "indianapolis colts": "IND",
    "colts": "IND",
    "ind": "IND",
    "jacksonville jaguars": "JAX",
    "jaguars": "JAX",
    "jags": "JAX",
    "jax": "JAX",
    "tennessee titans": "TEN",
    "titans": "TEN",
    "ten": "TEN",
    # AFC West
    "denver broncos": "DEN",
    "broncos": "DEN",
    "den": "DEN",
    "kansas city chiefs": "KC",
    "chiefs": "KC",
    "kc chiefs": "KC",
    "kc": "KC",
    "las vegas raiders": "LV",
    "raiders": "LV",
    "lv raiders": "LV",
    "lv": "LV",
    "oakland raiders": "LV",  # legacy alias
    "los angeles chargers": "LAC",
    "chargers": "LAC",
    "la chargers": "LAC",
    "lac": "LAC",
    # NFC East
    "dallas cowboys": "DAL",
    "cowboys": "DAL",
    "dal": "DAL",
    "new york giants": "NYG",
    "giants": "NYG",
    "nyg": "NYG",
    "philadelphia eagles": "PHI",
    "eagles": "PHI",
    "phi": "PHI",
    "washington commanders": "WSH",
    "commanders": "WSH",
    "washington football team": "WSH",
    "wsh": "WSH",
    "was": "WSH",
    # NFC North
    "chicago bears": "CHI",
    "bears": "CHI",
    "chi": "CHI",
    "detroit lions": "DET",
    "lions": "DET",
    "det": "DET",
    "green bay packers": "GB",
    "packers": "GB",
    "gb packers": "GB",
    "gb": "GB",
    "minnesota vikings": "MIN",
    "vikings": "MIN",
    "min": "MIN",
    # NFC South
    "atlanta falcons": "ATL",
    "falcons": "ATL",
    "atl": "ATL",
    "carolina panthers": "CAR",
    "panthers": "CAR",
    "car": "CAR",
    "new orleans saints": "NO",
    "saints": "NO",
    "no saints": "NO",
    "tampa bay buccaneers": "TB",
    "buccaneers": "TB",
    "bucs": "TB",
    "tb bucs": "TB",
    "tb": "TB",
    # NFC West
    "arizona cardinals": "ARI",
    "cardinals": "ARI",
    "ari": "ARI",
    "los angeles rams": "LAR",
    "rams": "LAR",
    "la rams": "LAR",
    "lar": "LAR",
    "san francisco 49ers": "SF",
    "49ers": "SF",
    "niners": "SF",
    "sf": "SF",
    "seattle seahawks": "SEA",
    "seahawks": "SEA",
    "sea": "SEA",
}

# Pre-compile a single regex for fast scanning.
# Sort by length desc so longer aliases match before shorter ones.
_TEAM_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(NFL_TEAMS, key=len, reverse=True))
    + r")\b",
    re.IGNORECASE,
)

# Abbreviation → human-readable team name (for prompt context)
_ABBR_TO_NAME: dict[str, str] = {
    "BUF": "Buffalo Bills",
    "MIA": "Miami Dolphins",
    "NE": "New England Patriots",
    "NYJ": "New York Jets",
    "BAL": "Baltimore Ravens",
    "CIN": "Cincinnati Bengals",
    "CLE": "Cleveland Browns",
    "PIT": "Pittsburgh Steelers",
    "HOU": "Houston Texans",
    "IND": "Indianapolis Colts",
    "JAX": "Jacksonville Jaguars",
    "TEN": "Tennessee Titans",
    "DEN": "Denver Broncos",
    "KC": "Kansas City Chiefs",
    "LV": "Las Vegas Raiders",
    "LAC": "Los Angeles Chargers",
    "DAL": "Dallas Cowboys",
    "NYG": "New York Giants",
    "PHI": "Philadelphia Eagles",
    "WSH": "Washington Commanders",
    "CHI": "Chicago Bears",
    "DET": "Detroit Lions",
    "GB": "Green Bay Packers",
    "MIN": "Minnesota Vikings",
    "ATL": "Atlanta Falcons",
    "CAR": "Carolina Panthers",
    "NO": "New Orleans Saints",
    "TB": "Tampa Bay Buccaneers",
    "ARI": "Arizona Cardinals",
    "LAR": "Los Angeles Rams",
    "SF": "San Francisco 49ers",
    "SEA": "Seattle Seahawks",
}

MAX_ARTICLE_CHARS = 1500  # truncate per article to stay within context window
MAX_BATCH_SIZE = 5  # max articles per team batch


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ArticleRecord:
    """Minimal article representation for batching."""

    content_hash: str
    raw_text: str
    title: str = ""
    pundit_name: str = ""
    source_name: str = ""
    published_date: str = ""
    teams_mentioned: set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Team mention extraction
# ---------------------------------------------------------------------------


def extract_team_mentions(text: str) -> set[str]:
    """
    Scans text for NFL team references and returns a set of team abbreviations.

    Handles full names, city names, and common abbreviations case-insensitively.
    An article can mention multiple teams.
    """
    matches = _TEAM_PATTERN.findall(text)
    return {NFL_TEAMS[m.lower()] for m in matches}


# ---------------------------------------------------------------------------
# Article batching
# ---------------------------------------------------------------------------


def batch_articles_by_team(
    articles: list[ArticleRecord],
    max_per_batch: int = MAX_BATCH_SIZE,
) -> dict[str, list[list[ArticleRecord]]]:
    """
    Groups articles by the NFL teams they mention.

    An article that mentions multiple teams will appear in each team's group.
    If a team's group exceeds max_per_batch, it is split into sub-batches
    sorted by published_date (oldest first).

    Returns: {team_abbr: [[batch_1_articles], [batch_2_articles], ...]}
    """
    team_pools: dict[str, list[ArticleRecord]] = defaultdict(list)

    for article in articles:
        if not article.teams_mentioned:
            article.teams_mentioned = extract_team_mentions(article.raw_text)
        for team in article.teams_mentioned:
            team_pools[team].append(article)

    # Sort each team pool by date, then split into sub-batches
    result: dict[str, list[list[ArticleRecord]]] = {}
    for team, pool in team_pools.items():
        pool_sorted = sorted(pool, key=lambda a: a.published_date or "")
        batches = [
            pool_sorted[i : i + max_per_batch]
            for i in range(0, len(pool_sorted), max_per_batch)
        ]
        result[team] = batches

    return result


# ---------------------------------------------------------------------------
# Batched extraction prompt builder
# ---------------------------------------------------------------------------


def build_batched_prompt(
    team_abbr: str,
    articles: list[ArticleRecord],
    sport: str = "NFL",
    current_date: Optional[str] = None,
) -> str:
    """
    Builds a single LLM extraction prompt covering multiple articles about one team.

    The prompt instructs the model to:
    1. Extract concrete, testable predictions from all articles.
    2. Note which pundit made each prediction.
    3. Flag consensus vs contrarian takes across pundits.

    Returns a prompt string ready to pass to LLMProvider.extract_predictions().
    """
    team_name = _ABBR_TO_NAME.get(team_abbr, team_abbr)
    n = len(articles)
    date_ctx = f" (as of {current_date})" if current_date else ""

    articles_text = "\n\n".join(
        _format_article_block(i + 1, article) for i, article in enumerate(articles)
    )

    return f"""You are a sports analytics AI extracting pundit predictions from {n} article(s) about the {team_name}{date_ctx}.

TASK: Extract every concrete, testable, future-facing prediction about the {team_name} from the articles below. Only include claims that can be objectively verified (e.g. "Bears will draft X at pick Y", "Mahomes will throw for 4000 yards", "player X will be released").

For each prediction, identify:
- Which pundit made it
- Whether other pundits in this batch agree or contradict it (consensus signal)

Return a JSON array. Each element must have:
{{
  "extracted_claim": "...",          // concise testable prediction
  "pundit_name": "...",
  "claim_category": "...",           // one of: player_performance|game_outcome|trade|draft_pick|injury|contract|other
  "season_year": <int or null>,
  "target_player_name": "...",       // if about a specific player, else null
  "target_team": "{team_abbr}",
  "consensus_note": "..."            // e.g. "3/3 pundits agree", "contrarian — others disagree", or ""
}}

Return [] if no concrete predictions are found.

ARTICLES:
{articles_text}

Return only the JSON array, no commentary."""


def _format_article_block(index: int, article: ArticleRecord) -> str:
    """Format a single article for inclusion in the batched prompt."""
    pundit = article.pundit_name or "Unknown Pundit"
    source = article.source_name or "Unknown Source"
    date = article.published_date or "Unknown Date"
    title = article.title or ""
    text = article.raw_text[:MAX_ARTICLE_CHARS]
    if len(article.raw_text) > MAX_ARTICLE_CHARS:
        text += "..."

    header = f"[Article {index} | Pundit: {pundit} | Source: {source} | Date: {date}]"
    if title:
        header += f"\nTitle: {title}"
    return f"{header}\n{text}"


# ---------------------------------------------------------------------------
# Convenience: annotate articles with team mentions
# ---------------------------------------------------------------------------


def annotate_team_mentions(articles: list[ArticleRecord]) -> list[ArticleRecord]:
    """
    In-place annotation of articles with teams_mentioned.
    Returns the same list for chaining.
    """
    for article in articles:
        if not article.teams_mentioned:
            article.teams_mentioned = extract_team_mentions(article.raw_text)
    return articles

"""
Daily Prediction Resolution Engine (Issue #169, #191)

Matches PENDING predictions from gold_layer.prediction_ledger against actual
NFL outcomes to automatically score pundit accuracy.

Handles three categories:
  1. draft_pick — resolved against bronze_sportsdataio_players draft data
  2. game_outcome — resolved against bronze_sportsdataio_scores
  3. player_performance — resolved against bronze_sportsdataio_player_season_stats

Usage (inside Docker):
    python -m src.resolve_daily                         # resolve all pending
    python -m src.resolve_daily --category draft_pick   # single category
    python -m src.resolve_daily --dry-run               # preview without writing
"""

import argparse
import logging
import os
import re
from typing import Optional

import pandas as pd
from google.api_core.exceptions import NotFound

from src.db_manager import DBManager
from src.resolution_engine import (
    get_pending_predictions,
    resolve_binary,
    void_prediction,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Draft pick resolver
# ---------------------------------------------------------------------------


def _load_draft_data(db: DBManager) -> pd.DataFrame:
    """Load draft pick data from bronze_sportsdataio_players."""
    project_id = os.environ["GCP_PROJECT_ID"]
    query = f"""
        SELECT
            Name,
            LOWER(Name) AS name_lower,
            CollegeDraftYear AS draft_year,
            CollegeDraftRound AS draft_round,
            CollegeDraftPick AS draft_pick,
            CollegeDraftTeam AS draft_team,
            Team AS current_team,
            IsUndraftedFreeAgent AS undrafted
        FROM `{project_id}.nfl_dead_money.bronze_sportsdataio_players`
        WHERE CollegeDraftYear IS NOT NULL
    """
    return db.fetch_df(query)


def _normalize_name(name: str) -> str:
    """Normalize player name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common suffixes
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    # Remove periods from initials
    name = name.replace(".", "")
    return name


def _extract_draft_claim(claim: str) -> dict:
    """
    Parse a draft_pick claim to extract structured components.
    Returns dict with keys: player_name, pick_number, round_number, team, draft_year
    """
    claim_lower = claim.lower()
    result = {}

    # Extract "No. 1 overall pick" or "#1 pick" or "first overall pick"
    ordinals = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
        "sixth": 6,
        "seventh": 7,
        "eighth": 8,
        "ninth": 9,
        "tenth": 10,
    }
    pick_match = re.search(r"(?:no\.?\s*|#)(\d+)\s*(?:overall\s*)?pick", claim_lower)
    if pick_match:
        result["pick_number"] = int(pick_match.group(1))
    else:
        for word, num in ordinals.items():
            if f"{word} overall" in claim_lower or f"{word} pick" in claim_lower:
                result["pick_number"] = num
                break

    # Extract "top-N pick"
    top_match = re.search(r"top[- ](\d+)\s*pick", claim_lower)
    if top_match:
        result["top_n"] = int(top_match.group(1))

    # Extract "Round 1" or "first round"
    round_match = re.search(r"round\s*(\d+)", claim_lower)
    if round_match:
        result["round_number"] = int(round_match.group(1))
    elif "first round" in claim_lower:
        result["round_number"] = 1

    # Extract draft year
    year_match = re.search(r"20\d{2}", claim)
    if year_match:
        result["draft_year"] = int(year_match.group())

    return result


def resolve_draft_picks(db: DBManager, dry_run: bool = False) -> dict:
    """
    Resolve draft_pick predictions against actual draft results.
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport="NFL", db=db)
    draft_preds = pending[pending["claim_category"] == "draft_pick"]

    if draft_preds.empty:
        logger.info("No pending draft_pick predictions to resolve.")
        return summary

    draft_data = _load_draft_data(db)
    if draft_data.empty:
        logger.warning("No draft data available for resolution.")
        return summary

    logger.info(
        f"Resolving {len(draft_preds)} draft_pick predictions "
        f"against {len(draft_data)} player draft records"
    )

    for _, pred in draft_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        player_name = pred.get("target_player_id") or ""  # Legacy field (has names)
        season_year = pred.get("season_year")

        parsed = _extract_draft_claim(claim)
        draft_year = parsed.get("draft_year")
        if not draft_year and pd.notna(season_year):
            draft_year = int(season_year)

        if not draft_year:
            logger.info(f"  SKIP {phash[:12]}… — no draft year in claim or metadata")
            summary["skipped"] += 1
            continue

        # Check if we have actual draft pick data for this year
        current_year = pd.Timestamp.now().year
        year_draft_data = draft_data[
            (draft_data["draft_year"] == draft_year)
            & (draft_data["draft_pick"].notna())
        ]
        if draft_year > current_year or (
            draft_year == current_year and len(year_draft_data) == 0
        ):
            logger.info(
                f"  SKIP {phash[:12]}… — no draft results available for {draft_year}"
            )
            summary["skipped"] += 1
            continue

        # Find the player in draft data
        norm_name = _normalize_name(player_name) if player_name else ""
        player_matches = (
            draft_data[draft_data["name_lower"].str.contains(norm_name, na=False)]
            if norm_name and norm_name != "none"
            else pd.DataFrame()
        )

        # Also try extracting player name from the claim itself
        if player_matches.empty:
            # Try each name in draft_data against the claim
            claim_lower = claim.lower()
            for _, draft_row in draft_data.iterrows():
                if draft_row["name_lower"] in claim_lower:
                    player_matches = pd.DataFrame([draft_row])
                    break

        if player_matches.empty:
            logger.info(
                f"  SKIP {phash[:12]}… — can't find player in draft data: {claim[:60]}"
            )
            summary["skipped"] += 1
            continue

        # Use the first match (best match)
        actual = player_matches.iloc[0]
        actual_pick = actual.get("draft_pick")
        actual_round = actual.get("draft_round")
        actual_team = actual.get("draft_team")
        actual_name = actual.get("Name")

        # Skip if pick data is missing or invalid (pick 0 = not yet assigned)
        if not pd.notna(actual_pick) or int(actual_pick) == 0:
            logger.info(
                f"  SKIP {phash[:12]}… — player found but pick not yet assigned: {actual_name}"
            )
            summary["skipped"] += 1
            continue

        # Now evaluate the claim
        correct = None
        notes_parts = [
            f"Actual: {actual_name} was pick #{actual_pick} (Round {actual_round}) by {actual_team}"
        ]

        if "pick_number" in parsed and pd.notna(actual_pick):
            correct = int(actual_pick) == parsed["pick_number"]
            notes_parts.append(
                f"Claimed pick #{parsed['pick_number']}, actual #{int(actual_pick)}"
            )
        elif "top_n" in parsed and pd.notna(actual_pick):
            correct = int(actual_pick) <= parsed["top_n"]
            notes_parts.append(
                f"Claimed top-{parsed['top_n']}, actual #{int(actual_pick)}"
            )
        elif "round_number" in parsed and pd.notna(actual_round):
            correct = int(actual_round) == parsed["round_number"]
            notes_parts.append(
                f"Claimed Round {parsed['round_number']}, actual Round {int(actual_round)}"
            )
        else:
            # Can't determine specific claim — void
            logger.info(
                f"  VOID {phash[:12]}… — can't parse specific claim: {claim[:60]}"
            )
            if not dry_run:
                void_prediction(phash, "unparseable_draft_claim", db=db)
            summary["voided"] += 1
            continue

        outcome_notes = "; ".join(notes_parts)
        status = "CORRECT" if correct else "INCORRECT"
        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")

        if not dry_run:
            resolve_binary(
                prediction_hash=phash,
                correct=correct,
                outcome_source="sportsdataio",
                outcome_notes=outcome_notes,
                db=db,
            )
        summary["resolved"] += 1

    logger.info(
        f"Draft resolution: {summary['resolved']} resolved, "
        f"{summary['voided']} voided, {summary['skipped']} skipped"
    )
    return summary


# ---------------------------------------------------------------------------
# Game outcome resolver
# ---------------------------------------------------------------------------

# NFL team abbreviation aliases (long name → abbreviation)
_TEAM_ALIASES: dict[str, str] = {
    "chiefs": "KC",
    "kansas city": "KC",
    "eagles": "PHI",
    "philadelphia": "PHI",
    "cowboys": "DAL",
    "dallas": "DAL",
    "patriots": "NE",
    "new england": "NE",
    "bills": "BUF",
    "buffalo": "BUF",
    "ravens": "BAL",
    "baltimore": "BAL",
    "49ers": "SF",
    "san francisco": "SF",
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
    "titans": "TEN",
    "tennessee": "TEN",
    "raiders": "LV",
    "las vegas": "LV",
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
    "buccaneers": "TB",
    "tampa bay": "TB",
    "commanders": "WAS",
    "washington": "WAS",
    "falcons": "ATL",
    "atlanta": "ATL",
    "panthers": "CAR",
    "carolina": "CAR",
    "saints": "NO",
    "new orleans": "NO",
    "cardinals": "ARI",
    "arizona": "ARI",
    "packers": "GB",
    "green bay": "GB",
}


def _normalize_team(name: str) -> Optional[str]:
    """Map a team name/nickname to its SportsData.io abbreviation."""
    name_lower = name.lower().strip()
    # Direct abbreviation match (e.g. "KC", "PHI")
    for alias, abbr in _TEAM_ALIASES.items():
        if alias in name_lower:
            return abbr
    # Already an abbreviation?
    if len(name_lower) <= 3:
        return name.upper()
    return None


def _extract_game_claim(claim: str) -> dict:
    """
    Parse a game_outcome claim to extract structured components.
    Returns dict with keys: team_a, team_b, season_year, win_prediction (bool or None),
    playoff_prediction (bool or None), team_focus.
    """
    claim_lower = claim.lower()
    result: dict = {}

    # Extract season year
    year_match = re.search(r"20\d{2}", claim)
    if year_match:
        result["season_year"] = int(year_match.group())

    # Win/defeat prediction: "Chiefs beat/defeat/top Eagles"
    win_patterns = [
        r"([a-z ]+?)\s+(?:will\s+)?(?:beat|defeat|top|win against|beat out)\s+(?:the\s+)?([a-z ]+?)(?:\s+in|\s+during|\s*$)",
        r"([a-z ]+?)\s+(?:over|vs\.?)\s+([a-z ]+?)(?:\s+in|\s*$)",
    ]
    for pattern in win_patterns:
        m = re.search(pattern, claim_lower)
        if m:
            team_a = _normalize_team(m.group(1).strip())
            team_b = _normalize_team(m.group(2).strip())
            if team_a and team_b:
                result["team_a"] = team_a
                result["team_b"] = team_b
                result["win_prediction"] = True  # team_a beats team_b
                break

    # Playoff prediction: "Bears will make playoffs" / "Bears miss playoffs"
    playoff_make = re.search(
        r"([a-z ]+?)\s+(?:will\s+)?(?:make|reach|qualify for|get to)\s+(?:the\s+)?playoffs",
        claim_lower,
    )
    if playoff_make:
        team = _normalize_team(playoff_make.group(1).strip())
        if team:
            result["team_focus"] = team
            result["playoff_prediction"] = True

    playoff_miss = re.search(
        r"([a-z ]+?)\s+(?:will\s+)?(?:miss|fail to make|not make)\s+(?:the\s+)?playoffs",
        claim_lower,
    )
    if playoff_miss:
        team = _normalize_team(playoff_miss.group(1).strip())
        if team:
            result["team_focus"] = team
            result["playoff_prediction"] = False

    # Super Bowl win: "Chiefs win Super Bowl"
    sb_win = re.search(
        r"([a-z ]+?)\s+(?:will\s+)?win\s+(?:the\s+)?super bowl", claim_lower
    )
    if sb_win:
        team = _normalize_team(sb_win.group(1).strip())
        if team:
            result["team_focus"] = team
            result["super_bowl_win"] = True

    return result


def _load_game_scores(db: DBManager, season_year: int) -> pd.DataFrame:
    """
    Load game scores for a season from bronze_sportsdataio_scores.
    Returns empty DataFrame if table doesn't exist.
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    query = f"""
        SELECT
            HomeTeam, AwayTeam, Season, Week,
            HomeScore, AwayScore,
            IsPlayoffGame
        FROM `{project_id}.nfl_dead_money.bronze_sportsdataio_scores`
        WHERE Season = {season_year}
          AND HomeScore IS NOT NULL
          AND AwayScore IS NOT NULL
    """
    try:
        return db.fetch_df(query)
    except (NotFound, Exception) as e:
        logger.warning(f"Game scores not available (season {season_year}): {e}")
        return pd.DataFrame()


def resolve_game_outcomes(db: DBManager, dry_run: bool = False) -> dict:
    """
    Resolve game_outcome predictions against actual game results.
    Data source: bronze_sportsdataio_scores (HomeTeam, AwayTeam, HomeScore, AwayScore).
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport="NFL", db=db)
    game_preds = pending[pending["claim_category"] == "game_outcome"]

    if game_preds.empty:
        logger.info("No pending game_outcome predictions to resolve.")
        return summary

    current_year = pd.Timestamp.now().year
    # NFL regular season ends in January; postseason in February
    # Only resolve predictions for seasons that have fully concluded
    # (i.e. prior year, or current year after February)
    season_data_cache: dict[int, pd.DataFrame] = {}

    for _, pred in game_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        season_year = pred.get("season_year")

        if pd.isna(season_year):
            logger.info(f"  SKIP {phash[:12]}… — no season_year in metadata")
            summary["skipped"] += 1
            continue

        season_year = int(season_year)

        # NFL season YYYY ends with the Super Bowl in February of YYYY+1.
        # Only resolve if we are past February of season_year+1.
        season_end_year = season_year + 1
        now = pd.Timestamp.now()
        season_complete = now.year > season_end_year or (
            now.year == season_end_year and now.month > 2
        )
        if not season_complete:
            logger.info(f"  SKIP {phash[:12]}… — {season_year} season not complete")
            summary["skipped"] += 1
            continue

        parsed = _extract_game_claim(claim)
        if not parsed:
            logger.info(f"  SKIP {phash[:12]}… — can't parse game claim: {claim[:60]}")
            summary["skipped"] += 1
            continue

        # Load season data (cached per season)
        if season_year not in season_data_cache:
            season_data_cache[season_year] = _load_game_scores(db, season_year)
        scores_df = season_data_cache[season_year]

        if scores_df.empty:
            logger.info(f"  SKIP {phash[:12]}… — no game score data for {season_year}")
            summary["skipped"] += 1
            continue

        correct: Optional[bool] = None
        notes_parts: list[str] = []

        if "team_a" in parsed and "team_b" in parsed:
            # Head-to-head win prediction
            team_a, team_b = parsed["team_a"], parsed["team_b"]
            matchups = scores_df[
                ((scores_df["HomeTeam"] == team_a) & (scores_df["AwayTeam"] == team_b))
                | (
                    (scores_df["HomeTeam"] == team_b)
                    & (scores_df["AwayTeam"] == team_a)
                )
            ]
            if matchups.empty:
                logger.info(
                    f"  SKIP {phash[:12]}… — no {team_a} vs {team_b} games found"
                )
                summary["skipped"] += 1
                continue

            # Check if team_a won in any matchup (or most matchups if multiple)
            team_a_wins = 0
            team_b_wins = 0
            for _, game in matchups.iterrows():
                if game["HomeTeam"] == team_a:
                    if game["HomeScore"] > game["AwayScore"]:
                        team_a_wins += 1
                    else:
                        team_b_wins += 1
                else:
                    if game["AwayScore"] > game["HomeScore"]:
                        team_a_wins += 1
                    else:
                        team_b_wins += 1
            correct = team_a_wins > team_b_wins
            notes_parts.append(
                f"{team_a} vs {team_b}: {team_a} won {team_a_wins}, lost {team_b_wins}"
            )

        elif "team_focus" in parsed and "playoff_prediction" in parsed:
            # Playoff prediction
            team = parsed["team_focus"]
            expected_playoff = parsed["playoff_prediction"]
            playoff_games = scores_df[
                ((scores_df["HomeTeam"] == team) | (scores_df["AwayTeam"] == team))
                & (scores_df["IsPlayoffGame"] == True)  # noqa: E712
            ]
            actually_made_playoffs = len(playoff_games) > 0
            correct = actually_made_playoffs == expected_playoff
            notes_parts.append(
                f"{team} playoff: expected={'made' if expected_playoff else 'missed'}, "
                f"actual={'made' if actually_made_playoffs else 'missed'}"
            )

        elif "team_focus" in parsed and "super_bowl_win" in parsed:
            # Super Bowl win prediction
            team = parsed["team_focus"]
            sb_games = scores_df[
                ((scores_df["HomeTeam"] == team) | (scores_df["AwayTeam"] == team))
                & (scores_df["IsPlayoffGame"] == True)  # noqa: E712
            ]
            if sb_games.empty:
                summary["skipped"] += 1
                continue
            # Super Bowl is the last playoff game; check if team won it
            last_game = sb_games.iloc[-1]
            if last_game["HomeTeam"] == team:
                correct = last_game["HomeScore"] > last_game["AwayScore"]
            else:
                correct = last_game["AwayScore"] > last_game["HomeScore"]
            notes_parts.append(f"{team} Super Bowl win: {correct}")

        else:
            logger.info(
                f"  VOID {phash[:12]}… — can't resolve game claim: {claim[:60]}"
            )
            if not dry_run:
                void_prediction(phash, "unparseable_game_claim", db=db)
            summary["voided"] += 1
            continue

        if correct is None:
            summary["skipped"] += 1
            continue

        outcome_notes = "; ".join(notes_parts)
        status = "CORRECT" if correct else "INCORRECT"
        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")

        if not dry_run:
            resolve_binary(
                prediction_hash=phash,
                correct=correct,
                outcome_source="sportsdataio_scores",
                outcome_notes=outcome_notes,
                db=db,
            )
        summary["resolved"] += 1

    logger.info(
        f"Game outcome resolution: {summary['resolved']} resolved, "
        f"{summary['voided']} voided, {summary['skipped']} skipped"
    )
    return summary


# ---------------------------------------------------------------------------
# Player performance resolver
# ---------------------------------------------------------------------------

# Mapping from common stat phrases → column names in bronze_sportsdataio_player_season_stats
_STAT_ALIASES: dict[str, str] = {
    "passing yards": "PassingYards",
    "passing yard": "PassingYards",
    "pass yards": "PassingYards",
    "passing touchdowns": "PassingTouchdowns",
    "passing tds": "PassingTouchdowns",
    "passing td": "PassingTouchdowns",
    "tds": "PassingTouchdowns",  # default to passing (resolved by position context)
    "interceptions": "Interceptions",
    "rushing yards": "RushingYards",
    "rushing yard": "RushingYards",
    "rush yards": "RushingYards",
    "rushes for": "RushingYards",
    "rush for": "RushingYards",
    "rushing touchdowns": "RushingTouchdowns",
    "rushing tds": "RushingTouchdowns",
    "receiving yards": "ReceivingYards",
    "receiving yard": "ReceivingYards",
    "rec yards": "ReceivingYards",
    "receiving touchdowns": "ReceivingTouchdowns",
    "receiving tds": "ReceivingTouchdowns",
    "receptions": "Receptions",
    "catches": "Receptions",
    "sacks": "Sacks",
    "tackles": "Tackles",
}


def _extract_player_stat_claim(claim: str) -> dict:
    """
    Parse a player_performance claim to extract structured components.
    Returns dict with keys: player_name, stat_column, threshold, operator, season_year.
    operator is ">=" (at least), ">" (more than), "==" (exactly), "<=" (at most).
    """
    claim_lower = claim.lower()
    result: dict = {}

    # Extract season year
    year_match = re.search(r"20\d{2}", claim)
    if year_match:
        result["season_year"] = int(year_match.group())

    # Extract numeric threshold — patterns like "40+", "40 or more", "at least 40",
    # "over 40", "more than 40", "1,500", "1500"
    threshold_patterns = [
        (r"(?:at least|minimum)\s+([\d,]+)\+?", ">="),
        (r"(?:over|more than|greater than)\s+([\d,]+)", ">"),
        (r"([\d,]+)\+\s*(?:or more)?", ">="),
        (r"([\d,]+)\s+or more", ">="),
        (r"fewer than\s+([\d,]+)", "<"),
        (r"under\s+([\d,]+)", "<"),
        (r"at most\s+([\d,]+)", "<="),
        (r"exactly\s+([\d,]+)", "=="),
        (r"(?:at least\s+)?([\d,]+)", ">="),  # bare number — assume "at least"
    ]
    for pattern, operator in threshold_patterns:
        m = re.search(pattern, claim_lower)
        if m:
            val_str = m.group(1).replace(",", "")
            try:
                result["threshold"] = int(val_str)
                result["operator"] = operator
                break
            except ValueError:
                continue

    # Extract stat category
    for phrase, col in sorted(_STAT_ALIASES.items(), key=lambda x: -len(x[0])):
        if phrase in claim_lower:
            result["stat_column"] = col
            break

    # Extract player name — heuristic: words before the verb "will"/"throws"/"records"
    # Look for capitalized words at start (common for player names)
    name_match = re.match(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s+(?:will|throws?|records?|rushes?|catches?|has|posts?)",
        claim,
    )
    if name_match:
        result["player_name"] = name_match.group(1)

    return result


def _load_player_season_stats(db: DBManager, season_year: int) -> pd.DataFrame:
    """
    Load player season stats from bronze_sportsdataio_player_season_stats.
    Returns empty DataFrame if table doesn't exist.
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    query = f"""
        SELECT
            Name, Season,
            PassingYards, PassingTouchdowns, Interceptions,
            RushingYards, RushingTouchdowns,
            ReceivingYards, ReceivingTouchdowns, Receptions,
            Sacks, Tackles
        FROM `{project_id}.nfl_dead_money.bronze_sportsdataio_player_season_stats`
        WHERE Season = {season_year}
    """
    try:
        return db.fetch_df(query)
    except (NotFound, Exception) as e:
        logger.warning(f"Player season stats not available (season {season_year}): {e}")
        return pd.DataFrame()


def resolve_player_performance(db: DBManager, dry_run: bool = False) -> dict:
    """
    Resolve player_performance predictions against actual season stats.
    Data source: bronze_sportsdataio_player_season_stats.
    Only resolves predictions for completed seasons.
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport="NFL", db=db)
    perf_preds = pending[pending["claim_category"] == "player_performance"]

    if perf_preds.empty:
        logger.info("No pending player_performance predictions to resolve.")
        return summary

    current_year = pd.Timestamp.now().year
    stats_cache: dict[int, pd.DataFrame] = {}

    for _, pred in perf_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        season_year = pred.get("season_year")

        if pd.isna(season_year):
            logger.info(f"  SKIP {phash[:12]}… — no season_year")
            summary["skipped"] += 1
            continue

        season_year = int(season_year)

        # NFL season YYYY ends with the Super Bowl in February of YYYY+1.
        season_end_year = season_year + 1
        now = pd.Timestamp.now()
        season_complete = now.year > season_end_year or (
            now.year == season_end_year and now.month > 2
        )
        if not season_complete:
            logger.info(f"  SKIP {phash[:12]}… — {season_year} season not complete")
            summary["skipped"] += 1
            continue

        parsed = _extract_player_stat_claim(claim)

        if "stat_column" not in parsed or "threshold" not in parsed:
            logger.info(f"  VOID {phash[:12]}… — can't parse stat claim: {claim[:60]}")
            if not dry_run:
                void_prediction(phash, "unparseable_stat_claim", db=db)
            summary["voided"] += 1
            continue

        # Load stats (cached per season)
        if season_year not in stats_cache:
            stats_cache[season_year] = _load_player_season_stats(db, season_year)
        stats_df = stats_cache[season_year]

        if stats_df.empty:
            logger.info(
                f"  SKIP {phash[:12]}… — no player stats data for {season_year}"
            )
            summary["skipped"] += 1
            continue

        # Find the player
        player_name = parsed.get("player_name") or pred.get("target_player_name") or ""
        player_name_lower = _normalize_name(player_name)

        if not player_name_lower:
            logger.info(f"  SKIP {phash[:12]}… — no player name: {claim[:60]}")
            summary["skipped"] += 1
            continue

        stats_df["name_lower"] = stats_df["Name"].str.lower().str.strip()
        player_rows = stats_df[
            stats_df["name_lower"].str.contains(player_name_lower, na=False)
        ]

        if player_rows.empty:
            logger.info(
                f"  SKIP {phash[:12]}… — player '{player_name}' not found in {season_year} stats"
            )
            summary["skipped"] += 1
            continue

        player_row = player_rows.iloc[0]
        stat_col = parsed["stat_column"]
        actual_val = player_row.get(stat_col)

        if pd.isna(actual_val):
            logger.info(f"  SKIP {phash[:12]}… — {stat_col} is NULL for {player_name}")
            summary["skipped"] += 1
            continue

        actual_val = float(actual_val)
        threshold = float(parsed["threshold"])
        operator = parsed["operator"]

        op_map = {
            ">=": actual_val >= threshold,
            ">": actual_val > threshold,
            "==": actual_val == threshold,
            "<=": actual_val <= threshold,
            "<": actual_val < threshold,
        }
        correct = op_map.get(operator, False)

        outcome_notes = (
            f"{player_name} {stat_col}: actual={actual_val:.0f}, "
            f"claimed {operator}{threshold:.0f} in {season_year}"
        )
        status = "CORRECT" if correct else "INCORRECT"
        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")

        if not dry_run:
            resolve_binary(
                prediction_hash=phash,
                correct=correct,
                outcome_source="sportsdataio_player_stats",
                outcome_notes=outcome_notes,
                db=db,
            )
        summary["resolved"] += 1

    logger.info(
        f"Player performance resolution: {summary['resolved']} resolved, "
        f"{summary['voided']} voided, {summary['skipped']} skipped"
    )
    return summary


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def resolve_all(
    category: Optional[str] = None,
    dry_run: bool = False,
    db: Optional[DBManager] = None,
) -> dict:
    """Run all resolution passes. Returns combined summary."""
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        summaries = {}

        if not category or category == "draft_pick":
            summaries["draft_pick"] = resolve_draft_picks(db, dry_run=dry_run)

        if not category or category == "game_outcome":
            summaries["game_outcome"] = resolve_game_outcomes(db, dry_run=dry_run)

        if not category or category == "player_performance":
            summaries["player_performance"] = resolve_player_performance(
                db, dry_run=dry_run
            )

        # Combined summary
        total = {
            "checked": sum(s["checked"] for s in summaries.values()),
            "resolved": sum(s["resolved"] for s in summaries.values()),
            "voided": sum(s["voided"] for s in summaries.values()),
            "skipped": sum(s["skipped"] for s in summaries.values()),
        }

        logger.info(
            f"Resolution complete: {total['resolved']} resolved, "
            f"{total['voided']} voided, {total['skipped']} skipped "
            f"out of {total['checked']} checked"
        )
        return total
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily Prediction Resolver")
    parser.add_argument(
        "--category",
        choices=["draft_pick", "game_outcome", "player_performance"],
        help="Resolve only a specific category",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result = resolve_all(category=args.category, dry_run=args.dry_run)
    import json

    print(json.dumps(result, indent=2))

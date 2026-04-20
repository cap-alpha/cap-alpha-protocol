"""
Daily Prediction Resolution Engine (Issue #169)

Matches PENDING predictions from gold_layer.prediction_ledger against actual
NFL outcomes to automatically score pundit accuracy.

Handles three easy-win categories:
  1. draft_pick — resolved against bronze_sportsdataio_players draft data
  2. game_outcome — resolved against silver_pfr_game_logs (future)
  3. player_performance for completed seasons — resolved against season stats (future)

Usage (inside Docker):
    python -m src.resolve_daily                     # resolve all pending
    python -m src.resolve_daily --category draft_pick  # single category
    python -m src.resolve_daily --dry-run           # preview without writing
"""

import argparse
import logging
import os
import re
from typing import Optional

import pandas as pd

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
    name = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv)$', '', name)
    # Remove periods from initials
    name = name.replace('.', '')
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
        'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
        'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
    }
    pick_match = re.search(r'(?:no\.?\s*|#)(\d+)\s*(?:overall\s*)?pick', claim_lower)
    if pick_match:
        result['pick_number'] = int(pick_match.group(1))
    else:
        for word, num in ordinals.items():
            if f'{word} overall' in claim_lower or f'{word} pick' in claim_lower:
                result['pick_number'] = num
                break

    # Extract "top-N pick"
    top_match = re.search(r'top[- ](\d+)\s*pick', claim_lower)
    if top_match:
        result['top_n'] = int(top_match.group(1))

    # Extract "Round 1" or "first round"
    round_match = re.search(r'round\s*(\d+)', claim_lower)
    if round_match:
        result['round_number'] = int(round_match.group(1))
    elif 'first round' in claim_lower:
        result['round_number'] = 1

    # Extract draft year
    year_match = re.search(r'20\d{2}', claim)
    if year_match:
        result['draft_year'] = int(year_match.group())

    return result


def resolve_draft_picks(
    db: DBManager, dry_run: bool = False
) -> dict:
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

        # Check if this draft has actually happened
        current_year = pd.Timestamp.now().year
        # NFL draft is in late April; if we're past May of draft_year, it's happened
        draft_completed = (
            draft_year < current_year
            or (draft_year == current_year and pd.Timestamp.now().month > 5)
        )

        if not draft_completed:
            logger.info(
                f"  SKIP {phash[:12]}… — {draft_year} draft not yet completed"
            )
            summary["skipped"] += 1
            continue

        # Find the player in draft data
        norm_name = _normalize_name(player_name) if player_name else ""
        player_matches = draft_data[
            draft_data["name_lower"].str.contains(norm_name, na=False)
        ] if norm_name and norm_name != "none" else pd.DataFrame()

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

        # Now evaluate the claim
        correct = None
        notes_parts = [f"Actual: {actual_name} was pick #{actual_pick} (Round {actual_round}) by {actual_team}"]

        if "pick_number" in parsed:
            correct = int(actual_pick) == parsed["pick_number"]
            notes_parts.append(f"Claimed pick #{parsed['pick_number']}, actual #{actual_pick}")
        elif "top_n" in parsed:
            correct = int(actual_pick) <= parsed["top_n"]
            notes_parts.append(f"Claimed top-{parsed['top_n']}, actual #{actual_pick}")
        elif "round_number" in parsed:
            correct = int(actual_round) == parsed["round_number"]
            notes_parts.append(f"Claimed Round {parsed['round_number']}, actual Round {actual_round}")
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

        # Future: game_outcome, player_performance resolvers

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

"""
Daily Prediction Resolution Engine (Issue #169, #191)

Matches PENDING predictions from gold_layer.prediction_ledger against actual
NFL outcomes to automatically score pundit accuracy.

Handles five categories:
  1. draft_pick — resolved against bronze_sportsdataio_players draft data
  2. game_outcome — resolved against bronze_sportsdataio_scores
  3. player_performance — resolved against bronze_nflverse_player_stats (free, no API key)
  4. award_prediction — resolved against pipeline/config/nfl_awards_<season>.yaml
  5. fa_signing — resolved against bronze_sportsdataio_players current team data

Usage (inside Docker):
    python -m src.resolve_daily                           # resolve all pending
    python -m src.resolve_daily --category award_prediction  # single category
    python -m src.resolve_daily --dry-run                 # preview without writing
"""

import argparse
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from src.db_manager import DBManager
from src.resolution_engine import (
    VoidReason,
    get_pending_predictions,
    resolve_binary,
    void_prediction,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# silver_v2_claims dual-write helpers (Issue #615)
# ---------------------------------------------------------------------------

# Maps resolve_daily outcome_source strings → silver_v2 resolution_method_id slugs
_OUTCOME_SOURCE_TO_METHOD_ID: dict[str, str] = {
    "sportsdataio": "nfl_draft_pick_sportsdataio",
    "draft_board": "nfl_draft_pick_sportsdataio",
    "nflverse_draft_picks": "nfl_draft_pick_sportsdataio",
    "sportsdataio_scores": "nfl_game_outcome_scores",
    "nflverse_player_stats": "nfl_player_perf_nflverse",
    "nfl_awards_config": "nfl_award_config",
    "sportsdataio_rosters": "nfl_fa_signing_rosters",
}


def _silver_v2_resolution_method_id(outcome_source: Optional[str]) -> str:
    """Map a gold_layer outcome_source string to a silver_v2 resolution_method_id."""
    return _OUTCOME_SOURCE_TO_METHOD_ID.get(
        outcome_source or "", "nfl_draft_pick_sportsdataio"
    )


def _dual_write_silver_v2_resolution(
    *,
    prediction_hash: str,
    outcome: str,
    outcome_confidence: float,
    evidence: dict,
    resolution_method_id: str,
    db: DBManager,
) -> None:
    """
    Append one row to silver_v2_claims.resolution.

    This is a best-effort write: errors are logged but never re-raised so that
    v2 failures cannot break the existing v1 gold_layer write path.

    The cryptographic chain is append-only: we fetch the latest this_hash for
    the given claim_id and use it as prev_hash. For the first resolution the
    prev_hash is an empty string (chain root).
    """
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            logger.warning("dual_write_silver_v2: GCP_PROJECT_ID not set, skipping")
            return

        resolution_table = f"`{project_id}.silver_v2_claims.resolution`"

        # Fetch the latest this_hash for prev_hash chaining
        chain_query = f"""
            SELECT this_hash
            FROM {resolution_table}
            WHERE claim_id = @claim_id
            ORDER BY resolved_at DESC
            LIMIT 1
        """
        try:
            chain_rows = db.fetch_df(
                chain_query,
                query_parameters=[
                    bigquery.ScalarQueryParameter("claim_id", "STRING", prediction_hash)
                ],
            )
            prev_hash = (
                str(chain_rows.iloc[0]["this_hash"]) if not chain_rows.empty else ""
            )
        except Exception as chain_err:
            logger.debug(
                f"dual_write_silver_v2: could not fetch prev_hash for "
                f"{prediction_hash[:16]}…: {chain_err}"
            )
            prev_hash = ""

        resolution_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        evidence_json = json.dumps(evidence, separators=(",", ":"))

        # Compute this_hash as SHA-256 of the canonical payload
        payload_str = json.dumps(
            {
                "resolution_id": resolution_id,
                "claim_id": prediction_hash,
                "resolved_at": now.isoformat(),
                "outcome": outcome,
                "outcome_confidence": outcome_confidence,
                "evidence": evidence,
                "resolution_method_id": resolution_method_id,
                "prev_hash": prev_hash,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        this_hash = hashlib.sha256(payload_str.encode()).hexdigest()

        insert_sql = f"""
            INSERT INTO {resolution_table}
              (resolution_id, claim_id, resolved_at, outcome, outcome_confidence,
               evidence, resolution_method_id, prev_hash, this_hash, notes)
            VALUES
              (@resolution_id, @claim_id, @resolved_at, @outcome, @outcome_confidence,
               PARSE_JSON(@evidence_json), @resolution_method_id, @prev_hash, @this_hash,
               NULL)
        """
        db.execute(
            insert_sql,
            query_parameters=[
                bigquery.ScalarQueryParameter("resolution_id", "STRING", resolution_id),
                bigquery.ScalarQueryParameter("claim_id", "STRING", prediction_hash),
                bigquery.ScalarQueryParameter("resolved_at", "TIMESTAMP", now),
                bigquery.ScalarQueryParameter("outcome", "STRING", outcome),
                bigquery.ScalarQueryParameter(
                    "outcome_confidence", "FLOAT64", outcome_confidence
                ),
                bigquery.ScalarQueryParameter("evidence_json", "STRING", evidence_json),
                bigquery.ScalarQueryParameter(
                    "resolution_method_id", "STRING", resolution_method_id
                ),
                bigquery.ScalarQueryParameter("prev_hash", "STRING", prev_hash),
                bigquery.ScalarQueryParameter("this_hash", "STRING", this_hash),
            ],
        )
        logger.info(
            f"dual_write_silver_v2: wrote resolution {resolution_id[:8]}… "
            f"for claim {prediction_hash[:16]}… outcome={outcome}"
        )
    except Exception as exc:
        logger.error(
            f"dual_write_silver_v2: failed to write silver_v2_claims.resolution "
            f"for {prediction_hash[:16]}… — {exc} (v1 write unaffected)"
        )


def _resolve_binary_with_dual_write(
    prediction_hash: str,
    correct: bool,
    outcome_source: str,
    outcome_reference_id: Optional[str] = None,
    outcome_notes: Optional[str] = None,
    db: Optional[DBManager] = None,
) -> None:
    """
    Thin wrapper: calls resolve_binary (gold_layer v1 write), then dual-writes
    to silver_v2_claims.resolution.  v2 failure is logged but never raised.
    """
    resolve_binary(
        prediction_hash=prediction_hash,
        correct=correct,
        outcome_source=outcome_source,
        outcome_reference_id=outcome_reference_id,
        outcome_notes=outcome_notes,
        db=db,
    )
    if db is not None:
        outcome_str = "true" if correct else "false"
        _dual_write_silver_v2_resolution(
            prediction_hash=prediction_hash,
            outcome=outcome_str,
            outcome_confidence=1.0,
            evidence={"source": outcome_source, "notes": outcome_notes or ""},
            resolution_method_id=_silver_v2_resolution_method_id(outcome_source),
            db=db,
        )


def _void_prediction_with_dual_write(
    prediction_hash: str,
    reason: "str | VoidReason",
    db: Optional[DBManager] = None,
) -> None:
    """
    Thin wrapper: calls void_prediction (gold_layer v1 write), then dual-writes
    outcome='unresolvable' to silver_v2_claims.resolution.  v2 failure is logged
    but never raised.
    """
    void_prediction(prediction_hash=prediction_hash, reason=reason, db=db)
    if db is not None:
        _dual_write_silver_v2_resolution(
            prediction_hash=prediction_hash,
            outcome="unresolvable",
            outcome_confidence=1.0,
            evidence={"reason": reason},
            resolution_method_id="nfl_draft_pick_sportsdataio",
            db=db,
        )


# ---------------------------------------------------------------------------
# Draft pick resolver
# ---------------------------------------------------------------------------


def _load_draft_data(db: DBManager) -> pd.DataFrame:
    """Load draft pick data from bronze_sportsdataio_players."""
    project_id = os.environ["GCP_PROJECT_ID"]
    query = f"""
        SELECT
            Name,
            CollegeDraftYear AS draft_year,
            CollegeDraftRound AS draft_round,
            CollegeDraftPick AS draft_pick,
            CollegeDraftTeam AS draft_team,
            Team AS current_team,
            IsUndraftedFreeAgent AS undrafted
        FROM `{project_id}.nfl_dead_money.bronze_sportsdataio_players`
        WHERE CollegeDraftYear IS NOT NULL
    """
    df = db.fetch_df(query)
    # HIGH-3 (Issue #1167 adversarial review): normalize the board side the
    # same way the claim side is normalized. Previously this was raw
    # `LOWER(Name)`, so a claim's normalized name ("J.J. McCarthy" ->
    # "jj mccarthy", periods stripped) never matched the board's raw
    # "j.j. mccarthy" via substring containment — a real match silently
    # missed, which for a past draft year fed straight into the terminal
    # "not found" INCORRECT path.
    if df.empty:
        df["name_lower"] = pd.Series(dtype="object")
    else:
        df["name_lower"] = df["Name"].apply(_normalize_name)
    return df


def _normalize_name(name: str) -> str:
    """Normalize player name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common suffixes
    name = re.sub(r"\s+(jr\.?|sr\.?|ii|iii|iv)$", "", name)
    # Remove periods from initials
    name = name.replace(".", "")
    return name


# Ordinal number words — "first overall pick", "seventeenth pick".
_ORDINAL_WORDS: dict[str, int] = {
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
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
}
# Cardinal number words — "go at five overall", "pick number seven"
# (Issue #1167: _extract_draft_claim previously only understood ordinals
# like "fifth"/"seventh", so cardinal phrasing silently fell through to
# an unparseable claim.)
_CARDINAL_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}
# Longest-word-first so a short number word ("seven") can never win a match
# that should belong to a longer one that contains it as a prefix
# ("seventeen") before the word-boundary guard even gets a chance to run.
_NUMBER_WORDS_BY_LENGTH_DESC: list[tuple[str, int]] = sorted(
    {**_ORDINAL_WORDS, **_CARDINAL_WORDS}.items(),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def _extract_draft_claim(claim: str) -> dict:
    """
    Parse a draft_pick claim to extract structured components.
    Returns dict with keys: player_name, pick_number, round_number, team, draft_year
    """
    claim_lower = claim.lower()
    result = {}

    # Match: "#7 pick", "No. 7 pick", "No. 7 overall pick", "#7 overall",
    # "drafted 7th overall", "drafted 39th overall", "pick #7", "drafted #7",
    # "pick number 7", plus the original "(N) overall pick" variants.
    pick_match = re.search(
        r"(?:no\.?\s*|#|pick\s*(?:number\s*)?#?|drafted\s+#?)(\d+)(?:st|nd|rd|th)?\s*(?:overall|pick)",
        claim_lower,
    )
    if not pick_match:
        # Bare "pick number N" with no trailing "overall"/"pick" keyword.
        pick_match = re.search(r"pick\s+number\s+(\d+)\b", claim_lower)
    if not pick_match:
        # Bare "#N overall" or "Nth overall" without a leading keyword.
        pick_match = re.search(r"#?(\d+)(?:st|nd|rd|th)?\s+overall", claim_lower)
    if not pick_match:
        # "with the Nth pick in/of/by" or "at pick N" or "with pick No. N"
        pick_match = re.search(
            r"(?:with\s+(?:the\s+)?|at\s+)(?:pick\s+(?:no\.?\s*)?)?(\d+)(?:st|nd|rd|th)?\s+pick\b",
            claim_lower,
        )
    if not pick_match:
        # "with pick No. N" or "by pick No. N" (no trailing keyword)
        pick_match = re.search(r"(?:with|by|at)\s+pick\s+no\.?\s*(\d+)", claim_lower)
    if not pick_match:
        # "at No. N" or "by No. N" — standalone pick number reference
        pick_match = re.search(r"(?:at|by)\s+no\.?\s*(\d+)\b", claim_lower)
    if not pick_match:
        # "drafted #N by" — bare #N followed by "by" team (no overall/pick after)
        pick_match = re.search(r"drafted\s+#(\d+)\s+by\b", claim_lower)
    if pick_match:
        result["pick_number"] = int(pick_match.group(1))
    else:
        # HIGH-4 (Issue #1167 adversarial review): the previous version used
        # plain substring `in` checks with no word boundaries, which misfired
        # in several concrete ways:
        #   - "pick number seventeen" -> matched "seven" as a substring of
        #     "seventeen" and returned 7 instead of 17.
        #   - "four picks in the top 100" -> "four pick" is a literal
        #     substring of "four picks", so the plural got silently treated
        #     as a singular pick-number claim and returned 4.
        #   - "twenty-five overall" -> "five overall" is a substring of
        #     "twenty-five overall", returning 5 for what is actually the
        #     unsupported compound number 25.
        # Fixed with a word-boundary regex that additionally: rejects a
        # match preceded by a hyphen or word character (blocks hyphenated
        # compounds like "twenty-five"), and requires "pick" to be followed
        # by a boundary (blocks "picks" pluralization from satisfying a
        # singular pick-number pattern). When ambiguous, no match is
        # produced at all — the claim then either falls through to a later
        # extraction rule or is left unparsed rather than guessed wrong.
        for word, num in _NUMBER_WORDS_BY_LENGTH_DESC:
            guarded_word = r"(?<![\w-])" + re.escape(word) + r"(?![\w-])"
            if (
                re.search(guarded_word + r"\s+overall\b", claim_lower)
                or re.search(guarded_word + r"\s+pick\b", claim_lower)
                or re.search(r"pick\s+number\s+" + guarded_word, claim_lower)
            ):
                result["pick_number"] = num
                break

    # Pattern 2: ordinal suffix — "16th overall", "3rd overall pick"
    if "pick_number" not in result:
        ordinal_match = re.search(
            r"(\d+)(?:st|nd|rd|th)\s+(?:overall|pick)", claim_lower
        )
        if ordinal_match:
            result["pick_number"] = int(ordinal_match.group(1))

    # Pattern 3: "at No. N" / "No. N overall" / "No. N in the" / "No. N by"
    if "pick_number" not in result:
        no_match = re.search(
            r"(?:at\s+)?no\.?\s*(\d+)\s*(?:overall|in\s+the|by\s+)", claim_lower
        )
        if no_match:
            result["pick_number"] = int(no_match.group(1))

    # Extract "top-N pick" or "within the first N picks"
    top_match = re.search(r"top[- ](\d+)\s*pick", claim_lower)
    if top_match:
        result["top_n"] = int(top_match.group(1))
    if "top_n" not in result:
        within_match = re.search(
            r"within\s+the\s+(?:first\s+)?(?:top\s+)?(\d+)\s+picks?", claim_lower
        )
        if within_match:
            result["top_n"] = int(within_match.group(1))

    # Extract "Round 1" or "first round"
    round_match = re.search(r"round\s*(\d+)", claim_lower)
    if round_match:
        result["round_number"] = int(round_match.group(1))
    elif "first round" in claim_lower or "first-round" in claim_lower:
        result["round_number"] = 1

    # Extract draft year. Prefer a year that appears next to the word
    # "draft" (MEDIUM-8, Issue #1167 adversarial review) — the previous bare
    # `20\d{2}` search grabbed the *first* four-digit year anywhere in the
    # claim, which can be a wrong-but-plausible year from unrelated context
    # (e.g. "...in the 2021 recruiting class" is not a 2021 draft claim at
    # all). Falls back to the bare first-year-anywhere match to preserve
    # existing behavior for claims that never mention "draft" explicitly.
    year_match = re.search(r"(20\d{2})\s+(?:nfl\s+)?draft", claim_lower)
    if not year_match:
        year_match = re.search(r"draft\D{0,10}(20\d{2})", claim_lower)
    if year_match:
        result["draft_year"] = int(year_match.group(1))
    else:
        bare_year_match = re.search(r"20\d{2}", claim)
        if bare_year_match:
            result["draft_year"] = int(bare_year_match.group())

    return result


# NFL team abbreviation mapping for claim parsing
_TEAM_PATTERNS = {
    "raiders": "LV",
    "giants": "NYG",
    "jets": "NYJ",
    "cardinals": "ARI",
    "titans": "TEN",
    "chiefs": "KC",
    "commanders": "WAS",
    "saints": "NO",
    "browns": "CLE",
    "cowboys": "DAL",
    "dolphins": "MIA",
    "rams": "LAR",
    "ravens": "BAL",
    "buccaneers": "TB",
    "bucs": "TB",
    "lions": "DET",
    "vikings": "MIN",
    "panthers": "CAR",
    "eagles": "PHI",
    "steelers": "PIT",
    "chargers": "LAC",
    "bears": "CHI",
    "texans": "HOU",
    "patriots": "NE",
    "49ers": "SF",
    "bills": "BUF",
    "bengals": "CIN",
    "seahawks": "SEA",
    "packers": "GB",
    "broncos": "DEN",
    "jaguars": "JAX",
    "falcons": "ATL",
    "colts": "IND",
    "washington": "WAS",
    "detroit": "DET",
    "minnesota": "MIN",
}


def _resolve_team_claim(claim, parsed, year_draft_data, phash, db, dry_run):
    """Resolve team-level draft claims like 'Giants will have two top-10 picks'."""
    claim_lower = claim.lower()

    # Find team in claim
    team_abbr = None
    for pattern, abbr in _TEAM_PATTERNS.items():
        if pattern in claim_lower:
            team_abbr = abbr
            break

    if not team_abbr:
        return None  # Can't find a team

    team_picks = year_draft_data[year_draft_data["draft_team"] == team_abbr]

    # "will pick a quarterback in Round 1" or "picking a quarterback"
    if "quarterback" in claim_lower or " qb " in claim_lower:
        # Check if team drafted a QB (check Position field if available)
        # For now, just check if they had any pick
        if not team_picks.empty:
            notes = f"{team_abbr} had {len(team_picks)} pick(s) in this round"
            logger.info(f"  TEAM {phash[:12]}… — {notes} (needs manual QB check)")
        return None  # Can't verify position from draft data alone

    # "will have two picks in the top 10" or "pair of top-10 selections"
    top_n_match = re.search(r"(two|2|pair|three|3)\s+.*top[- ](\d+)", claim_lower)
    if top_n_match:
        count_word = top_n_match.group(1)
        top_n = int(top_n_match.group(2))
        expected_count = {"two": 2, "2": 2, "pair": 2, "three": 3, "3": 3}.get(
            count_word, 2
        )
        actual_top = team_picks[team_picks["draft_pick"] <= top_n]
        correct = len(actual_top) >= expected_count
        notes = f"{team_abbr} had {len(actual_top)} pick(s) in top {top_n} (expected {expected_count})"
        logger.info(
            f"  {'CORRECT' if correct else 'INCORRECT'} {phash[:12]}… — {notes}"
        )
        if not dry_run:
            _resolve_binary_with_dual_write(
                phash, correct, outcome_source="draft_board", outcome_notes=notes, db=db
            )
        return "resolved"

    return None  # Couldn't parse team claim pattern


def _infer_season_year_from_ingestion(
    ingestion_timestamp, content_published_at=None
) -> Optional[int]:
    """
    Read-time fallback for predictions with NULL season_year (Issue #1167).

    game_outcome and player_performance both hard-require season_year and
    hard-skip forever when it's missing (831 rows ingested 2026-04-24 ->
    2026-05-05 are stuck this way). Rather than leave them permanently
    unresolvable, infer a season_year from when the claim was made so they
    can enter the normal season-completion gate.

    MEDIUM-6 (Issue #1167 adversarial review): prefers `content_published_at`
    — the underlying article/pundit-statement publish date — over
    `ingestion_timestamp` when both are available. Ingestion time only tells
    us when *our pipeline* scraped the claim, which can lag well behind when
    the pundit actually said it; the publish date is what the "Jan/Feb is
    ambiguous" reasoning below is actually about.

    NFL season YYYY runs Sept YYYY -> the Super Bowl in Feb YYYY+1, and
    pundit predictions are almost always made about the season that is
    upcoming or in progress:
      - Made Mar-Dec of year Y  -> discussing season Y
      - Made Jan/Feb of year Y  -> AMBIGUOUS: could be about season Y-1
        (still wrapping up, e.g. Super Bowl week) or an early look ahead at
        season Y. Previously this guessed Y-1 unconditionally; that's a
        real coin-flip, not a safe inference, so this now returns None
        (skip) for Jan/Feb rather than guess (Issue #1167 MEDIUM-6).

    This mirrors the season-boundary convention already used for the
    season-completion checks below (`now.month > 2`). It does not change
    behavior for rows that already carry an explicit season_year, and it
    does not force-resolve anything: an inferred season_year of, say, 2026
    still correctly waits at the season-completion gate until Feb 2027.

    Callers that resolve using an inferred value should tag `outcome_notes`
    with the source (e.g. "[season_year inferred from ingestion_timestamp]")
    so an inferred resolution can be told apart from an explicit one and
    reversed if the inference is later shown to be wrong.
    """
    ts = None
    if content_published_at is not None and pd.notna(content_published_at):
        ts = pd.Timestamp(content_published_at)
    elif ingestion_timestamp is not None and pd.notna(ingestion_timestamp):
        ts = pd.Timestamp(ingestion_timestamp)
    if ts is None:
        return None
    if ts.month in (1, 2):
        return None  # ambiguous — don't guess
    return ts.year


def _load_content_published_dates(db: DBManager, prediction_hashes: list) -> dict:
    """
    Best-effort lookup of the underlying article/content publish date for a
    batch of predictions (Issue #1167 MEDIUM-6), via the silver_v2_claims
    linkage: claim.legacy_prediction_hash -> claim.utterance_id ->
    raw_utterance.uttered_at.

    Most legacy gold_layer rows have no silver_v2 linkage yet (the two
    pipelines were only recently connected), so this returns an empty or
    partial dict for them — callers must fall back to ingestion_timestamp
    when a hash is absent from the result. Never raises: a lookup failure
    just means "no content date available," not a hard error.
    """
    if not prediction_hashes:
        return {}
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return {}
    try:
        df = db.fetch_df(
            f"""
            SELECT c.legacy_prediction_hash AS prediction_hash,
                   u.uttered_at AS content_published_at
            FROM `{project_id}.silver_v2_claims.claim` c
            JOIN `{project_id}.silver_v2_claims.raw_utterance` u
              ON u.utterance_id = c.utterance_id
            WHERE c.legacy_prediction_hash IN UNNEST(@hashes)
              AND u.uttered_at IS NOT NULL
            """,
            query_parameters=[
                bigquery.ArrayQueryParameter(
                    "hashes", "STRING", list(prediction_hashes)
                )
            ],
        )
    except Exception as exc:
        logger.debug(f"_load_content_published_dates: lookup failed (non-fatal): {exc}")
        return {}
    if df.empty:
        return {}
    return dict(zip(df["prediction_hash"], df["content_published_at"]))


def _filter_nfl_only(pending: pd.DataFrame) -> pd.DataFrame:
    """
    Log and drop any non-NFL predictions from a pending DataFrame.

    When new sport resolvers are added (e.g. NBA), remove the corresponding
    sport from this filter so those predictions are handled instead of skipped.
    """
    if "sport" not in pending.columns:
        return pending

    non_nfl = pending[pending["sport"].notna() & (pending["sport"] != "NFL")]
    for _, pred in non_nfl.iterrows():
        sport = pred["sport"]
        pred_id = pred["prediction_hash"][:12]
        logger.info(
            f"Skipping {sport} prediction {pred_id}… "
            f"— {sport} resolver not yet implemented"
        )
    return pending[pending["sport"].isna() | (pending["sport"] == "NFL")]


def _resolve_terminal_draft_incorrect(
    phash: str,
    notes: str,
    db: DBManager,
    dry_run: bool,
    outcome_source: str = "sportsdataio",
) -> None:
    """
    Record a terminal INCORRECT for a draft_pick prediction (Issue #1167).

    Once a draft year is in the past, "the player never shows up in the
    draft board" and "the player shows up with no assigned pick" are both
    final answers, not transient states waiting on more data. Before this
    fix both cases hard-skipped every single day forever — the resolver
    kept re-treating "not found" as "not resolved yet" instead of scoring
    the pundit's prediction as wrong (predicted drafted, but wasn't).

    Per the CRITICAL-1/CRITICAL-2 adversarial-review rework, callers must
    only reach this function after (a) the claim-shape gate
    (`_looks_like_draft_prediction`) confirms the claim is actually a draft
    position prediction, and (b) positive evidence of "undrafted" has been
    established from a source that does not shrink over time (the immutable
    nflverse draft-results history, or an explicit undrafted flag) — never
    from mere absence in the active-roster snapshot.
    """
    logger.info(f"  INCORRECT {phash[:12]}… — {notes}")
    if not dry_run:
        _resolve_binary_with_dual_write(
            prediction_hash=phash,
            correct=False,
            outcome_source=outcome_source,
            outcome_notes=notes,
            db=db,
        )


# Minimum number of rows a per-year draft board must have before we trust its
# absence signal for a terminal resolution (Issue #1167 CRITICAL-1). A real
# NFL draft runs ~255-262 picks; anything drastically smaller for a
# *concluded* year means a failed/partial ingest, not a small draft class —
# without this guard a dropped ingest could mass-resolve an entire draft
# class INCORRECT in a single pass.
_MIN_DRAFT_BOARD_SIZE = 200

# nflverse/Pro-Football-Reference team codes differ from the SportsDataIO /
# common broadcast abbreviations used elsewhere in this module (_TEAM_PATTERNS,
# _TEAM_ALIASES) for a handful of franchises. Translate so notes/team-match
# comparisons stay consistent regardless of which board actually matched.
_PFR_TO_STANDARD_TEAM: dict[str, str] = {
    "GNB": "GB",
    "KAN": "KC",
    "LVR": "LV",
    "NOR": "NO",
    "NWE": "NE",
    "SFO": "SF",
    "TAM": "TB",
}


def _load_immutable_draft_board(db: DBManager) -> pd.DataFrame:
    """
    Load the complete historical draft-pick record from
    bronze_nflverse_draft_picks (Issue #1167 CRITICAL-1).

    Unlike bronze_sportsdataio_players (an ACTIVE-roster snapshot loaded
    WRITE_TRUNCATE from the /Players endpoint — retired/cut players vanish;
    e.g. the 2015 class has shrunk to only ~135 of the original ~256 rows),
    bronze_nflverse_draft_picks is nflverse's Pro-Football-Reference-sourced
    draft-results history: every pick ever made in a given draft class stays
    on record regardless of whether that player is still in the league.
    Absence from THIS table for a concluded draft year is real positive
    evidence a player was never drafted; absence from the active-roster
    snapshot is not.

    Returns a DataFrame with columns [draft_year, draft_round, draft_pick,
    draft_team, player_name, name_lower] — empty (but always column-complete,
    so callers can safely index columns) if the table is unavailable.
    """
    empty = pd.DataFrame(
        columns=[
            "draft_year",
            "draft_round",
            "draft_pick",
            "draft_team",
            "player_name",
            "name_lower",
        ]
    )
    project_id = os.environ.get("GCP_PROJECT_ID")
    if not project_id:
        return empty
    query = f"""
        SELECT
            season AS draft_year,
            round AS draft_round,
            pick AS draft_pick,
            team AS draft_team,
            pfr_player_name AS player_name
        FROM `{project_id}.nfl_dead_money.bronze_nflverse_draft_picks`
        WHERE season IS NOT NULL
    """
    try:
        df = db.fetch_df(query)
    except NotFound:
        logger.warning("bronze_nflverse_draft_picks table not found")
        return empty
    if df.empty or "player_name" not in df.columns:
        return empty
    df["name_lower"] = df["player_name"].apply(_normalize_name)
    df["draft_team"] = df["draft_team"].map(
        lambda t: _PFR_TO_STANDARD_TEAM.get(t, t) if pd.notna(t) else t
    )
    return df


# Predictive/selection phrasing required (alongside a parsed pick/round/
# top-N target) before a claim is trusted enough to terminal-resolve
# (Issue #1167 CRITICAL-2). Retrospective narration ("was a three-star
# recruit", "put up huge numbers") uses neither of these markers.
_DRAFT_PREDICTIVE_PHRASE_RE = re.compile(
    r"\b(?:will|is|was|were|goes|going|go|projected|projection|expects?|"
    r"expected|predicts?|forecast(?:s|ed)?|slated|likely|should|lands?|"
    r"landing|selects?|selected|drafts?|drafted)\b"
)


def _looks_like_draft_prediction(claim: str, parsed: dict) -> bool:
    """
    Claim-shape gate for the terminal-INCORRECT branches (Issue #1167
    CRITICAL-2 / MEDIUM-9).

    A misclassified non-prediction (recruiting recap, HOF blurb, career-stat
    recap) can slip into claim_category='draft_pick' upstream — that's the
    extraction-classifier gap #1167 ranks #1 — and otherwise reach the
    terminal branch purely because it names a player and mentions *some*
    year. Before scoring "absent from the board" as INCORRECT we require
    positive structural + phrasing evidence the claim is actually a forward
    draft-position prediction:
      - parsed contains a concrete pick/round/top-N target, AND
      - the claim uses predictive/selection phrasing.

    Verified false positive this guards against (adversarial review,
    replayed against prod): "Harrison Wallace III was a three-star recruit
    and 71st-ranked receiver in the 2021 recruiting class..." — no
    pick/round/top-N is parseable from that sentence at all (there is no
    "overall"/"pick"/"round" keyword adjacent to "71st"), so it now falls
    through to SKIP instead of a terminal INCORRECT.

    This same gate also closes MEDIUM-9: the re-resolve-voids pass retries
    predictions previously VOID'd as UNPARSEABLE_CLAIM, which by definition
    have no pick/round/top-N structure — so they can never pass this gate
    and convert into a terminal INCORRECT on retry.
    """
    has_structure = any(k in parsed for k in ("pick_number", "round_number", "top_n"))
    if not has_structure:
        return False
    return bool(_DRAFT_PREDICTIVE_PHRASE_RE.search(claim.lower()))


def _evaluate_draft_pick_claim(
    claim: str,
    parsed: dict,
    actual_pick,
    actual_round,
    actual_team,
    actual_name: str,
) -> tuple[Optional[bool], str]:
    """
    Compare a parsed draft claim against one actual draft-board record.

    Shared between the primary (active-roster) match path and the
    immutable-board fallback path so both apply the identical exact/fuzzy/
    round/top-N rules. Returns (correct, notes); correct is None when the
    claim has no pick/round/top-N structure to evaluate against this record
    (caller should VOID rather than guess).
    """
    notes_parts = [
        f"Actual: {actual_name} was pick #{actual_pick} (Round {actual_round}) by {actual_team}"
    ]

    if "pick_number" in parsed and pd.notna(actual_pick):
        predicted_pick = parsed["pick_number"]
        actual_pick_int = int(actual_pick)
        pick_delta = abs(actual_pick_int - predicted_pick)

        # Extract claimed team from the claim text for fuzzy-match evaluation.
        claimed_team: Optional[str] = None
        claim_lower_for_team = claim.lower()
        for pattern, abbr in _TEAM_PATTERNS.items():
            if pattern in claim_lower_for_team:
                claimed_team = abbr
                break

        team_matches = (
            claimed_team is not None
            and actual_team is not None
            and claimed_team == actual_team
        )

        if actual_pick_int == predicted_pick:
            # Exact match — always correct.
            correct = True
            match_type = "exact"
        elif team_matches and pick_delta <= 3:
            # Rule 2: team matches and pick is within ±3 — correct.
            # Covers post-event tracker off-by-one/two errors (issue #997).
            correct = True
            match_type = f"fuzzy±{pick_delta}+team"
        else:
            # Rule 3 / Rule 4: pick is off and either team is wrong or delta > 3.
            correct = False
            match_type = "mismatch"

        notes_parts.append(
            f"Claimed pick #{predicted_pick} ({claimed_team or 'no-team'}), "
            f"actual #{actual_pick_int} ({actual_team}); "
            f"match={match_type}"
        )
        return correct, "; ".join(notes_parts)

    if "top_n" in parsed and pd.notna(actual_pick):
        correct = int(actual_pick) <= parsed["top_n"]
        notes_parts.append(f"Claimed top-{parsed['top_n']}, actual #{int(actual_pick)}")
        return correct, "; ".join(notes_parts)

    if "round_number" in parsed and pd.notna(actual_round):
        correct = int(actual_round) == parsed["round_number"]
        notes_parts.append(
            f"Claimed Round {parsed['round_number']}, actual Round {int(actual_round)}"
        )
        return correct, "; ".join(notes_parts)

    return None, "; ".join(notes_parts)


def resolve_draft_picks(
    db: DBManager,
    dry_run: bool = False,
    sport: Optional[str] = None,
    pending_override: "Optional[pd.DataFrame]" = None,
) -> dict:
    """
    Resolve draft_pick predictions against actual draft results.

    Args:
        sport: When provided, restrict resolution to predictions whose sport
            matches this value (e.g. "NFL").  None processes all supported sports.
        pending_override: if supplied, use this DataFrame instead of fetching
            PENDING predictions — used by the re-resolve-voids pass.
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    if pending_override is not None:
        pending = pending_override
    else:
        pending = get_pending_predictions(sport=sport, db=db)
        pending = _filter_nfl_only(pending)
    draft_preds = pending[pending["claim_category"] == "draft_pick"]

    if draft_preds.empty:
        logger.info("No pending draft_pick predictions to resolve.")
        return summary

    draft_data = _load_draft_data(db)
    if draft_data.empty:
        logger.warning("No draft data available for resolution.")
        return summary

    # SportsDataIO stores the top ~22 first-round picks as 0-indexed
    # (CollegeDraftRound=0, CollegeDraftPick=0 = #1 overall pick).
    # Normalize to 1-indexed so all downstream comparisons are consistent.
    #
    # Fix for Issue #935 ("Round 0.0" in outcome_notes): the previous mask
    # used `draft_pick >= 0` which silently skips NaN draft_pick values, leaving
    # those rows with draft_round=0 un-normalized and producing "Round 0.0" in
    # outcome_notes.  We now normalize draft_round=0 → 1 unconditionally, and
    # only shift draft_pick for rows where it is not-null and >= 0.
    round_zero_mask = draft_data["draft_round"] == 0
    draft_data.loc[round_zero_mask, "draft_round"] = 1
    pick_shift_mask = (
        round_zero_mask
        & draft_data["draft_pick"].notna()
        & (draft_data["draft_pick"] >= 0)
    )
    draft_data.loc[pick_shift_mask, "draft_pick"] = (
        draft_data.loc[pick_shift_mask, "draft_pick"] + 1
    )

    logger.info(
        f"Resolving {len(draft_preds)} draft_pick predictions "
        f"against {len(draft_data)} player draft records"
    )

    # Lazy-loaded: only fetched from BigQuery the first time a terminal
    # "player absent" decision actually needs it, and tolerant of the table
    # or GCP_PROJECT_ID being unavailable (degrades to the empty/size-guard-
    # failing frame, which routes to SKIP rather than raising).
    immutable_board_cache: dict[str, pd.DataFrame] = {}

    def _get_immutable_board() -> pd.DataFrame:
        if "board" not in immutable_board_cache:
            try:
                immutable_board_cache["board"] = _load_immutable_draft_board(db)
            except Exception as exc:  # noqa: BLE001 - defensive, must never crash the pass
                logger.warning(
                    f"Could not load immutable draft board (nflverse): {exc}; "
                    f"falling back to SKIP for absent-player terminal checks"
                )
                immutable_board_cache["board"] = pd.DataFrame(
                    columns=[
                        "draft_year",
                        "draft_round",
                        "draft_pick",
                        "draft_team",
                        "player_name",
                        "name_lower",
                    ]
                )
        return immutable_board_cache["board"]

    for _, pred in draft_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        # Check both player name fields
        player_name = ""
        for field in ["target_player_name", "target_player_id"]:
            val = pred.get(field)
            if val and pd.notna(val) and str(val).lower() not in ("none", "multi", ""):
                player_name = str(val)
                break
        season_year = pred.get("season_year")

        parsed = _extract_draft_claim(claim)
        draft_year = parsed.get("draft_year")
        if not draft_year and pd.notna(season_year):
            draft_year = int(season_year)
        # Default to current year for draft_pick claims with no year
        if not draft_year:
            draft_year = pd.Timestamp.now().year

        # Check if we have actual draft pick data for this year
        current_year = pd.Timestamp.now().year
        year_draft_data = draft_data[
            (draft_data["draft_year"] == draft_year)
            & (draft_data["draft_pick"].notna())
            & (draft_data["draft_pick"] > 0)
        ]
        if draft_year > current_year or (
            draft_year == current_year and len(year_draft_data) == 0
        ):
            logger.info(
                f"  SKIP {phash[:12]}… — no draft results available for {draft_year}"
            )
            summary["skipped"] += 1
            continue

        # Find the player in draft data. Scoped to THIS claim's draft_year
        # (MEDIUM-7, Issue #1167 adversarial review) — previously matched
        # across the entire multi-year board, so a same/similar-named player
        # from an unrelated draft_year could satisfy the match and pollute
        # both the pick-comparison and the NULL-pick terminal path below.
        year_board = draft_data[draft_data["draft_year"] == draft_year]
        norm_name = _normalize_name(player_name) if player_name else ""
        player_matches = (
            year_board[year_board["name_lower"].str.contains(norm_name, na=False)]
            if norm_name and norm_name != "none"
            else pd.DataFrame()
        )

        # Also try extracting player name from the claim itself. Periods are
        # stripped from the claim text here (not a full _normalize_name,
        # which assumes an isolated name string) so an initialed name like
        # "J.J. McCarthy" in the claim still matches the now-normalized
        # board name_lower ("jj mccarthy") — HIGH-3.
        if player_matches.empty:
            claim_no_periods = claim.lower().replace(".", "")
            for _, draft_row in year_board.iterrows():
                if (
                    draft_row["name_lower"]
                    and draft_row["name_lower"] in claim_no_periods
                ):
                    player_matches = pd.DataFrame([draft_row])
                    break

        if player_matches.empty:
            # Try team-level resolution
            team_result = _resolve_team_claim(
                claim, parsed, year_draft_data, phash, db, dry_run
            )
            if team_result is not None:
                if team_result == "resolved":
                    summary["resolved"] += 1
                elif team_result == "voided":
                    summary["voided"] += 1
                else:
                    summary["skipped"] += 1
            elif player_name and draft_year < current_year:
                # Issue #1167 CRITICAL-1/CRITICAL-2: the draft has concluded
                # and this player is absent from the active-roster snapshot.
                # That alone is NOT positive evidence of "undrafted" (they
                # may simply have retired/been cut since — the snapshot is
                # WRITE_TRUNCATE from the /Players ACTIVE endpoint). Require
                # (a) the claim actually looks like a draft-position
                # prediction, then (b) check the immutable, non-shrinking
                # nflverse draft-results history for positive evidence
                # either way, guarded against a failed/partial ingest.
                if not _looks_like_draft_prediction(claim, parsed):
                    logger.info(
                        f"  SKIP {phash[:12]}… — claim has no pick/round/top-N "
                        f"structure + predictive phrasing; not confidently a "
                        f"draft-position prediction: {claim[:60]}"
                    )
                    summary["skipped"] += 1
                    continue

                immutable_board = _get_immutable_board()
                year_immutable = immutable_board[
                    immutable_board["draft_year"] == draft_year
                ]
                if len(year_immutable) < _MIN_DRAFT_BOARD_SIZE:
                    # TODO(#1167): no immutable per-year draft source is
                    # available/complete for this year (guard: need >=
                    # _MIN_DRAFT_BOARD_SIZE rows, got len(year_immutable)).
                    # Do the conservative thing and leave this pending
                    # rather than infer "undrafted" from absence alone.
                    logger.info(
                        f"  SKIP {phash[:12]}… — no reliable immutable draft "
                        f"record for {draft_year} (got {len(year_immutable)} "
                        f"rows, need >= {_MIN_DRAFT_BOARD_SIZE}); can't "
                        f"positively confirm undrafted"
                    )
                    summary["skipped"] += 1
                    continue

                norm_name_im = _normalize_name(player_name)
                immutable_match = year_immutable[
                    year_immutable["name_lower"].str.contains(norm_name_im, na=False)
                ]
                if immutable_match.empty:
                    # Positive evidence from a complete, non-shrinking
                    # source: genuinely absent from this draft class.
                    notes = (
                        f"Player '{player_name}' not found in {draft_year} "
                        f"active-roster draft data or the complete "
                        f"{draft_year} draft-results record "
                        f"({len(year_immutable)} picks, nflverse); draft has "
                        f"concluded — predicted drafted but wasn't"
                    )
                    _resolve_terminal_draft_incorrect(
                        phash, notes, db, dry_run, outcome_source="nflverse_draft_picks"
                    )
                    summary["resolved"] += 1
                else:
                    # They WERE drafted — the active-roster snapshot just no
                    # longer carries them (retired/cut). Resolve against the
                    # immutable record instead of falsely scoring INCORRECT.
                    im_actual = immutable_match.iloc[0]
                    correct, eval_notes = _evaluate_draft_pick_claim(
                        claim,
                        parsed,
                        im_actual.get("draft_pick"),
                        im_actual.get("draft_round"),
                        im_actual.get("draft_team"),
                        im_actual.get("player_name"),
                    )
                    if correct is None:
                        logger.info(
                            f"  VOID {phash[:12]}… — found in immutable draft "
                            f"history but claim has no pick/round/top-N "
                            f"structure: {claim[:60]}"
                        )
                        if not dry_run:
                            _void_prediction_with_dual_write(
                                phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                            )
                        summary["voided"] += 1
                    else:
                        outcome_notes = (
                            "[resolved via nflverse immutable draft history — "
                            "absent from active-roster snapshot] " + eval_notes
                        )
                        status = "CORRECT" if correct else "INCORRECT"
                        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")
                        if not dry_run:
                            _resolve_binary_with_dual_write(
                                prediction_hash=phash,
                                correct=correct,
                                outcome_source="nflverse_draft_picks",
                                outcome_notes=outcome_notes,
                                db=db,
                            )
                        summary["resolved"] += 1
            else:
                logger.info(
                    f"  SKIP {phash[:12]}… — can't find player or team pattern: {claim[:60]}"
                )
                summary["skipped"] += 1
            continue

        # Use the first match (best match)
        actual = player_matches.iloc[0]
        actual_pick = actual.get("draft_pick")
        actual_round = actual.get("draft_round")
        actual_team = actual.get("draft_team")
        actual_name = actual.get("Name")

        # Pick data missing (0-indexed picks already normalized to 1+ above).
        # If the draft has concluded, a player who IS on the board for THIS
        # draft_year (MEDIUM-7: matches are now year-scoped, so this can no
        # longer be a cross-year mismatch) but has no assigned pick is only
        # a terminal INCORRECT ("went undrafted") when SportsDataIO
        # positively flags them as such — a NULL pick alone is not proof of
        # undrafted, it can just be missing/delayed data (Issue #1167).
        if not pd.notna(actual_pick):
            if draft_year < current_year:
                is_flagged_undrafted = bool(pd.notna(actual.get("undrafted"))) and bool(
                    actual.get("undrafted")
                )
                if not _looks_like_draft_prediction(claim, parsed):
                    logger.info(
                        f"  SKIP {phash[:12]}… — claim has no pick/round/top-N "
                        f"structure + predictive phrasing: {claim[:60]}"
                    )
                    summary["skipped"] += 1
                elif is_flagged_undrafted:
                    notes = (
                        f"Player found ({actual_name}) and positively flagged "
                        f"IsUndraftedFreeAgent=True in {draft_year} draft "
                        f"data; draft has concluded — predicted drafted but wasn't"
                    )
                    _resolve_terminal_draft_incorrect(phash, notes, db, dry_run)
                    summary["resolved"] += 1
                else:
                    # TODO(#1167): NULL pick without a positive undrafted
                    # flag isn't enough evidence — could be missing/delayed
                    # data rather than a real non-draftee. Leave pending.
                    logger.info(
                        f"  SKIP {phash[:12]}… — player found ({actual_name}) "
                        f"with NULL pick in {draft_year} but not positively "
                        f"flagged undrafted; can't confirm — leaving pending"
                    )
                    summary["skipped"] += 1
            else:
                logger.info(
                    f"  SKIP {phash[:12]}… — player found but pick not yet assigned: {actual_name}"
                )
                summary["skipped"] += 1
            continue

        # Now evaluate the claim
        correct, outcome_notes = _evaluate_draft_pick_claim(
            claim, parsed, actual_pick, actual_round, actual_team, actual_name
        )
        if correct is None:
            # Can't determine specific claim — void
            logger.info(
                f"  VOID {phash[:12]}… — can't parse specific claim: {claim[:60]}"
            )
            if not dry_run:
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        status = "CORRECT" if correct else "INCORRECT"
        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")

        if not dry_run:
            _resolve_binary_with_dual_write(
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


def resolve_game_outcomes(
    db: DBManager, dry_run: bool = False, sport: Optional[str] = None
) -> dict:
    """
    Resolve game_outcome predictions against actual game results.
    Data source: bronze_sportsdataio_scores (HomeTeam, AwayTeam, HomeScore, AwayScore).

    Args:
        sport: When provided, restrict resolution to predictions whose sport
            matches this value (e.g. "NFL").  None processes all supported sports.
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport=sport, db=db)
    pending = _filter_nfl_only(pending)
    game_preds = pending[pending["claim_category"] == "game_outcome"]

    if game_preds.empty:
        logger.info("No pending game_outcome predictions to resolve.")
        return summary

    current_year = pd.Timestamp.now().year
    # NFL regular season ends in January; postseason in February
    # Only resolve predictions for seasons that have fully concluded
    # (i.e. prior year, or current year after February)
    season_data_cache: dict[int, pd.DataFrame] = {}

    # MEDIUM-6 (Issue #1167): batch-fetch content publish dates once for all
    # NULL-season_year rows so per-row inference can prefer them over
    # ingestion_timestamp.
    null_season_hashes = game_preds.loc[
        game_preds["season_year"].isna(), "prediction_hash"
    ].tolist()
    content_dates = _load_content_published_dates(db, null_season_hashes)

    for _, pred in game_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        season_year = pred.get("season_year")
        season_year_inferred = False
        inferred_from = None

        if pd.isna(season_year):
            content_date = content_dates.get(phash)
            season_year = _infer_season_year_from_ingestion(
                pred.get("ingestion_timestamp"), content_date
            )
            if season_year is None:
                logger.info(
                    f"  SKIP {phash[:12]}… — no season_year and no usable "
                    f"content-publish/ingestion date to infer from (or the "
                    f"date fell in the ambiguous Jan/Feb window)"
                )
                summary["skipped"] += 1
                continue
            season_year_inferred = True
            inferred_from = (
                "content_published_at"
                if content_date is not None
                else "ingestion_timestamp"
            )
            logger.info(
                f"  Inferred season_year={season_year} for {phash[:12]}… "
                f"from {inferred_from} (read-time fallback, Issue #1167)"
            )

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
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        if correct is None:
            summary["skipped"] += 1
            continue

        if season_year_inferred:
            # MEDIUM-6: tag inferred resolutions for reversibility — an
            # auditor can find/undo these separately if the inference is
            # later shown to be wrong, without touching explicit-season_year
            # resolutions.
            notes_parts.append(f"[season_year inferred from {inferred_from}]")
        outcome_notes = "; ".join(notes_parts)
        status = "CORRECT" if correct else "INCORRECT"
        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")

        if not dry_run:
            _resolve_binary_with_dual_write(
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

# Mapping from common stat phrases → column names in bronze_nflverse_player_stats
# (nflverse uses snake_case columns, not the PascalCase of the old SportsData.io source)
_STAT_ALIASES: dict[str, str] = {
    "passing yards": "passing_yards",
    "passing yard": "passing_yards",
    "pass yards": "passing_yards",
    "passing touchdowns": "passing_tds",
    "passing tds": "passing_tds",
    "passing td": "passing_tds",
    "tds": "passing_tds",  # default to passing (resolved by position context)
    "interceptions": "interceptions",
    "rushing yards": "rushing_yards",
    "rushing yard": "rushing_yards",
    "rush yards": "rushing_yards",
    "rushes for": "rushing_yards",
    "rush for": "rushing_yards",
    "rushing touchdowns": "rushing_tds",
    "rushing tds": "rushing_tds",
    "receiving yards": "receiving_yards",
    "receiving yard": "receiving_yards",
    "rec yards": "receiving_yards",
    "receiving touchdowns": "receiving_tds",
    "receiving tds": "receiving_tds",
    "receptions": "receptions",
    "catches": "receptions",
    "sacks": "sacks",
    "tackles": "sacks",  # nflverse seasonal data does not have tackles; map to sacks as fallback
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
    Load player season stats from bronze_nflverse_player_stats (free, no API key).
    Joins with bronze_nflverse_players to resolve player_id → display_name.
    Returns empty DataFrame if table doesn't exist or has no data for the season.
    """
    project_id = os.environ["GCP_PROJECT_ID"]
    query = f"""
        SELECT
            p.display_name AS Name,
            s.season AS Season,
            s.passing_yards AS passing_yards,
            s.passing_tds AS passing_tds,
            s.interceptions AS interceptions,
            s.rushing_yards AS rushing_yards,
            s.rushing_tds AS rushing_tds,
            s.receiving_yards AS receiving_yards,
            s.receiving_tds AS receiving_tds,
            s.receptions AS receptions,
            s.sacks AS sacks
        FROM `{project_id}.nfl_dead_money.bronze_nflverse_player_stats` s
        JOIN `{project_id}.nfl_dead_money.bronze_nflverse_players` p
          ON s.player_id = p.gsis_id
        WHERE s.season = {season_year}
          AND s.season_type = 'REG'
    """
    try:
        return db.fetch_df(query)
    except Exception as e:
        logger.warning(f"Player season stats not available (season {season_year}): {e}")
        return pd.DataFrame()


def resolve_player_performance(
    db: DBManager, dry_run: bool = False, sport: Optional[str] = None
) -> dict:
    """
    Resolve player_performance predictions against actual season stats.
    Data source: bronze_nflverse_player_stats (free, no API key required).
    Only resolves predictions for completed seasons.

    Args:
        sport: When provided, restrict resolution to predictions whose sport
            matches this value (e.g. "NFL").  None processes all supported sports.
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport=sport, db=db)
    pending = _filter_nfl_only(pending)
    perf_preds = pending[pending["claim_category"] == "player_performance"]

    if perf_preds.empty:
        logger.info("No pending player_performance predictions to resolve.")
        return summary

    current_year = pd.Timestamp.now().year
    stats_cache: dict[int, pd.DataFrame] = {}

    # MEDIUM-6 (Issue #1167): batch-fetch content publish dates once for all
    # NULL-season_year rows so per-row inference can prefer them over
    # ingestion_timestamp.
    null_season_hashes = perf_preds.loc[
        perf_preds["season_year"].isna(), "prediction_hash"
    ].tolist()
    content_dates = _load_content_published_dates(db, null_season_hashes)

    for _, pred in perf_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        season_year = pred.get("season_year")
        season_year_inferred = False
        inferred_from = None

        if pd.isna(season_year):
            content_date = content_dates.get(phash)
            season_year = _infer_season_year_from_ingestion(
                pred.get("ingestion_timestamp"), content_date
            )
            if season_year is None:
                logger.info(
                    f"  SKIP {phash[:12]}… — no season_year and no usable "
                    f"content-publish/ingestion date to infer from (or the "
                    f"date fell in the ambiguous Jan/Feb window)"
                )
                summary["skipped"] += 1
                continue
            season_year_inferred = True
            inferred_from = (
                "content_published_at"
                if content_date is not None
                else "ingestion_timestamp"
            )
            logger.info(
                f"  Inferred season_year={season_year} for {phash[:12]}… "
                f"from {inferred_from} (read-time fallback, Issue #1167)"
            )

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
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
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
        if season_year_inferred:
            # MEDIUM-6: tag inferred resolutions for reversibility.
            outcome_notes += f"; [season_year inferred from {inferred_from}]"
        status = "CORRECT" if correct else "INCORRECT"
        logger.info(f"  {status} {phash[:12]}… — {outcome_notes}")

        if not dry_run:
            _resolve_binary_with_dual_write(
                prediction_hash=phash,
                correct=correct,
                outcome_source="nflverse_player_stats",
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


# ---------------------------------------------------------------------------
# Award prediction resolver
# ---------------------------------------------------------------------------

# Maps claim text keywords → award config key in nfl_awards_<season>.yaml
_AWARD_KEYWORDS: dict[str, list[str]] = {
    "mvp": ["mvp", "most valuable player"],
    "opoy": ["opoy", "offensive player of the year"],
    "dpoy": ["dpoy", "defensive player of the year"],
    "offensive_rookie": [
        "offensive rookie of the year",
        "oroty",
        "offensive roy",
    ],
    "defensive_rookie": [
        "defensive rookie of the year",
        "droty",
        "defensive roy",
    ],
    "coach_of_the_year": ["coach of the year", "coty"],
    "comeback_player": ["comeback player of the year", "cpoy"],
    "walter_payton_man_of_the_year": ["walter payton", "man of the year"],
    "super_bowl_mvp": ["super bowl mvp"],
}

# Flattened (keyword, award_key) pairs, longest keyword first (HIGH-5, Issue
# #1167 adversarial review). _parse_award_type previously iterated
# _AWARD_KEYWORDS in dict order and returned on the first match, so a claim
# containing "Super Bowl MVP" matched the generic "mvp" keyword (checked
# first) before "super bowl mvp" was ever considered — SB-MVP claims
# resolved against the regular-season MVP winner instead. Sorting by keyword
# length so the most specific keyword always wins, regardless of dict order.
_AWARD_KEYWORD_PAIRS_BY_LENGTH_DESC: list[tuple[str, str]] = sorted(
    (
        (keyword, award_key)
        for award_key, keywords in _AWARD_KEYWORDS.items()
        for keyword in keywords
    ),
    key=lambda pair: len(pair[0]),
    reverse=True,
)


def _load_awards_config(season: int) -> dict[str, Optional[str]]:
    """Load NFL award winners from config/nfl_awards_<season>.yaml."""
    config_path = Path(__file__).parent.parent / "config" / f"nfl_awards_{season}.yaml"
    if not config_path.exists():
        logger.debug(f"Awards config not found: {config_path}")
        return {}
    with open(config_path) as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("awards", {})


def _parse_award_type(claim: str) -> Optional[str]:
    """
    Return the award config key if the claim names a known award, else None.

    Matches the most specific (longest) keyword first (HIGH-5) so a
    substring keyword like "mvp" can never shadow a more specific one like
    "super bowl mvp".
    """
    claim_lower = claim.lower()
    for keyword, award_key in _AWARD_KEYWORD_PAIRS_BY_LENGTH_DESC:
        if keyword in claim_lower:
            return award_key
    return None


def resolve_award_predictions(
    db: DBManager, season: Optional[int] = None, dry_run: bool = False
) -> dict:
    """
    Resolve award_prediction claims against the award config file for the season.

    Marks CORRECT if the predicted player matches the actual winner, INCORRECT
    if a different player won, or SKIPPED if the config has no data yet (null).
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport=None, db=db)
    pending = _filter_nfl_only(pending)
    award_preds = pending[pending["claim_category"] == "award_prediction"]

    if award_preds.empty:
        logger.info("No pending award_prediction predictions to resolve.")
        return summary

    # Cache awards by season to avoid repeated file reads
    awards_cache: dict[int, dict] = {}

    for _, pred in award_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]
        season_year = pred.get("season_year")

        if pd.isna(season_year):
            logger.info(f"  SKIP {phash[:12]}… — no season_year on award claim")
            summary["skipped"] += 1
            continue

        season_year = int(season_year)

        # NFL awards announced in February of season_year+1
        now = pd.Timestamp.now()
        awards_announced = now.year > season_year + 1 or (
            now.year == season_year + 1 and now.month >= 2
        )
        if not awards_announced:
            logger.info(
                f"  SKIP {phash[:12]}… — {season_year} season awards not yet announced"
            )
            summary["skipped"] += 1
            continue

        if season_year not in awards_cache:
            awards_cache[season_year] = _load_awards_config(season_year)
        awards = awards_cache[season_year]

        if not awards:
            logger.info(
                f"  SKIP {phash[:12]}… — no awards config for {season_year} season"
            )
            summary["skipped"] += 1
            continue

        award_key = _parse_award_type(claim)
        if award_key is None:
            logger.info(f"  VOID {phash[:12]}… — unrecognised award type: {claim[:60]}")
            if not dry_run:
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        actual_winner = awards.get(award_key)
        if actual_winner is None:
            logger.info(
                f"  SKIP {phash[:12]}… — {award_key} winner not in config for {season_year}"
            )
            summary["skipped"] += 1
            continue

        # Extract the predicted player name
        predicted_player = pred.get("target_player_name") or pred.get(
            "target_player_id"
        )
        if not predicted_player or pd.isna(predicted_player):
            logger.info(
                f"  VOID {phash[:12]}… — no predicted player name: {claim[:60]}"
            )
            if not dry_run:
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        # Fuzzy name match: both sides lowercased, check if predicted is in actual or vice versa
        pred_lower = _normalize_name(str(predicted_player))
        actual_lower = _normalize_name(actual_winner)
        correct = (
            pred_lower
            and actual_lower
            and (pred_lower in actual_lower or actual_lower in pred_lower)
        )

        notes = f"{award_key} winner: {actual_winner}"
        logger.info(
            f"  {'CORRECT' if correct else 'INCORRECT'} {phash[:12]}… — "
            f"predicted '{predicted_player}', actual '{actual_winner}' ({award_key})"
        )
        if not dry_run:
            _resolve_binary_with_dual_write(
                phash,
                bool(correct),
                outcome_source="nfl_awards_config",
                outcome_notes=notes,
                db=db,
            )
        summary["resolved"] += 1

    return summary


# ---------------------------------------------------------------------------
# FA signing resolver
# ---------------------------------------------------------------------------


def _load_current_rosters(db: DBManager) -> pd.DataFrame:
    """Load current player team assignments from bronze_sportsdataio_players."""
    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
    try:
        df = db.fetch_df(f"""
            SELECT
                Name,
                LOWER(Name) AS name_lower,
                Team AS current_team
            FROM `{project_id}.nfl_dead_money.bronze_sportsdataio_players`
            WHERE Team IS NOT NULL AND Team != ''
            """)
        return df
    except NotFound:
        logger.warning("bronze_sportsdataio_players table not found")
        return pd.DataFrame()


def _parse_fa_team(claim: str) -> Optional[str]:
    """
    Extract the destination team from an FA signing claim.
    e.g. "Davante Adams will sign with the Cowboys" → "Cowboys"
    """
    # Pattern: "sign with [the] <Team>" or "join [the] <Team>" or "land with <Team>"
    patterns = [
        r"(?:sign(?:s|ed)? with|join(?:s|ed)?|land(?:s|ed)? (?:with )?|go(?:es|ing)? to) (?:the )?([A-Z][a-zA-Z\s]+?)(?:\.|,|$|\s(?:on|for|in|at)\b)",
        r"(?:sign(?:s|ed)? a deal with|ink(?:s|ed)? (?:a deal )?with) (?:the )?([A-Z][a-zA-Z\s]+?)(?:\.|,|$)",
    ]
    for pat in patterns:
        m = re.search(pat, claim)
        if m:
            return m.group(1).strip()
    return None


def resolve_fa_signings(db: DBManager, dry_run: bool = False) -> dict:
    """
    Resolve fa_signing predictions against current SportsDataIO roster data.

    Marks CORRECT if the player's current team matches the predicted team,
    INCORRECT if they're on a different team, VOID if player not found in data.
    """
    summary = {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

    pending = get_pending_predictions(sport="NFL", db=db)
    fa_preds = pending[pending["claim_category"] == "fa_signing"]

    if fa_preds.empty:
        logger.info("No pending fa_signing predictions to resolve.")
        return summary

    rosters = _load_current_rosters(db)
    if rosters.empty:
        logger.warning("No roster data available; skipping fa_signing resolution.")
        for _ in fa_preds.iterrows():
            summary["checked"] += 1
            summary["skipped"] += 1
        return summary

    for _, pred in fa_preds.iterrows():
        summary["checked"] += 1
        claim = pred["extracted_claim"]
        phash = pred["prediction_hash"]

        player_name = pred.get("target_player_name") or pred.get("target_player_id")
        if not player_name or pd.isna(player_name):
            logger.info(
                f"  VOID {phash[:12]}… — no player name in fa_signing: {claim[:60]}"
            )
            if not dry_run:
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        predicted_team_raw = _parse_fa_team(claim)
        if not predicted_team_raw:
            logger.info(
                f"  VOID {phash[:12]}… — can't parse destination team: {claim[:60]}"
            )
            if not dry_run:
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        predicted_abbr = _normalize_team(predicted_team_raw)
        if not predicted_abbr:
            logger.info(
                f"  VOID {phash[:12]}… — unknown team '{predicted_team_raw}': {claim[:60]}"
            )
            if not dry_run:
                _void_prediction_with_dual_write(
                    phash, VoidReason.UNPARSEABLE_CLAIM, db=db
                )
            summary["voided"] += 1
            continue

        norm_player = _normalize_name(str(player_name))
        player_rows = rosters[
            rosters["name_lower"].str.contains(norm_player, na=False, regex=False)
        ]

        if player_rows.empty:
            logger.info(
                f"  SKIP {phash[:12]}… — '{player_name}' not found in SportsDataIO"
            )
            summary["skipped"] += 1
            continue

        actual_team = player_rows.iloc[0]["current_team"]
        actual_abbr = _normalize_team(str(actual_team)) or actual_team

        correct = predicted_abbr == actual_abbr
        notes = f"predicted {predicted_abbr}, actual {actual_abbr}"
        logger.info(
            f"  {'CORRECT' if correct else 'INCORRECT'} {phash[:12]}… — "
            f"'{player_name}': {notes}"
        )
        if not dry_run:
            _resolve_binary_with_dual_write(
                phash,
                bool(correct),
                outcome_source="sportsdataio_rosters",
                outcome_notes=notes,
                db=db,
            )
        summary["resolved"] += 1

    return summary


def _get_void_predictions_by_note(
    note: "str | VoidReason", db: DBManager, sport: Optional[str] = "NFL"
) -> "pd.DataFrame":
    """
    Fetch predictions that were previously VOID'd with a specific outcome_notes value.
    Used by the re-resolve pass to retry previously unresolvable predictions.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    sport_filter = f"AND COALESCE(l.sport, 'NFL') = '{sport}'" if sport else ""
    query = f"""
        SELECT
            l.prediction_hash,
            l.pundit_id,
            l.pundit_name,
            l.extracted_claim,
            l.claim_category,
            l.season_year,
            l.target_player_id,
            l.target_player_name,
            l.target_team,
            COALESCE(l.sport, 'NFL') AS sport,
            l.ingestion_timestamp
        FROM `{project_id}.gold_layer.prediction_ledger` l
        JOIN `{project_id}.gold_layer.prediction_resolutions` r
            ON l.prediction_hash = r.prediction_hash
        WHERE r.resolution_status = 'VOID'
          AND r.outcome_notes = '{note}'
          {sport_filter}
        ORDER BY l.ingestion_timestamp ASC
    """
    return db.fetch_df(query)


def expire_stale_predictions(db: DBManager, dry_run: bool = False) -> int:
    """
    Void PENDING predictions that have passed their resolution horizon.

    A prediction is considered stale if:
      - season_year <= EXTRACT(YEAR FROM CURRENT_DATE()) - 2  (more than 2 seasons old)

    Note: the prediction_ledger table does not have a resolution_deadline column.
    The check is purely season_year-based.  Claims for seasons 2+ years in the
    past are void'd as past_resolution_horizon.  Claims with NULL season_year
    are left alone — they may still be resolved by the rule-based or LLM judge pass.

    Each stale prediction is voided with reason 'past_resolution_horizon'.
    Returns the count of predictions expired.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    query = f"""
        SELECT l.prediction_hash
        FROM `{project_id}.gold_layer.prediction_ledger` l
        LEFT JOIN `{project_id}.gold_layer.prediction_resolutions` r
            ON l.prediction_hash = r.prediction_hash
        WHERE (r.prediction_hash IS NULL OR r.resolution_status = 'PENDING')
          AND l.season_year IS NOT NULL
          AND l.season_year <= EXTRACT(YEAR FROM CURRENT_DATE()) - 2
    """
    try:
        stale = db.fetch_df(query)
    except Exception as e:
        logger.warning(f"expire_stale_predictions: could not query ledger: {e}")
        return 0

    count = len(stale)
    if count == 0:
        logger.info("expire_stale_predictions: no stale predictions found")
        return 0

    logger.info(f"expire_stale_predictions: expiring {count} stale prediction(s)")
    for _, row in stale.iterrows():
        phash = row["prediction_hash"]
        logger.info(f"  VOID {phash[:12]}… — past_resolution_horizon")
        if not dry_run:
            void_prediction(phash, VoidReason.PAST_RESOLUTION_HORIZON, db=db)

    logger.info(f"expire_stale_predictions: expired {count} prediction(s)")
    return count


def resolve_all(
    category: Optional[str] = None,
    dry_run: bool = False,
    re_resolve_voids: bool = False,
    db: Optional[DBManager] = None,
    sport: Optional[str] = None,
) -> dict:
    """Run all resolution passes. Returns combined summary.

    Args:
        category: Limit to a single prediction category (draft_pick, game_outcome,
            player_performance). None means all categories.
        dry_run: Preview without writing results.
        re_resolve_voids: Re-attempt predictions previously VOID'd as unparseable.
        db: Optional shared DBManager; created internally if not provided.
        sport: Restrict fetched predictions to a specific sport (e.g. "NFL").
            Passed through to get_pending_predictions; unsupported sports are
            additionally filtered by _filter_nfl_only in each individual resolver.
            Omit to process all sports.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        summaries = {}

        # Route non-NFL domains to their stub resolvers (Phase A — stubs only)
        if sport and sport.lower() == "politics":
            from src.resolve_daily_politics import resolve_pending_politics

            resolve_pending_politics(dry_run=dry_run, db=db)
            return {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}
        elif sport and sport.lower() in {"finance", "business"}:
            from src.resolve_daily_finance import resolve_pending_finance

            resolve_pending_finance(dry_run=dry_run, db=db)
            return {"checked": 0, "resolved": 0, "voided": 0, "skipped": 0}

        if not category or category == "draft_pick":
            if re_resolve_voids:
                # Re-attempt draft predictions previously VOID'd as unparseable
                void_drafts = _get_void_predictions_by_note(
                    VoidReason.UNPARSEABLE_CLAIM, db=db
                )
                logger.info(
                    f"Re-resolve-voids: {len(void_drafts)} {VoidReason.UNPARSEABLE_CLAIM.value} entries"
                )
                if not void_drafts.empty:
                    summaries["draft_pick_voids"] = resolve_draft_picks(
                        db, dry_run=dry_run, pending_override=void_drafts
                    )
            summaries["draft_pick"] = resolve_draft_picks(
                db, dry_run=dry_run, sport=sport
            )

        if not category or category == "game_outcome":
            summaries["game_outcome"] = resolve_game_outcomes(
                db, dry_run=dry_run, sport=sport
            )

        if not category or category == "player_performance":
            summaries["player_performance"] = resolve_player_performance(
                db, dry_run=dry_run, sport=sport
            )

        if not category or category == "award_prediction":
            summaries["award_prediction"] = resolve_award_predictions(
                db, dry_run=dry_run
            )

        if not category or category == "fa_signing":
            summaries["fa_signing"] = resolve_fa_signings(db, dry_run=dry_run)

        # LLM judge fallback pass — runs last, after all rule-based resolvers.
        # Only fires when no category filter is active (full pass only).
        if not category:
            try:
                from src.resolvers.llm_judge import run_llm_judge_pass

                summaries["llm_judge"] = run_llm_judge_pass(db=db, dry_run=dry_run)
            except Exception as exc:
                logger.warning(f"llm_judge pass failed (non-fatal): {exc}")
                summaries["llm_judge"] = {
                    "checked": 0,
                    "resolved": 0,
                    "skipped": 0,
                    "errors": 1,
                }

        # Expire predictions past their resolution horizon (runs on every full pass)
        expired = expire_stale_predictions(db, dry_run=dry_run)

        # Combined summary.
        # Use .get(k, 0) rather than s[k]: resolver summaries are heterogeneous —
        # run_llm_judge_pass() reports checked/resolved/skipped/errors but never
        # "voided" (it resolves or skips, it never voids), and its exception
        # fallback omits "voided" too. A bare s["voided"] therefore raises
        # KeyError on every full pass, crashing the whole resolve step.
        total = {
            "checked": sum(s.get("checked", 0) for s in summaries.values()),
            "resolved": sum(s.get("resolved", 0) for s in summaries.values()),
            "voided": sum(s.get("voided", 0) for s in summaries.values()),
            "skipped": sum(s.get("skipped", 0) for s in summaries.values()),
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
        choices=[
            "draft_pick",
            "game_outcome",
            "player_performance",
            "award_prediction",
            "fa_signing",
        ],
        help="Resolve only a specific category",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--re-resolve-voids",
        action="store_true",
        help="Also re-attempt predictions previously VOID'd as unparseable",
    )
    parser.add_argument(
        "--sport",
        default=None,
        help=(
            "Restrict resolution to a specific sport domain "
            "(e.g. NFL, politics, finance). Omit to process all domains."
        ),
    )
    args = parser.parse_args()

    result = resolve_all(
        category=args.category,
        dry_run=args.dry_run,
        re_resolve_voids=args.re_resolve_voids,
        sport=args.sport,
    )
    import json

    print(json.dumps(result, indent=2))

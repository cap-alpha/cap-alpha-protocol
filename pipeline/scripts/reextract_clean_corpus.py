#!/usr/bin/env python3
"""
reextract_clean_corpus.py — Re-extract pft_staff and athletic_nfl_staff from
the clean (non-post-event) corpus only. (Issue #999)

Background
----------
PR #995 removed pft_staff and athletic_nfl_staff from the leaderboard after an
audit found their extractions were contaminated with post-event draft-tracker
articles (articles published AFTER the events they appear to "predict").

PR #998 added an is_post_event flag to raw_pundit_media and a filter in
assertion_extractor.get_unprocessed_media() so that is_post_event=TRUE rows
are never extracted again.

This script does the three steps needed to complete the cleanup:

  Step 1 — Delete existing contaminated assertions
           Removes all prediction_ledger rows for pft_staff / athletic_nfl_staff.
           Also removes silver_v2_claims.raw_utterance rows for those pundits so
           the ledger and the silver layer are consistent.

  Step 2 — Clear processed_media_hashes for the two source IDs
           Forces the extractor to re-process pft_nbc and theathletic_nfl
           articles on the next pipeline run. Only clean rows (is_post_event=FALSE
           or NULL) will be picked up, because assertion_extractor already
           applies that filter.

  Step 3 — Optionally trigger extraction immediately
           Pass --run-extraction to invoke assertion_extractor right after the
           reset, so you don't have to wait for the next daily cron run.

Usage
-----
    # Dry-run — print counts, write nothing
    cd pipeline
    python scripts/reextract_clean_corpus.py --dry-run

    # Live run — delete contaminated assertions, reset hashes
    python scripts/reextract_clean_corpus.py

    # Live run + immediately re-extract (slow — runs Ollama/LLM)
    python scripts/reextract_clean_corpus.py --run-extraction

    # DuckDB offline mode (no BQ connectivity needed)
    USE_LOCAL_DB=1 python scripts/reextract_clean_corpus.py --dry-run

Environment
-----------
    GCP_PROJECT_ID   Required when running against BigQuery.
    USE_LOCAL_DB     Set to "1" to use DuckDB instead of BigQuery.

Source ID → Pundit ID mapping
------------------------------
    pft_nbc          → pft_staff, mike_florio, josh_alper, michael_david_smith,
                        charean_williams, myles_simmons
    theathletic_nfl  → athletic_nfl_staff, dianna_russini, jeff_howe

The script deletes by pundit_id (pft_staff, athletic_nfl_staff) which are the
staff/aggregate buckets that held the contaminated predictions. Named pundits
from those sources (mike_florio, dianna_russini, etc.) are kept — they were
not the contaminated bucket and should not be touched.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Make src/ importable when run from pipeline/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db_manager import DBManager  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — must match assertion_extractor.py table names
# ---------------------------------------------------------------------------

# Source IDs in raw_pundit_media that map to the contaminated pundit buckets
CONTAMINATED_SOURCE_IDS: tuple[str, ...] = ("pft_nbc", "theathletic_nfl")

# Pundit IDs of the staff/aggregate buckets that hold contaminated predictions.
# Named pundits (mike_florio, dianna_russini, etc.) are NOT in this list
# and are NOT deleted — they had real individual predictions.
CONTAMINATED_PUNDIT_IDS: tuple[str, ...] = ("pft_staff", "athletic_nfl_staff")

# Table names (BigQuery-qualified; DuckDB translate layer handles the schema)
_PROCESSED_HASHES_TABLE = "nfl_dead_money.processed_media_hashes"
_RAW_MEDIA_TABLE = "nfl_dead_money.raw_pundit_media"
_LEDGER_TABLE = "gold_layer.prediction_ledger"
_RAW_UTTERANCE_TABLE = "silver_v2_claims.raw_utterance"


# ---------------------------------------------------------------------------
# Helper: quote tuple for IN clause (safe — values are hard-coded constants)
# ---------------------------------------------------------------------------


def _in_literal(values: tuple[str, ...]) -> str:
    """Return a SQL IN-list literal: ('a', 'b', 'c')"""
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"({quoted})"


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------


def step1_delete_contaminated_predictions(
    db: DBManager, project_id: str | None, dry_run: bool
) -> dict[str, int]:
    """
    Delete prediction_ledger and raw_utterance rows for the contaminated
    staff buckets.

    Returns a dict with row-count estimates for each table.
    """
    results: dict[str, int] = {}
    pundit_in = _in_literal(CONTAMINATED_PUNDIT_IDS)

    # ---- prediction_ledger: join is direct (has pundit_id column) ----
    bq_ledger = (
        f"`{project_id}.{_LEDGER_TABLE}`"
        if project_id
        else f'"{_LEDGER_TABLE.replace(".", '"."')}"'
    )
    try:
        row = db.fetch_df(
            f"SELECT COUNT(*) FROM {bq_ledger} WHERE pundit_id IN {pundit_in}"
        )
        ledger_count = int(row.iloc[0, 0])
    except Exception as exc:
        logger.warning(f"Count query failed for {_LEDGER_TABLE}: {exc}")
        ledger_count = -1
    results[_LEDGER_TABLE] = ledger_count
    logger.info(f"  {_LEDGER_TABLE}: {ledger_count} rows to delete")

    # ---- raw_utterance: pundit is linked via source_doc_id → raw_pundit_media ----
    # raw_utterance.source_doc_id = raw_pundit_media.content_hash
    # raw_pundit_media.matched_pundit_id = the pundit bucket
    bq_utterance = (
        f"`{project_id}.{_RAW_UTTERANCE_TABLE}`"
        if project_id
        else f'"{_RAW_UTTERANCE_TABLE.replace(".", '"."')}"'
    )
    bq_media = (
        f"`{project_id}.{_RAW_MEDIA_TABLE}`"
        if project_id
        else f'"{_RAW_MEDIA_TABLE.replace(".", '"."')}"'
    )
    utterance_count_q = f"""
        SELECT COUNT(*)
        FROM {bq_utterance} u
        WHERE u.source_doc_id IN (
            SELECT content_hash FROM {bq_media}
            WHERE matched_pundit_id IN {pundit_in}
        )
    """
    try:
        row = db.fetch_df(utterance_count_q)
        utterance_count = int(row.iloc[0, 0])
    except Exception as exc:
        logger.warning(f"Count query failed for {_RAW_UTTERANCE_TABLE}: {exc}")
        utterance_count = -1
    results[_RAW_UTTERANCE_TABLE] = utterance_count
    logger.info(f"  {_RAW_UTTERANCE_TABLE}: {utterance_count} rows to delete")

    if dry_run:
        logger.info("  DRY RUN — skipping deletes")
        return results

    # ---- Delete prediction_ledger ----
    try:
        result = db.execute(f"DELETE FROM {bq_ledger} WHERE pundit_id IN {pundit_in}")
        deleted = getattr(getattr(result, "job", None), "num_dml_affected_rows", None)
        if deleted is None:
            deleted = ledger_count
        logger.info(f"  Deleted {deleted} rows from {_LEDGER_TABLE}")
    except Exception as exc:
        logger.error(f"  DELETE failed for {_LEDGER_TABLE}: {exc}")
        raise

    # ---- Delete raw_utterance ----
    utterance_delete_q = f"""
        DELETE FROM {bq_utterance}
        WHERE source_doc_id IN (
            SELECT content_hash FROM {bq_media}
            WHERE matched_pundit_id IN {pundit_in}
        )
    """
    try:
        result = db.execute(utterance_delete_q)
        deleted = getattr(getattr(result, "job", None), "num_dml_affected_rows", None)
        if deleted is None:
            deleted = utterance_count
        logger.info(f"  Deleted {deleted} rows from {_RAW_UTTERANCE_TABLE}")
    except Exception as exc:
        logger.error(f"  DELETE failed for {_RAW_UTTERANCE_TABLE}: {exc}")
        raise

    return results


def step2_reset_processed_hashes(
    db: DBManager, project_id: str | None, dry_run: bool
) -> dict[str, int]:
    """
    Clear processed_media_hashes for pft_nbc and theathletic_nfl so those
    articles are re-extracted on the next assertion_extractor run.

    Only rows whose content_hash exists in raw_pundit_media for those sources
    are deleted — other sources are not affected.
    """
    results: dict[str, int] = {}
    source_in = _in_literal(CONTAMINATED_SOURCE_IDS)

    bq_processed = (
        f"`{project_id}.{_PROCESSED_HASHES_TABLE}`"
        if project_id
        else f'"{_PROCESSED_HASHES_TABLE.replace(".", '"."')}"'
    )
    bq_media = (
        f"`{project_id}.{_RAW_MEDIA_TABLE}`"
        if project_id
        else f'"{_RAW_MEDIA_TABLE.replace(".", '"."')}"'
    )

    count_q = f"""
        SELECT COUNT(*)
        FROM {bq_processed} p
        WHERE p.content_hash IN (
            SELECT content_hash
            FROM {bq_media}
            WHERE source_id IN {source_in}
        )
    """
    try:
        row = db.fetch_df(count_q)
        count = int(row.iloc[0, 0])
    except Exception as exc:
        logger.warning(f"Count query failed for processed_media_hashes: {exc}")
        count = -1
    results[_PROCESSED_HASHES_TABLE] = count
    logger.info(
        f"  processed_media_hashes: {count} rows to delete (source_id IN {source_in})"
    )

    if dry_run:
        logger.info("  DRY RUN — skipping delete")
        return results

    delete_q = f"""
        DELETE FROM {bq_processed} p
        WHERE p.content_hash IN (
            SELECT content_hash
            FROM {bq_media}
            WHERE source_id IN {source_in}
        )
    """
    try:
        result = db.execute(delete_q)
        deleted = getattr(getattr(result, "job", None), "num_dml_affected_rows", None)
        if deleted is None:
            deleted = count
        logger.info(f"  Deleted {deleted} rows from processed_media_hashes")
    except Exception as exc:
        logger.error(f"  DELETE failed for processed_media_hashes: {exc}")
        raise

    return results


def step3_run_extraction(limit: int = 500) -> None:
    """
    Invoke assertion_extractor immediately so re-extraction doesn't wait for
    the next daily cron. Only clean articles will be picked up (is_post_event
    filter is already live in get_unprocessed_media).
    """
    import subprocess

    python = sys.executable
    pipeline_dir = str(Path(__file__).resolve().parent.parent)
    cmd = [python, "-m", "src.assertion_extractor", "--limit", str(limit)]
    logger.info(f"Running extraction: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=pipeline_dir)
    if result.returncode != 0:
        logger.error(f"Extraction exited with code {result.returncode}")
        sys.exit(result.returncode)
    logger.info("Extraction complete.")


# ---------------------------------------------------------------------------
# Verification queries (printed after a live run for PR audit trail)
# ---------------------------------------------------------------------------

VERIFICATION_QUERIES = """
-- After running this script, verify the cleanup:

-- 1. Confirm no pft_staff / athletic_nfl_staff in prediction_ledger
SELECT pundit_id, COUNT(*) AS remaining
FROM `{project_id}.gold_layer.prediction_ledger`
WHERE pundit_id IN ('pft_staff', 'athletic_nfl_staff')
GROUP BY pundit_id;
-- Expected: 0 rows

-- 2. Confirm processed_media_hashes cleared for the two sources
SELECT p.content_hash, m.source_id
FROM `{project_id}.nfl_dead_money.processed_media_hashes` p
JOIN `{project_id}.nfl_dead_money.raw_pundit_media` m ON p.content_hash = m.content_hash
WHERE m.source_id IN ('pft_nbc', 'theathletic_nfl')
LIMIT 5;
-- Expected: 0 rows (all hashes cleared, ready for re-extraction)

-- 3. After re-extraction — confirm no draft-tracker content slipped through
SELECT content_hash, title, source_url
FROM `{project_id}.nfl_dead_money.raw_pundit_media`
WHERE source_id IN ('pft_nbc', 'theathletic_nfl')
  AND (is_post_event IS NULL OR is_post_event = FALSE)
  AND (
    LOWER(title) LIKE '%selects%' OR LOWER(title) LIKE '%drafts %'
    OR LOWER(source_url) LIKE '%draft-tracker%'
    OR LOWER(source_url) LIKE '%live-draft%'
  )
LIMIT 10;
-- Expected: 0 rows (post-event filter caught all of these)

-- 4. Check new clean assertions count after re-extraction
SELECT pundit_id, COUNT(*) AS predictions, COUNTIF(resolution_status IS NOT NULL) AS resolved
FROM `{project_id}.gold_layer.prediction_ledger`
WHERE pundit_id IN ('pft_staff', 'athletic_nfl_staff')
GROUP BY pundit_id;
-- Expected: non-zero counts with dramatically fewer predictions than before
--           (contaminated articles are filtered; only real forward-looking claims remain)
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Re-extract pft_staff and athletic_nfl_staff from clean corpus only "
            "(Issue #999). Deletes contaminated assertions, clears processed hashes, "
            "and optionally triggers immediate re-extraction."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print row counts and SQL; write nothing to the database.",
    )
    parser.add_argument(
        "--run-extraction",
        action="store_true",
        help="After resetting hashes, immediately run assertion_extractor (slow).",
    )
    parser.add_argument(
        "--extraction-limit",
        type=int,
        default=500,
        help="--limit passed to assertion_extractor when --run-extraction is set (default: 500).",
    )
    args = parser.parse_args()

    use_local = os.environ.get("USE_LOCAL_DB", "").lower() in ("1", "true", "yes")
    project_id = None if use_local else os.environ.get("GCP_PROJECT_ID")

    if not use_local and not project_id:
        logger.error(
            "GCP_PROJECT_ID is not set. Either set it or run with USE_LOCAL_DB=1."
        )
        sys.exit(1)

    backend = "DuckDB (local)" if use_local else f"BigQuery ({project_id})"
    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info(f"=== reextract_clean_corpus — {mode} / {backend} ===")
    logger.info(f"Target sources: {CONTAMINATED_SOURCE_IDS}")
    logger.info(f"Target pundit IDs (deletions): {CONTAMINATED_PUNDIT_IDS}")

    db = DBManager()

    summary: dict[str, object] = {
        "dry_run": args.dry_run,
        "backend": backend,
        "step1_deletions": {},
        "step2_hash_resets": {},
    }

    # ---- Step 1: delete contaminated assertions ----
    logger.info(
        "\n--- Step 1: Delete contaminated predictions from ledger + utterances ---"
    )
    summary["step1_deletions"] = step1_delete_contaminated_predictions(
        db, project_id, args.dry_run
    )

    # ---- Step 2: reset processed hashes ----
    logger.info(
        "\n--- Step 2: Reset processed_media_hashes for contaminated sources ---"
    )
    summary["step2_hash_resets"] = step2_reset_processed_hashes(
        db, project_id, args.dry_run
    )

    # ---- Step 3: optional immediate extraction ----
    if args.run_extraction and not args.dry_run:
        logger.info("\n--- Step 3: Run assertion_extractor (clean corpus only) ---")
        step3_run_extraction(limit=args.extraction_limit)
    elif args.run_extraction and args.dry_run:
        logger.info(
            "\n--- Step 3: --run-extraction requested but skipped (dry-run) ---"
        )

    # ---- Summary ----
    logger.info("\n=== Summary ===")
    print(json.dumps(summary, indent=2, default=str))

    if not args.dry_run:
        pid = project_id or "<local>"
        logger.info(
            "\n=== Verification queries (paste into BigQuery/DuckDB) ===\n"
            + VERIFICATION_QUERIES.format(project_id=pid)
        )
        logger.info(
            "\nNext steps:\n"
            "  1. Run the daily pipeline (or pass --run-extraction) to re-extract "
            "clean pft_nbc + theathletic_nfl articles.\n"
            "  2. After extraction completes, regenerate the leaderboard snapshot:\n"
            "     python pipeline/scripts/regen_leaderboard_snapshot.py\n"
            "     (Remove pft_staff and athletic_nfl_staff from STAFF_BUCKET_IDS\n"
            "     in that script first — they should be included once clean.)\n"
            "  3. Verify accuracy numbers are plausibly higher than 8.2% / 4.9%\n"
            "     (the contaminated baseline from issue #993).\n"
            "  4. Commit the updated leaderboard snapshot to close #999."
        )


if __name__ == "__main__":
    main()

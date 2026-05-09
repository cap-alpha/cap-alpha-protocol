#!/usr/bin/env python3
"""
backfill_metadata.py — Metadata completeness backfill for silver_v2_claims.raw_utterance

Issue: claims in raw_utterance may have NULL in key metadata fields:
  - speech_act_type     (NOT NULL after Phase C; default: "assertion")
  - testability_score   (NOT NULL after Phase C; default: 0.5)
  - resolution_horizon  (nullable TIMESTAMP; inferred via rule-based logic)
  - extraction_confidence (NOT NULL after Phase C; default: testability_score)
  - claim_category      (stored in prediction_ledger, not raw_utterance)

This script uses rule-based inference (NO LLM calls) to populate NULL metadata
fields in batches. It writes UPDATE-equivalent rows by reading the source table
and performing a MERGE into raw_utterance.

BigQuery does not support UPDATE on clustered tables without MERGE, so the
approach is:
  1. SELECT rows with NULL metadata fields.
  2. For each row, compute the inferred values in Python.
  3. MERGE the computed values back into the table keyed on utterance_id.

Targets:
  - silver_v2_claims.raw_utterance    — resolution_horizon + missing scores
  - gold_layer.prediction_ledger      — claim_category (defaulted to "general")

Usage:
    python -m scripts.backfill_metadata [--dry-run] [--limit N] [--table TABLE]

Options:
    --dry-run       Print what would be updated without writing to BQ.
    --limit N       Max rows to process per run (default: 5000).
    --table TABLE   Which table to backfill: "raw_utterance" (default) or
                    "prediction_ledger".
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python scripts/backfill_metadata.py` from repo root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from src.assertion_extractor import (
    DEFAULT_CLAIM_CATEGORY,
    DEFAULT_TESTABILITY_SCORE,
    infer_resolution_horizon,
)
from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RAW_UTTERANCE_TABLE = "silver_v2_claims.raw_utterance"
PREDICTION_LEDGER_TABLE = "gold_layer.prediction_ledger"

_DEFAULT_SPEECH_ACT_TYPE = "assertion"
_DEFAULT_EXTRACTION_CONFIDENCE = DEFAULT_TESTABILITY_SCORE


def _infer_row_resolution_horizon(row: dict) -> str | None:
    """
    Infer resolution_horizon for a single raw_utterance row.

    Priority order:
      1. Use `text` column if non-empty.
      2. Use `resolution_condition` column as fallback text.
    Returns an ISO-8601 string or None.
    """
    text = (row.get("text") or "").strip()
    resolution_condition = (row.get("resolution_condition") or "").strip()
    uttered_at_raw = row.get("uttered_at")

    uttered_at = None
    if uttered_at_raw is not None:
        try:
            uttered_at = pd.Timestamp(uttered_at_raw).to_pydatetime()
            if uttered_at.tzinfo is None:
                uttered_at = uttered_at.replace(tzinfo=timezone.utc)
        except Exception:
            uttered_at = None

    # Try primary text first, then resolution_condition as fallback
    result = infer_resolution_horizon(text, uttered_at=uttered_at)
    if result is None and resolution_condition:
        result = infer_resolution_horizon(resolution_condition, uttered_at=uttered_at)
    return result


def backfill_raw_utterance(
    db: DBManager,
    limit: int = 5000,
    dry_run: bool = False,
) -> dict:
    """
    Backfill NULL metadata fields in silver_v2_claims.raw_utterance.

    Fields targeted:
      - speech_act_type     → "assertion" if NULL
      - testability_score   → DEFAULT_TESTABILITY_SCORE (0.5) if NULL
      - extraction_confidence → testability_score value if NULL
      - resolution_horizon  → inferred from text pattern if NULL

    Returns a summary dict with counts of rows affected per field.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID env var is required")

    table_ref = f"`{project_id}.{RAW_UTTERANCE_TABLE}`"

    # Step 1: fetch rows with NULL metadata
    query = f"""
        SELECT
            utterance_id,
            text,
            resolution_condition,
            uttered_at,
            speech_act_type,
            testability_score,
            extraction_confidence,
            resolution_horizon
        FROM {table_ref}
        WHERE
            speech_act_type IS NULL
            OR testability_score IS NULL
            OR extraction_confidence IS NULL
            OR resolution_horizon IS NULL
        LIMIT {int(limit)}
    """
    logger.info(f"Fetching up to {limit} rows with NULL metadata from {RAW_UTTERANCE_TABLE}…")
    df = db.fetch_df(query)

    if df.empty:
        logger.info("No rows with NULL metadata found. Nothing to backfill.")
        return {
            "rows_scanned": 0,
            "speech_act_type_filled": 0,
            "testability_score_filled": 0,
            "extraction_confidence_filled": 0,
            "resolution_horizon_filled": 0,
            "rows_updated": 0,
        }

    logger.info(f"Found {len(df)} rows with NULL metadata.")

    # Step 2: compute inferred values
    updates = []
    counts = {
        "speech_act_type_filled": 0,
        "testability_score_filled": 0,
        "extraction_confidence_filled": 0,
        "resolution_horizon_filled": 0,
    }

    for _, row in df.iterrows():
        utterance_id = row["utterance_id"]
        new_sat = new_ts = new_ec = new_rh = None

        if pd.isna(row.get("speech_act_type")) or not row.get("speech_act_type"):
            new_sat = _DEFAULT_SPEECH_ACT_TYPE
            counts["speech_act_type_filled"] += 1

        if pd.isna(row.get("testability_score")):
            new_ts = DEFAULT_TESTABILITY_SCORE
            counts["testability_score_filled"] += 1

        # extraction_confidence defaults to testability_score (after its potential fill)
        if pd.isna(row.get("extraction_confidence")):
            new_ec = float(new_ts) if new_ts is not None else DEFAULT_TESTABILITY_SCORE
            counts["extraction_confidence_filled"] += 1

        if pd.isna(row.get("resolution_horizon")) or row.get("resolution_horizon") is None:
            inferred = _infer_row_resolution_horizon(row.to_dict())
            if inferred:
                new_rh = inferred
                counts["resolution_horizon_filled"] += 1

        if new_sat is None and new_ts is None and new_ec is None and new_rh is None:
            continue  # Nothing to update for this row

        updates.append({
            "utterance_id": utterance_id,
            "speech_act_type": new_sat,
            "testability_score": new_ts,
            "extraction_confidence": new_ec,
            "resolution_horizon": new_rh,
        })

    if not updates:
        logger.info("All NULL fields were unresolvable (e.g., resolution_horizon with no text patterns).")
        return {
            "rows_scanned": len(df),
            "rows_updated": 0,
            **counts,
        }

    logger.info(
        f"Computed updates for {len(updates)} rows: "
        f"speech_act_type={counts['speech_act_type_filled']}, "
        f"testability_score={counts['testability_score_filled']}, "
        f"extraction_confidence={counts['extraction_confidence_filled']}, "
        f"resolution_horizon={counts['resolution_horizon_filled']}"
    )

    if dry_run:
        logger.info("DRY RUN — no writes performed. Sample of first 5 updates:")
        for u in updates[:5]:
            logger.info(f"  {u}")
        return {
            "rows_scanned": len(df),
            "rows_updated": 0,
            "dry_run": True,
            **counts,
        }

    # Step 3: MERGE updates back using a temp table approach
    # BigQuery: stage updates as a VALUES subquery in a MERGE statement.
    # We batch to avoid overly large SQL statements.
    _BATCH_SIZE = 500
    total_updated = 0

    for batch_start in range(0, len(updates), _BATCH_SIZE):
        batch = updates[batch_start : batch_start + _BATCH_SIZE]

        # Build VALUES rows for MERGE source
        value_rows = []
        for u in batch:
            uid = u["utterance_id"].replace("'", "''")  # escape single quotes
            sat = f"'{u['speech_act_type']}'" if u["speech_act_type"] else "NULL"
            ts = str(u["testability_score"]) if u["testability_score"] is not None else "NULL"
            ec = str(u["extraction_confidence"]) if u["extraction_confidence"] is not None else "NULL"
            rh = f"TIMESTAMP('{u['resolution_horizon']}')" if u["resolution_horizon"] else "NULL"
            value_rows.append(
                f"('{uid}', {sat}, CAST({ts} AS FLOAT64), CAST({ec} AS FLOAT64), {rh})"
            )

        values_sql = ",\n        ".join(value_rows)

        merge_sql = f"""
            MERGE {table_ref} AS target
            USING (
                SELECT * FROM UNNEST([
                    STRUCT<utterance_id STRING, speech_act_type STRING,
                           testability_score FLOAT64, extraction_confidence FLOAT64,
                           resolution_horizon TIMESTAMP>
                    {values_sql}
                ])
            ) AS source
            ON target.utterance_id = source.utterance_id
            WHEN MATCHED THEN UPDATE SET
                speech_act_type = COALESCE(target.speech_act_type, source.speech_act_type),
                testability_score = COALESCE(target.testability_score, source.testability_score),
                extraction_confidence = COALESCE(target.extraction_confidence, source.extraction_confidence),
                resolution_horizon = COALESCE(target.resolution_horizon, source.resolution_horizon)
        """

        try:
            result = db.execute(merge_sql)
            rows_affected = result.job.num_dml_affected_rows or 0
            total_updated += rows_affected
            logger.info(
                f"Batch {batch_start // _BATCH_SIZE + 1}: "
                f"merged {rows_affected} rows"
            )
        except Exception as exc:
            logger.error(f"MERGE failed for batch starting at {batch_start}: {exc}")
            raise

    logger.info(f"Backfill complete. Total rows updated: {total_updated}")
    return {
        "rows_scanned": len(df),
        "rows_updated": total_updated,
        **counts,
    }


def backfill_prediction_ledger(
    db: DBManager,
    limit: int = 5000,
    dry_run: bool = False,
) -> dict:
    """
    Backfill NULL claim_category in gold_layer.prediction_ledger.

    Sets claim_category = DEFAULT_CLAIM_CATEGORY ("general") for any row
    where claim_category IS NULL.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if not project_id:
        raise RuntimeError("GCP_PROJECT_ID env var is required")

    table_ref = f"`{project_id}.{PREDICTION_LEDGER_TABLE}`"

    query = f"""
        SELECT prediction_hash, claim_category
        FROM {table_ref}
        WHERE claim_category IS NULL
        LIMIT {int(limit)}
    """
    logger.info(f"Fetching rows with NULL claim_category from {PREDICTION_LEDGER_TABLE}…")
    df = db.fetch_df(query)

    if df.empty:
        logger.info("No rows with NULL claim_category. Nothing to backfill.")
        return {"rows_scanned": 0, "rows_updated": 0, "claim_category_filled": 0}

    logger.info(f"Found {len(df)} rows with NULL claim_category.")

    if dry_run:
        logger.info(f"DRY RUN — would set claim_category='{DEFAULT_CLAIM_CATEGORY}' for {len(df)} rows.")
        return {
            "rows_scanned": len(df),
            "rows_updated": 0,
            "claim_category_filled": len(df),
            "dry_run": True,
        }

    # MERGE to update claim_category
    hashes = [str(r).replace("'", "''") for r in df["prediction_hash"].tolist()]
    _BATCH_SIZE = 500

    total_updated = 0
    for batch_start in range(0, len(hashes), _BATCH_SIZE):
        batch = hashes[batch_start : batch_start + _BATCH_SIZE]
        hash_list = ", ".join(f"'{h}'" for h in batch)

        update_sql = f"""
            UPDATE {table_ref}
            SET claim_category = '{DEFAULT_CLAIM_CATEGORY}'
            WHERE prediction_hash IN ({hash_list})
              AND claim_category IS NULL
        """
        try:
            result = db.execute(update_sql)
            rows_affected = result.job.num_dml_affected_rows or 0
            total_updated += rows_affected
            logger.info(f"Batch {batch_start // _BATCH_SIZE + 1}: updated {rows_affected} rows")
        except Exception as exc:
            logger.error(f"UPDATE failed for batch starting at {batch_start}: {exc}")
            raise

    logger.info(f"Prediction ledger backfill complete. Total rows updated: {total_updated}")
    return {
        "rows_scanned": len(df),
        "rows_updated": total_updated,
        "claim_category_filled": total_updated,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Backfill NULL metadata in silver_v2_claims.raw_utterance and gold_layer.prediction_ledger"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be updated without writing to BigQuery.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Max rows to process per run (default: 5000).",
    )
    parser.add_argument(
        "--table",
        choices=["raw_utterance", "prediction_ledger", "both"],
        default="both",
        help="Which table to backfill (default: both).",
    )
    args = parser.parse_args()

    db = DBManager()
    try:
        results = {}
        if args.table in ("raw_utterance", "both"):
            results["raw_utterance"] = backfill_raw_utterance(
                db, limit=args.limit, dry_run=args.dry_run
            )
        if args.table in ("prediction_ledger", "both"):
            results["prediction_ledger"] = backfill_prediction_ledger(
                db, limit=args.limit, dry_run=args.dry_run
            )

        import json
        print(json.dumps(results, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()

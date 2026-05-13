#!/usr/bin/env python3
"""
backfill_provider_attribution.py — Attribute llm_provider / llm_model on legacy ledger rows.

Context
-------
gold_layer.prediction_ledger has 1,498 rows where llm_provider IS NULL and llm_model IS NULL.
These rows were written before the llm_provider / llm_model columns were added or populated
(ingestion_timestamp range: 2026-04-04 → 2026-05-01).

Attribution strategy
--------------------
Step 1 — extraction_run join (confident attribution):
    For each NULL ledger row, attempt to match it to a silver_v2_claims.extraction_run via:
        ledger.source_url
            → nfl_dead_money.raw_pundit_media.source_url (content_hash)
            → silver_v2_claims.raw_utterance.source_doc_id
            → silver_v2_claims.extraction_run (utterance.created_at between run.started_at and run.finished_at)
    Only a UNIQUE match per prediction_hash counts; ambiguous multi-run matches are skipped
    and fall through to Step 2.

Step 2 — legacy fallback (honesty constraint):
    Rows that cannot be confidently attributed via Step 1 receive:
        llm_provider = 'legacy_pre_attribution'
        llm_model    = 'unknown_pre_2025_q3'
    These sentinel values signal that the exact extraction provenance is unknown.
    DO NOT invent provider names; use only these two sentinel values.

Idempotence
-----------
The script checks CURRENT state before writing. Rows already attributed (non-NULL
llm_provider) are skipped unconditionally — re-running is always a no-op for those rows.

Temporal distribution of NULL rows (as of 2026-05-13):
    2026-04: 1,038 rows  (earliest 2026-04-04)
    2026-05: 460 rows    (latest 2026-05-01)
    All rows predate the extraction_run table (first entry: 2026-05-03), so in
    practice all rows fall through to the legacy_pre_attribution sentinel.

Usage
-----
    python pipeline/scripts/backfill_provider_attribution.py --dry-run   # report only
    python pipeline/scripts/backfill_provider_attribution.py             # apply updates
    python pipeline/scripts/backfill_provider_attribution.py --limit 500 # cap rows per run
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.db_manager import get_db_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ── Sentinel values for rows that cannot be confidently attributed ──────────
# Honesty constraint: do not invent real provider names for unknown rows.
LEGACY_PROVIDER = "legacy_pre_attribution"
LEGACY_MODEL = "unknown_pre_2025_q3"

# Batch size for UPDATE statements (avoid oversized SQL on both BQ and DuckDB)
_BATCH_SIZE = 500


def _fetch_null_rows(db, limit: int):
    """Return DataFrame of prediction_ledger rows with NULL llm_provider."""
    query = """
        SELECT prediction_hash, source_url, ingestion_timestamp
        FROM gold_layer.prediction_ledger
        WHERE llm_provider IS NULL
        LIMIT {limit}
    """.format(limit=int(limit))
    return db.fetch_df(query)


def _find_attributed_rows(db, null_hashes: list[str]) -> dict[str, tuple[str, str]]:
    """
    Attempt to join NULL ledger rows back to silver_v2_claims.extraction_run via:
        ledger.source_url → raw_pundit_media.content_hash
                          → raw_utterance.source_doc_id
                          → extraction_run (timestamp window)

    Returns a dict mapping prediction_hash → (provider, model) for rows where
    exactly ONE extraction_run matches (ambiguous multi-run matches are excluded).
    """
    if not null_hashes:
        return {}

    # Build a comma-delimited literal list for the IN clause
    hash_literals = ", ".join(f"'{h.replace(chr(39), chr(39)*2)}'" for h in null_hashes)

    query = f"""
        SELECT
            l.prediction_hash,
            er.provider,
            er.model,
            COUNT(DISTINCT er.run_id) AS run_count
        FROM gold_layer.prediction_ledger l
        JOIN nfl_dead_money.raw_pundit_media m
            ON l.source_url = m.source_url
        JOIN silver_v2_claims.raw_utterance u
            ON u.source_doc_id = m.content_hash
        JOIN silver_v2_claims.extraction_run er
            ON u.created_at >= er.started_at
           AND u.created_at <= er.finished_at
        WHERE l.prediction_hash IN ({hash_literals})
          AND l.llm_provider IS NULL
        GROUP BY l.prediction_hash, er.provider, er.model
        HAVING COUNT(DISTINCT er.run_id) = 1
    """
    try:
        df = db.fetch_df(query)
    except Exception as exc:
        logger.warning("extraction_run join failed (will fall back to legacy): %s", exc)
        return {}

    attribution: dict[str, tuple[str, str]] = {}
    for _, row in df.iterrows():
        ph = row["prediction_hash"]
        if ph in attribution:
            # If a second provider pair appears for the same hash, it's ambiguous — skip
            del attribution[ph]
        else:
            attribution[ph] = (row["provider"], row["model"])

    return attribution


def _apply_updates(db, updates: list[dict], dry_run: bool) -> int:
    """
    Write provider/model updates to gold_layer.prediction_ledger.

    Each element of `updates` is a dict with keys:
        prediction_hash, llm_provider, llm_model

    Returns the number of rows actually updated (0 in dry-run mode).
    Uses UPDATE … WHERE … AND llm_provider IS NULL to preserve idempotence.
    """
    if not updates:
        return 0

    if dry_run:
        logger.info("DRY RUN — sample of first 5 planned updates:")
        for u in updates[:5]:
            logger.info(
                "  %s -> %s / %s",
                u["prediction_hash"][:16],
                u["llm_provider"],
                u["llm_model"],
            )
        return 0

    total_updated = 0
    for batch_start in range(0, len(updates), _BATCH_SIZE):
        batch = updates[batch_start : batch_start + _BATCH_SIZE]

        # Group by (provider, model) to minimise the number of UPDATE statements
        by_key: dict[tuple[str, str], list[str]] = {}
        for u in batch:
            key = (u["llm_provider"], u["llm_model"])
            by_key.setdefault(key, []).append(u["prediction_hash"])

        for (provider, model), hashes in by_key.items():
            hash_literals = ", ".join(f"'{h.replace(chr(39), chr(39)*2)}'" for h in hashes)
            p_esc = provider.replace("'", "''")
            m_esc = model.replace("'", "''")
            update_sql = f"""
                UPDATE gold_layer.prediction_ledger
                SET llm_provider = '{p_esc}',
                    llm_model    = '{m_esc}'
                WHERE prediction_hash IN ({hash_literals})
                  AND llm_provider IS NULL
            """
            try:
                db.execute(update_sql)
                total_updated += len(hashes)
                logger.info(
                    "Updated %d rows: provider=%s model=%s",
                    len(hashes),
                    provider,
                    model,
                )
            except Exception as exc:
                logger.error("UPDATE failed for batch (%s/%s): %s", provider, model, exc)
                raise

    return total_updated


def run_backfill(limit: int = 10_000, dry_run: bool = False) -> dict:
    """
    Main backfill logic. Returns a summary dict.

    Returns
    -------
    dict with keys:
        null_rows_found         int  — rows with NULL llm_provider
        attributed_via_join     int  — rows matched to an extraction_run
        labeled_legacy          int  — rows receiving legacy_pre_attribution sentinel
        rows_updated            int  — rows actually written (0 in dry-run)
        dry_run                 bool
    """
    db = get_db_manager()
    try:
        # ── Step 0: fetch NULL rows ─────────────────────────────────────────
        logger.info(
            "Fetching NULL rows from gold_layer.prediction_ledger (limit=%d)…", limit
        )
        df = _fetch_null_rows(db, limit)

        if df.empty:
            logger.info("No NULL rows found — nothing to backfill.")
            return {
                "null_rows_found": 0,
                "attributed_via_join": 0,
                "labeled_legacy": 0,
                "rows_updated": 0,
                "dry_run": dry_run,
            }

        null_hashes = df["prediction_hash"].tolist()
        logger.info("Found %d rows with NULL llm_provider / llm_model.", len(null_hashes))

        # ── Step 1: attempt extraction_run join ────────────────────────────
        logger.info("Attempting extraction_run join for confident attribution…")
        join_attrs = _find_attributed_rows(db, null_hashes)
        logger.info(
            "extraction_run join attributed %d / %d rows.",
            len(join_attrs),
            len(null_hashes),
        )

        # ── Step 2: build update list ──────────────────────────────────────
        updates: list[dict] = []
        attributed_count = 0
        legacy_count = 0

        for ph in null_hashes:
            if ph in join_attrs:
                provider, model = join_attrs[ph]
                updates.append(
                    {"prediction_hash": ph, "llm_provider": provider, "llm_model": model}
                )
                attributed_count += 1
            else:
                # Honesty constraint: use sentinel values for unattributable rows
                updates.append(
                    {
                        "prediction_hash": ph,
                        "llm_provider": LEGACY_PROVIDER,
                        "llm_model": LEGACY_MODEL,
                    }
                )
                legacy_count += 1

        logger.info(
            "Update plan: %d via join, %d via legacy_pre_attribution sentinel.",
            attributed_count,
            legacy_count,
        )

        # ── Step 3: apply updates ──────────────────────────────────────────
        rows_updated = _apply_updates(db, updates, dry_run=dry_run)

        summary = {
            "null_rows_found": len(null_hashes),
            "attributed_via_join": attributed_count,
            "labeled_legacy": legacy_count,
            "rows_updated": rows_updated,
            "dry_run": dry_run,
        }

        if not dry_run:
            # Re-query for final composition
            composition_query = """
                SELECT llm_provider, llm_model, COUNT(*) AS cnt
                FROM gold_layer.prediction_ledger
                GROUP BY llm_provider, llm_model
                ORDER BY cnt DESC
            """
            comp_df = db.fetch_df(composition_query)
            summary["final_composition"] = comp_df.to_dict(orient="records")

        return summary

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Backfill llm_provider / llm_model on legacy NULL rows in prediction_ledger."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be updated without writing any rows.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10_000,
        help="Maximum NULL rows to process per run (default: 10,000).",
    )
    args = parser.parse_args()

    import json

    result = run_backfill(limit=args.limit, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Sync BigQuery tables → local DuckDB.

Pulls every tracked table from BQ and reloads it into the local DuckDB file.
Safe to re-run: each table is truncated before reload (full refresh).

Usage:
    python -m src.sync_bq_to_duckdb                 # uses DUCKDB_PATH or default
    python -m src.sync_bq_to_duckdb --dry-run       # print counts only, no write
    python -m src.sync_bq_to_duckdb --tables gold_layer.prediction_ledger

Skips tables that don't exist in BQ (404) — they stay empty in DuckDB.
"""

import argparse
import json
import logging
import os
import sys
import time

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Tables to sync: (bq_dataset, table_name)
# Ordered so FK parents come before children where it matters.
SYNC_TABLES = [
    ("nfl_dead_money", "pundit_registry"),
    ("nfl_dead_money", "source_registry"),
    ("nfl_dead_money", "raw_pundit_media"),
    ("nfl_dead_money", "processed_media_hashes"),
    ("nfl_dead_money", "registry_audit_log"),
    ("nfl_dead_money", "entities"),
    ("nfl_dead_money", "prediction_ledger_graph_extension"),
    ("gold_layer", "ledger_chain_head"),
    ("gold_layer", "prediction_ledger"),
    ("gold_layer", "prediction_resolutions"),
    ("silver_v2_claims", "extraction_run"),
    ("silver_v2_claims", "raw_utterance"),
    ("silver_v2_claims", "resolution_method"),
    ("silver_v2_claims", "claim"),
    ("silver_v2_claims", "resolution"),
    ("silver_v2_core", "domain_taxonomy"),
    ("silver_v2_core", "entity"),
    ("silver_v2_core", "entity_alias"),
    ("silver_v2_core", "entity_attribute_event"),
    ("silver_v2_core", "transition_event"),
    ("silver_v2_sports", "franchise_lineage"),
]

# JSON columns that BQ returns as dicts/objects — serialise back to strings for DuckDB
_JSON_COLS = {
    "metadata",
    "asserted_state",
    "raw_metadata",
    "attribute_specs",
    "resolution_adapter",
    "config",
    "predicate_args",
    "evidence",
    "external_ids",
    "value_json",
    "payload",
    "target_entity",
}


def _duck_columns(duck_conn, schema: str, table: str) -> list[str]:
    """Return column names from the DuckDB table definition."""
    rows = duck_conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = $s AND table_name = $t ORDER BY ordinal_position",
        {"s": schema, "t": table},
    ).fetchall()
    return [r[0] for r in rows]


def _duck_numeric_cols(duck_conn, schema: str, table: str) -> set[str]:
    """Return column names whose DuckDB type is numeric (DOUBLE, BIGINT, etc.)."""
    rows = duck_conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = $s AND table_name = $t",
        {"s": schema, "t": table},
    ).fetchall()
    numeric_types = {
        "DOUBLE",
        "FLOAT",
        "BIGINT",
        "INTEGER",
        "HUGEINT",
        "SMALLINT",
        "TINYINT",
        "DECIMAL",
        "REAL",
    }
    return {r[0] for r in rows if r[1].upper() in numeric_types}


def _normalise_df(
    df: pd.DataFrame, duck_cols: list[str], numeric_cols: set[str]
) -> pd.DataFrame:
    """
    Project df to only the columns DuckDB knows about, then coerce types.
    - Drops BQ-only columns (schema drift)
    - Serialises JSON object/list columns to strings
    - Converts pandas 'None' strings to None only for numeric columns
      (VARCHAR columns can legitimately store the string "None" as data)
    """
    keep = [c for c in duck_cols if c in df.columns]
    df = df[keep].copy()

    for col in df.columns:
        if col in _JSON_COLS:
            df[col] = df[col].apply(
                lambda v: json.dumps(v) if isinstance(v, (dict, list)) else v
            )
        # Only convert "None" → None for numeric columns to avoid corrupting VARCHAR data.
        if df[col].dtype == object and col in numeric_cols:
            df[col] = df[col].apply(
                lambda v: None if (isinstance(v, str) and v == "None") else v
            )

    return df


def sync(dry_run: bool = False, only_tables: list[str] | None = None) -> None:
    import os as _os

    project = _os.environ.get("GCP_PROJECT_ID")
    if not project:
        logger.error("GCP_PROJECT_ID not set — cannot connect to BigQuery.")
        sys.exit(1)

    from src.db_manager import DBManager
    from src.duckdb_manager import DuckDBManager

    bq = DBManager()
    duck = DuckDBManager()

    results = []

    for dataset, table in SYNC_TABLES:
        qualified = f"{dataset}.{table}"
        if only_tables and qualified not in only_tables:
            continue

        t0 = time.time()

        # Get DuckDB column list and numeric types for type-safe normalisation
        duck_cols = _duck_columns(duck._conn, dataset, table)
        numeric_cols = _duck_numeric_cols(duck._conn, dataset, table)
        if not duck_cols:
            logger.warning("  %-50s SKIP  (no DuckDB table)", qualified)
            results.append((qualified, "skip", 0, 0))
            continue

        try:
            df = bq.fetch_df(f"SELECT * FROM `{project}.{dataset}.{table}`")
        except Exception as e:
            msg = str(e)
            if "404" in msg or "Not found" in msg:
                logger.info("  %-50s SKIP  (table not in BQ)", qualified)
                results.append((qualified, "skip", 0, 0))
            else:
                logger.warning("  %-50s ERROR %s", qualified, msg[:120])
                results.append((qualified, "error", 0, 0))
            continue

        rows = len(df)
        elapsed = time.time() - t0

        # Report any BQ columns we're dropping
        extra = [c for c in df.columns if c not in duck_cols]
        if extra:
            logger.info(
                "  %-50s %5d rows  (%.1fs)  [dropping BQ-only cols: %s]",
                qualified,
                rows,
                elapsed,
                ", ".join(extra),
            )
        else:
            logger.info("  %-50s %5d rows  (%.1fs)", qualified, rows, elapsed)

        if dry_run:
            results.append((qualified, "dry-run", rows, elapsed))
            continue

        df = _normalise_df(df, duck_cols, numeric_cols)

        # Truncate then reload
        try:
            duck._conn.execute(f"DELETE FROM {qualified}")
            if rows > 0:
                duck.append_dataframe_to_table(df, qualified)
            results.append((qualified, "ok", rows, elapsed))
        except Exception as e:
            logger.error("  %-50s WRITE ERROR: %s", qualified, e)
            results.append((qualified, "error", rows, elapsed))

    bq.close()
    duck.close()

    print("\n── Sync summary ──────────────────────────────────────")
    ok = skip = err = total_rows = 0
    for table, status, rows, _ in results:
        icon = {"ok": "✓", "skip": "–", "error": "✗", "dry-run": "○"}.get(status, "?")
        print(f"  {icon}  {table:<45}  {rows:>6} rows  [{status}]")
        total_rows += rows
        if status == "ok":
            ok += 1
        elif status == "skip":
            skip += 1
        elif status == "error":
            err += 1
    print(
        f"\n  {ok} synced · {skip} skipped · {err} errors · {total_rows:,} total rows"
    )
    if err:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Count rows only, no write"
    )
    parser.add_argument(
        "--tables",
        nargs="+",
        metavar="SCHEMA.TABLE",
        help="Sync only these tables (e.g. gold_layer.prediction_ledger)",
    )
    args = parser.parse_args()
    sync(dry_run=args.dry_run, only_tables=args.tables)

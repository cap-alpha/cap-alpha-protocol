"""
seed_test_data_duckdb.py — Insert synthetic test data into DuckDB for Phase 2 migration validation.

Seeds:
  - gold_layer.prediction_ledger  (~20 rows)
  - gold_layer.prediction_resolutions (~10 rows)

Usage:
    DB_BACKEND=duckdb python3 pipeline/scripts/seed_test_data_duckdb.py

Prerequisites:
    DB_BACKEND=duckdb python3 pipeline/scripts/init_local_db.py  (schema must exist)
"""

import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PIPELINE_DIR.parent))

_DEFAULT_DB_PATH = _PIPELINE_DIR / "data" / "local.duckdb"


def _sha256(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def _ts(days_ago: int = 0, hours: int = 0) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours)
    return dt.strftime("%Y-%m-%d %H:%M:%S+00")


def build_ledger_rows() -> list[dict]:
    """Build 20 synthetic prediction_ledger rows."""
    pundits = [
        ("adam_schefter", "Adam Schefter"),
        ("pat_mcafee", "Pat McAfee"),
        ("ian_rapoport", "Ian Rapoport"),
        ("mel_kiper", "Mel Kiper Jr."),
    ]
    players = [
        ("travis_kelce", "Travis Kelce", "KC"),
        ("lamar_jackson", "Lamar Jackson", "BAL"),
        ("patrick_mahomes", "Patrick Mahomes", "KC"),
        ("tyreek_hill", "Tyreek Hill", "MIA"),
        ("justin_jefferson", "Justin Jefferson", "MIN"),
        (None, None, "NE"),  # team-only claim
    ]
    statuses = ["PENDING", "CORRECT", "INCORRECT", "VOID", "PENDING"]

    rows = []
    for i in range(20):
        pundit_id, pundit_name = pundits[i % len(pundits)]
        player_id, player_name, team = players[i % len(players)]
        status = statuses[i % len(statuses)]
        src_url = f"https://example.com/article/{i+1}"
        raw_text = f"Claim #{i+1}: {pundit_name} says {player_name or team} will perform well in 2024."
        extracted = f"Prediction #{i+1} about {player_name or team}"
        ingestion_ts = _ts(days_ago=60 - i * 2)
        prediction_hash = _sha256(ingestion_ts, src_url, pundit_id, raw_text)
        chain_hash = _sha256(prediction_hash, f"prev_{i}")
        rows.append({
            "prediction_hash": prediction_hash,
            "chain_hash": chain_hash,
            "ingestion_timestamp": ingestion_ts,
            "source_url": src_url,
            "pundit_id": pundit_id,
            "pundit_name": pundit_name,
            "raw_assertion_text": raw_text,
            "extracted_claim": extracted,
            "claim_category": "player_performance",
            "season_year": 2024,
            "target_player_id": player_id,
            "target_team": team,
            "sport": "NFL",
            "resolution_status": status,
            "resolved_at": _ts(days_ago=10) if status != "PENDING" else None,
            "resolution_notes": f"Resolved as {status}" if status != "PENDING" else None,
            "target_player_name": player_name,
            "stance": "assertive",
            "prompt_version": "v2.1",
            "llm_provider": "ollama",
            "llm_model": "qwen2.5:32b",
            "target_entity": player_name or team,
        })
    return rows


def build_resolutions_rows(ledger_rows: list[dict]) -> list[dict]:
    """Build ~10 resolution rows for non-PENDING ledger rows."""
    rows = []
    for row in ledger_rows:
        if row["resolution_status"] == "PENDING":
            continue
        brier = 0.1 if row["resolution_status"] == "CORRECT" else 0.8
        binary_correct = row["resolution_status"] == "CORRECT"
        weighted = 0.9 if binary_correct else 0.1
        rows.append({
            "prediction_hash": row["prediction_hash"],
            "sport": row["sport"],
            "resolution_status": row["resolution_status"],
            "resolved_at": row["resolved_at"],
            "resolver": "auto",
            "brier_score": brier,
            "binary_correct": binary_correct,
            "timeliness_weight": 1.0,
            "weighted_score": weighted,
            "outcome_source": "manual",
            "outcome_reference_id": None,
            "outcome_notes": f"Outcome: {row['resolution_status']}",
            "created_at": row["resolved_at"],
            "updated_at": row["resolved_at"],
        })
    return rows


def seed(db_path: str) -> None:
    import duckdb

    conn = duckdb.connect(db_path)

    # Ensure schemas exist
    for schema in ("gold_layer", "silver_v2_claims", "silver_v2_core"):
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

    ledger_rows = build_ledger_rows()
    resolution_rows = build_resolutions_rows(ledger_rows)

    # Check if already seeded
    existing = conn.execute(
        "SELECT COUNT(*) FROM gold_layer.prediction_ledger"
    ).fetchone()[0]
    if existing > 0:
        print(f"  Already seeded ({existing} rows in prediction_ledger). Skipping.")
        conn.close()
        return

    # Seed prediction_ledger — introspect columns so we don't insert non-existent ones
    existing_pl_cols = {
        c[0]
        for c in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='gold_layer' AND table_name='prediction_ledger'"
        ).fetchall()
    }
    ts_cols = {"ingestion_timestamp", "resolved_at"}
    for row in ledger_rows:
        insert_row = {k: v for k, v in row.items() if k in existing_pl_cols}
        col_parts = []
        val_parts = []
        bound_params: dict = {}
        for k, v in insert_row.items():
            if k in ts_cols and v is None:
                col_parts.append(k)
                val_parts.append("NULL")
            elif k in ts_cols:
                col_parts.append(k)
                val_parts.append(f"${k}::TIMESTAMP")
                bound_params[k] = v
            else:
                col_parts.append(k)
                val_parts.append(f"${k}")
                bound_params[k] = v
        conn.execute(
            f"INSERT INTO gold_layer.prediction_ledger ({', '.join(col_parts)}) VALUES ({', '.join(val_parts)})",
            bound_params,
        )

    print(f"  Seeded {len(ledger_rows)} rows into gold_layer.prediction_ledger")

    # Seed prediction_resolutions — introspect columns similarly
    existing_pr_cols = {
        c[0]
        for c in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='gold_layer' AND table_name='prediction_resolutions'"
        ).fetchall()
    }
    pr_ts_cols = {"resolved_at", "created_at", "updated_at"}
    for row in resolution_rows:
        insert_row = {k: v for k, v in row.items() if k in existing_pr_cols}
        col_parts = []
        val_parts = []
        bound_params: dict = {}
        for k, v in insert_row.items():
            if k in pr_ts_cols and v is None:
                col_parts.append(k)
                val_parts.append("NULL")
            elif k in pr_ts_cols:
                col_parts.append(k)
                val_parts.append(f"${k}::TIMESTAMP")
                bound_params[k] = v
            else:
                col_parts.append(k)
                val_parts.append(f"${k}")
                bound_params[k] = v
        conn.execute(
            f"INSERT INTO gold_layer.prediction_resolutions ({', '.join(col_parts)}) VALUES ({', '.join(val_parts)})",
            bound_params,
        )

    print(f"  Seeded {len(resolution_rows)} rows into gold_layer.prediction_resolutions")

    # Verify counts
    pl_count = conn.execute("SELECT COUNT(*) FROM gold_layer.prediction_ledger").fetchone()[0]
    pr_count = conn.execute("SELECT COUNT(*) FROM gold_layer.prediction_resolutions").fetchone()[0]
    print(f"  Verification: prediction_ledger={pl_count}, prediction_resolutions={pr_count}")

    conn.close()


def main() -> None:
    db_path = os.environ.get("DUCKDB_PATH", str(_DEFAULT_DB_PATH))
    print(f"Seeding test data into: {db_path}")
    seed(db_path)
    print("Done.")


if __name__ == "__main__":
    main()

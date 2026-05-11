#!/usr/bin/env python3
"""
backfill_entities.py — Populate gold_layer.entities and
nfl_dead_money.prediction_ledger_graph_extension from existing
prediction_ledger rows.

Usage (DuckDB local):
    DB_BACKEND=duckdb DUCKDB_PATH=pipeline/data/local.duckdb \\
        python -m src.backfill_entities

Usage (BigQuery — not yet implemented, exits early):
    python -m src.backfill_entities

Entity derivation priority per prediction_ledger row:
  1. target_entity IS NOT NULL  → parse JSON, extract type/name/sport
  2. target_player_name IS NOT NULL → synthesise {type:"player", name, sport}
  3. target_team IS NOT NULL       → synthesise {type:"team", name, sport}
  4. otherwise                     → skip (no entity data)

Entity ID: sha256(type + "|" + name + "|" + (sport or ""))[:32] formatted as UUID.
Deduplication: exact (type, name, sport) match — one entity row per triple.

Acceptance criteria (idempotent):
  SELECT COUNT(*) FROM gold_layer.entities        > 0
  SELECT COUNT(*) FROM claim_edges WHERE primary_entity_id IS NOT NULL > 0
  Running twice produces same result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPORT_DOMAIN_MAP = {
    "NFL": "sports.nfl",
    "NBA": "sports.nba",
    "MLB": "sports.mlb",
    "NHL": "sports.nhl",
    "CFB": "sports.cfb",
    "CBB": "sports.cbb",
}


def _derive_entity_id(entity_type: str, name: str, sport: Optional[str]) -> str:
    """
    Deterministic UUID-shaped ID derived from (type, name, sport).

    sha256(type + "|" + name + "|" + (sport or ""))[:32] formatted as a UUID.
    Re-running with the same inputs always returns the same string.
    """
    raw = f"{entity_type}|{name}|{sport or ''}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
    # Format as UUID: 8-4-4-4-12
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
    )


def _parse_target_entity(json_val, row_sport: Optional[str]) -> Optional[dict]:
    """
    Extract (type, name, sport) from a target_entity JSON value.
    Returns None if the JSON is unparseable or missing required fields.
    """
    if json_val is None:
        return None
    if isinstance(json_val, str):
        try:
            parsed = json.loads(json_val)
        except (json.JSONDecodeError, ValueError):
            return None
    elif isinstance(json_val, dict):
        parsed = json_val
    else:
        return None

    entity_type = parsed.get("type") or parsed.get("entity_type")
    name = parsed.get("name") or parsed.get("canonical_name")
    sport = parsed.get("sport") or row_sport

    if not entity_type or not name:
        return None

    return {
        "type": entity_type.lower(),
        "name": str(name).strip(),
        "sport": str(sport).upper() if sport else None,
    }


def _sport_to_domain(sport: Optional[str]) -> str:
    """Map sport code to domain string."""
    if not sport:
        return "sports"
    return _SPORT_DOMAIN_MAP.get(sport.upper(), "sports")


# ---------------------------------------------------------------------------
# Core backfill
# ---------------------------------------------------------------------------


def run_backfill(db_path: str, dry_run: bool = False) -> dict:
    """
    Execute the full backfill: read prediction_ledger, upsert entities and
    graph-extension rows.  Returns a dict with counts.
    """
    import duckdb

    con = duckdb.connect(db_path)

    # Ensure schemas + tables exist (safe to re-run).
    # We only create them if missing; we do NOT drop/truncate anything.
    _ensure_schema(con)

    # ------------------------------------------------------------------
    # Read all prediction_ledger rows
    # ------------------------------------------------------------------
    try:
        df = con.execute(
            """
            SELECT
                prediction_hash,
                target_entity,
                target_player_name,
                target_team,
                sport
            FROM gold_layer.prediction_ledger
            """
        ).df()
    except Exception as exc:
        log.error("Could not read prediction_ledger: %s", exc)
        con.close()
        raise

    total_rows = len(df)
    log.info("Read %d rows from prediction_ledger", total_rows)

    # ------------------------------------------------------------------
    # Derive entity triples (type, name, sport) per row
    # ------------------------------------------------------------------
    # entity_map: (type, name, sport) → entity_id
    entity_map: dict[tuple, str] = {}
    # row_entity: prediction_hash → entity_id (None if skipped)
    row_entity: dict[str, Optional[str]] = {}

    skipped_rows = 0

    for _, row in df.iterrows():
        phash = row["prediction_hash"]
        sport_val = row.get("sport")
        if sport_val and hasattr(sport_val, "item"):
            sport_val = sport_val.item()
        sport = str(sport_val).upper() if sport_val and sport_val == sport_val else None

        entity_info: Optional[dict] = None

        # Priority 1: target_entity JSON
        te = row.get("target_entity")
        if te is not None and te == te:  # not NaN
            entity_info = _parse_target_entity(te, sport)

        # Priority 2: target_player_name
        if entity_info is None:
            tpn = row.get("target_player_name")
            if tpn is not None and tpn == tpn and str(tpn).strip():
                entity_info = {
                    "type": "player",
                    "name": str(tpn).strip(),
                    "sport": sport,
                }

        # Priority 3: target_team
        if entity_info is None:
            tt = row.get("target_team")
            if tt is not None and tt == tt and str(tt).strip():
                entity_info = {
                    "type": "team",
                    "name": str(tt).strip(),
                    "sport": sport,
                }

        if entity_info is None:
            skipped_rows += 1
            row_entity[phash] = None
            continue

        key = (entity_info["type"], entity_info["name"], entity_info["sport"])
        if key not in entity_map:
            entity_map[key] = _derive_entity_id(*key)
        row_entity[phash] = entity_map[key]

    log.info(
        "Derived %d unique entity triples from %d rows (%d skipped — no entity data)",
        len(entity_map),
        total_rows,
        skipped_rows,
    )

    # ------------------------------------------------------------------
    # Upsert entities
    # ------------------------------------------------------------------
    now = datetime.now(tz=timezone.utc)
    entities_created = 0
    entities_skipped = 0

    if not dry_run:
        for (etype, name, sport), eid in entity_map.items():
            domain = _sport_to_domain(sport)
            try:
                con.execute(
                    """
                    INSERT INTO nfl_dead_money.entities
                        (entity_id, entity_type, canonical_name, aliases, domain,
                         metadata, first_seen_at, last_seen_at, claim_count, created_at)
                    VALUES
                        ($entity_id, $entity_type, $canonical_name, $aliases, $domain,
                         NULL, NULL, NULL, 0, $created_at)
                    ON CONFLICT (entity_id) DO NOTHING
                    """,
                    {
                        "entity_id": eid,
                        "entity_type": etype,
                        "canonical_name": name,
                        "aliases": [],
                        "domain": domain,
                        "created_at": now,
                    },
                )
                entities_created += 1
            except Exception as exc:
                log.warning("Failed to upsert entity %s (%s): %s", eid, name, exc)
                entities_skipped += 1

        # Count actual rows to report accurate state (ON CONFLICT DO NOTHING is idempotent)
        actual_count = con.execute(
            "SELECT COUNT(*) FROM nfl_dead_money.entities"
        ).fetchone()[0]
        log.info(
            "Entities table now has %d rows (attempted %d, failed %d)",
            actual_count,
            len(entity_map),
            entities_skipped,
        )
    else:
        log.info("[DRY RUN] Would upsert %d entities", len(entity_map))

    # ------------------------------------------------------------------
    # Upsert prediction_ledger_graph_extension
    # ------------------------------------------------------------------
    graph_links_created = 0
    graph_links_skipped = 0

    if not dry_run:
        for phash, eid in row_entity.items():
            if eid is None:
                continue
            try:
                con.execute(
                    """
                    INSERT INTO nfl_dead_money.prediction_ledger_graph_extension
                        (prediction_hash, entity_ids, primary_entity_id, claim_type,
                         domain, asserted_state, embedding, cluster_id,
                         entity_resolution_confidence, created_at, updated_at)
                    VALUES
                        ($prediction_hash, $entity_ids, $primary_entity_id, NULL,
                         NULL, NULL, NULL, NULL, NULL, $created_at, $updated_at)
                    ON CONFLICT (prediction_hash) DO NOTHING
                    """,
                    {
                        "prediction_hash": phash,
                        "entity_ids": [eid],
                        "primary_entity_id": eid,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                graph_links_created += 1
            except Exception as exc:
                log.warning(
                    "Failed to upsert graph_extension for %s: %s", phash[:16], exc
                )
                graph_links_skipped += 1

        actual_graph = con.execute(
            "SELECT COUNT(*) FROM nfl_dead_money.prediction_ledger_graph_extension"
        ).fetchone()[0]
        log.info(
            "graph_extension table now has %d rows (attempted %d with entity, failed %d)",
            actual_graph,
            graph_links_created,
            graph_links_skipped,
        )
    else:
        with_entity = sum(1 for v in row_entity.values() if v is not None)
        log.info("[DRY RUN] Would upsert %d graph_extension rows", with_entity)

    con.close()

    summary = {
        "total_ledger_rows": total_rows,
        "unique_entities": len(entity_map),
        "rows_skipped_no_entity": skipped_rows,
        "entities_upsert_attempted": len(entity_map),
        "entities_upsert_failed": entities_skipped,
        "graph_links_attempted": sum(1 for v in row_entity.values() if v is not None),
        "graph_links_failed": graph_links_skipped,
        "dry_run": dry_run,
    }
    return summary


# ---------------------------------------------------------------------------
# Schema bootstrap (safe to re-run)
# ---------------------------------------------------------------------------


def _ensure_schema(con) -> None:
    """
    Create any missing schemas/tables needed by the backfill.
    Uses IF NOT EXISTS everywhere — safe on a pre-initialised DB.
    """
    ddl_statements = [
        "CREATE SCHEMA IF NOT EXISTS nfl_dead_money",
        "CREATE SCHEMA IF NOT EXISTS gold_layer",
        """
        CREATE TABLE IF NOT EXISTS nfl_dead_money.entities (
            entity_id       VARCHAR     NOT NULL PRIMARY KEY,
            entity_type     VARCHAR     NOT NULL,
            canonical_name  VARCHAR     NOT NULL,
            aliases         VARCHAR[],
            domain          VARCHAR     NOT NULL,
            metadata        JSON,
            first_seen_at   TIMESTAMP,
            last_seen_at    TIMESTAMP,
            claim_count     BIGINT,
            created_at      TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS nfl_dead_money.prediction_ledger_graph_extension (
            prediction_hash               VARCHAR     NOT NULL PRIMARY KEY,
            entity_ids                    VARCHAR[],
            primary_entity_id             VARCHAR,
            claim_type                    VARCHAR,
            domain                        VARCHAR,
            asserted_state                JSON,
            embedding                     DOUBLE[],
            cluster_id                    VARCHAR,
            entity_resolution_confidence  DOUBLE,
            created_at                    TIMESTAMP,
            updated_at                    TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS gold_layer.prediction_ledger (
            prediction_hash     VARCHAR     NOT NULL,
            chain_hash          VARCHAR     NOT NULL,
            ingestion_timestamp TIMESTAMP   NOT NULL,
            source_url          VARCHAR     NOT NULL,
            pundit_id           VARCHAR     NOT NULL,
            pundit_name         VARCHAR     NOT NULL,
            raw_assertion_text  VARCHAR     NOT NULL,
            extracted_claim     VARCHAR,
            claim_category      VARCHAR,
            season_year         BIGINT,
            target_player_id    VARCHAR,
            target_player_name  VARCHAR,
            target_team         VARCHAR,
            sport               VARCHAR     DEFAULT 'NFL',
            resolution_status   VARCHAR     DEFAULT 'PENDING',
            resolved_at         TIMESTAMP,
            resolution_notes    VARCHAR,
            stance              VARCHAR,
            prompt_version      VARCHAR,
            llm_provider        VARCHAR,
            llm_model           VARCHAR,
            target_entity       JSON,
            claim_norm_key      VARCHAR
        )
        """,
    ]
    for stmt in ddl_statements:
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            con.execute(stmt)
        except Exception as exc:
            log.debug("DDL skipped (%s): %.80s", exc, stmt)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and log counts but do not write anything to the DB.",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help=(
            "Path to the DuckDB file. "
            "Defaults to DUCKDB_PATH env var or pipeline/data/local.duckdb."
        ),
    )
    args = parser.parse_args()

    backend = os.environ.get("DB_BACKEND", "").lower()
    if backend not in ("duckdb", ""):
        log.error(
            "backfill_entities only supports DB_BACKEND=duckdb. "
            "Set DB_BACKEND=duckdb or leave unset."
        )
        sys.exit(1)

    db_path = args.db_path or os.environ.get(
        "DUCKDB_PATH",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "local.duckdb",
        ),
    )

    log.info("Starting entity backfill (db_path=%s, dry_run=%s)", db_path, args.dry_run)
    summary = run_backfill(db_path=db_path, dry_run=args.dry_run)

    log.info("=== Backfill complete ===")
    log.info("  total_ledger_rows         : %d", summary["total_ledger_rows"])
    log.info("  unique_entities           : %d", summary["unique_entities"])
    log.info("  rows_skipped_no_entity    : %d", summary["rows_skipped_no_entity"])
    log.info("  entities_upsert_attempted : %d", summary["entities_upsert_attempted"])
    log.info("  entities_upsert_failed    : %d", summary["entities_upsert_failed"])
    log.info("  graph_links_attempted     : %d", summary["graph_links_attempted"])
    log.info("  graph_links_failed        : %d", summary["graph_links_failed"])

    if summary["unique_entities"] == 0:
        log.warning(
            "No entities derived — prediction_ledger may be empty "
            "or all rows lack entity data."
        )


if __name__ == "__main__":
    main()

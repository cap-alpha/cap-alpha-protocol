"""
run_kg_migration_duckdb.py — DuckDB-native Phase 2 migration runner.

Migrates:
  gold_layer.prediction_ledger        → silver_v2_claims.claim
                                          + claim_entity_link
                                          + claim_state_history
  gold_layer.prediction_resolutions  → silver_v2_claims.resolution
                                          + claim_state_history (resolved row)
                                          + silver_v2_core.entity_attribute_event (CORRECT only)

This is the DuckDB-equivalent of:
  migrate_prediction_ledger_to_silver_v2.py  (uses bigquery.Client)
  migrate_prediction_resolutions_to_silver_v2.py (uses bigquery.Client)

Usage:
    DB_BACKEND=duckdb python3 pipeline/scripts/run_kg_migration_duckdb.py [--dry-run]

Prerequisites:
    DB_BACKEND=duckdb python3 pipeline/scripts/init_local_db.py
    DB_BACKEND=duckdb python3 pipeline/scripts/seed_test_data_duckdb.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_PIPELINE_DIR = _SCRIPT_DIR.parent
_DEFAULT_DB_PATH = _PIPELINE_DIR / "data" / "local.duckdb"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(s: str) -> str:
    return s.lower().strip() if s else ""


def _unresolved_entity_id(raw: str) -> str:
    h = hashlib.sha256(_normalize(raw).encode()).hexdigest()[:16]
    return f"unresolved:{h}"


def _category_to_domain(cat: str | None) -> str:
    if not cat:
        return "sports.nfl"
    c = cat.lower()
    if "politi" in c:
        return "politics"
    if "finance" in c or "economy" in c:
        return "finance"
    return "sports.nfl"


def _compute_this_hash(claim_id: str, speaker_id: str, asserted_at: str, pred_args: str) -> str:
    payload = f"{claim_id}|{speaker_id}|{asserted_at}|{pred_args}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _ts_str(ts: Any) -> str | None:
    if ts is None:
        return None
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


# ---------------------------------------------------------------------------
# DuckDB-native migration: prediction_ledger → silver_v2
# ---------------------------------------------------------------------------


def migrate_ledger(conn, dry_run: bool) -> tuple[int, int, int]:
    """
    Migrate gold_layer.prediction_ledger → silver_v2_claims.
    Returns (processed, inserted, skipped).
    """
    # Load existing migrated hashes for idempotency
    existing_hashes = {
        r[0]
        for r in conn.execute(
            "SELECT legacy_prediction_hash FROM silver_v2_claims.claim "
            "WHERE legacy_prediction_hash IS NOT NULL"
        ).fetchall()
        if r[0]
    }
    log.info("Ledger migration: %d rows already migrated", len(existing_hashes))

    rows = conn.execute(
        """
        SELECT
            prediction_hash, chain_hash, ingestion_timestamp, source_url,
            pundit_id, pundit_name, raw_assertion_text, extracted_claim,
            claim_category, season_year, target_player_id, target_team,
            sport, resolution_status, resolved_at, resolution_notes,
            target_player_name, prompt_version, llm_provider, llm_model
        FROM gold_layer.prediction_ledger
        ORDER BY ingestion_timestamp, prediction_hash
        """
    ).fetchall()

    cols = [
        "prediction_hash", "chain_hash", "ingestion_timestamp", "source_url",
        "pundit_id", "pundit_name", "raw_assertion_text", "extracted_claim",
        "claim_category", "season_year", "target_player_id", "target_team",
        "sport", "resolution_status", "resolved_at", "resolution_notes",
        "target_player_name", "prompt_version", "llm_provider", "llm_model",
    ]
    # Some columns may not exist (added by later migrations that failed)
    actual_cols = [
        c[0]
        for c in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='gold_layer' AND table_name='prediction_ledger'"
        ).fetchall()
    ]
    cols = [c for c in cols if c in actual_cols]

    rows_as_dicts = [dict(zip(cols, r[:len(cols)])) for r in rows]

    processed = 0
    inserted = 0
    skipped = 0
    speaker_cache: dict[str, str] = {}

    for row in rows_as_dicts:
        processed += 1
        ph = row.get("prediction_hash") or ""
        if not ph:
            continue
        if ph in existing_hashes:
            skipped += 1
            continue

        # --- Speaker entity (upsert) ---
        pundit_id = row.get("pundit_id") or "unknown"
        pundit_name = row.get("pundit_name") or pundit_id
        if pundit_id not in speaker_cache:
            existing = conn.execute(
                "SELECT entity_id FROM silver_v2_core.entity "
                "WHERE json_extract_string(external_ids, '$.pundit_id') = $pid LIMIT 1",
                {"pid": pundit_id},
            ).fetchone()
            if existing:
                speaker_cache[pundit_id] = existing[0]
            else:
                eid = _new_uuid()
                if not dry_run:
                    ext_ids = json.dumps({"pundit_id": pundit_id})
                    conn.execute(
                        "INSERT INTO silver_v2_core.entity "
                        "(entity_id, entity_kind, primary_domain, external_ids, created_at) "
                        "VALUES ($eid, 'person', 'sports.nfl', $ext_ids::JSON, current_timestamp)",
                        {"eid": eid, "ext_ids": ext_ids},
                    )
                speaker_cache[pundit_id] = eid

        speaker_id = speaker_cache[pundit_id]

        # --- Domain / timestamps ---
        domain = _category_to_domain(row.get("claim_category"))
        ingestion_ts = row.get("ingestion_timestamp")
        if ingestion_ts is None:
            asserted_at = _now_ts()
        else:
            asserted_at = _ts_str(ingestion_ts) or _now_ts()

        # --- predicate_args ---
        pred_args = json.dumps({
            k: v
            for k, v in {
                "text": row.get("extracted_claim") or row.get("raw_assertion_text") or "",
                "season_year": row.get("season_year"),
                "sport": row.get("sport"),
                "claim_category": row.get("claim_category"),
            }.items()
            if v is not None
        })

        # --- Resolution window ---
        sy = row.get("season_year")
        if sy:
            try:
                yr = int(sy)
                rw_start = f"{yr}-09-01T00:00:00+00:00"
                rw_end = f"{yr + 1}-02-28T23:59:59+00:00"
            except (ValueError, TypeError):
                rw_start = rw_end = asserted_at
        else:
            rw_start = rw_end = asserted_at

        claim_id = _new_uuid()
        this_hash = _compute_this_hash(claim_id, speaker_id, asserted_at, pred_args)

        legacy_status = (row.get("resolution_status") or "PENDING").upper()
        claim_state = (
            legacy_status
            if legacy_status in ("CORRECT", "INCORRECT", "VOID", "PARTIAL", "UNVERIFIABLE")
            else "PENDING"
        )

        if dry_run:
            log.info(
                "[DRY-RUN] Would insert claim: claim_id=%s legacy_hash=%.16s speaker=%s state=%s",
                claim_id, ph, speaker_id, claim_state,
            )
            inserted += 1
            existing_hashes.add(ph)
            continue

        # Insert claim (idempotent guard via WHERE NOT EXISTS equivalent)
        already = conn.execute(
            "SELECT claim_id FROM silver_v2_claims.claim WHERE legacy_prediction_hash = $ph",
            {"ph": ph},
        ).fetchone()
        if already:
            skipped += 1
            existing_hashes.add(ph)
            continue

        # Generate a synthetic utterance_id for backfilled claims (no real utterance row)
        synthetic_utterance_id = _new_uuid()

        conn.execute(
            """
            INSERT INTO silver_v2_claims.claim (
                claim_id, utterance_id, speaker_entity_id, domain,
                claim_subject_type, predicate, predicate_args,
                resolution_window_start, resolution_window_end,
                resolution_method_id, asserted_at, ledger_locked_at,
                prev_hash, this_hash, legacy_prediction_hash, legacy_chain_hash,
                created_at
            ) VALUES (
                $claim_id, $utterance_id, $speaker_id, $domain,
                'entity', 'predicted', $pred_args::JSON,
                $rw_start::TIMESTAMP, $rw_end::TIMESTAMP,
                'legacy_migration', $asserted_at::TIMESTAMP, current_timestamp,
                '', $this_hash, $ph, $ch,
                current_timestamp
            )
            """,
            {
                "claim_id": claim_id,
                "utterance_id": synthetic_utterance_id,
                "speaker_id": speaker_id,
                "domain": domain,
                "pred_args": pred_args,
                "rw_start": rw_start,
                "rw_end": rw_end,
                "asserted_at": asserted_at,
                "this_hash": this_hash,
                "ph": ph,
                "ch": row.get("chain_hash") or "",
            },
        )

        # Insert initial claim_state_history row
        conn.execute(
            """
            INSERT INTO silver_v2_claims.claim_state_history (
                history_id, claim_id, state, effective_from, effective_to,
                effective_source, notes, created_at
            )
            SELECT $hid, $claim_id, $state, $asserted_at::TIMESTAMP, NULL,
                   'asserted_at', 'backfill from gold_layer.prediction_ledger', current_timestamp
            WHERE NOT EXISTS (
                SELECT 1 FROM silver_v2_claims.claim_state_history WHERE claim_id = $claim_id
            )
            """,
            {
                "hid": _new_uuid(),
                "claim_id": claim_id,
                "state": claim_state,
                "asserted_at": asserted_at,
            },
        )

        # Resolve + insert subject entities and claim_entity_link
        player_name = row.get("target_player_name") or row.get("target_player_id")
        team_name = row.get("target_team")

        subject_pairs: list[tuple[str, str]] = []
        if player_name:
            eid = _get_or_create_placeholder(conn, str(player_name), "person", domain)
            subject_pairs.append((eid, "subject"))
        if team_name:
            eid = _get_or_create_placeholder(conn, str(team_name), "team_brand", domain)
            subject_pairs.append((eid, "object"))
        if not subject_pairs:
            raw_text = row.get("extracted_claim") or row.get("raw_assertion_text") or ""
            eid = _get_or_create_placeholder(conn, raw_text[:100], "unresolved", domain)
            subject_pairs.append((eid, "subject"))

        for ordinal, (entity_id, entity_role) in enumerate(subject_pairs):
            conn.execute(
                """
                INSERT INTO silver_v2_claims.claim_entity_link
                    (link_id, claim_id, entity_id, entity_role, ordinal, created_at)
                SELECT $lid, $claim_id, $eid, $role, $ordinal, current_timestamp
                WHERE NOT EXISTS (
                    SELECT 1 FROM silver_v2_claims.claim_entity_link
                    WHERE claim_id = $claim_id AND entity_id = $eid AND entity_role = $role
                )
                """,
                {
                    "lid": _new_uuid(),
                    "claim_id": claim_id,
                    "eid": entity_id,
                    "role": entity_role,
                    "ordinal": ordinal,
                },
            )

        inserted += 1
        existing_hashes.add(ph)

    log.info(
        "Ledger migration: processed=%d inserted=%d skipped=%d",
        processed, inserted, skipped,
    )
    return processed, inserted, skipped


def _get_or_create_placeholder(conn, raw: str, kind: str, domain: str) -> str:
    """Return existing or new placeholder entity_id for a raw entity string."""
    placeholder_id = _unresolved_entity_id(raw)
    existing = conn.execute(
        "SELECT entity_id FROM silver_v2_core.entity WHERE entity_id = $eid LIMIT 1",
        {"eid": placeholder_id},
    ).fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO silver_v2_core.entity "
            "(entity_id, entity_kind, primary_domain, notes, created_at) "
            "VALUES ($eid, $kind, $domain, $notes, current_timestamp)",
            {"eid": placeholder_id, "kind": kind, "domain": domain, "notes": raw[:500]},
        )
        # Queue for resolution (guard: check if already queued)
        already_queued = conn.execute(
            "SELECT queue_id FROM silver_v2_claims.entity_resolution_queue "
            "WHERE placeholder_entity_id = $eid LIMIT 1",
            {"eid": placeholder_id},
        ).fetchone()
        if not already_queued:
            conn.execute(
                """
                INSERT INTO silver_v2_claims.entity_resolution_queue
                    (queue_id, raw_entity_string, normalized_string, domain,
                     placeholder_entity_id, first_seen_at, attempt_count, status, created_at)
                VALUES ($qid, $raw, $norm, $domain, $eid, current_timestamp, 0, 'PENDING', current_timestamp)
                """,
                {
                    "qid": _new_uuid(),
                    "raw": raw[:500],
                    "norm": _normalize(raw[:500]),
                    "domain": domain,
                    "eid": placeholder_id,
                },
            )
    return placeholder_id


# ---------------------------------------------------------------------------
# DuckDB-native migration: prediction_resolutions → silver_v2
# ---------------------------------------------------------------------------


def migrate_resolutions(conn, dry_run: bool) -> tuple[int, int, int]:
    """
    Migrate gold_layer.prediction_resolutions → silver_v2_claims.
    Returns (processed, inserted, skipped).
    """
    existing_claim_ids = {
        r[0]
        for r in conn.execute(
            "SELECT claim_id FROM silver_v2_claims.resolution"
        ).fetchall()
        if r[0]
    }
    log.info("Resolutions migration: %d rows already migrated", len(existing_claim_ids))

    rows = conn.execute(
        """
        SELECT
            pr.prediction_hash,
            pr.resolution_status,
            pr.resolved_at,
            pr.resolver,
            pr.brier_score,
            pr.binary_correct,
            pr.timeliness_weight,
            pr.weighted_score,
            pr.outcome_source,
            pr.outcome_reference_id,
            pr.outcome_notes,
            pr.created_at AS resolution_created_at,
            pr.updated_at AS resolution_updated_at,
            c.claim_id,
            c.resolution_window_start,
            c.speaker_entity_id
        FROM gold_layer.prediction_resolutions pr
        LEFT JOIN silver_v2_claims.claim c
            ON c.legacy_prediction_hash = pr.prediction_hash
        ORDER BY pr.resolved_at, pr.prediction_hash
        """
    ).fetchall()

    col_names = [
        "prediction_hash", "resolution_status", "resolved_at", "resolver",
        "brier_score", "binary_correct", "timeliness_weight", "weighted_score",
        "outcome_source", "outcome_reference_id", "outcome_notes",
        "resolution_created_at", "resolution_updated_at",
        "claim_id", "resolution_window_start", "speaker_entity_id",
    ]
    rows_as_dicts = [dict(zip(col_names, r)) for r in rows]

    processed = 0
    inserted = 0
    skipped = 0

    for row in rows_as_dicts:
        processed += 1
        claim_id = row.get("claim_id")
        ph = row.get("prediction_hash") or ""

        if not claim_id:
            log.warning("prediction_hash=%.16s has no silver_v2 claim — run ledger migration first", ph)
            continue

        if claim_id in existing_claim_ids:
            skipped += 1
            continue

        resolution_status = (row.get("resolution_status") or "PENDING").upper()
        resolved_at = _ts_str(row.get("resolved_at")) or _now_ts()

        if dry_run:
            log.info(
                "[DRY-RUN] Would insert resolution: claim_id=%s status=%s resolved_at=%s",
                claim_id, resolution_status, resolved_at,
            )
            inserted += 1
            existing_claim_ids.add(claim_id)
            continue

        outcome_map = {
            "CORRECT": "true", "INCORRECT": "false", "VOID": "vacuous",
            "PARTIAL": "partial", "UNVERIFIABLE": "unresolvable", "PENDING": "pending",
        }
        outcome = outcome_map.get(resolution_status, "pending")

        weighted = row.get("weighted_score")
        brier = row.get("brier_score")
        binary_correct = row.get("binary_correct")
        outcome_confidence = float(weighted) if weighted is not None else 0.5

        evidence = json.dumps({
            "outcome_source": row.get("outcome_source"),
            "outcome_reference_id": row.get("outcome_reference_id"),
            "outcome_notes": row.get("outcome_notes"),
            "timeliness_weight": float(row.get("timeliness_weight") or 1.0),
            "weighted_score": float(weighted) if weighted is not None else None,
            "legacy_resolver": row.get("resolver"),
        })

        resolution_id = _new_uuid()
        this_hash = hashlib.sha256(
            f"{resolution_id}|{claim_id}|{resolved_at}|{outcome}".encode()
        ).hexdigest()

        conn.execute(
            """
            INSERT INTO silver_v2_claims.resolution (
                resolution_id, claim_id, resolved_at, outcome,
                outcome_confidence, evidence, resolution_method_id,
                prev_hash, this_hash, notes
            ) VALUES (
                $rid, $claim_id, $resolved_at::TIMESTAMP, $outcome,
                $oc, $evidence::JSON, 'legacy_migration',
                '', $this_hash, $notes
            )
            """,
            {
                "rid": resolution_id,
                "claim_id": claim_id,
                "resolved_at": resolved_at,
                "outcome": outcome,
                "oc": outcome_confidence,
                "evidence": evidence,
                "this_hash": this_hash,
                "notes": row.get("outcome_notes") or "",
            },
        )

        # Close PENDING claim_state_history row
        conn.execute(
            "UPDATE silver_v2_claims.claim_state_history "
            "SET effective_to = $resolved_at::TIMESTAMP "
            "WHERE claim_id = $claim_id AND state = 'PENDING' AND effective_to IS NULL",
            {"claim_id": claim_id, "resolved_at": resolved_at},
        )

        # Open resolved state row
        conn.execute(
            """
            INSERT INTO silver_v2_claims.claim_state_history (
                history_id, claim_id, state, effective_from, effective_to,
                effective_source, resolution_id, brier_score, binary_correct,
                notes, created_at
            ) VALUES (
                $hid, $claim_id, $state, $resolved_at::TIMESTAMP, NULL,
                'asserted_at', $rid,
                CASE WHEN $brier IS NULL THEN NULL ELSE CAST($brier AS DOUBLE) END,
                CAST($bc AS BOOLEAN),
                'backfill from gold_layer.prediction_resolutions', current_timestamp
            )
            """,
            {
                "hid": _new_uuid(),
                "claim_id": claim_id,
                "state": resolution_status,
                "resolved_at": resolved_at,
                "rid": resolution_id,
                "brier": brier,
                "bc": binary_correct,
            },
        )

        # For CORRECT resolutions: write entity_attribute_event
        if resolution_status == "CORRECT":
            _write_entity_attr_event(
                conn, claim_id,
                row.get("speaker_entity_id"),
                _ts_str(row.get("resolution_window_start")),
                weighted,
            )

        inserted += 1
        existing_claim_ids.add(claim_id)

    log.info(
        "Resolutions migration: processed=%d inserted=%d skipped=%d",
        processed, inserted, skipped,
    )
    return processed, inserted, skipped


def _write_entity_attr_event(
    conn, claim_id: str, speaker_id: str | None,
    valid_from: str | None, weighted_score: Any,
) -> None:
    subject = conn.execute(
        """
        SELECT l.entity_id, e.primary_domain
        FROM silver_v2_claims.claim_entity_link l
        JOIN silver_v2_core.entity e ON e.entity_id = l.entity_id
        WHERE l.claim_id = $claim_id AND l.entity_role = 'subject'
        LIMIT 1
        """,
        {"claim_id": claim_id},
    ).fetchone()

    if subject:
        entity_id, domain = subject[0], subject[1] or "sports.nfl"
    elif speaker_id:
        entity_id, domain = speaker_id, "sports.nfl"
    else:
        log.warning("No subject entity for CORRECT claim_id=%s — skipping attr event", claim_id)
        return

    vf = valid_from or _now_ts()
    confidence = max(0.0, min(1.0, float(weighted_score) if weighted_score is not None else 0.5))
    value_json = json.dumps({"claim_id": claim_id, "confirmed_correct": True})

    conn.execute(
        """
        INSERT INTO silver_v2_core.entity_attribute_event (
            event_id, entity_id, domain, attr, value, value_json,
            valid_from, valid_to, evidence_type, source_claim_id,
            source_doc_id, extraction_confidence, corroboration_count,
            is_concurrent_ok, superseded_by, created_at
        )
        SELECT $eid, $entity_id, $domain, 'prediction_confirmed', 'true', $vj::JSON,
               $vf::TIMESTAMP, NULL, 'resolved_prediction', $claim_id,
               NULL, $conf, 1, TRUE, NULL, current_timestamp
        WHERE NOT EXISTS (
            SELECT 1 FROM silver_v2_core.entity_attribute_event
            WHERE source_claim_id = $claim_id AND attr = 'prediction_confirmed'
        )
        """,
        {
            "eid": _new_uuid(),
            "entity_id": entity_id,
            "domain": domain,
            "vj": value_json,
            "vf": vf,
            "claim_id": claim_id,
            "conf": confidence,
        },
    )


# ---------------------------------------------------------------------------
# Verification checks
# ---------------------------------------------------------------------------


def run_verification(conn) -> bool:
    """Run the 4 zero-count checks from issue #920. Returns True if all pass."""
    checks = [
        (
            "Every legacy claim present in silver_v2",
            """
            SELECT COUNT(*)
            FROM gold_layer.prediction_ledger pl
            LEFT JOIN silver_v2_claims.claim c
                ON c.legacy_prediction_hash = pl.prediction_hash
            WHERE c.claim_id IS NULL
            """,
        ),
        (
            "Every legacy resolution present in silver_v2",
            """
            SELECT COUNT(*)
            FROM gold_layer.prediction_resolutions pr
            LEFT JOIN silver_v2_claims.claim c
                ON c.legacy_prediction_hash = pr.prediction_hash
            LEFT JOIN silver_v2_claims.resolution r
                ON r.claim_id = c.claim_id
            WHERE r.resolution_id IS NULL
            """,
        ),
        (
            "Every claim has at least one claim_state_history row",
            """
            SELECT COUNT(*)
            FROM silver_v2_claims.claim c
            LEFT JOIN silver_v2_claims.claim_state_history h
                ON h.claim_id = c.claim_id
            WHERE h.history_id IS NULL
            """,
        ),
        (
            "Every claim with a subject has at least one claim_entity_link",
            """
            SELECT COUNT(*)
            FROM silver_v2_claims.claim c
            LEFT JOIN silver_v2_claims.claim_entity_link l
                ON l.claim_id = c.claim_id
            WHERE l.link_id IS NULL
              AND c.claim_subject_type IS NOT NULL
            """,
        ),
    ]

    print("\nKnowledge Graph Migration Verification")
    print("=" * 60)

    results = []
    for name, query in checks:
        count = conn.execute(query).fetchone()[0]
        if count == 0:
            print(f"  PASS  {name} (count=0)")
            results.append(True)
        else:
            print(f"  FAIL  {name} (count={count})")
            results.append(False)

    print("=" * 60)
    if all(results):
        print(f"ALL {len(results)} CHECKS PASSED — Phase 2 migration verified.")
    else:
        failed = sum(1 for r in results if not r)
        print(f"{failed}/{len(results)} CHECKS FAILED")
    return all(results)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DuckDB-native Phase 2 KG migration runner"
    )
    parser.add_argument("--dry-run", action="store_true", help="Log only, no writes")
    parser.add_argument("--verify-only", action="store_true", help="Only run verification checks")
    args = parser.parse_args()

    import duckdb

    db_path = os.environ.get("DUCKDB_PATH", str(_DEFAULT_DB_PATH))
    log.info("DuckDB path: %s", db_path)

    conn = duckdb.connect(db_path)

    if args.verify_only:
        success = run_verification(conn)
        conn.close()
        sys.exit(0 if success else 1)

    # Show before counts
    pl_count = conn.execute("SELECT COUNT(*) FROM gold_layer.prediction_ledger").fetchone()[0]
    pr_count = conn.execute("SELECT COUNT(*) FROM gold_layer.prediction_resolutions").fetchone()[0]
    log.info("Before migration: prediction_ledger=%d, prediction_resolutions=%d", pl_count, pr_count)

    # Step 1: Migrate ledger
    log.info("--- Step 1: Migrating prediction_ledger ---")
    migrate_ledger(conn, dry_run=args.dry_run)

    # Step 2: Migrate resolutions
    log.info("--- Step 2: Migrating prediction_resolutions ---")
    migrate_resolutions(conn, dry_run=args.dry_run)

    # Step 3: Verify
    if not args.dry_run:
        log.info("--- Step 3: Running verification checks ---")
        success = run_verification(conn)
        conn.close()
        sys.exit(0 if success else 1)
    else:
        log.info("DRY-RUN complete — no data written.")
        conn.close()


if __name__ == "__main__":
    main()

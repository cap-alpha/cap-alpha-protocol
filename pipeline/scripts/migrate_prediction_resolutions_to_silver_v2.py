"""
migrate_prediction_resolutions_to_silver_v2.py — Phase 2 backfill (resolutions).

Migrates gold_layer.prediction_resolutions (437 rows) →
  silver_v2_claims.resolution
  + closes/opens silver_v2_claims.claim_state_history
  + writes entity_attribute_event for CORRECT resolutions (all 437 decided in #920)

Design decisions (from issue #920 comments):
  - look up claim_id from silver_v2_claims.claim by legacy_prediction_hash = prediction_hash
  - close existing PENDING claim_state_history row (effective_to = resolved_at)
  - open new state row with actual resolution status + brier_score, binary_correct
  - for CORRECT: INSERT entity_attribute_event with source_claim_id, evidence_type='resolved_prediction',
    valid_from=resolution_window_start, extraction_confidence=weighted_score
  - idempotent: skip if resolution already in silver_v2_claims.resolution
  - resumable: process in batches of 100

Prerequisite: migrate_prediction_ledger_to_silver_v2.py must have run first.

Usage:
    python pipeline/scripts/migrate_prediction_resolutions_to_silver_v2.py
    python pipeline/scripts/migrate_prediction_resolutions_to_silver_v2.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
    from google.api_core.exceptions import NotFound
except ImportError:  # pragma: no cover
    bigquery = None  # type: ignore[assignment]
    NotFound = Exception  # type: ignore[assignment]

BATCH_SIZE_DEFAULT = 100
LOG_DIR = pathlib.Path(__file__).parent.parent / "migrations" / "logs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error("Environment variable %s is required but not set.", name)
        sys.exit(1)
    return val


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts_str(ts: Any) -> Optional[str]:
    """Convert a BQ timestamp value to ISO string, or None."""
    if ts is None:
        return None
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


def _ensure_tables_exist(client: "bigquery.Client", project_id: str) -> None:
    required = [
        (project_id, "silver_v2_claims", "claim"),
        (project_id, "silver_v2_claims", "resolution"),
        (project_id, "silver_v2_claims", "claim_state_history"),
        (project_id, "silver_v2_core", "entity_attribute_event"),
    ]
    for proj, dataset, table in required:
        try:
            client.get_table(f"{proj}.{dataset}.{table}")
        except NotFound:
            log.error(
                "Required table `%s.%s.%s` does not exist. "
                "Run Phase 1 DDL and ledger migration first.",
                proj,
                dataset,
                table,
            )
            sys.exit(1)
    log.info("All required Phase 2 resolution tables verified.")


def _load_existing_resolution_claim_ids(
    client: "bigquery.Client", project_id: str
) -> set[str]:
    """Return claim_ids that already have a row in silver_v2_claims.resolution."""
    query = f"""
        SELECT claim_id
        FROM `{project_id}.silver_v2_claims.resolution`
    """
    job = client.query(query)
    result = {r["claim_id"] for r in job.result() if r["claim_id"]}
    log.info("Found %d resolutions already migrated.", len(result))
    return result


def _fetch_resolution_batch(
    client: "bigquery.Client", project_id: str, offset: int, batch_size: int
) -> list[dict[str, Any]]:
    """Fetch a batch from gold_layer.prediction_resolutions, joined to claim for claim_id lookup."""
    query = f"""
        SELECT
            pr.prediction_hash,
            pr.sport,
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
            c.resolution_window_end,
            c.speaker_entity_id
        FROM `{project_id}.gold_layer.prediction_resolutions` pr
        LEFT JOIN `{project_id}.silver_v2_claims.claim` c
            ON c.legacy_prediction_hash = pr.prediction_hash
        ORDER BY pr.resolved_at, pr.prediction_hash
        LIMIT {batch_size} OFFSET {offset}
    """
    job = client.query(query)
    return [dict(r) for r in job.result()]


def _migrate_resolution_row(
    client: "bigquery.Client",
    project_id: str,
    row: dict[str, Any],
    dry_run: bool,
) -> bool:
    """
    Process a single prediction_resolutions row.
    Returns True if inserted (or would be in dry-run).
    """
    prediction_hash = row.get("prediction_hash") or ""
    claim_id = row.get("claim_id")

    if not claim_id:
        log.warning(
            "prediction_hash=%s has no matching claim in silver_v2_claims.claim — "
            "run ledger migration first. Skipping.",
            prediction_hash,
        )
        return False

    resolution_status = (row.get("resolution_status") or "PENDING").upper()
    resolved_at_ts = row.get("resolved_at")
    resolved_at_str = _ts_str(resolved_at_ts)
    if not resolved_at_str:
        resolved_at_str = _now_ts()

    brier_score = row.get("brier_score")
    binary_correct_raw = row.get("binary_correct")
    if binary_correct_raw is not None:
        binary_correct = bool(binary_correct_raw)
    else:
        binary_correct = None

    weighted_score = row.get("weighted_score")
    resolution_window_start = _ts_str(row.get("resolution_window_start"))
    speaker_entity_id = row.get("speaker_entity_id")

    if dry_run:
        log.info(
            "[DRY-RUN] Would insert resolution: claim_id=%s status=%s resolved_at=%s brier=%s",
            claim_id,
            resolution_status,
            resolved_at_str,
            brier_score,
        )
        return True

    resolution_id = _new_uuid()

    # ---------------------------------------------------------------------------
    # 1. Insert into silver_v2_claims.resolution
    # ---------------------------------------------------------------------------
    outcome_map = {
        "CORRECT": "true",
        "INCORRECT": "false",
        "VOID": "vacuous",
        "PARTIAL": "partial",
        "UNVERIFIABLE": "unresolvable",
        "PENDING": "pending",
    }
    outcome = outcome_map.get(resolution_status, "pending")

    evidence_payload = json.dumps(
        {
            "outcome_source": row.get("outcome_source"),
            "outcome_reference_id": row.get("outcome_reference_id"),
            "outcome_notes": row.get("outcome_notes"),
            "timeliness_weight": float(row.get("timeliness_weight") or 1.0),
            "weighted_score": float(weighted_score) if weighted_score is not None else None,
            "legacy_resolver": row.get("resolver"),
        }
    )

    outcome_confidence = float(weighted_score) if weighted_score is not None else 0.5

    insert_resolution_sql = f"""
        INSERT INTO `{project_id}.silver_v2_claims.resolution` (
            resolution_id,
            claim_id,
            resolved_at,
            outcome,
            outcome_confidence,
            evidence,
            resolution_method_id,
            prev_hash,
            this_hash,
            notes
        )
        VALUES (
            @resolution_id,
            @claim_id,
            TIMESTAMP(@resolved_at),
            @outcome,
            @outcome_confidence,
            JSON @evidence_payload,
            'legacy_migration',
            '',
            @this_hash,
            @notes
        )
    """
    this_hash = hashlib.sha256(
        f"{resolution_id}|{claim_id}|{resolved_at_str}|{outcome}".encode()
    ).hexdigest()

    client.query(
        insert_resolution_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "resolution_id", "STRING", resolution_id
                ),
                bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id),
                bigquery.ScalarQueryParameter("resolved_at", "STRING", resolved_at_str),
                bigquery.ScalarQueryParameter("outcome", "STRING", outcome),
                bigquery.ScalarQueryParameter(
                    "outcome_confidence", "FLOAT64", outcome_confidence
                ),
                bigquery.ScalarQueryParameter(
                    "evidence_payload", "STRING", evidence_payload
                ),
                bigquery.ScalarQueryParameter("this_hash", "STRING", this_hash),
                bigquery.ScalarQueryParameter(
                    "notes",
                    "STRING",
                    row.get("outcome_notes") or "",
                ),
            ]
        ),
    ).result()

    # ---------------------------------------------------------------------------
    # 2. Close PENDING claim_state_history row
    # ---------------------------------------------------------------------------
    close_pending_sql = f"""
        UPDATE `{project_id}.silver_v2_claims.claim_state_history`
        SET effective_to = TIMESTAMP(@resolved_at)
        WHERE claim_id = @claim_id
          AND state = 'PENDING'
          AND effective_to IS NULL
    """
    client.query(
        close_pending_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id),
                bigquery.ScalarQueryParameter("resolved_at", "STRING", resolved_at_str),
            ]
        ),
    ).result()

    # ---------------------------------------------------------------------------
    # 3. Open new claim_state_history row for resolved state
    # ---------------------------------------------------------------------------
    new_history_id = _new_uuid()
    binary_correct_param = (
        bigquery.ScalarQueryParameter("binary_correct", "BOOL", binary_correct)
        if binary_correct is not None
        else bigquery.ScalarQueryParameter("binary_correct", "BOOL", None)
    )
    brier_param = (
        bigquery.ScalarQueryParameter(
            "brier_score",
            "FLOAT64",
            float(brier_score) if brier_score is not None else None,
        )
    )

    insert_history_sql = f"""
        INSERT INTO `{project_id}.silver_v2_claims.claim_state_history` (
            history_id, claim_id, state, effective_from, effective_to,
            effective_source, resolution_id, brier_score, binary_correct,
            notes, created_at
        )
        VALUES (
            @history_id,
            @claim_id,
            @state,
            TIMESTAMP(@resolved_at),
            NULL,
            'asserted_at',
            @resolution_id,
            @brier_score,
            @binary_correct,
            'backfill from gold_layer.prediction_resolutions',
            CURRENT_TIMESTAMP()
        )
    """
    client.query(
        insert_history_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "history_id", "STRING", new_history_id
                ),
                bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id),
                bigquery.ScalarQueryParameter("state", "STRING", resolution_status),
                bigquery.ScalarQueryParameter("resolved_at", "STRING", resolved_at_str),
                bigquery.ScalarQueryParameter(
                    "resolution_id", "STRING", resolution_id
                ),
                brier_param,
                binary_correct_param,
            ]
        ),
    ).result()

    # ---------------------------------------------------------------------------
    # 4. For CORRECT resolutions: write entity_attribute_event
    # ---------------------------------------------------------------------------
    if resolution_status == "CORRECT":
        _write_entity_attribute_event(
            client,
            project_id,
            claim_id=claim_id,
            speaker_entity_id=speaker_entity_id,
            resolution_window_start=resolution_window_start,
            weighted_score=weighted_score,
        )

    return True


def _write_entity_attribute_event(
    client: "bigquery.Client",
    project_id: str,
    claim_id: str,
    speaker_entity_id: Optional[str],
    resolution_window_start: Optional[str],
    weighted_score: Any,
) -> None:
    """
    Write an entity_attribute_event row for a CORRECT resolution.
    Links the entity (speaker/pundit) to a 'prediction_confirmed' attribute.
    valid_from = resolution_window_start (from the claim).
    extraction_confidence = weighted_score from resolution.
    """
    # Derive subject entity from claim_entity_link (first subject role)
    subject_query = f"""
        SELECT l.entity_id, e.entity_kind, e.primary_domain
        FROM `{project_id}.silver_v2_claims.claim_entity_link` l
        JOIN `{project_id}.silver_v2_core.entity` e
            ON e.entity_id = l.entity_id
        WHERE l.claim_id = @claim_id
          AND l.entity_role = 'subject'
        LIMIT 1
    """
    job = client.query(
        subject_query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id)
            ]
        ),
    )
    rows = list(job.result())

    if not rows:
        # Fall back to speaker entity if no subject link
        if not speaker_entity_id:
            log.warning(
                "No subject entity found for CORRECT claim_id=%s — skipping entity_attribute_event",
                claim_id,
            )
            return
        entity_id = speaker_entity_id
        domain = "sports.nfl"
    else:
        entity_id = rows[0]["entity_id"]
        domain = rows[0]["primary_domain"] or "sports.nfl"

    valid_from_str = resolution_window_start or _now_ts()
    extraction_confidence = (
        float(weighted_score) if weighted_score is not None else 0.5
    )
    # Clamp to [0, 1]
    extraction_confidence = max(0.0, min(1.0, extraction_confidence))

    event_id = _new_uuid()
    value_json = json.dumps(
        {
            "claim_id": claim_id,
            "confirmed_correct": True,
        }
    )

    insert_attr_sql = f"""
        INSERT INTO `{project_id}.silver_v2_core.entity_attribute_event` (
            event_id,
            entity_id,
            domain,
            attr,
            value,
            value_json,
            valid_from,
            valid_to,
            evidence_type,
            source_claim_id,
            source_doc_id,
            extraction_confidence,
            corroboration_count,
            is_concurrent_ok,
            superseded_by,
            created_at
        )
        SELECT
            @event_id,
            @entity_id,
            @domain,
            'prediction_confirmed',
            'true',
            JSON @value_json,
            TIMESTAMP(@valid_from),
            NULL,
            'resolved_prediction',
            @claim_id,
            NULL,
            @extraction_confidence,
            1,
            TRUE,
            NULL,
            CURRENT_TIMESTAMP()
        WHERE NOT EXISTS (
            SELECT 1
            FROM `{project_id}.silver_v2_core.entity_attribute_event`
            WHERE source_claim_id = @claim_id
              AND attr = 'prediction_confirmed'
        )
    """
    client.query(
        insert_attr_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("event_id", "STRING", event_id),
                bigquery.ScalarQueryParameter("entity_id", "STRING", entity_id),
                bigquery.ScalarQueryParameter("domain", "STRING", domain),
                bigquery.ScalarQueryParameter("value_json", "STRING", value_json),
                bigquery.ScalarQueryParameter("valid_from", "STRING", valid_from_str),
                bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id),
                bigquery.ScalarQueryParameter(
                    "extraction_confidence",
                    "FLOAT64",
                    extraction_confidence,
                ),
            ]
        ),
    ).result()
    log.debug(
        "Wrote entity_attribute_event for CORRECT claim_id=%s entity_id=%s",
        claim_id,
        entity_id,
    )


def _write_log(
    total_processed: int,
    total_inserted: int,
    total_skipped: int,
    total_missing_claim: int,
    dry_run: bool,
) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = "dry-run" if dry_run else "live"
    log_file = LOG_DIR / f"migrate_resolutions_{mode}_{ts}.txt"
    summary = (
        f"migrate_prediction_resolutions_to_silver_v2 — {mode}\n"
        f"  Run at:               {ts}\n"
        f"  Total processed:      {total_processed}\n"
        f"  Inserted:             {total_inserted}\n"
        f"  Skipped (dup):        {total_skipped}\n"
        f"  Skipped (no claim):   {total_missing_claim}\n"
    )
    log_file.write_text(summary)
    log.info("Migration log written to %s", log_file)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Migrate gold_layer.prediction_resolutions → silver_v2_claims (Phase 2)"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help=f"Rows per batch (default: {BATCH_SIZE_DEFAULT})",
    )
    args = parser.parse_args()

    project_id = _require_env("GCP_PROJECT_ID")

    if bigquery is None:
        log.error(
            "google-cloud-bigquery is not installed. Run: pip install google-cloud-bigquery"
        )
        sys.exit(1)

    client = bigquery.Client(project=project_id)

    _ensure_tables_exist(client, project_id)
    existing_resolution_claim_ids = _load_existing_resolution_claim_ids(
        client, project_id
    )

    total_processed = 0
    total_inserted = 0
    total_skipped = 0
    total_missing_claim = 0

    offset = 0
    batch_num = 0

    while True:
        batch = _fetch_resolution_batch(client, project_id, offset, args.batch_size)
        if not batch:
            break

        batch_num += 1
        batch_inserted = 0
        batch_skipped = 0

        for row in batch:
            total_processed += 1
            claim_id = row.get("claim_id")

            if not claim_id:
                log.warning(
                    "prediction_hash=%s has no matching silver_v2 claim — skipping.",
                    row.get("prediction_hash"),
                )
                total_missing_claim += 1
                continue

            if claim_id in existing_resolution_claim_ids:
                total_skipped += 1
                batch_skipped += 1
                continue

            try:
                inserted = _migrate_resolution_row(
                    client, project_id, row, args.dry_run
                )
                if inserted:
                    total_inserted += 1
                    batch_inserted += 1
                    if not args.dry_run:
                        existing_resolution_claim_ids.add(claim_id)
            except Exception as exc:
                log.error(
                    "Failed to migrate resolution for prediction_hash=%s: %s",
                    row.get("prediction_hash"),
                    exc,
                )
                raise

        log.info(
            "Batch %d: offset=%d inserted=%d skipped=%d missing=%d "
            "(total inserted=%d skipped=%d missing=%d)",
            batch_num,
            offset,
            batch_inserted,
            batch_skipped,
            total_missing_claim,
            total_inserted,
            total_skipped,
            total_missing_claim,
        )

        offset += args.batch_size

        if len(batch) < args.batch_size:
            break

    _write_log(
        total_processed,
        total_inserted,
        total_skipped,
        total_missing_claim,
        args.dry_run,
    )

    mode = "DRY-RUN complete" if args.dry_run else "Migration complete"
    log.info(
        "%s: processed=%d inserted=%d skipped=%d missing_claim=%d",
        mode,
        total_processed,
        total_inserted,
        total_skipped,
        total_missing_claim,
    )


if __name__ == "__main__":
    main()

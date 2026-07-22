"""
migrate_prediction_ledger_to_silver_v2.py — Phase 0 bridge migration (issue #1129 §5).

Migrates gold_layer.prediction_ledger (2,669 legacy rows) → silver_v2_claims.claim
+ claim_entity_link + claim_state_history + entities. ALL legacy rows are migrated
as-is — this script intentionally does NO dedup (the ~2.3x duplicate inflation from
non-content-stable prediction_hash is a separate, explicit follow-up per #1129 §5).

Design decisions (from issue #920 comments):
  - claim_id: fresh UUID (legacy prediction_hash stored in legacy_prediction_hash)
  - Unresolvable entities: placeholder entity (entity_kind='unresolved') + row in
    entity_resolution_queue
  - Effective dates: effective_source='asserted_at' using ingestion_timestamp as proxy
  - Resumable: batches of 100 rows; progress logged

Idempotency (hardened — issue #1129 Phase 0 slice):
  - A row is only considered "fully migrated" when its claim row AND a matching
    claim_state_history row AND at least one claim_entity_link row all exist.
    Checking legacy_prediction_hash presence alone is NOT sufficient: if a prior
    run was interrupted between the claim INSERT and the history/link INSERTs,
    the claim looks "present" but is missing its history/link rows. The old
    all-or-nothing skip based on legacy_prediction_hash membership would
    permanently skip that row on every subsequent run, silently leaving it
    incomplete forever. Partially-migrated rows are now detected and *repaired*
    (backfilled) on the next run — see _load_migration_state / _classify_row.
  - Every write statement additionally guards itself with its own
    WHERE NOT EXISTS / MERGE ... WHEN NOT MATCHED check, so re-running this
    script (including re-running it because it was already fully migrated) is
    always safe and never double-inserts.
  - --dry-run now exercises the *same* subject-entity resolution code path as a
    live run (alias lookup, placeholder fallback) instead of a divergent stub,
    so its preview accurately reflects what a live run would decide.

Usage:
    python pipeline/scripts/migrate_prediction_ledger_to_silver_v2.py
    python pipeline/scripts/migrate_prediction_ledger_to_silver_v2.py --dry-run
    python pipeline/scripts/migrate_prediction_ledger_to_silver_v2.py --batch-size 50
    python pipeline/scripts/migrate_prediction_ledger_to_silver_v2.py --verify-only
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
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google Cloud imports — graceful failure if package missing
# ---------------------------------------------------------------------------
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


def _normalize_entity_string(raw: str) -> str:
    """Lowercase + strip for entity normalization."""
    return raw.lower().strip() if raw else ""


def _unresolved_entity_id(raw_string: str) -> str:
    """Deterministic placeholder entity_id for unresolvable strings."""
    h = hashlib.sha256(_normalize_entity_string(raw_string).encode()).hexdigest()[:16]
    return f"unresolved:{h}"


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _now_ts() -> str:
    """Return current UTC timestamp as ISO string for BQ."""
    return datetime.now(timezone.utc).isoformat()


def _category_to_domain(claim_category: str | None) -> str:
    """Map legacy claim_category values to silver_v2 domain strings."""
    if not claim_category:
        return "sports.nfl"
    cat = claim_category.lower()
    if "politi" in cat:
        return "politics"
    if "finance" in cat or "economy" in cat:
        return "finance"
    # default for all NFL/sports categories
    return "sports.nfl"


def _ensure_tables_exist(client: "bigquery.Client", project_id: str) -> None:
    """Verify required Phase 1 tables exist. Exit 1 if not."""
    required = [
        f"`{project_id}.silver_v2_claims.claim`",
        f"`{project_id}.silver_v2_claims.claim_entity_link`",
        f"`{project_id}.silver_v2_claims.claim_state_history`",
        f"`{project_id}.silver_v2_core.entity`",
        f"`{project_id}.silver_v2_claims.entity_resolution_queue`",
    ]
    for table_ref in required:
        # Strip backticks for the API call
        clean = table_ref.replace("`", "")
        dataset_table = clean.split(".", 1)[1]  # project.dataset.table → dataset.table
        parts = clean.split(".")
        try:
            client.get_table(f"{parts[0]}.{parts[1]}.{parts[2]}")
        except NotFound:
            log.error(
                "Required table %s does not exist. Run Phase 1 DDL migration first.",
                table_ref,
            )
            sys.exit(1)
    log.info("All required Phase 1 tables verified.")


def _load_migration_state(
    client: "bigquery.Client", project_id: str
) -> dict[str, dict[str, Any]]:
    """Return legacy_prediction_hash -> completeness info for already-bridged claims.

    A row is only "fully migrated" once the claim row AND a claim_state_history
    row AND at least one claim_entity_link row all exist. Rows where the claim
    exists but history/links are missing indicate an interrupted prior run and
    are flagged for repair rather than silently skipped forever (see module
    docstring). Also detects legacy_prediction_hash values mapped to more than
    one claim row, which would violate the idempotency invariant.
    """
    query = f"""
        SELECT
            c.legacy_prediction_hash AS legacy_prediction_hash,
            c.claim_id AS claim_id,
            EXISTS (
                SELECT 1 FROM `{project_id}.silver_v2_claims.claim_state_history` h
                WHERE h.claim_id = c.claim_id
            ) AS has_history,
            EXISTS (
                SELECT 1 FROM `{project_id}.silver_v2_claims.claim_entity_link` l
                WHERE l.claim_id = c.claim_id
            ) AS has_links
        FROM `{project_id}.silver_v2_claims.claim` c
        WHERE c.legacy_prediction_hash IS NOT NULL
    """
    job = client.query(query)
    rows = list(job.result())

    state: dict[str, dict[str, Any]] = {}
    duplicate_hashes: list[str] = []
    for r in rows:
        row = dict(r)
        legacy_hash = row.get("legacy_prediction_hash")
        if not legacy_hash:
            continue
        if legacy_hash in state:
            duplicate_hashes.append(legacy_hash)
        state[legacy_hash] = {
            "claim_id": row.get("claim_id"),
            "has_history": bool(row.get("has_history")),
            "has_links": bool(row.get("has_links")),
        }

    if duplicate_hashes:
        log.warning(
            "IDEMPOTENCY INVARIANT VIOLATED: %d legacy_prediction_hash value(s) map "
            "to more than one claim row in silver_v2_claims.claim (showing up to 10): %s",
            len(duplicate_hashes),
            duplicate_hashes[:10],
        )

    complete = sum(1 for s in state.values() if s["has_history"] and s["has_links"])
    partial = len(state) - complete
    log.info(
        "Found %d claims already bridged (%d complete, %d partial/needs-repair).",
        len(state),
        complete,
        partial,
    )
    return state


def _classify_row(prediction_hash: str, migration_state: dict[str, dict]) -> str:
    """Decide what to do with a source row given the current bridged state.

    Pure function (no I/O) so the skip/repair/insert decision is independently
    unit-testable without mocking BigQuery.

    Returns one of:
      "malformed" — no usable prediction_hash; cannot key off it, cannot migrate.
      "skip"      — already fully bridged (claim + history + >=1 link all present).
      "repair"    — claim row exists but history and/or links are missing (an
                    interrupted prior run). Safe to reprocess: _migrate_row's own
                    WHERE NOT EXISTS / MERGE guards make the claim re-insert a
                    no-op and only backfill the missing history/link rows.
      "new"       — never migrated; full insert required.
    """
    if not prediction_hash:
        return "malformed"
    state = migration_state.get(prediction_hash)
    if state is None:
        return "new"
    if state["has_history"] and state["has_links"]:
        return "skip"
    return "repair"


def _fetch_ledger_batch(
    client: "bigquery.Client", project_id: str, offset: int, batch_size: int
) -> list[dict[str, Any]]:
    """Fetch a batch of rows from gold_layer.prediction_ledger."""
    query = f"""
        SELECT
            prediction_hash,
            chain_hash,
            ingestion_timestamp,
            source_url,
            pundit_id,
            pundit_name,
            raw_assertion_text,
            extracted_claim,
            claim_category,
            season_year,
            target_player_id,
            target_team,
            sport,
            resolution_status,
            resolved_at,
            resolution_notes,
            target_player_name,
            stance,
            prompt_version,
            llm_provider,
            llm_model,
            target_entity
        FROM `{project_id}.gold_layer.prediction_ledger`
        ORDER BY ingestion_timestamp, prediction_hash
        LIMIT {batch_size} OFFSET {offset}
    """
    job = client.query(query)
    return [dict(r) for r in job.result()]


def _get_or_create_speaker_entity(
    client: "bigquery.Client",
    project_id: str,
    pundit_id: str,
    pundit_name: str,
    dry_run: bool,
) -> str:
    """
    Look up pundit by pundit_id in silver_v2_core.entity external_ids.
    Upsert if not found. Returns entity_id.
    """
    # Check if entity with this pundit_id already exists
    query = f"""
        SELECT entity_id
        FROM `{project_id}.silver_v2_core.entity`
        WHERE JSON_VALUE(external_ids, '$.pundit_id') = @pundit_id
        LIMIT 1
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("pundit_id", "STRING", pundit_id)
            ]
        ),
    )
    rows = list(job.result())
    if rows:
        return rows[0]["entity_id"]

    # Not found — create new person entity
    entity_id = _new_uuid()
    if dry_run:
        log.info(
            "[DRY-RUN] Would create speaker entity: entity_id=%s pundit_id=%s name=%s",
            entity_id,
            pundit_id,
            pundit_name,
        )
        return entity_id

    external_ids = json.dumps({"pundit_id": pundit_id})
    insert_sql = f"""
        INSERT INTO `{project_id}.silver_v2_core.entity`
            (entity_id, entity_kind, primary_domain, external_ids, created_at)
        VALUES
            (@entity_id, 'person', 'sports.nfl', JSON @external_ids, CURRENT_TIMESTAMP())
    """
    client.query(
        insert_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("entity_id", "STRING", entity_id),
                bigquery.ScalarQueryParameter("external_ids", "STRING", external_ids),
            ]
        ),
    ).result()
    log.debug("Created speaker entity: %s → %s", pundit_id, entity_id)
    return entity_id


def _resolve_subject_entity(
    client: "bigquery.Client",
    project_id: str,
    raw_string: str,
    entity_kind: str,
    domain: str,
    dry_run: bool,
    resolution_queue_rows: list[dict],
) -> str:
    """
    Try to resolve raw_string to an existing entity in silver_v2_core.entity.
    On miss: create placeholder + queue for resolution. Returns entity_id.
    """
    normalized = _normalize_entity_string(raw_string)
    if not normalized:
        return _unresolved_entity_id("__blank__")

    # Try exact match against entity_alias.alias_text
    lookup_query = f"""
        SELECT e.entity_id
        FROM `{project_id}.silver_v2_core.entity` e
        JOIN `{project_id}.silver_v2_core.entity_alias` a USING (entity_id)
        WHERE LOWER(a.alias_text) = LOWER(@raw_string)
          AND e.entity_kind = @entity_kind
        LIMIT 1
    """
    job = client.query(
        lookup_query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("raw_string", "STRING", normalized),
                bigquery.ScalarQueryParameter("entity_kind", "STRING", entity_kind),
            ]
        ),
    )
    rows = list(job.result())
    if rows:
        return rows[0]["entity_id"]

    # Also try direct entity notes (for previously backfilled placeholders)
    fallback_query = f"""
        SELECT entity_id
        FROM `{project_id}.silver_v2_core.entity`
        WHERE entity_kind = 'unresolved'
          AND notes = @raw_string
        LIMIT 1
    """
    job = client.query(
        fallback_query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("raw_string", "STRING", raw_string)
            ]
        ),
    )
    rows = list(job.result())
    if rows:
        return rows[0]["entity_id"]

    # Not found — create placeholder
    placeholder_id = _unresolved_entity_id(raw_string)

    if not dry_run:
        # Upsert placeholder entity (idempotent via INSERT IF NOT EXISTS)
        upsert_placeholder = f"""
            MERGE `{project_id}.silver_v2_core.entity` AS target
            USING (SELECT @entity_id AS entity_id) AS source
            ON target.entity_id = source.entity_id
            WHEN NOT MATCHED THEN
                INSERT (entity_id, entity_kind, primary_domain, notes, created_at)
                VALUES (@entity_id, 'unresolved', @domain, @notes, CURRENT_TIMESTAMP())
        """
        client.query(
            upsert_placeholder,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter(
                        "entity_id", "STRING", placeholder_id
                    ),
                    bigquery.ScalarQueryParameter("domain", "STRING", domain),
                    bigquery.ScalarQueryParameter("notes", "STRING", raw_string),
                ]
            ),
        ).result()

    # Queue for resolution
    queue_id = _new_uuid()
    resolution_queue_rows.append(
        {
            "queue_id": queue_id,
            "raw_entity_string": raw_string,
            "normalized_string": normalized,
            "domain": domain,
            "placeholder_entity_id": placeholder_id,
            "first_seen_at": _now_ts(),
            "attempt_count": 0,
            "status": "PENDING",
            "created_at": _now_ts(),
        }
    )

    log.debug("Created placeholder entity: %s → %s", raw_string, placeholder_id)
    return placeholder_id


def _insert_entity_resolution_queue_batch(
    client: "bigquery.Client",
    project_id: str,
    rows: list[dict],
    dry_run: bool,
) -> None:
    """Insert queued unresolvable entity rows, idempotent on (placeholder_entity_id)."""
    if not rows:
        return
    if dry_run:
        log.info(
            "[DRY-RUN] Would insert %d rows into entity_resolution_queue", len(rows)
        )
        return

    # Build VALUES list — idempotent via MERGE on placeholder_entity_id
    for row in rows:
        merge_sql = f"""
            MERGE `{project_id}.silver_v2_claims.entity_resolution_queue` AS target
            USING (SELECT @placeholder_entity_id AS placeholder_entity_id) AS source
            ON target.placeholder_entity_id = source.placeholder_entity_id
              AND target.raw_entity_string = @raw_entity_string
            WHEN NOT MATCHED THEN
                INSERT (
                    queue_id, raw_entity_string, normalized_string, domain,
                    placeholder_entity_id, first_seen_at, attempt_count,
                    status, created_at
                )
                VALUES (
                    @queue_id, @raw_entity_string, @normalized_string, @domain,
                    @placeholder_entity_id, CURRENT_TIMESTAMP(), 0,
                    'PENDING', CURRENT_TIMESTAMP()
                )
        """
        client.query(
            merge_sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter(
                        "queue_id", "STRING", row["queue_id"]
                    ),
                    bigquery.ScalarQueryParameter(
                        "raw_entity_string", "STRING", row["raw_entity_string"]
                    ),
                    bigquery.ScalarQueryParameter(
                        "normalized_string", "STRING", row.get("normalized_string", "")
                    ),
                    bigquery.ScalarQueryParameter(
                        "domain", "STRING", row.get("domain", "sports.nfl")
                    ),
                    bigquery.ScalarQueryParameter(
                        "placeholder_entity_id",
                        "STRING",
                        row["placeholder_entity_id"],
                    ),
                ]
            ),
        ).result()


def _compute_this_hash(
    claim_id: str,
    speaker_entity_id: str,
    asserted_at: str,
    predicate_args: str,
) -> str:
    """SHA-256 over silver_v2 canonical payload fields."""
    payload = f"{claim_id}|{speaker_entity_id}|{asserted_at}|{predicate_args}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _migrate_row(
    client: "bigquery.Client",
    project_id: str,
    row: dict[str, Any],
    dry_run: bool,
    resolution_queue_rows: list[dict],
    speaker_entity_cache: dict[str, str],
) -> bool:
    """
    Process a single prediction_ledger row.
    Returns True if row was inserted (or would be in dry-run), False if skipped.
    """
    prediction_hash = row.get("prediction_hash") or ""
    if not prediction_hash:
        log.warning("Row has no prediction_hash, skipping.")
        return False

    # Generate fresh UUID claim_id
    claim_id = _new_uuid()

    # Speaker entity
    pundit_id = row.get("pundit_id") or "unknown"
    pundit_name = row.get("pundit_name") or pundit_id
    if pundit_id not in speaker_entity_cache:
        speaker_entity_id = _get_or_create_speaker_entity(
            client, project_id, pundit_id, pundit_name, dry_run
        )
        speaker_entity_cache[pundit_id] = speaker_entity_id
    speaker_entity_id = speaker_entity_cache[pundit_id]

    # Domain
    domain = _category_to_domain(row.get("claim_category"))

    # Timestamps
    ingestion_ts = row.get("ingestion_timestamp")
    if ingestion_ts is None:
        asserted_at_str = _now_ts()
    elif hasattr(ingestion_ts, "isoformat"):
        asserted_at_str = ingestion_ts.isoformat()
    else:
        asserted_at_str = str(ingestion_ts)

    # predicate_args — structured from legacy fields
    predicate_args = {
        "text": row.get("extracted_claim") or row.get("raw_assertion_text") or "",
        "stance": row.get("stance"),
        "season_year": row.get("season_year"),
        "sport": row.get("sport"),
        "claim_category": row.get("claim_category"),
    }
    predicate_args_json = json.dumps(
        {k: v for k, v in predicate_args.items() if v is not None}
    )

    # Resolution window: legacy claims used season_year for window; approximate as year boundaries
    season_year = row.get("season_year")
    if season_year:
        try:
            yr = int(season_year)
            resolution_window_start = f"{yr}-09-01T00:00:00+00:00"
            resolution_window_end = f"{yr + 1}-02-28T23:59:59+00:00"
        except (ValueError, TypeError):
            resolution_window_start = asserted_at_str
            resolution_window_end = asserted_at_str
    else:
        resolution_window_start = asserted_at_str
        resolution_window_end = asserted_at_str

    # Hash chain
    this_hash = _compute_this_hash(
        claim_id, speaker_entity_id, asserted_at_str, predicate_args_json
    )
    legacy_prediction_hash = prediction_hash
    legacy_chain_hash = row.get("chain_hash") or ""

    # Derive claim state from legacy resolution_status
    legacy_status = row.get("resolution_status")
    claim_state = "PENDING"
    if legacy_status and legacy_status.upper() in (
        "CORRECT",
        "INCORRECT",
        "VOID",
        "PARTIAL",
        "UNVERIFIABLE",
    ):
        claim_state = legacy_status.upper()

    # ---------------------------------------------------------------------------
    # Resolve subject entities. This runs identically in dry-run and live mode —
    # _resolve_subject_entity / _build_subject_entity_list already internally
    # skip their own writes when dry_run=True (see `if not dry_run:` guards
    # inside them) but still perform the real alias-match / placeholder-fallback
    # SELECT lookups. Running the same resolution path in both modes is what
    # makes --dry-run a faithful preview of what a live run would decide,
    # instead of the entity_id being a NEW random placeholder guess every time.
    # ---------------------------------------------------------------------------
    subject_entities = _build_subject_entity_list(
        client, project_id, row, domain, dry_run, resolution_queue_rows
    )

    if dry_run:
        log.info(
            "[DRY-RUN] Would insert claim: claim_id=%s legacy_hash=%s speaker=%s "
            "domain=%s state=%s subject_entities=%s",
            claim_id,
            legacy_prediction_hash,
            speaker_entity_id,
            domain,
            claim_state,
            subject_entities,
        )
        return True

    # ---------------------------------------------------------------------------
    # Write claim row
    # ---------------------------------------------------------------------------
    insert_claim_sql = f"""
        INSERT INTO `{project_id}.silver_v2_claims.claim` (
            claim_id,
            utterance_id,
            speaker_entity_id,
            domain,
            claim_subject_type,
            subject_entity_ids,
            subject_metric,
            predicate,
            predicate_args,
            resolution_window_start,
            resolution_window_end,
            resolution_method_id,
            asserted_at,
            ledger_locked_at,
            prior_claim_id,
            prev_hash,
            this_hash,
            legacy_prediction_hash,
            legacy_chain_hash,
            created_at
        )
        SELECT
            @claim_id,
            NULL,
            @speaker_entity_id,
            @domain,
            'entity',
            NULL,
            NULL,
            'predicted',
            JSON @predicate_args_json,
            TIMESTAMP(@resolution_window_start),
            TIMESTAMP(@resolution_window_end),
            'legacy_migration',
            TIMESTAMP(@asserted_at),
            CURRENT_TIMESTAMP(),
            NULL,
            '',
            @this_hash,
            @legacy_prediction_hash,
            @legacy_chain_hash,
            CURRENT_TIMESTAMP()
        WHERE NOT EXISTS (
            SELECT 1
            FROM `{project_id}.silver_v2_claims.claim`
            WHERE legacy_prediction_hash = @legacy_prediction_hash
        )
    """
    client.query(
        insert_claim_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("claim_id", "STRING", claim_id),
                bigquery.ScalarQueryParameter(
                    "speaker_entity_id", "STRING", speaker_entity_id
                ),
                bigquery.ScalarQueryParameter("domain", "STRING", domain),
                bigquery.ScalarQueryParameter(
                    "predicate_args_json", "STRING", predicate_args_json
                ),
                bigquery.ScalarQueryParameter(
                    "resolution_window_start", "STRING", resolution_window_start
                ),
                bigquery.ScalarQueryParameter(
                    "resolution_window_end", "STRING", resolution_window_end
                ),
                bigquery.ScalarQueryParameter("asserted_at", "STRING", asserted_at_str),
                bigquery.ScalarQueryParameter("this_hash", "STRING", this_hash),
                bigquery.ScalarQueryParameter(
                    "legacy_prediction_hash", "STRING", legacy_prediction_hash
                ),
                bigquery.ScalarQueryParameter(
                    "legacy_chain_hash", "STRING", legacy_chain_hash
                ),
            ]
        ),
    ).result()

    # ---------------------------------------------------------------------------
    # Write claim_state_history — initial PENDING row
    # ---------------------------------------------------------------------------
    history_id = _new_uuid()
    insert_history_sql = f"""
        INSERT INTO `{project_id}.silver_v2_claims.claim_state_history` (
            history_id, claim_id, state, effective_from, effective_to,
            effective_source, resolution_id, brier_score, binary_correct,
            notes, created_at
        )
        SELECT
            @history_id,
            c.claim_id,
            @state,
            TIMESTAMP(@asserted_at),
            NULL,
            'asserted_at',
            NULL,
            NULL,
            NULL,
            'backfill from gold_layer.prediction_ledger',
            CURRENT_TIMESTAMP()
        FROM `{project_id}.silver_v2_claims.claim` c
        WHERE c.legacy_prediction_hash = @legacy_prediction_hash
          AND NOT EXISTS (
              SELECT 1 FROM `{project_id}.silver_v2_claims.claim_state_history`
              WHERE claim_id = c.claim_id
          )
    """
    client.query(
        insert_history_sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("history_id", "STRING", history_id),
                bigquery.ScalarQueryParameter("state", "STRING", claim_state),
                bigquery.ScalarQueryParameter("asserted_at", "STRING", asserted_at_str),
                bigquery.ScalarQueryParameter(
                    "legacy_prediction_hash", "STRING", legacy_prediction_hash
                ),
            ]
        ),
    ).result()

    # ---------------------------------------------------------------------------
    # Write claim_entity_link rows (subject_entities already resolved above)
    # ---------------------------------------------------------------------------
    for ordinal, (entity_id_subject, entity_role) in enumerate(subject_entities):
        link_id = _new_uuid()
        insert_link_sql = f"""
            INSERT INTO `{project_id}.silver_v2_claims.claim_entity_link` (
                link_id, claim_id, entity_id, entity_role, ordinal, created_at
            )
            SELECT
                @link_id,
                c.claim_id,
                @entity_id,
                @entity_role,
                @ordinal,
                CURRENT_TIMESTAMP()
            FROM `{project_id}.silver_v2_claims.claim` c
            WHERE c.legacy_prediction_hash = @legacy_prediction_hash
              AND NOT EXISTS (
                  SELECT 1
                  FROM `{project_id}.silver_v2_claims.claim_entity_link` l
                  JOIN `{project_id}.silver_v2_claims.claim` c2
                    ON l.claim_id = c2.claim_id
                  WHERE c2.legacy_prediction_hash = @legacy_prediction_hash
                    AND l.entity_id = @entity_id
                    AND l.entity_role = @entity_role
              )
        """
        client.query(
            insert_link_sql,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("link_id", "STRING", link_id),
                    bigquery.ScalarQueryParameter(
                        "entity_id", "STRING", entity_id_subject
                    ),
                    bigquery.ScalarQueryParameter("entity_role", "STRING", entity_role),
                    bigquery.ScalarQueryParameter("ordinal", "INT64", ordinal),
                    bigquery.ScalarQueryParameter(
                        "legacy_prediction_hash", "STRING", legacy_prediction_hash
                    ),
                ]
            ),
        ).result()

    return True


def _build_subject_entity_list(
    client: "bigquery.Client",
    project_id: str,
    row: dict[str, Any],
    domain: str,
    dry_run: bool,
    resolution_queue_rows: list[dict],
) -> list[tuple[str, str]]:
    """
    Return list of (entity_id, entity_role) tuples for claim_entity_link.
    """
    results: list[tuple[str, str]] = []

    # Player as primary subject
    player_name = row.get("target_player_name") or row.get("target_player_id")
    if player_name:
        entity_id = _resolve_subject_entity(
            client,
            project_id,
            str(player_name),
            "person",
            domain,
            dry_run,
            resolution_queue_rows,
        )
        results.append((entity_id, "subject"))

    # Team as context/object
    team_name = row.get("target_team")
    if team_name:
        entity_id = _resolve_subject_entity(
            client,
            project_id,
            str(team_name),
            "team_brand",
            domain,
            dry_run,
            resolution_queue_rows,
        )
        results.append((entity_id, "object"))

    # If no explicit subjects, create a generic unresolved placeholder
    if not results:
        raw_claim = row.get("extracted_claim") or row.get("raw_assertion_text") or ""
        placeholder_id = _unresolved_entity_id(raw_claim[:100])
        if not dry_run:
            upsert_blank_placeholder = f"""
                MERGE `{project_id}.silver_v2_core.entity` AS target
                USING (SELECT @entity_id AS entity_id) AS source
                ON target.entity_id = source.entity_id
                WHEN NOT MATCHED THEN
                    INSERT (entity_id, entity_kind, primary_domain, notes, created_at)
                    VALUES (@entity_id, 'unresolved', @domain, @notes, CURRENT_TIMESTAMP())
            """
            client.query(
                upsert_blank_placeholder,
                job_config=bigquery.QueryJobConfig(
                    query_parameters=[
                        bigquery.ScalarQueryParameter(
                            "entity_id", "STRING", placeholder_id
                        ),
                        bigquery.ScalarQueryParameter("domain", "STRING", domain),
                        bigquery.ScalarQueryParameter(
                            "notes", "STRING", raw_claim[:500]
                        ),
                    ]
                ),
            ).result()
        resolution_queue_rows.append(
            {
                "queue_id": _new_uuid(),
                "raw_entity_string": raw_claim[:500],
                "normalized_string": _normalize_entity_string(raw_claim[:100]),
                "domain": domain,
                "placeholder_entity_id": placeholder_id,
                "first_seen_at": _now_ts(),
                "attempt_count": 0,
                "status": "PENDING",
                "created_at": _now_ts(),
            }
        )
        results.append((placeholder_id, "subject"))

    return results


def _write_log(
    total_processed: int,
    total_inserted: int,
    total_repaired: int,
    total_skipped: int,
    total_malformed: int,
    dry_run: bool,
) -> None:
    """Write a migration summary log to pipeline/migrations/logs/."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = "dry-run" if dry_run else "live"
    log_file = LOG_DIR / f"migrate_ledger_{mode}_{ts}.txt"
    summary = (
        f"migrate_prediction_ledger_to_silver_v2 — {mode}\n"
        f"  Run at:          {ts}\n"
        f"  Total processed: {total_processed}\n"
        f"  Inserted (new):  {total_inserted}\n"
        f"  Repaired:        {total_repaired}\n"
        f"  Skipped:         {total_skipped}\n"
        f"  Malformed:       {total_malformed}\n"
    )
    log_file.write_text(summary)
    log.info("Migration log written to %s", log_file)


# ---------------------------------------------------------------------------
# Verification report — read-only, safe to run anytime (--verify-only)
# ---------------------------------------------------------------------------


def _generate_verification_report(
    client: "bigquery.Client", project_id: str
) -> dict[str, int]:
    """Read-only bridge-status report. Safe before, during, or after a run.

    Reports (all copy-pasteable as DuckDB equivalents in the PR description):
      source_row_count                    — COUNT(*) of gold_layer.prediction_ledger
      source_null_or_blank_hash_count     — source rows with no usable prediction_hash
                                             (can never be bridged; not an error, just
                                             unmigratable data)
      source_duplicate_hash_count         — source rows beyond the first for a repeated
                                             prediction_hash (issue #1129 analysis found
                                             this is 0/2669 today; kept as a live safety
                                             net rather than an assumption)
      bridged_complete_count              — fully migrated (claim + history + >=1 link)
      bridged_partial_count               — claim exists but is missing history and/or
                                             links (an interrupted prior run; the next
                                             run will repair these, not skip them)
      pending_migration_count             — usable-hash source rows untouched so far
      target_duplicate_legacy_hash_count  — legacy_prediction_hash mapped to more than
                                             one claim row in the target (idempotency
                                             invariant violation if nonzero — should
                                             always be 0)
    """
    source_stats_query = f"""
        SELECT
            COUNT(*) AS total_rows,
            COUNTIF(prediction_hash IS NULL OR prediction_hash = '') AS null_hash_rows,
            COUNT(*) - COUNT(DISTINCT prediction_hash) AS duplicate_hash_rows
        FROM `{project_id}.gold_layer.prediction_ledger`
    """
    source_row = dict(next(iter(client.query(source_stats_query).result())))

    migration_state = _load_migration_state(client, project_id)
    bridged_complete = sum(
        1 for s in migration_state.values() if s["has_history"] and s["has_links"]
    )
    bridged_partial = len(migration_state) - bridged_complete

    source_total = int(source_row.get("total_rows") or 0)
    source_null_hash = int(source_row.get("null_hash_rows") or 0)
    source_duplicate_hash = int(source_row.get("duplicate_hash_rows") or 0)

    pending = max(
        0, source_total - source_null_hash - bridged_complete - bridged_partial
    )

    duplicate_legacy_hash_query = f"""
        SELECT COUNT(*) AS n FROM (
            SELECT legacy_prediction_hash
            FROM `{project_id}.silver_v2_claims.claim`
            WHERE legacy_prediction_hash IS NOT NULL
            GROUP BY legacy_prediction_hash
            HAVING COUNT(*) > 1
        )
    """
    target_dup_row = dict(
        next(iter(client.query(duplicate_legacy_hash_query).result()))
    )
    target_duplicate_legacy_hash = int(target_dup_row.get("n") or 0)

    report = {
        "source_row_count": source_total,
        "source_null_or_blank_hash_count": source_null_hash,
        "source_duplicate_hash_count": source_duplicate_hash,
        "bridged_complete_count": bridged_complete,
        "bridged_partial_count": bridged_partial,
        "pending_migration_count": pending,
        "target_duplicate_legacy_hash_count": target_duplicate_legacy_hash,
    }

    log.info("=" * 68)
    log.info(
        "Bridge verification: %s.gold_layer.prediction_ledger -> silver_v2_claims",
        project_id,
    )
    log.info("=" * 68)
    for key, value in report.items():
        log.info("  %-38s %d", key, value)
    if target_duplicate_legacy_hash:
        log.warning(
            "%d legacy_prediction_hash value(s) map to more than one claim row "
            "— idempotency invariant violated.",
            target_duplicate_legacy_hash,
        )
    log.info("=" * 68)

    return report


# ---------------------------------------------------------------------------
# Migration driver — extracted from main() so it's directly callable from
# tests (no argv/sys.exit) with a mocked client.
# ---------------------------------------------------------------------------


def run_migration(
    client: "bigquery.Client",
    project_id: str,
    dry_run: bool,
    batch_size: int,
) -> dict[str, int]:
    """Run one full pass over gold_layer.prediction_ledger.

    Idempotency contract: calling this twice in a row with no source changes
    must make the second call a no-op (inserted=0, repaired=0, skipped=all).
    See _classify_row for the skip/repair/new decision and the module
    docstring for why a plain "does legacy_prediction_hash exist" check is
    not sufficient on its own.
    """
    _ensure_tables_exist(client, project_id)

    migration_state = _load_migration_state(client, project_id)

    total_processed = 0
    total_inserted = 0
    total_repaired = 0
    total_skipped = 0
    total_malformed = 0
    resolution_queue_rows: list[dict] = []
    speaker_entity_cache: dict[str, str] = {}

    offset = 0
    batch_num = 0

    while True:
        batch = _fetch_ledger_batch(client, project_id, offset, batch_size)
        if not batch:
            break

        batch_num += 1
        batch_inserted = 0
        batch_repaired = 0
        batch_skipped = 0
        batch_malformed = 0

        for row in batch:
            total_processed += 1
            prediction_hash = row.get("prediction_hash") or ""
            action = _classify_row(prediction_hash, migration_state)

            if action == "malformed":
                log.warning("Row has no usable prediction_hash, skipping.")
                total_malformed += 1
                batch_malformed += 1
                continue

            if action == "skip":
                total_skipped += 1
                batch_skipped += 1
                continue

            try:
                inserted = _migrate_row(
                    client,
                    project_id,
                    row,
                    dry_run,
                    resolution_queue_rows,
                    speaker_entity_cache,
                )
            except Exception as exc:
                log.error(
                    "Failed to migrate row prediction_hash=%s: %s",
                    prediction_hash,
                    exc,
                )
                raise

            if not inserted:
                # _migrate_row's own data-quality guard fired (e.g. blank hash
                # discovered mid-row despite passing the outer check).
                total_malformed += 1
                batch_malformed += 1
                continue

            if action == "repair":
                total_repaired += 1
                batch_repaired += 1
            else:
                total_inserted += 1
                batch_inserted += 1

            # Update in-memory state immediately (not just on the next run) so
            # a duplicate prediction_hash later in the SAME source batch/run
            # is correctly classified "skip" instead of double-counted as a
            # second insert — belt-and-suspenders alongside the WHERE NOT
            # EXISTS / MERGE guards each write statement already has.
            migration_state[prediction_hash] = {
                "claim_id": None,
                "has_history": True,
                "has_links": True,
            }

        log.info(
            "Batch %d: offset=%d inserted=%d repaired=%d skipped=%d malformed=%d "
            "(totals: inserted=%d repaired=%d skipped=%d malformed=%d)",
            batch_num,
            offset,
            batch_inserted,
            batch_repaired,
            batch_skipped,
            batch_malformed,
            total_inserted,
            total_repaired,
            total_skipped,
            total_malformed,
        )

        # Flush entity_resolution_queue batch
        _insert_entity_resolution_queue_batch(
            client, project_id, resolution_queue_rows, dry_run
        )
        resolution_queue_rows.clear()

        offset += batch_size

        if len(batch) < batch_size:
            break  # last partial batch

    accounted = total_inserted + total_repaired + total_skipped + total_malformed
    if accounted != total_processed:
        log.warning(
            "Row-count invariant violated: processed=%d but "
            "inserted+repaired+skipped+malformed=%d — investigate before "
            "trusting this run's numbers.",
            total_processed,
            accounted,
        )

    _write_log(
        total_processed,
        total_inserted,
        total_repaired,
        total_skipped,
        total_malformed,
        dry_run,
    )

    mode = "DRY-RUN complete" if dry_run else "Migration complete"
    log.info(
        "%s: processed=%d inserted=%d repaired=%d skipped=%d malformed=%d",
        mode,
        total_processed,
        total_inserted,
        total_repaired,
        total_skipped,
        total_malformed,
    )

    return {
        "total_processed": total_processed,
        "total_inserted": total_inserted,
        "total_repaired": total_repaired,
        "total_skipped": total_skipped,
        "total_malformed": total_malformed,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate gold_layer.prediction_ledger → silver_v2_claims (Phase 0 bridge, issue #1129)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would happen without writing to BigQuery",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=BATCH_SIZE_DEFAULT,
        help=f"Rows per batch (default: {BATCH_SIZE_DEFAULT})",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help=(
            "Print the verification report (source/bridged/partial/pending counts, "
            "NULL and duplicate key checks) and exit without migrating anything."
        ),
    )
    args = parser.parse_args()

    project_id = _require_env("GCP_PROJECT_ID")

    if bigquery is None:
        log.error(
            "google-cloud-bigquery is not installed. Run: pip install google-cloud-bigquery"
        )
        sys.exit(1)

    client = bigquery.Client(project=project_id)

    if args.verify_only:
        _ensure_tables_exist(client, project_id)
        _generate_verification_report(client, project_id)
        return

    run_migration(client, project_id, args.dry_run, args.batch_size)


if __name__ == "__main__":
    main()

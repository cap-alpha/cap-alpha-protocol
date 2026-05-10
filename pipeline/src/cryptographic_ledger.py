"""
Cryptographic Hashing Pipeline for Prediction Integrity (Issue #111)

Ingests pundit predictions into the append-only gold_layer.prediction_ledger
BigQuery table with SHA-256 hashing for tamper-evident record keeping.

Immutability is enforced at two layers:
  1. Application layer: only WRITE_APPEND via append_dataframe_to_table()
  2. IAM layer: service account lacks bigquery.tables.delete/update on this table

Concurrency safety (Issue #552):
  The chain-hash read → compute → write sequence is protected by a MERGE-based
  optimistic-concurrency guard against the ``gold_layer.ledger_chain_head``
  sentinel table.  Two concurrent ingest calls will race on the MERGE; exactly
  one wins (MERGE rows_affected > 0) and the loser retries after brief backoff.
  This guarantees the SHA-256 chain remains strictly linear regardless of how
  many concurrent pipeline runs overlap.
"""

import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
CHAIN_HEAD_TABLE = "gold_layer.ledger_chain_head"
HASH_SEED = ""  # Empty string seed for the first chain_hash

# Concurrency-guard tunables
_MAX_RETRIES = 10
_RETRY_BASE_SLEEP_S = 0.5  # exponential back-off base (seconds)


@dataclass
class PunditPrediction:
    """
    A single pundit prediction to be written to the ledger.
    Fields marked Optional are nullable in BigQuery.
    """

    pundit_id: str
    pundit_name: str
    source_url: str
    raw_assertion_text: str
    extracted_claim: Optional[str] = None
    claim_category: Optional[str] = (
        None  # player_performance|game_outcome|trade|draft_pick|injury|contract
    )
    season_year: Optional[int] = None
    target_player_id: Optional[str] = None  # Resolved player ID (from lookup)
    target_player_name: Optional[str] = None  # Raw player name from extraction
    target_team: Optional[str] = None
    stance: Optional[str] = None  # bullish|bearish|neutral
    sport: str = "NFL"  # NFL|MLB|NBA|NHL|NCAAF|NCAAB
    ingestion_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    prompt_version: Optional[str] = None  # SHA-256 prefix of extraction prompt template
    llm_provider: Optional[str] = None  # e.g. "ollama", "gemini", "openai"
    llm_model: Optional[str] = None  # e.g. "qwen2.5:32b", "gemini-2.5-flash"
    target_entity: Optional[str] = (
        None  # Issue #688 — JSON string, polymorphic entity envelope
    )
    claim_norm_key: Optional[str] = (
        None  # SHA-256 of normalised category|player|team|season (Issue #808)
    )


def _canonical_payload(prediction: PunditPrediction) -> str:
    """Returns the deterministic string that is SHA-256 hashed for prediction_hash."""
    ts = prediction.ingestion_timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return "|".join(
        [ts, prediction.source_url, prediction.pundit_id, prediction.raw_assertion_text]
    )


def compute_prediction_hash(prediction: PunditPrediction) -> str:
    """SHA-256 of the canonical payload."""
    payload = _canonical_payload(prediction)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_chain_hash(prediction_hash: str, previous_chain_hash: str) -> str:
    """SHA-256 of prediction_hash concatenated with the previous row's chain_hash."""
    combined = prediction_hash + previous_chain_hash
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def get_latest_chain_hash(db: DBManager) -> str:
    """
    Fetches the chain_hash of the most recently ingested ledger row.
    Returns HASH_SEED if the table is empty.

    NOTE: kept for ``verify_chain_integrity`` and direct inspection.
    Do NOT use inside ingest paths — use the chain-head sentinel instead.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    query = f"""
        SELECT chain_hash
        FROM `{project_id}.{LEDGER_TABLE}`
        ORDER BY ingestion_timestamp DESC
        LIMIT 1
    """
    try:
        df = db.fetch_df(query)
        if df.empty:
            return HASH_SEED
        return str(df.iloc[0]["chain_hash"])
    except Exception as e:
        # Table may not exist yet — return seed
        logger.warning(f"Could not fetch latest chain_hash (table may be empty): {e}")
        return HASH_SEED


# ---------------------------------------------------------------------------
# Chain-head sentinel helpers (Issue #552 — atomic concurrency guard)
# ---------------------------------------------------------------------------


def _ensure_chain_head_table(db: DBManager) -> None:
    """
    Creates ``gold_layer.ledger_chain_head`` if it does not yet exist.
    The table holds exactly one row: the current tail chain_hash.
    BigQuery DDL is idempotent with IF NOT EXISTS.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    ddl = f"""
        CREATE TABLE IF NOT EXISTS `{project_id}.{CHAIN_HEAD_TABLE}` (
            singleton_key STRING NOT NULL,
            chain_hash    STRING NOT NULL,
            updated_at    TIMESTAMP NOT NULL
        )
    """
    db.client.query(ddl).result()


def _read_chain_head(db: DBManager) -> str:
    """
    Returns the current tail chain_hash from the sentinel table.
    Returns HASH_SEED when the sentinel row does not exist yet.
    Creates the table if needed.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    _ensure_chain_head_table(db)
    query = f"""
        SELECT chain_hash
        FROM `{project_id}.{CHAIN_HEAD_TABLE}`
        WHERE singleton_key = 'HEAD'
        LIMIT 1
    """
    try:
        df = db.fetch_df(query)
        if df.empty:
            return HASH_SEED
        return str(df.iloc[0]["chain_hash"])
    except Exception as e:
        logger.warning(f"Could not read chain_head sentinel: {e}")
        return HASH_SEED


def _try_advance_chain_head(db: DBManager, expected_hash: str, new_hash: str) -> bool:
    """
    Atomically advances the chain-head sentinel from ``expected_hash`` to
    ``new_hash`` using a BigQuery MERGE statement.

    Returns True  — we won the race; safe to append rows to the ledger.
    Returns False — another writer changed the head first; caller must retry.

    MERGE semantics:
      WHEN NOT MATCHED AND expected_hash == HASH_SEED → INSERT first-ever row
      WHEN MATCHED AND chain_hash == expected_hash    → UPDATE to new_hash
    Both branches are conditional, so a concurrent writer that already advanced
    the head will cause 0 rows_affected → returns False.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f UTC")

    # Safely embed hashes — they are SHA-256 hex strings (no SQL injection risk),
    # but we quote defensively to be explicit.
    merge_sql = f"""
        MERGE `{project_id}.{CHAIN_HEAD_TABLE}` AS T
        USING (SELECT 'HEAD' AS singleton_key) AS S
        ON T.singleton_key = S.singleton_key
        WHEN NOT MATCHED AND '{expected_hash}' = '{HASH_SEED}' THEN
            INSERT (singleton_key, chain_hash, updated_at)
            VALUES ('HEAD', '{new_hash}', TIMESTAMP '{now_ts}')
        WHEN MATCHED AND T.chain_hash = '{expected_hash}' THEN
            UPDATE SET chain_hash = '{new_hash}',
                       updated_at = TIMESTAMP '{now_ts}'
    """
    job = db.client.query(merge_sql)
    job.result()
    affected = job.num_dml_affected_rows if job.num_dml_affected_rows is not None else 0
    return affected > 0


def _append_to_ledger(df: pd.DataFrame, db: DBManager) -> None:
    """
    Writes rows to gold_layer.prediction_ledger using WRITE_APPEND.
    Uses the BQ client directly because the table lives in a different dataset
    (gold_layer) than the default nfl_dead_money dataset in DBManager.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    table_ref = f"{project_id}.{LEDGER_TABLE}"
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    job = db.client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()


# ---------------------------------------------------------------------------
# Public ingest API
# ---------------------------------------------------------------------------


def ingest_prediction(
    prediction: PunditPrediction, db: Optional[DBManager] = None
) -> str:
    """
    Hash a single PunditPrediction and append it to the ledger.

    Delegates to ``ingest_batch`` so concurrency protection is applied.
    Returns the prediction_hash of the newly ingested record.
    """
    return ingest_batch([prediction], db=db)[0]


def ingest_batch(
    predictions: list[PunditPrediction], db: Optional[DBManager] = None
) -> list[str]:
    """
    Hash and append a batch of predictions sequentially (order matters for chain integrity).

    Concurrency guarantee (Issue #552):
      1. Read current chain-head from ``ledger_chain_head`` sentinel.
      2. Build the full chain for this batch in-process (no I/O).
      3. Atomically claim the sentinel via a conditional MERGE:
           - MERGE sets chain_head = new_tail ONLY IF current == expected.
           - If another writer won the race (0 rows affected), back off + retry.
      4. After winning the MERGE, append rows to the append-only ledger.

    Exactly one concurrent caller can claim a given chain-head value; the chain
    therefore stays strictly linear regardless of overlapping pipeline runs.

    Returns list of prediction_hashes in ingestion order.
    """
    if not predictions:
        return []

    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        for attempt in range(1, _MAX_RETRIES + 1):
            # Step 1: read current chain head
            previous_chain_hash = _read_chain_head(db)

            # Step 2: build chain in-process
            rows = []
            hashes = []
            current_chain_hash = previous_chain_hash

            for prediction in predictions:
                prediction_hash = compute_prediction_hash(prediction)
                chain_hash = compute_chain_hash(prediction_hash, current_chain_hash)

                rows.append(
                    {
                        "prediction_hash": prediction_hash,
                        "chain_hash": chain_hash,
                        "ingestion_timestamp": prediction.ingestion_timestamp,
                        "source_url": prediction.source_url,
                        "pundit_id": prediction.pundit_id,
                        "pundit_name": prediction.pundit_name,
                        "raw_assertion_text": prediction.raw_assertion_text,
                        "extracted_claim": prediction.extracted_claim,
                        "claim_category": prediction.claim_category,
                        "season_year": prediction.season_year,
                        "target_player_id": prediction.target_player_id,
                        "target_player_name": prediction.target_player_name,
                        "target_team": prediction.target_team,
                        "target_entity": prediction.target_entity,
                        "stance": prediction.stance,
                        "sport": prediction.sport,
                        "prompt_version": prediction.prompt_version,
                        "llm_provider": prediction.llm_provider,
                        "llm_model": prediction.llm_model,
                        "resolution_status": "PENDING",
                        "resolved_at": None,
                        "resolution_notes": None,
                        "claim_norm_key": prediction.claim_norm_key,
                    }
                )
                hashes.append(prediction_hash)
                current_chain_hash = chain_hash  # advance chain

            new_chain_head = current_chain_hash  # tail of this batch

            # Step 3: atomically claim the sentinel slot
            won = _try_advance_chain_head(db, previous_chain_hash, new_chain_head)
            if not won:
                sleep_s = _RETRY_BASE_SLEEP_S * (2 ** (attempt - 1))
                logger.warning(
                    "ingest_batch: chain-head conflict on attempt %d/%d; "
                    "another writer advanced the head — retrying in %.1fs",
                    attempt,
                    _MAX_RETRIES,
                    sleep_s,
                )
                time.sleep(sleep_s)
                continue

            # Step 4: append rows to the ledger (we now exclusively own this slot)
            _append_to_ledger(pd.DataFrame(rows), db)

            logger.info(
                "Ingested batch of %d predictions into ledger (attempt %d).",
                len(predictions),
                attempt,
            )
            return hashes

        raise RuntimeError(
            f"ingest_batch: failed to claim chain-head after {_MAX_RETRIES} attempts. "
            "Another writer may be holding the slot or BQ MERGE is misbehaving."
        )
    finally:
        if close_db:
            db.close()


def verify_chain_integrity(db: Optional[DBManager] = None) -> dict:
    """
    Walks the full ledger in chronological order and re-derives each chain_hash.
    Returns a dict with:
      - verified: bool
      - total_records: int
      - first_break_at: prediction_hash of first tampered record (or None)
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT prediction_hash, chain_hash, ingestion_timestamp,
                   source_url, pundit_id, raw_assertion_text
            FROM `{project_id}.{LEDGER_TABLE}`
            ORDER BY ingestion_timestamp ASC
        """
        df = db.fetch_df(query)

        if df.empty:
            return {"verified": True, "total_records": 0, "first_break_at": None}

        previous_chain_hash = HASH_SEED
        for _, row in df.iterrows():
            stored_prediction_hash = row["prediction_hash"]
            stored_chain_hash = row["chain_hash"]

            expected_chain = compute_chain_hash(
                stored_prediction_hash, previous_chain_hash
            )
            if expected_chain != stored_chain_hash:
                logger.error(
                    "Chain integrity BROKEN at prediction_hash=%s",
                    stored_prediction_hash,
                )
                return {
                    "verified": False,
                    "total_records": len(df),
                    "first_break_at": stored_prediction_hash,
                }
            previous_chain_hash = stored_chain_hash

        logger.info("Chain integrity verified: %d records intact.", len(df))
        return {"verified": True, "total_records": len(df), "first_break_at": None}
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    result = verify_chain_integrity()
    print(result)

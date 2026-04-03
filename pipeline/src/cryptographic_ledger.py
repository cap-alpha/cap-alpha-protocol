"""
Cryptographic Hashing Pipeline for Prediction Integrity (Issue #111)

Ingests pundit predictions into the append-only gold_layer.prediction_ledger
BigQuery table with SHA-256 hashing for tamper-evident record keeping.

Immutability is enforced at two layers:
  1. Application layer: only WRITE_APPEND via append_dataframe_to_table()
  2. IAM layer: service account lacks bigquery.tables.delete/update on this table
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
HASH_SEED = ""  # Empty string seed for the first chain_hash


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
    target_player_id: Optional[str] = None
    target_team: Optional[str] = None
    sport: str = "NFL"  # NFL|MLB|NBA|NHL|NCAAF|NCAAB
    ingestion_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
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


def ingest_prediction(
    prediction: PunditPrediction, db: Optional[DBManager] = None
) -> str:
    """
    Hash a single PunditPrediction and append it to the ledger.

    Returns the prediction_hash of the newly ingested record.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        previous_chain_hash = get_latest_chain_hash(db)
        prediction_hash = compute_prediction_hash(prediction)
        chain_hash = compute_chain_hash(prediction_hash, previous_chain_hash)

        row = {
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
            "target_team": prediction.target_team,
            "sport": prediction.sport,
            "resolution_status": "PENDING",
            "resolved_at": None,
            "resolution_notes": None,
        }

        _append_to_ledger(pd.DataFrame([row]), db)

        logger.info(
            f"Ingested prediction {prediction_hash[:16]}… "
            f"pundit={prediction.pundit_id} chain={chain_hash[:16]}…"
        )
        return prediction_hash
    finally:
        if close_db:
            db.close()


def ingest_batch(
    predictions: list[PunditPrediction], db: Optional[DBManager] = None
) -> list[str]:
    """
    Hash and append a batch of predictions sequentially (order matters for chain integrity).
    Returns list of prediction_hashes in ingestion order.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    hashes = []
    try:
        previous_chain_hash = get_latest_chain_hash(db)
        rows = []

        for prediction in predictions:
            prediction_hash = compute_prediction_hash(prediction)
            chain_hash = compute_chain_hash(prediction_hash, previous_chain_hash)

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
                    "target_team": prediction.target_team,
                    "sport": prediction.sport,
                    "resolution_status": "PENDING",
                    "resolved_at": None,
                    "resolution_notes": None,
                }
            )
            hashes.append(prediction_hash)
            previous_chain_hash = chain_hash  # advance chain

        _append_to_ledger(pd.DataFrame(rows), db)

        logger.info(f"Ingested batch of {len(predictions)} predictions into ledger.")
        return hashes
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
                    f"Chain integrity BROKEN at prediction_hash={stored_prediction_hash}"
                )
                return {
                    "verified": False,
                    "total_records": len(df),
                    "first_break_at": stored_prediction_hash,
                }
            previous_chain_hash = stored_chain_hash

        logger.info(f"Chain integrity verified: {len(df)} records intact.")
        return {"verified": True, "total_records": len(df), "first_break_at": None}
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    result = verify_chain_integrity()
    print(result)

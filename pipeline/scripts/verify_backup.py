#!/usr/bin/env python3
"""
verify_backup.py — BigQuery snapshot + cryptographic ledger backup verification.

Steps:
  1. Create or verify a BigQuery table snapshot of the ledger
  2. Run chain integrity check against the live table
  3. Export ledger table to GCS for point-in-time restore capability
  4. Alert Slack on any failure

Usage:
    python pipeline/scripts/verify_backup.py [--dry-run]

Env vars required:
    GCP_PROJECT_ID
    GCP_CLIENT_EMAIL
    GCP_PRIVATE_KEY
    GCS_BACKUP_BUCKET         — e.g. cap-alpha-backups
    SLACK_WEBHOOK_URL         — for failure alerts (optional)

Exit codes:
    0 — all checks passed
    1 — chain integrity failure or export error
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def _slack_alert(message: str, webhook_url: str | None) -> None:
    if not webhook_url:
        logger.warning("SLACK_WEBHOOK_URL not set — skipping alert: %s", message)
        return
    try:
        import urllib.request

        payload = json.dumps({"text": f":rotating_light: *Cap Alpha Backup Alert*\n{message}"}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10)
        logger.info("Slack alert sent.")
    except Exception as exc:
        logger.warning("Failed to send Slack alert: %s", exc)


def _get_bq_client():
    from google.cloud import bigquery
    from google.oauth2 import service_account

    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
    client_email = os.environ.get("GCP_CLIENT_EMAIL")
    private_key_raw = os.environ.get("GCP_PRIVATE_KEY")

    if client_email and private_key_raw:
        private_key = private_key_raw.replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            {
                "type": "service_account",
                "project_id": project_id,
                "private_key_id": "key",
                "private_key": private_key,
                "client_email": client_email,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        return bigquery.Client(project=project_id, credentials=creds)
    return bigquery.Client(project=project_id)


def run_chain_integrity_check(dry_run: bool) -> dict:
    """Run the cryptographic chain integrity check on the live ledger."""
    if dry_run:
        logger.info("[DRY RUN] Skipping live chain integrity check.")
        return {"verified": True, "total_records": 0, "first_break_at": None}

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    try:
        from src.cryptographic_ledger import verify_chain_integrity
        result = verify_chain_integrity()
        logger.info("Chain integrity result: %s", result)
        return result
    except Exception as exc:
        logger.error("Chain integrity check failed: %s", exc)
        return {"verified": False, "total_records": 0, "error": str(exc)}


def create_table_snapshot(project_id: str, dry_run: bool) -> str | None:
    """
    Create a BigQuery table snapshot of the ledger for point-in-time recovery.
    Snapshots are automatically managed by BigQuery (7-day default expiry unless extended).
    Returns snapshot table reference or None on failure.
    """
    dataset = "gold_layer"
    table = "pundit_ledger"
    snapshot_name = f"pundit_ledger_snap_{datetime.now(timezone.utc).strftime('%Y%m%d')}"
    snapshot_ref = f"{project_id}.{dataset}_backups.{snapshot_name}"

    if dry_run:
        logger.info("[DRY RUN] Would create snapshot: %s", snapshot_ref)
        return snapshot_ref

    try:
        bq = _get_bq_client()
        # Create a snapshot copy using CLONE or DDL
        # BigQuery snapshots require DDL:  CREATE SNAPSHOT TABLE ... CLONE ...
        query = f"""
            CREATE SNAPSHOT TABLE IF NOT EXISTS `{snapshot_ref}`
            CLONE `{project_id}.{dataset}.{table}`
            OPTIONS (expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 90 DAY))
        """
        bq.query(query).result()
        logger.info("Created snapshot: %s", snapshot_ref)
        return snapshot_ref
    except Exception as exc:
        # Snapshots may not be available on all project tiers; non-fatal
        logger.warning("Snapshot creation failed (may not be available): %s", exc)
        return None


def export_to_gcs(project_id: str, bucket: str, dry_run: bool) -> str | None:
    """
    Export the ledger table to GCS as a dated Parquet file.
    Returns the GCS URI or None on failure.
    """
    today = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    gcs_uri = f"gs://{bucket}/ledger/{today}/pundit_ledger_*.parquet"

    if dry_run:
        logger.info("[DRY RUN] Would export to: %s", gcs_uri)
        return gcs_uri

    try:
        from google.cloud import bigquery

        bq = _get_bq_client()
        dataset = "gold_layer"
        table = "pundit_ledger"
        job_config = bigquery.ExtractJobConfig(
            destination_format=bigquery.DestinationFormat.PARQUET,
            compression=bigquery.Compression.SNAPPY,
        )
        extract_job = bq.extract_table(
            f"{project_id}.{dataset}.{table}",
            gcs_uri,
            job_config=job_config,
        )
        extract_job.result()
        logger.info("Exported ledger to GCS: %s", gcs_uri)
        return gcs_uri
    except Exception as exc:
        logger.error("GCS export failed: %s", exc)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup verification for ledger")
    parser.add_argument("--dry-run", action="store_true", help="Skip writes, validate only")
    args = parser.parse_args()

    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
    bucket = os.environ.get("GCS_BACKUP_BUCKET", "cap-alpha-backups")
    slack_url = os.environ.get("SLACK_WEBHOOK_URL")

    logger.info("=== Cap Alpha Backup Verification ===")
    logger.info("Project: %s | Bucket: %s | Dry-run: %s", project_id, bucket, args.dry_run)

    failures = []

    # Step 1: Chain integrity
    logger.info("--- Step 1: Chain integrity check ---")
    chain = run_chain_integrity_check(args.dry_run)
    if not chain.get("verified"):
        msg = (
            f"Chain integrity FAILED. Records checked: {chain.get('total_records', 0)}. "
            f"First break at: {chain.get('first_break_at', 'unknown')}. "
            f"Error: {chain.get('error', '')}"
        )
        logger.error(msg)
        _slack_alert(msg, slack_url)
        failures.append("chain_integrity")
    else:
        logger.info("Chain integrity OK: %d records verified.", chain.get("total_records", 0))

    # Step 2: Table snapshot
    logger.info("--- Step 2: Table snapshot ---")
    snapshot = create_table_snapshot(project_id, args.dry_run)
    if snapshot:
        logger.info("Snapshot OK: %s", snapshot)
    else:
        logger.warning("Snapshot failed (non-fatal — may not be available on this tier)")

    # Step 3: GCS export
    logger.info("--- Step 3: GCS Parquet export ---")
    gcs_uri = export_to_gcs(project_id, bucket, args.dry_run)
    if gcs_uri:
        logger.info("GCS export OK: %s", gcs_uri)
    else:
        if not args.dry_run:
            msg = f"GCS export FAILED for bucket gs://{bucket}"
            logger.error(msg)
            _slack_alert(msg, slack_url)
            failures.append("gcs_export")

    # Summary
    logger.info("=== Backup Verification Summary ===")
    if failures:
        logger.error("FAILURES: %s", failures)
        return 1

    logger.info("All checks passed.")
    if not args.dry_run:
        slack_msg = (
            f":white_check_mark: *Weekly backup verified* — "
            f"chain integrity OK ({chain.get('total_records', 0)} records), "
            f"GCS export OK"
        )
        _slack_alert(slack_msg, slack_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())

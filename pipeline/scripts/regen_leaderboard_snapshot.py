#!/usr/bin/env python3
"""
regen_leaderboard_snapshot.py — Regenerate web/lib/data/leaderboard-snapshot.json
from live BigQuery data.

Usage
-----
    # From repo root (runs against BigQuery cap-alpha-protocol):
    python pipeline/scripts/regen_leaderboard_snapshot.py

    # Dry-run: print JSON to stdout instead of writing the file
    python pipeline/scripts/regen_leaderboard_snapshot.py --dry-run

    # Override output path
    python pipeline/scripts/regen_leaderboard_snapshot.py --out /tmp/leaderboard.json

Environment
-----------
    GCP_PROJECT_ID            Required. Must be set to "cap-alpha-protocol".
    GCP_SERVICE_ACCOUNT_JSON  Optional. Service-account JSON string for non-ADC auth.
                              If omitted, Application Default Credentials are used.

Staff-bucket exclusion (issue #995 / #1017)
-------------------------------------------
The following pundit_id values are ALWAYS excluded from the snapshot regardless
of what BigQuery returns:

    - espn_nfl_staff       — aggregate ESPN staff predictions; not an individual
    - pft_staff            — Pro Football Talk staff aggregate
    - athletic_nfl_staff   — The Athletic NFL staff aggregate

These buckets contain post-event recap articles that were mis-classified as
predictions during ingestion.  Including them inflates aggregate counts (many
predictions) and distorts individual rankings by crowding out real pundits.

PR #995 first removed them; PR #1016 accidentally re-added espn_nfl_staff via
an ad-hoc query.  The exclusion list is encoded here so every future snapshot
regeneration respects it without needing to re-read the history.

To add a new exclusion, extend STAFF_BUCKET_IDS below and add a comment
explaining why.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Staff-bucket exclusion list (issue #995)
# ---------------------------------------------------------------------------
STAFF_BUCKET_IDS: frozenset[str] = frozenset(
    {
        "espn_nfl_staff",    # ESPN aggregate bucket — post-event contamination
        "pft_staff",         # Pro Football Talk aggregate — post-event contamination
        "athletic_nfl_staff",  # The Athletic aggregate — post-event contamination
    }
)

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_PIPELINE_ROOT = _SCRIPT_DIR.parent
_REPO_ROOT = _PIPELINE_ROOT.parent
_DEFAULT_OUT = _REPO_ROOT / "web" / "lib" / "data" / "leaderboard-snapshot.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def _build_query(project_id: str) -> str:
    """
    Returns the BigQuery SQL that produces per-pundit accuracy metrics.

    Mirrors the query in pipeline/src/resolution_engine.py
    ``get_pundit_accuracy_summary`` (no quality filter, no min_resolved_claims
    gate, all sports) but adds an explicit staff-bucket exclusion in the
    WHERE clause.  Sorted by accuracy_rate DESC, then correct_count DESC for
    tie-breaking.
    """
    staff_list = ", ".join(f"'{pid}'" for pid in sorted(STAFF_BUCKET_IDS))
    return f"""
SELECT
    l.pundit_id,
    l.pundit_name,
    COALESCE(l.sport, 'NFL') AS sport,
    COUNT(*)                                          AS total_predictions,
    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))  AS resolved_count,
    COUNTIF(r.resolution_status = 'CORRECT')          AS correct_count,
    SAFE_DIVIDE(
        COUNTIF(r.resolution_status = 'CORRECT'),
        COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
    ) AS accuracy_rate,
    AVG(r.brier_score) AS avg_brier_score
FROM `{project_id}.gold_layer.prediction_ledger` l
LEFT JOIN `{project_id}.gold_layer.prediction_resolutions` r
    ON l.prediction_hash = r.prediction_hash
WHERE l.pundit_id NOT IN ({staff_list})
GROUP BY l.pundit_id, l.pundit_name, sport
ORDER BY
    accuracy_rate DESC NULLS LAST,
    COUNTIF(r.resolution_status = 'CORRECT') DESC
"""


def _row_to_pundit(row) -> dict:
    """Map a BigQuery row to the snapshot pundit schema."""
    accuracy = row.get("accuracy_rate")
    if accuracy is not None:
        accuracy = float(accuracy)

    brier = row.get("avg_brier_score")
    if brier is not None:
        brier = float(brier)

    resolved = int(row.get("resolved_count") or 0)
    correct = int(row.get("correct_count") or 0)

    return {
        "pundit_id": row["pundit_id"],
        "pundit_name": row["pundit_name"],
        "sport": row.get("sport") or "NFL",
        "total_predictions": int(row.get("total_predictions") or 0),
        "resolved_predictions": resolved,
        "correct_predictions": correct,
        "incorrect_predictions": resolved - correct,
        "accuracy_rate": accuracy,
        "avg_brier_score": brier,
    }


def fetch_snapshot(project_id: str) -> list[dict]:
    """Query BigQuery and return a list of pundit dicts, staff buckets excluded."""
    try:
        from google.cloud import bigquery
        from google.oauth2 import service_account
    except ImportError as exc:
        logger.error("google-cloud-bigquery not installed: %s", exc)
        sys.exit(1)

    credentials_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if credentials_json:
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(credentials_json)
        )
        client = bigquery.Client(project=project_id, credentials=credentials)
    else:
        client = bigquery.Client(project=project_id)

    sql = _build_query(project_id)
    logger.info("Running leaderboard query against %s …", project_id)
    logger.debug("SQL:\n%s", sql)

    job = client.query(sql)
    rows = list(job.result())

    logger.info("Query returned %d pundit rows", len(rows))

    pundits = []
    for row in rows:
        row_dict = dict(row)
        # Belt-and-suspenders: enforce exclusion in Python too
        if row_dict.get("pundit_id") in STAFF_BUCKET_IDS:
            logger.warning("Staff bucket leaked through SQL filter — skipping: %s", row_dict["pundit_id"])
            continue
        pundits.append(_row_to_pundit(row_dict))

    return pundits


def build_snapshot(pundits: list[dict], project_id: str) -> dict:
    """Wrap the pundit list in the standard snapshot envelope."""
    resolved_total = sum(p["resolved_predictions"] for p in pundits)
    return {
        "snapshot_metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": f"BigQuery {project_id}.gold_layer (direct query)",
            "note": (
                "Staff buckets excluded: espn_nfl_staff, pft_staff, athletic_nfl_staff "
                "(issue #995 — post-event contamination distorts individual rankings)."
            ),
            "total_resolved": resolved_total,
            "total_pundits": len(pundits),
        },
        "pundits": pundits,
    }


def write_snapshot(snapshot: dict, out_path: Path, dry_run: bool = False) -> None:
    """Serialise snapshot to JSON and write (or print if dry_run)."""
    payload = json.dumps(snapshot, indent=2, ensure_ascii=False)
    if dry_run:
        print(payload)
        logger.info("Dry-run: printed %d bytes to stdout", len(payload))
    else:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
        logger.info("Wrote %d bytes to %s", len(payload), out_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate web/lib/data/leaderboard-snapshot.json from BigQuery.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DEFAULT_OUT,
        help="Output JSON path (default: web/lib/data/leaderboard-snapshot.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print JSON to stdout instead of writing the file",
    )
    parser.add_argument(
        "--project",
        default=os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol"),
        help="GCP project ID (default: $GCP_PROJECT_ID or cap-alpha-protocol)",
    )
    args = parser.parse_args()

    if not args.project:
        logger.error("GCP_PROJECT_ID is not set. Pass --project or set the env var.")
        sys.exit(1)

    logger.info(
        "Staff buckets excluded: %s", ", ".join(sorted(STAFF_BUCKET_IDS))
    )

    pundits = fetch_snapshot(project_id=args.project)
    if not pundits:
        logger.warning("No pundits returned from BigQuery — snapshot will be empty")

    snapshot = build_snapshot(pundits, args.project)
    write_snapshot(snapshot, args.out, dry_run=args.dry_run)

    logger.info(
        "Done. %d pundits, %d total resolved predictions.",
        snapshot["snapshot_metadata"]["total_pundits"],
        snapshot["snapshot_metadata"]["total_resolved"],
    )


if __name__ == "__main__":
    # Ensure pipeline/src is importable when run from repo root
    sys.path.insert(0, str(_PIPELINE_ROOT))
    main()

"""
verify_kg_migration.py — Phase 2 verification gate.

Runs the four zero-count checks from issue #920 Phase 2 verification gate.
Prints PASS/FAIL for each check. Exits 0 if all pass, 1 if any fail.

Usage:
    python pipeline/scripts/verify_kg_migration.py

Prerequisites:
    - GCP_PROJECT_ID environment variable set
    - Phase 1 DDL applied (claim_entity_link, claim_state_history tables exist)
    - Phase 2 ledger + resolution migrations run
"""

from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

try:
    from google.cloud import bigquery
except ImportError:  # pragma: no cover
    bigquery = None  # type: ignore[assignment]


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        log.error("Environment variable %s is required but not set.", name)
        sys.exit(1)
    return val


def _run_check(
    client: "bigquery.Client",
    project_id: str,
    check_name: str,
    query: str,
) -> bool:
    """Run a single verification query. Returns True (PASS) if count == 0."""
    try:
        job = client.query(query.format(project_id=project_id))
        rows = list(job.result())
        count = rows[0][0] if rows else -1
        if count == 0:
            print(f"  PASS  {check_name} (count=0)")
            return True
        else:
            print(f"  FAIL  {check_name} (count={count})")
            return False
    except Exception as exc:
        print(f"  ERROR {check_name}: {exc}")
        return False


CHECKS: list[tuple[str, str]] = [
    (
        "Every legacy claim present in silver_v2",
        """
        SELECT COUNT(*)
        FROM `{project_id}.gold_layer.prediction_ledger` pl
        LEFT JOIN `{project_id}.silver_v2_claims.claim` c
            ON c.legacy_prediction_hash = pl.prediction_hash
        WHERE c.claim_id IS NULL
        """,
    ),
    (
        "Every legacy resolution present in silver_v2",
        """
        SELECT COUNT(*)
        FROM `{project_id}.gold_layer.prediction_resolutions` pr
        LEFT JOIN `{project_id}.silver_v2_claims.claim` c
            ON c.legacy_prediction_hash = pr.prediction_hash
        LEFT JOIN `{project_id}.silver_v2_claims.resolution` r
            ON r.claim_id = c.claim_id
        WHERE r.resolution_id IS NULL
        """,
    ),
    (
        "Every claim has at least one claim_state_history row",
        """
        SELECT COUNT(*)
        FROM `{project_id}.silver_v2_claims.claim` c
        LEFT JOIN `{project_id}.silver_v2_claims.claim_state_history` h
            ON h.claim_id = c.claim_id
        WHERE h.history_id IS NULL
        """,
    ),
    (
        "Every claim with a subject has at least one claim_entity_link",
        """
        SELECT COUNT(*)
        FROM `{project_id}.silver_v2_claims.claim` c
        LEFT JOIN `{project_id}.silver_v2_claims.claim_entity_link` l
            ON l.claim_id = c.claim_id
        WHERE l.link_id IS NULL
          AND c.claim_subject_type IS NOT NULL
        """,
    ),
]


def run_all_checks(project_id: str) -> bool:
    """Run all verification checks. Returns True if all pass."""
    if bigquery is None:
        log.error(
            "google-cloud-bigquery is not installed. Run: pip install google-cloud-bigquery"
        )
        sys.exit(1)

    client = bigquery.Client(project=project_id)

    print(f"\nKnowledge Graph Migration Verification — project: {project_id}")
    print("=" * 70)

    results = []
    for check_name, query in CHECKS:
        passed = _run_check(client, project_id, check_name, query)
        results.append(passed)

    print("=" * 70)
    passed_count = sum(results)
    total = len(results)
    if all(results):
        print(f"ALL {total} CHECKS PASSED — Phase 2 migration verified.")
        return True
    else:
        failed = total - passed_count
        print(f"{failed}/{total} CHECKS FAILED — migration incomplete or has gaps.")
        return False


def main() -> None:
    project_id = _require_env("GCP_PROJECT_ID")
    success = run_all_checks(project_id)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

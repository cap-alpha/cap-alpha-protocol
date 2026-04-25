"""
Post-ingestion BigQuery data quality checks (SP29-2).

Runs after each pipeline ingestion cycle to detect data issues before they
propagate into Gold layer or user-facing APIs.

Checks:
  - NULL rate on critical columns (alerts at >20% NULL)
  - Cap figure outliers via z-score (flags values >3 standard deviations)
  - Year coverage gaps in contract tables
  - Row count health per table

Usage:
    python -m src.bq_data_quality               # run all checks
    python -m src.bq_data_quality --strict      # exit 1 if any WARNING or ERROR
    python -m src.bq_data_quality --json        # output JSON report
"""

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

DATASET = "nfl_dead_money"

# Thresholds
NULL_WARN_PCT = 5.0  # >5% NULLs in a critical column → WARNING
NULL_ERROR_PCT = 20.0  # >20% NULLs → ERROR
OUTLIER_Z = 3.0  # z-score threshold for cap figure outliers
MIN_ROWS_PER_TABLE = {  # absolute minimum expected row counts
    "silver_spotrac_contracts": 10_000,
    "fact_player_efficiency": 10_000,
    "staging_feature_matrix": 10_000,
}
EXPECTED_YEAR_RANGE = range(2011, 2026)  # 2011–2025 inclusive


@dataclass
class CheckResult:
    table: str
    column: Optional[str]
    check: str
    status: str  # OK | WARNING | ERROR
    detail: str
    value: Optional[float] = None
    outlier_count: Optional[int] = None
    missing_years: Optional[list] = field(default=None)


def _client_and_project():
    """Return (bigquery.Client, project_id). Raises if BQ not accessible."""
    from google.cloud import bigquery

    project_id = os.environ.get("GCP_PROJECT_ID")
    client = bigquery.Client(project=project_id)
    if not project_id:
        project_id = client.project
    return client, project_id


def check_null_rate(client, project: str, table: str, column: str) -> CheckResult:
    """Return NULL percentage for *column* in *table*."""
    fqt = f"`{project}.{DATASET}.{table}`"
    sql = f"""
        SELECT
            COUNTIF({column} IS NULL) AS null_ct,
            COUNT(1) AS total_ct
        FROM {fqt}
    """
    row = list(client.query(sql).result())[0]
    null_ct = row.null_ct or 0
    total_ct = row.total_ct or 0
    pct = (null_ct / total_ct * 100) if total_ct else 0.0

    if pct > NULL_ERROR_PCT:
        status = "ERROR"
    elif pct > NULL_WARN_PCT:
        status = "WARNING"
    else:
        status = "OK"

    return CheckResult(
        table=table,
        column=column,
        check="null_rate",
        status=status,
        detail=f"{null_ct}/{total_ct} rows NULL ({pct:.1f}%)",
        value=round(pct, 2),
    )


def check_cap_outliers(
    client, project: str, table: str, column: str, z_threshold: float = OUTLIER_Z
) -> CheckResult:
    """
    Flag rows where *column* deviates by more than *z_threshold* standard
    deviations from the mean (ignoring NULLs).
    """
    fqt = f"`{project}.{DATASET}.{table}`"
    sql = f"""
        WITH stats AS (
            SELECT
                AVG({column}) AS mu,
                STDDEV({column}) AS sigma
            FROM {fqt}
            WHERE {column} IS NOT NULL
        )
        SELECT COUNT(1) AS outlier_ct
        FROM {fqt}, stats
        WHERE {column} IS NOT NULL
          AND ABS({column} - mu) > {z_threshold} * sigma
          AND sigma > 0
    """
    row = list(client.query(sql).result())[0]
    outlier_ct = row.outlier_ct or 0

    status = "WARNING" if outlier_ct > 0 else "OK"
    return CheckResult(
        table=table,
        column=column,
        check="cap_outliers",
        status=status,
        detail=f"{outlier_ct} rows exceed {z_threshold}σ from mean",
        outlier_count=int(outlier_ct),
    )


def check_year_coverage(client, project: str, table: str) -> CheckResult:
    """Verify all years in EXPECTED_YEAR_RANGE are present in *table*."""
    fqt = f"`{project}.{DATASET}.{table}`"
    sql = f"SELECT DISTINCT year FROM {fqt} WHERE year IS NOT NULL ORDER BY year"
    actual_years = {row.year for row in client.query(sql).result()}
    expected_years = set(EXPECTED_YEAR_RANGE)
    missing = sorted(expected_years - actual_years)

    status = "ERROR" if missing else "OK"
    return CheckResult(
        table=table,
        column="year",
        check="year_coverage",
        status=status,
        detail=(f"Missing years: {missing}" if missing else "All years present"),
        missing_years=missing if missing else None,
    )


def check_row_count(client, project: str, table: str, min_rows: int) -> CheckResult:
    """Alert if row count falls below *min_rows*."""
    fqt = f"`{project}.{DATASET}.{table}`"
    sql = f"SELECT COUNT(1) AS row_ct FROM {fqt}"
    row = list(client.query(sql).result())[0]
    row_ct = row.row_ct or 0

    status = "ERROR" if row_ct < min_rows else "OK"
    return CheckResult(
        table=table,
        column=None,
        check="row_count",
        status=status,
        detail=f"{row_ct:,} rows (minimum: {min_rows:,})",
        value=float(row_ct),
    )


def run_all_checks(client=None, project: str = None) -> list[CheckResult]:
    """
    Run the full post-ingestion check suite.  Returns a list of CheckResult.

    If *client* / *project* are None they are initialised from environment.
    """
    if client is None or project is None:
        client, project = _client_and_project()

    results: list[CheckResult] = []

    # silver_spotrac_contracts — primary contract table
    table = "silver_spotrac_contracts"
    for col in ("player_name", "team", "year"):
        results.append(check_null_rate(client, project, table, col))
    results.append(check_null_rate(client, project, table, "cap_hit_millions"))
    results.append(check_cap_outliers(client, project, table, "cap_hit_millions"))
    results.append(check_year_coverage(client, project, table))

    # fact_player_efficiency — gold layer
    table = "fact_player_efficiency"
    for col in ("player_name", "year"):
        results.append(check_null_rate(client, project, table, col))
    results.append(check_year_coverage(client, project, table))

    # Row count health across core tables
    for tbl, min_rows in MIN_ROWS_PER_TABLE.items():
        results.append(check_row_count(client, project, tbl, min_rows))

    return results


def format_report(results: list[CheckResult]) -> str:
    """Return a human-readable text report."""
    lines = [
        f"BQ Data Quality Report — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 70,
    ]
    for r in results:
        col_tag = f".{r.column}" if r.column else ""
        icon = {"OK": "✓", "WARNING": "⚠", "ERROR": "✗"}.get(r.status, "?")
        lines.append(
            f"  {icon} [{r.status:<7}] {r.table}{col_tag} ({r.check}): {r.detail}"
        )
    lines.append("=" * 70)

    ok = sum(1 for r in results if r.status == "OK")
    warn = sum(1 for r in results if r.status == "WARNING")
    err = sum(1 for r in results if r.status == "ERROR")
    lines.append(f"  Total: {ok} OK, {warn} WARNING, {err} ERROR")
    return "\n".join(lines)


def to_json(results: list[CheckResult]) -> str:
    return json.dumps(
        [
            {
                "table": r.table,
                "column": r.column,
                "check": r.check,
                "status": r.status,
                "detail": r.detail,
                "value": r.value,
                "outlier_count": r.outlier_count,
                "missing_years": r.missing_years,
            }
            for r in results
        ],
        indent=2,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="BQ post-ingestion data quality checks"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 if any WARNING or ERROR"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output JSON report to stdout"
    )
    args = parser.parse_args()

    try:
        results = run_all_checks()
    except Exception as e:
        logger.error(f"Quality checks failed to run: {e}")
        sys.exit(1)

    if args.json:
        print(to_json(results))
    else:
        print(format_report(results))
        for r in results:
            if r.status == "ERROR":
                logger.error(f"{r.table}.{r.column} [{r.check}]: {r.detail}")
            elif r.status == "WARNING":
                logger.warning(f"{r.table}.{r.column} [{r.check}]: {r.detail}")

    if args.strict:
        has_issues = any(r.status in ("WARNING", "ERROR") for r in results)
        sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()

"""
Schema Integrity Validator (Issue #106)

Validates that core identity columns have no NULL values and that expected
NOT NULL constraints are in place across Players, Teams, and Contracts tables.

Run before migration 009 to check for blocking NULLs:
    python -m src.schema_validator --pre-check

Run after migration 009 to verify constraints were applied:
    python -m src.schema_validator --post-check

Run as part of CI/CD or daily data quality:
    python -m src.schema_validator --full
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column contracts — what we expect to be NOT NULL in each table
# ---------------------------------------------------------------------------


@dataclass
class ColumnContract:
    dataset: str
    table: str
    columns: list[str]
    description: str = ""


CORE_CONTRACTS: list[ColumnContract] = [
    ColumnContract(
        dataset="nfl_dead_money",
        table="bronze_sportsdataio_players",
        columns=["PlayerID", "Name", "Team"],
        description="Player identity from SportsData.io",
    ),
    ColumnContract(
        dataset="nfl_dead_money",
        table="fact_player_efficiency",
        columns=["player_name", "team", "position"],
        description="Analytical player layer",
    ),
    ColumnContract(
        dataset="nfl_dead_money",
        table="silver_spotrac_contracts",
        columns=["player_name", "year"],
        description="Contract reference data",
    ),
    ColumnContract(
        dataset="nfl_dead_money",
        table="raw_pundit_media",
        columns=[
            "content_hash",
            "source_id",
            "source_url",
            "ingested_at",
            "content_type",
            "fetch_source_type",
        ],
        description="Bronze media ingestion",
    ),
    ColumnContract(
        dataset="gold_layer",
        table="prediction_ledger",
        columns=[
            "prediction_hash",
            "chain_hash",
            "ingestion_timestamp",
            "source_url",
            "pundit_id",
            "pundit_name",
            "raw_assertion_text",
        ],
        description="Gold prediction ledger with prompt versioning + LLM tracking",
    ),
    ColumnContract(
        dataset="gold_layer",
        table="prediction_resolutions",
        columns=["prediction_hash", "resolution_status", "created_at", "updated_at"],
        description="Prediction resolutions",
    ),
]


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------


@dataclass
class NullViolation:
    dataset: str
    table: str
    column: str
    null_count: int


@dataclass
class ConstraintViolation:
    dataset: str
    table: str
    column: str
    is_nullable: str  # 'YES' means NOT NULL constraint is missing


@dataclass
class ValidationReport:
    null_violations: list[NullViolation] = field(default_factory=list)
    constraint_violations: list[ConstraintViolation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.null_violations and not self.constraint_violations

    def print(self) -> None:
        if self.passed:
            logger.info("All schema integrity checks PASSED.")
            return

        if self.null_violations:
            logger.error(
                f"Found {len(self.null_violations)} NULL violations "
                f"(migration 009 will fail until resolved):"
            )
            for v in self.null_violations:
                logger.error(
                    f"  {v.dataset}.{v.table}.{v.column}: {v.null_count} NULL rows"
                )

        if self.constraint_violations:
            logger.warning(
                f"Found {len(self.constraint_violations)} missing NOT NULL "
                f"constraints (migration 009 not yet applied):"
            )
            for v in self.constraint_violations:
                logger.warning(f"  {v.dataset}.{v.table}.{v.column} is NULLABLE")


# ---------------------------------------------------------------------------
# Validation logic
# ---------------------------------------------------------------------------


def _table_exists(db: DBManager, project_id: str, dataset: str, table: str) -> bool:
    """Returns True if the table exists in BigQuery."""
    query = f"""
        SELECT COUNT(*) AS cnt
        FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`
        WHERE table_name = '{table}'
    """
    try:
        df = db.fetch_df(query)
        return int(df.iloc[0]["cnt"]) > 0
    except Exception:
        return False


def check_null_violations(
    db: DBManager, contract: ColumnContract, project_id: str
) -> list[NullViolation]:
    """Returns a list of columns that have NULL rows in the target table."""
    if not _table_exists(db, project_id, contract.dataset, contract.table):
        logger.warning(
            f"Table {contract.dataset}.{contract.table} not found — skipping"
        )
        return []

    null_checks = ", ".join(
        f"COUNTIF({col} IS NULL) AS `{col}`" for col in contract.columns
    )
    query = f"""
        SELECT {null_checks}
        FROM `{project_id}.{contract.dataset}.{contract.table}`
    """
    try:
        df = db.fetch_df(query)
        violations = []
        if not df.empty:
            row = df.iloc[0]
            for col in contract.columns:
                count = int(row.get(col, 0) or 0)
                if count > 0:
                    violations.append(
                        NullViolation(
                            dataset=contract.dataset,
                            table=contract.table,
                            column=col,
                            null_count=count,
                        )
                    )
        return violations
    except Exception as e:
        logger.warning(
            f"Could not check NULLs for {contract.dataset}.{contract.table}: {e}"
        )
        return []


def check_constraint_violations(
    db: DBManager, contract: ColumnContract, project_id: str
) -> list[ConstraintViolation]:
    """Returns columns that are missing NOT NULL constraints in the schema."""
    if not _table_exists(db, project_id, contract.dataset, contract.table):
        return []

    cols_in = ", ".join(f"'{c}'" for c in contract.columns)
    query = f"""
        SELECT column_name, is_nullable
        FROM `{project_id}.{contract.dataset}.INFORMATION_SCHEMA.COLUMNS`
        WHERE table_name = '{contract.table}'
          AND column_name IN ({cols_in})
          AND is_nullable = 'YES'
    """
    try:
        df = db.fetch_df(query)
        return [
            ConstraintViolation(
                dataset=contract.dataset,
                table=contract.table,
                column=str(row["column_name"]),
                is_nullable=str(row["is_nullable"]),
            )
            for _, row in df.iterrows()
        ]
    except Exception as e:
        logger.warning(
            f"Could not check constraints for {contract.dataset}.{contract.table}: {e}"
        )
        return []


def run_pre_check(db: DBManager, project_id: str) -> ValidationReport:
    """Pre-migration: verify no NULLs exist that would block ALTER COLUMN."""
    report = ValidationReport()
    for contract in CORE_CONTRACTS:
        logger.info(
            f"Checking NULLs: {contract.dataset}.{contract.table} "
            f"({contract.description})"
        )
        report.null_violations.extend(check_null_violations(db, contract, project_id))
    return report


def run_post_check(db: DBManager, project_id: str) -> ValidationReport:
    """Post-migration: verify NOT NULL constraints are in place."""
    report = ValidationReport()
    for contract in CORE_CONTRACTS:
        logger.info(
            f"Checking constraints: {contract.dataset}.{contract.table} "
            f"({contract.description})"
        )
        report.constraint_violations.extend(
            check_constraint_violations(db, contract, project_id)
        )
    return report


def run_full(db: DBManager, project_id: str) -> ValidationReport:
    """Combined pre + post check."""
    report = ValidationReport()
    for contract in CORE_CONTRACTS:
        report.null_violations.extend(check_null_violations(db, contract, project_id))
        report.constraint_violations.extend(
            check_constraint_violations(db, contract, project_id)
        )
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Schema integrity validator")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--pre-check",
        action="store_true",
        help="Check for NULL violations before migration 009",
    )
    group.add_argument(
        "--post-check",
        action="store_true",
        help="Verify NOT NULL constraints after migration 009",
    )
    group.add_argument(
        "--full",
        action="store_true",
        help="Run both NULL check and constraint verification",
    )
    args = parser.parse_args()

    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")

    with DBManager() as db:
        if args.pre_check:
            report = run_pre_check(db, project_id)
        elif args.post_check:
            report = run_post_check(db, project_id)
        else:
            report = run_full(db, project_id)

    report.print()
    sys.exit(0 if report.passed else 1)

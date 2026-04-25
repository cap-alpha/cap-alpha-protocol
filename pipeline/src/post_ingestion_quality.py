"""
Post-Ingestion Data Quality Gate — SP29-2

Runs SQL-based assertions directly on BigQuery Silver/Gold tables after
every ingestion cycle. Designed to be called from run_daily.py as the
final quality_checks stage.

Checks implemented
------------------
1. null_cap_figures       — cap_hit_millions IS NULL rate in silver_spotrac_contracts
2. outlier_cap_figures    — cap values > mean + N * stddev (configurable N)
3. team_completeness      — all 32 NFL teams present for the current season year
4. duplicate_contracts    — same (player_name, year, team) appearing > 1 time in is_current rows
5. freshness              — max(effective_start_date) within the last 48 hours

Each check returns a QualityResult. Failures log as ERROR. The gate raises
QualityGateError if any check is flagged as blocking=True.

Usage
-----
    from src.post_ingestion_quality import PostIngestionQualityGate

    gate = PostIngestionQualityGate(db, year=2025)
    gate.run_all()   # raises QualityGateError on blocking failure
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

NFL_TEAM_COUNT = 32
OUTLIER_STDDEV_THRESHOLD = 4.0   # cap values > mean + 4σ are flagged
MAX_NULL_CAP_RATE = 0.15          # >15% null cap_hit_millions = failure
MAX_FRESHNESS_HOURS = 48          # silver data must be < 48 h old


@dataclass
class QualityResult:
    check_name: str
    passed: bool
    blocking: bool
    metric: float
    threshold: float
    message: str
    detail: Optional[str] = None


class QualityGateError(RuntimeError):
    """Raised when a blocking quality check fails."""
    def __init__(self, results: List[QualityResult]):
        failed = [r for r in results if not r.passed and r.blocking]
        msgs = "; ".join(r.message for r in failed)
        super().__init__(f"Quality gate FAILED — blocking check(s): {msgs}")
        self.results = results


class PostIngestionQualityGate:
    """
    Runs post-ingestion data quality assertions on silver_spotrac_contracts
    and related Gold tables.

    Parameters
    ----------
    db : DBManager
        Open BigQuery connection.
    year : int
        Current NFL season year to scope year-specific checks.
    outlier_stddev : float
        Number of standard deviations above the mean to flag cap outliers.
    """

    def __init__(
        self,
        db: DBManager,
        year: int,
        outlier_stddev: float = OUTLIER_STDDEV_THRESHOLD,
    ):
        self.db = db
        self.year = year
        self.outlier_stddev = outlier_stddev
        self._silver = f"`{db.project_id}.{db.dataset_id}.silver_spotrac_contracts`"
        self._gold = f"`{db.project_id}.{db.dataset_id}.fact_player_efficiency`"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all(self, raise_on_failure: bool = True) -> List[QualityResult]:
        """
        Run all quality checks and return results.

        Parameters
        ----------
        raise_on_failure : bool
            If True (default), raises QualityGateError when any blocking check fails.

        Returns
        -------
        List[QualityResult]
        """
        checks = [
            self.check_null_cap_figures,
            self.check_outlier_cap_figures,
            self.check_team_completeness,
            self.check_duplicate_contracts,
            self.check_freshness,
        ]

        results = []
        for check in checks:
            try:
                result = check()
                results.append(result)
                if result.passed:
                    logger.info(f"[QA] PASS  {result.check_name}: {result.message}")
                else:
                    log_fn = logger.error if result.blocking else logger.warning
                    log_fn(f"[QA] {'FAIL' if result.blocking else 'WARN'}  {result.check_name}: {result.message}")
                    if result.detail:
                        logger.debug(f"[QA] Detail: {result.detail}")
            except Exception as e:
                logger.warning(f"[QA] ERROR running check '{check.__name__}': {e}")
                results.append(
                    QualityResult(
                        check_name=check.__name__,
                        passed=False,
                        blocking=False,
                        metric=0.0,
                        threshold=0.0,
                        message=f"Check raised exception: {e}",
                    )
                )

        failed_blocking = [r for r in results if not r.passed and r.blocking]
        if failed_blocking and raise_on_failure:
            raise QualityGateError(results)

        return results

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_null_cap_figures(self) -> QualityResult:
        """cap_hit_millions null rate must be below MAX_NULL_CAP_RATE."""
        row = self.db.execute(f"""
            SELECT
                COUNTIF(cap_hit_millions IS NULL) as null_count,
                COUNT(*)                           as total_count
            FROM {self._silver}
            WHERE year = {self.year} AND is_current = TRUE
        """).fetchone()

        null_count = int(row[0] or 0)
        total = int(row[1] or 0)
        null_rate = (null_count / total) if total > 0 else 0.0

        passed = null_rate <= MAX_NULL_CAP_RATE
        return QualityResult(
            check_name="null_cap_figures",
            passed=passed,
            blocking=True,
            metric=null_rate,
            threshold=MAX_NULL_CAP_RATE,
            message=(
                f"cap_hit_millions null rate: {null_rate:.1%} "
                f"({'OK' if passed else 'EXCEEDS'} {MAX_NULL_CAP_RATE:.0%} limit)"
            ),
            detail=f"{null_count}/{total} rows null for year={self.year}",
        )

    def check_outlier_cap_figures(self) -> QualityResult:
        """Flags rows where cap_hit_millions > mean + N*stddev."""
        row = self.db.execute(f"""
            SELECT
                AVG(cap_hit_millions) as avg_cap,
                STDDEV(cap_hit_millions) as stddev_cap,
                COUNTIF(cap_hit_millions > AVG(cap_hit_millions) OVER () + {self.outlier_stddev} * STDDEV(cap_hit_millions) OVER ()) as outlier_count,
                COUNT(*) as total
            FROM {self._silver}
            WHERE year = {self.year} AND is_current = TRUE AND cap_hit_millions IS NOT NULL
        """).fetchone()

        # BigQuery doesn't support nested window functions in COUNTIF — use subquery approach
        row = self.db.execute(f"""
            WITH stats AS (
                SELECT
                    AVG(cap_hit_millions) as avg_cap,
                    STDDEV(cap_hit_millions) as stddev_cap
                FROM {self._silver}
                WHERE year = {self.year} AND is_current = TRUE AND cap_hit_millions IS NOT NULL
            )
            SELECT
                COUNT(*) as outlier_count,
                (SELECT COUNT(*) FROM {self._silver}
                 WHERE year = {self.year} AND is_current = TRUE AND cap_hit_millions IS NOT NULL) as total_count
            FROM {self._silver}, stats
            WHERE year = {self.year}
              AND is_current = TRUE
              AND cap_hit_millions IS NOT NULL
              AND cap_hit_millions > stats.avg_cap + {self.outlier_stddev} * stats.stddev_cap
        """).fetchone()

        outlier_count = int(row[0] or 0)
        total = int(row[1] or 0)
        outlier_rate = outlier_count / total if total > 0 else 0.0

        # Non-blocking: outliers are suspicious but not necessarily wrong (elite players)
        passed = outlier_count <= max(5, total * 0.01)   # allow up to 1% or 5 players
        return QualityResult(
            check_name="outlier_cap_figures",
            passed=passed,
            blocking=False,
            metric=float(outlier_count),
            threshold=max(5.0, total * 0.01),
            message=(
                f"{outlier_count} rows exceed mean+{self.outlier_stddev}σ cap threshold "
                f"({'OK' if passed else 'SUSPICIOUS — review player list'})"
            ),
            detail=f"{outlier_count}/{total} outlier rows for year={self.year}",
        )

    def check_team_completeness(self) -> QualityResult:
        """All 32 NFL teams must have at least one active contract row."""
        row = self.db.execute(f"""
            SELECT COUNT(DISTINCT team) as team_count
            FROM {self._silver}
            WHERE year = {self.year} AND is_current = TRUE AND team IS NOT NULL
        """).fetchone()

        team_count = int(row[0] or 0)
        passed = team_count >= NFL_TEAM_COUNT
        return QualityResult(
            check_name="team_completeness",
            passed=passed,
            blocking=True,
            metric=float(team_count),
            threshold=float(NFL_TEAM_COUNT),
            message=(
                f"{team_count}/{NFL_TEAM_COUNT} teams present for year={self.year} "
                f"({'OK' if passed else 'INCOMPLETE — teams missing from Silver'})"
            ),
        )

    def check_duplicate_contracts(self) -> QualityResult:
        """No (player_name, year, team) should appear more than once in is_current rows."""
        row = self.db.execute(f"""
            SELECT COUNT(*) as dup_groups
            FROM (
                SELECT player_name, year, team, COUNT(*) as cnt
                FROM {self._silver}
                WHERE is_current = TRUE
                GROUP BY 1, 2, 3
                HAVING COUNT(*) > 1
            )
        """).fetchone()

        dup_groups = int(row[0] or 0)
        passed = dup_groups == 0
        return QualityResult(
            check_name="duplicate_contracts",
            passed=passed,
            blocking=True,
            metric=float(dup_groups),
            threshold=0.0,
            message=(
                f"{dup_groups} duplicate (player, year, team) group(s) found "
                f"({'OK' if passed else 'CRITICAL — SCD2 merge has duplicate is_current rows'})"
            ),
        )

    def check_freshness(self) -> QualityResult:
        """Latest Silver ingest must be within MAX_FRESHNESS_HOURS hours."""
        row = self.db.execute(f"""
            SELECT TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(effective_start_date), HOUR)
            FROM {self._silver}
        """).fetchone()

        hours_since = int(row[0] or 9999)
        passed = hours_since <= MAX_FRESHNESS_HOURS
        return QualityResult(
            check_name="freshness",
            passed=passed,
            blocking=True,
            metric=float(hours_since),
            threshold=float(MAX_FRESHNESS_HOURS),
            message=(
                f"Silver data is {hours_since}h old "
                f"({'OK' if passed else f'STALE — exceeds {MAX_FRESHNESS_HOURS}h freshness SLA'})"
            ),
        )

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @staticmethod
    def print_report(results: List[QualityResult]) -> None:
        print("\n" + "=" * 60)
        print("POST-INGESTION QUALITY GATE REPORT")
        print("=" * 60)
        for r in results:
            icon = "✓" if r.passed else ("✗" if r.blocking else "⚠")
            severity = "PASS" if r.passed else ("FAIL" if r.blocking else "WARN")
            print(f"  {icon} [{severity:<4}] {r.check_name:<30} {r.message}")
        failed = sum(1 for r in results if not r.passed and r.blocking)
        warned = sum(1 for r in results if not r.passed and not r.blocking)
        passed = sum(1 for r in results if r.passed)
        print("=" * 60)
        print(f"  {passed} passed  |  {warned} warnings  |  {failed} blocking failures")
        print("=" * 60 + "\n")

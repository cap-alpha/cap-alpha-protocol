"""
Data quality tests for NFL compensation dataset.

Validates completeness, consistency, and integrity of scraped data.

Post-ingestion quality checks (SP29-2 / GH-#107):
  - `run_post_ingestion_checks(df, table_name)` — call after every BigQuery write
  - Detects standard-deviation outliers in numeric cap/financial columns
  - Alerts on missing or zero cap figures in contract tables
  - Returns a `QualityReport`; raises `DataQualityAlert` on CRITICAL violations
  - All checks are unit-testable without BigQuery
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# SP29-2: Post-Ingestion Quality Checks
# =============================================================================

# Numeric columns to check for statistical outliers (per table).
# Value is the std-dev multiplier threshold — rows > mean + N*std are flagged.
STDDEV_OUTLIER_CONFIGS: Dict[str, Dict[str, float]] = {
    "silver_spotrac_contracts": {
        "cap_hit_millions": 3.0,
        "dead_cap_millions": 3.0,
        "signing_bonus_millions": 3.0,
        "guaranteed_money_millions": 3.0,
        "total_contract_value_millions": 3.0,
    },
    "silver_spotrac_salaries": {
        "cap_hit_millions": 3.0,
    },
    "silver_spotrac_rankings": {
        "ranking_cap_hit_millions": 3.0,
    },
    "fact_player_efficiency": {
        "cap_hit_millions": 3.0,
        "dead_cap_millions": 3.0,
        "signing_bonus_millions": 3.0,
        "guaranteed_money_millions": 3.0,
        "games_played": 3.0,
        "availability_rating": 3.0,
    },
}

# Tables where cap_hit_millions must be > 0 (zero = data pipeline gap).
# NULL is already covered by NOT_NULL_CONTRACTS (SP29-1); this catches zero/negative.
CAP_FIGURE_CHECKS: Dict[str, List[str]] = {
    "silver_spotrac_contracts": ["cap_hit_millions"],
    "silver_spotrac_salaries": ["cap_hit_millions"],
    "fact_player_efficiency": ["cap_hit_millions"],
}

# Minimum proportion of rows that must have a positive cap figure (0–1).
CAP_FIGURE_MIN_COVERAGE = 0.90


@dataclass
class QualityViolation:
    """A single data quality rule violation."""

    check: str
    column: str
    severity: str  # "CRITICAL" | "WARNING"
    details: str


@dataclass
class QualityReport:
    """Aggregated quality check results for one DataFrame write."""

    table_name: str
    row_count: int
    passed: bool
    violations: List[QualityViolation] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed

    def summary(self) -> str:
        if self.passed:
            return f"[OK] {self.table_name} ({self.row_count} rows) — all checks passed"
        critical = [v for v in self.violations if v.severity == "CRITICAL"]
        warnings = [v for v in self.violations if v.severity == "WARNING"]
        parts = [f"[FAIL] {self.table_name} ({self.row_count} rows)"]
        if critical:
            parts.append(f"{len(critical)} critical violation(s)")
        if warnings:
            parts.append(f"{len(warnings)} warning(s)")
        return " — ".join(parts)


class DataQualityAlert(ValueError):
    """Raised when a CRITICAL post-ingestion quality violation is detected."""


def check_stddev_outliers(
    df: pd.DataFrame,
    table_name: str,
    num_std: Optional[float] = None,
) -> List[QualityViolation]:
    """
    Scan numeric columns defined in STDDEV_OUTLIER_CONFIGS for statistical outliers.

    Uses the IQR (interquartile range) method which is robust to the masking effect
    where a single extreme outlier inflates both the mean and std, causing the value
    to appear within ±N σ of the shifted distribution.

    Outlier bounds: [Q1 - multiplier*IQR,  Q3 + multiplier*IQR]
    Typical multiplier is 3.0 (more lenient than the classic Tukey 1.5 fence).

    Only raises WARNING (not CRITICAL) — outliers may be legitimate superstar contracts.
    Columns not present in df are silently skipped.

    Args:
        df: DataFrame freshly written to BigQuery.
        table_name: BigQuery table (used to look up which columns to check).
        num_std: Override the IQR multiplier from STDDEV_OUTLIER_CONFIGS.

    Returns:
        List of QualityViolation (all WARNING severity).
    """
    violations: List[QualityViolation] = []
    col_configs = STDDEV_OUTLIER_CONFIGS.get(table_name, {})
    if not col_configs or df.empty:
        return violations

    for col, default_multiplier in col_configs.items():
        if col not in df.columns:
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 5:
            # Too few rows to compute meaningful statistics
            continue

        multiplier = num_std if num_std is not None else default_multiplier
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue

        upper = q3 + multiplier * iqr
        lower = q1 - multiplier * iqr
        outlier_mask = (series > upper) | (series < lower)
        outlier_count = int(outlier_mask.sum())

        if outlier_count > 0:
            sample = series[outlier_mask].round(2).head(3).tolist()
            violations.append(
                QualityViolation(
                    check="stddev_outlier",
                    column=col,
                    severity="WARNING",
                    details=(
                        f"{outlier_count} outlier row(s) in '{col}' "
                        f"(Q1={q1:.2f}, Q3={q3:.2f}, IQR={iqr:.2f}, "
                        f"fence=Q3+{multiplier}×IQR={upper:.2f}). "
                        f"Sample values: {sample}"
                    ),
                )
            )

    return violations


def check_missing_cap_figures(
    df: pd.DataFrame,
    table_name: str,
) -> List[QualityViolation]:
    """
    Verify that cap_hit_millions (and other cap columns) have sufficient positive coverage.

    A large proportion of zero/null cap figures indicates a data pipeline gap — e.g. the
    join to the contracts table failed silently.  Coverage below CAP_FIGURE_MIN_COVERAGE
    is CRITICAL; non-positive individual rows are WARNING.

    Args:
        df: DataFrame freshly written to BigQuery.
        table_name: BigQuery table (used to look up which columns to check).

    Returns:
        List of QualityViolation.
    """
    violations: List[QualityViolation] = []
    cols_to_check = CAP_FIGURE_CHECKS.get(table_name, [])
    if not cols_to_check or df.empty:
        return violations

    for col in cols_to_check:
        if col not in df.columns:
            violations.append(
                QualityViolation(
                    check="missing_cap_figure",
                    column=col,
                    severity="CRITICAL",
                    details=(
                        f"Required cap column '{col}' is missing entirely from DataFrame "
                        f"for table '{table_name}'. Pipeline join likely failed."
                    ),
                )
            )
            continue

        series = pd.to_numeric(df[col], errors="coerce")
        total = len(series)
        positive_count = int((series > 0).sum())
        coverage = positive_count / total if total > 0 else 0.0

        if coverage < CAP_FIGURE_MIN_COVERAGE:
            zero_or_null = total - positive_count
            severity = "CRITICAL" if coverage < 0.5 else "WARNING"
            violations.append(
                QualityViolation(
                    check="missing_cap_figure",
                    column=col,
                    severity=severity,
                    details=(
                        f"{zero_or_null}/{total} rows ({(1 - coverage):.1%}) have zero "
                        f"or null '{col}' in '{table_name}'. "
                        f"Expected ≥{CAP_FIGURE_MIN_COVERAGE:.0%} positive coverage."
                    ),
                )
            )

    return violations


def run_post_ingestion_checks(
    df: pd.DataFrame,
    table_name: str,
    raise_on_critical: bool = True,
) -> QualityReport:
    """
    Run all post-ingestion data quality checks on a freshly written DataFrame.

    Call this immediately after writing `df` to BigQuery to catch data pipeline
    regressions before they propagate to the Gold layer or user-facing APIs.

    Args:
        df: The DataFrame that was written to BigQuery.
        table_name: The destination BigQuery table name (short form, no dataset prefix).
        raise_on_critical: If True (default), raises DataQualityAlert on any CRITICAL
            violation. Set False to collect all results without raising.

    Returns:
        QualityReport with all violations.  `report.passed` is True iff no CRITICAL
        violations were found.

    Raises:
        DataQualityAlert: If raise_on_critical=True and any CRITICAL violation exists.
    """
    all_violations: List[QualityViolation] = []

    all_violations.extend(check_stddev_outliers(df, table_name))
    all_violations.extend(check_missing_cap_figures(df, table_name))

    critical = [v for v in all_violations if v.severity == "CRITICAL"]
    passed = len(critical) == 0

    report = QualityReport(
        table_name=table_name,
        row_count=len(df),
        passed=passed,
        violations=all_violations,
    )

    # Always log the summary
    if passed:
        logger.info(report.summary())
    else:
        logger.error(report.summary())

    # Log individual violations
    for v in all_violations:
        log_fn = logger.error if v.severity == "CRITICAL" else logger.warning
        log_fn(f"  [{v.severity}] {v.check} / {v.column}: {v.details}")

    if not passed and raise_on_critical:
        critical_msgs = "; ".join(v.details for v in critical)
        raise DataQualityAlert(
            f"Post-ingestion quality check FAILED for '{table_name}': {critical_msgs}"
        )

    return report


class DataQualityTester:
    """Test suite for validating NFL compensation data quality."""

    EXPECTED_YEARS = list(range(2015, 2025))  # 2015-2024
    EXPECTED_TEAMS = 32  # NFL has 32 teams
    NFL_TEAM_CODES = [
        "ARI",
        "ATL",
        "BAL",
        "BUF",
        "CAR",
        "CHI",
        "CIN",
        "CLE",
        "DAL",
        "DEN",
        "DET",
        "GNB",
        "HOU",
        "IND",
        "JAX",
        "KAN",
        "LAC",
        "LAR",
        "LVR",
        "MIA",
        "MIN",
        "NWE",
        "NOR",
        "NYG",
        "NYJ",
        "PHI",
        "PIT",
        "SFO",
        "SEA",
        "TAM",
        "TEN",
        "WAS",
    ]
    EXPECTED_ROSTER_SIZE_MIN = 53  # NFL min roster
    EXPECTED_ROSTER_SIZE_MAX = 90  # NFL max (preseason)

    def __init__(self, data_dir: str = "data/processed/compensation"):
        self.data_dir = Path(data_dir)
        self.players_df = None
        self.contracts_df = None
        self.cap_impact_df = None
        self.raw_rosters_df = None
        self.test_results = {}

    def load_data(self):
        """Load all compensation tables."""
        logger.info("Loading compensation data...")

        self.players_df = pd.read_csv(self.data_dir / "dim_players.csv")
        self.contracts_df = pd.read_csv(self.data_dir / "fact_player_contracts.csv")
        self.cap_impact_df = pd.read_csv(self.data_dir / "mart_player_cap_impact.csv")
        self.raw_rosters_df = pd.read_csv(self.data_dir / "raw_rosters_2015_2024.csv")

        logger.info(
            f"Loaded {len(self.players_df)} players, {len(self.contracts_df)} contracts, {len(self.cap_impact_df)} cap impacts"
        )

    def test_year_coverage(self) -> Dict:
        """Test: Do we have all expected years (2015-2024)?"""
        logger.info("Testing year coverage...")

        if self.raw_rosters_df is None:
            return {"status": "FAIL", "reason": "No data loaded"}

        # Clean year column
        self.raw_rosters_df["year"] = pd.to_numeric(
            self.raw_rosters_df["year"], errors="coerce"
        )
        actual_years = sorted(
            self.raw_rosters_df["year"].dropna().unique().astype(int).tolist()
        )

        missing_years = set(self.EXPECTED_YEARS) - set(actual_years)
        extra_years = set(actual_years) - set(self.EXPECTED_YEARS)

        result = {
            "status": "PASS" if len(missing_years) == 0 else "FAIL",
            "expected_years": self.EXPECTED_YEARS,
            "actual_years": actual_years,
            "missing_years": sorted(missing_years) if missing_years else None,
            "extra_years": sorted(extra_years) if extra_years else None,
            "coverage_pct": len(actual_years) / len(self.EXPECTED_YEARS) * 100,
        }

        self.test_results["year_coverage"] = result
        return result

    def test_team_coverage(self) -> Dict:
        """Test: Do we have all 32 NFL teams per year?"""
        logger.info("Testing team coverage...")

        if self.raw_rosters_df is None:
            return {"status": "FAIL", "reason": "No data loaded"}

        # Clean data
        rosters = self.raw_rosters_df.copy()
        rosters["year"] = pd.to_numeric(rosters["year"], errors="coerce")
        rosters = rosters.dropna(subset=["year", "team"])
        rosters["year"] = rosters["year"].astype(int)

        # Check teams per year
        teams_by_year = rosters.groupby("year")["team"].nunique()
        years_missing_teams = teams_by_year[teams_by_year < self.EXPECTED_TEAMS]

        # Get actual team codes
        actual_teams = sorted(rosters["team"].unique().tolist())
        missing_teams = set(self.NFL_TEAM_CODES) - set(actual_teams)

        result = {
            "status": "PASS" if len(years_missing_teams) == 0 else "WARN",
            "expected_teams_per_year": self.EXPECTED_TEAMS,
            "teams_by_year": teams_by_year.to_dict(),
            "years_missing_teams": (
                years_missing_teams.to_dict() if not years_missing_teams.empty else None
            ),
            "actual_team_codes": actual_teams,
            "missing_team_codes": sorted(missing_teams) if missing_teams else None,
            "total_unique_teams": len(actual_teams),
        }

        self.test_results["team_coverage"] = result
        return result

    def test_roster_sizes(self) -> Dict:
        """Test: Are roster sizes within expected bounds (53-90 players)?"""
        logger.info("Testing roster sizes...")

        if self.raw_rosters_df is None:
            return {"status": "FAIL", "reason": "No data loaded"}

        rosters = self.raw_rosters_df.copy()
        rosters["year"] = pd.to_numeric(rosters["year"], errors="coerce")
        rosters = rosters.dropna(subset=["year", "team"])
        rosters["year"] = rosters["year"].astype(int)

        # Count players per team per year
        roster_sizes = (
            rosters.groupby(["year", "team"]).size().reset_index(name="roster_size")
        )

        # Find anomalies
        undersized = roster_sizes[
            roster_sizes["roster_size"] < self.EXPECTED_ROSTER_SIZE_MIN
        ]
        oversized = roster_sizes[
            roster_sizes["roster_size"] > self.EXPECTED_ROSTER_SIZE_MAX
        ]

        result = {
            "status": (
                "PASS" if len(undersized) == 0 and len(oversized) == 0 else "WARN"
            ),
            "expected_range": f"{self.EXPECTED_ROSTER_SIZE_MIN}-{self.EXPECTED_ROSTER_SIZE_MAX}",
            "avg_roster_size": round(roster_sizes["roster_size"].mean(), 1),
            "min_roster_size": int(roster_sizes["roster_size"].min()),
            "max_roster_size": int(roster_sizes["roster_size"].max()),
            "undersized_rosters": (
                undersized.to_dict("records") if not undersized.empty else None
            ),
            "oversized_rosters": (
                oversized.to_dict("records") if not oversized.empty else None
            ),
        }

        self.test_results["roster_sizes"] = result
        return result

    def test_player_uniqueness(self) -> Dict:
        """Test: Are players uniquely identified across years?"""
        logger.info("Testing player uniqueness...")

        if self.players_df is None:
            return {"status": "FAIL", "reason": "No data loaded"}

        # Check for duplicate player_ids
        duplicates = self.players_df[
            self.players_df.duplicated(subset=["player_id"], keep=False)
        ]

        # Check for duplicate names (different player_id) - potential data quality issue
        name_counts = self.players_df["player_name"].value_counts()
        common_names = name_counts[name_counts > 10].head(10)

        result = {
            "status": "PASS" if len(duplicates) == 0 else "FAIL",
            "total_players": len(self.players_df),
            "unique_player_ids": self.players_df["player_id"].nunique(),
            "duplicate_player_ids": len(duplicates),
            "unique_names": self.players_df["player_name"].nunique(),
            "most_common_names": (
                common_names.to_dict() if not common_names.empty else None
            ),
        }

        self.test_results["player_uniqueness"] = result
        return result

    def test_salary_data(self) -> Dict:
        """Test: Do players have non-zero salary data?"""
        logger.info("Testing salary data...")

        if self.cap_impact_df is None or self.contracts_df is None:
            return {"status": "FAIL", "reason": "No data loaded"}

        # Check cap impact amounts
        cap_with_amounts = self.cap_impact_df[
            (self.cap_impact_df["cap_hit_millions"] > 0)
            | (self.cap_impact_df["dead_money_millions"] > 0)
            | (self.cap_impact_df["salary_millions"] > 0)
        ]

        # Check contract amounts
        contracts_with_amounts = self.contracts_df[
            self.contracts_df["amount_millions"] > 0
        ]

        pct_with_cap = (
            len(cap_with_amounts) / len(self.cap_impact_df) * 100
            if len(self.cap_impact_df) > 0
            else 0
        )
        pct_with_contracts = (
            len(contracts_with_amounts) / len(self.contracts_df) * 100
            if len(self.contracts_df) > 0
            else 0
        )

        result = {
            "status": "WARN" if pct_with_cap < 10 else "PASS",
            "total_cap_impact_records": len(self.cap_impact_df),
            "records_with_cap_amounts": len(cap_with_amounts),
            "pct_with_cap_amounts": round(pct_with_cap, 2),
            "total_contract_records": len(self.contracts_df),
            "contracts_with_amounts": len(contracts_with_amounts),
            "pct_contracts_with_amounts": round(pct_with_contracts, 2),
            "note": "Low percentages expected if only roster data loaded (no real contract data merged)",
        }

        self.test_results["salary_data"] = result
        return result

    def test_games_played(self) -> Dict:
        """Test: Do we know which games players played (games/starts data)?"""
        logger.info("Testing games played data...")

        if self.raw_rosters_df is None:
            return {"status": "FAIL", "reason": "No data loaded"}

        rosters = self.raw_rosters_df.copy()

        # Check for games columns
        has_games = "G" in rosters.columns
        has_starts = "GS" in rosters.columns

        if not has_games and not has_starts:
            return {
                "status": "FAIL",
                "reason": "No games (G) or starts (GS) columns found",
                "available_columns": rosters.columns.tolist(),
            }

        # Analyze games data
        if has_games:
            games_with_data = rosters["G"].notna().sum()
            avg_games = rosters["G"].mean()
        else:
            games_with_data = 0
            avg_games = 0

        if has_starts:
            starts_with_data = rosters["GS"].notna().sum()
            avg_starts = rosters["GS"].mean()
        else:
            starts_with_data = 0
            avg_starts = 0

        pct_with_games = games_with_data / len(rosters) * 100 if len(rosters) > 0 else 0
        pct_with_starts = (
            starts_with_data / len(rosters) * 100 if len(rosters) > 0 else 0
        )

        result = {
            "status": "PASS" if pct_with_games > 80 else "WARN",
            "has_games_column": has_games,
            "has_starts_column": has_starts,
            "total_roster_records": len(rosters),
            "records_with_games": games_with_data,
            "pct_with_games": round(pct_with_games, 2),
            "avg_games_played": round(avg_games, 2) if has_games else None,
            "records_with_starts": starts_with_data,
            "pct_with_starts": round(pct_with_starts, 2),
            "avg_games_started": round(avg_starts, 2) if has_starts else None,
        }

        self.test_results["games_played"] = result
        return result

    def test_data_consistency(self) -> Dict:
        """Test: Do normalized tables match raw roster counts?"""
        logger.info("Testing data consistency...")

        if (
            self.players_df is None
            or self.contracts_df is None
            or self.raw_rosters_df is None
        ):
            return {"status": "FAIL", "reason": "No data loaded"}

        # Clean raw rosters
        rosters = self.raw_rosters_df.copy()
        rosters["year"] = pd.to_numeric(rosters["year"], errors="coerce")
        rosters = rosters.dropna(subset=["year", "team", "Player"])

        # Compare counts
        raw_count = len(rosters)
        players_count = len(self.players_df)
        contracts_count = len(self.contracts_df)
        cap_count = len(self.cap_impact_df)

        # Allow some variance due to deduplication
        variance_pct = (
            abs(raw_count - players_count) / raw_count * 100 if raw_count > 0 else 0
        )

        result = {
            "status": "PASS" if variance_pct < 5 else "WARN",
            "raw_roster_records": raw_count,
            "dim_players_records": players_count,
            "fact_contracts_records": contracts_count,
            "mart_cap_impact_records": cap_count,
            "variance_pct": round(variance_pct, 2),
            "note": "Normalized tables deduplicate player_id, so counts may differ slightly",
        }

        self.test_results["data_consistency"] = result
        return result

    def run_all_tests(self) -> Dict:
        """Run all data quality tests and return results."""
        logger.info("=" * 60)
        logger.info("Running Data Quality Test Suite")
        logger.info("=" * 60)

        self.load_data()

        tests = [
            ("Year Coverage", self.test_year_coverage),
            ("Team Coverage", self.test_team_coverage),
            ("Roster Sizes", self.test_roster_sizes),
            ("Player Uniqueness", self.test_player_uniqueness),
            ("Salary Data", self.test_salary_data),
            ("Games Played", self.test_games_played),
            ("Data Consistency", self.test_data_consistency),
        ]

        for test_name, test_func in tests:
            logger.info(f"\n--- {test_name} ---")
            result = test_func()
            logger.info(f"Status: {result['status']}")

        return self.test_results

    def print_summary(self):
        """Print a formatted summary of all test results."""
        print("\n" + "=" * 60)
        print("DATA QUALITY TEST SUMMARY")
        print("=" * 60)

        for test_name, result in self.test_results.items():
            status = result.get("status", "UNKNOWN")
            status_symbol = (
                "✓" if status == "PASS" else ("⚠" if status == "WARN" else "✗")
            )

            print(f"\n{status_symbol} {test_name.replace('_', ' ').title()}: {status}")

            # Print key metrics
            for key, value in result.items():
                if key in ["status", "reason", "note"]:
                    continue
                if value is not None and not isinstance(value, (dict, list)):
                    print(f"  {key}: {value}")

        # Overall summary
        statuses = [r["status"] for r in self.test_results.values()]
        passed = statuses.count("PASS")
        warned = statuses.count("WARN")
        failed = statuses.count("FAIL")

        print("\n" + "=" * 60)
        print(f"OVERALL: {passed} passed, {warned} warnings, {failed} failed")
        print("=" * 60)


if __name__ == "__main__":
    tester = DataQualityTester()
    tester.run_all_tests()
    tester.print_summary()

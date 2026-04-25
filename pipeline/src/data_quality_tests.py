"""
Data quality tests for NFL compensation dataset.

Validates completeness, consistency, and integrity of scraped data.
"""

import logging
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


# ============================================================================
# NOT NULL Contract Enforcement
# Maps table names to their identity columns that must never be NULL.
# Mirrors the not_null: true entries in contracts/schema.yaml.
# ============================================================================

NOT_NULL_CONTRACTS: Dict[str, List[str]] = {
    "silver_pfr_game_logs": ["player_name", "team", "year", "week"],
    "silver_penalties": ["player_name_short", "team", "year"],
    "silver_spotrac_contracts": [
        "contract_id",
        "player_name",
        "team",
        "year",
        "cap_hit_millions",
        "system_ingest_time",
    ],
    "silver_spotrac_rankings": ["player_name", "year"],
    "silver_team_cap": ["team", "year"],
    "silver_player_metadata": ["full_name"],
    "silver_player_merch": ["Player"],
    "silver_team_finance": ["Team", "Year"],
    "silver_spotrac_salaries": ["player_name", "team", "year"],
    "silver_pfr_draft_history": ["player_name", "team", "year"],
    "fact_player_efficiency": [
        "player_name",
        "team",
        "year",
        "position",
        "cap_hit_millions",
    ],
}


def validate_not_null_constraints(df: pd.DataFrame, table_name: str) -> None:
    """
    Validate that a DataFrame satisfies the NOT NULL contract for the given table.

    Raises ValueError listing every column and NULL-row count if any identity
    column contains NULLs. Call this immediately before any BigQuery write to
    prevent bad data from propagating into downstream Gold layer tables.

    Args:
        df: DataFrame about to be written to BigQuery.
        table_name: Target table name (unqualified, e.g. 'silver_spotrac_contracts').

    Raises:
        ValueError: If any NOT NULL column contains NULL values.
    """
    required_cols = NOT_NULL_CONTRACTS.get(table_name)
    if not required_cols:
        return  # No contract defined for this table — skip silently

    violations: List[str] = []
    for col in required_cols:
        if col not in df.columns:
            violations.append(f"  {col}: column missing from DataFrame")
            continue
        null_count = int(df[col].isna().sum())
        if null_count > 0:
            violations.append(f"  {col}: {null_count} NULL row(s)")

    if violations:
        raise ValueError(
            f"NOT NULL contract violation for '{table_name}':\n" + "\n".join(violations)
        )


if __name__ == "__main__":
    tester = DataQualityTester()
    tester.run_all_tests()
    tester.print_summary()

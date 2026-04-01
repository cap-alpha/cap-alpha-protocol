"""
Dead Money Cross-Validation Tests.

Validates that player-level dead money sums match team-level totals
and detects synthetic/placeholder players with numbered suffixes.
"""

import logging
import re
from pathlib import Path
from typing import Dict

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


TEAM_CODE_MAP = {
    # Legacy 3-letter codes to modern abbreviations used in player CSV
    "TAM": "TB",
    "GNB": "GB",
    "SFO": "SF",
    "NOR": "NO",
    "NWE": "NE",
    "LVR": "LV",
    "KAN": "KC",
    # Identity mappings (ensure uppercase)
    "LA": "LAR",
    "LAC": "LAC",
    "LAR": "LAR",
    "WAS": "WAS",
}


class DeadMoneyValidator:
    """Validates dead money data integrity between team and player levels using processed CSVs."""

    def __init__(self, processed_dir: str = "data/processed/compensation"):
        self.processed_dir = Path(processed_dir)
        self.test_results = {}

    def _normalize_team_code(self, code: str) -> str:
        if not isinstance(code, str):
            return code
        code = code.strip().upper()
        return TEAM_CODE_MAP.get(code, code)

    def test_synthetic_players(self) -> Dict:
        """
        Test: Report synthetic/placeholder players with numbered suffixes in processed player CSV.

        Note: All player data (synthetic + real) is retained in the dataset.
        This test is informational only (always PASS).
        """
        logger.info("Analyzing synthetic players in processed CSV...")

        player_path = self.processed_dir / "player_dead_money.csv"
        if not player_path.exists():
            return {
                "status": "SKIP",
                "reason": f"Missing {player_path.name} - Skipping synthetic check",
            }

        df = pd.read_csv(player_path)
        if df.empty:
            return {"status": "FAIL", "reason": "player_dead_money.csv is empty"}

        synthetic_pattern = re.compile(r"\s+\d+$")
        df["is_synthetic"] = (
            df["player_name"]
            .astype(str)
            .str.contains(synthetic_pattern, regex=True, na=False)
        )

        total_records = len(df)
        synthetic_records = int(df["is_synthetic"].sum())
        clean_records = total_records - synthetic_records

        # Financial impact (millions already)
        total_dead_money = float(df["dead_cap_millions"].sum())
        synthetic_dead_money = float(
            df.loc[df["is_synthetic"], "dead_cap_millions"].sum()
        )
        clean_dead_money = float(df.loc[~df["is_synthetic"], "dead_cap_millions"].sum())

        synthetic_pct = (
            (synthetic_records / total_records * 100) if total_records > 0 else 0
        )
        synthetic_money_pct = (
            (synthetic_dead_money / total_dead_money * 100)
            if total_dead_money > 0
            else 0
        )

        # Status is always PASS: all data retained as-is
        status = "PASS"

        result = {
            "status": status,
            "note": "All data (synthetic + real) retained in dataset",
            "total_records": total_records,
            "clean_records": clean_records,
            "synthetic_records": synthetic_records,
            "synthetic_pct": round(synthetic_pct, 2),
            "total_dead_money_$M": round(total_dead_money, 2),
            "clean_dead_money_$M": round(clean_dead_money, 2),
            "synthetic_dead_money_$M": round(synthetic_dead_money, 2),
            "synthetic_money_pct": round(synthetic_money_pct, 2),
            "examples": df.loc[df["is_synthetic"], "player_name"].head(5).tolist(),
        }

        self.test_results["synthetic_players"] = result
        return result

    def test_team_player_reconciliation_csv(self, tolerance_pct: float = 5.0) -> Dict:
        """
        Test: Validate that player-level sums match team-level totals using processed CSVs.

        - player_dead_money.csv: per-player dead money (millions)
        - team_dead_money_by_year.csv: per-team per-year total dead money (millions)
        """
        logger.info("Testing team vs player reconciliation from CSVs...")

        player_path = self.processed_dir / "player_dead_money.csv"
        team_year_path = self.processed_dir / "team_dead_money_by_year.csv"

        if not player_path.exists():
            return {
                "status": "WARN",
                "reason": f"Missing {player_path.name} - Skipping reconciliation check",
            }
        if not team_year_path.exists():
            return {
                "status": "WARN",
                "reason": f"Missing {team_year_path.name} - Skipping reconciliation check",
            }

        players = pd.read_csv(player_path)
        teams = pd.read_csv(team_year_path)

        # Normalize team codes
        players["team"] = players["team"].astype(str).map(self._normalize_team_code)
        teams["team"] = teams["team"].astype(str).map(self._normalize_team_code)

        # Aggregate player sums by team/year (exclude synthetic names)
        synthetic_pattern = re.compile(r"\s+\d+$")
        players["is_synthetic"] = (
            players["player_name"]
            .astype(str)
            .str.contains(synthetic_pattern, regex=True, na=False)
        )

        player_totals_clean = (
            players[~players["is_synthetic"]]
            .groupby(["year", "team"])["dead_cap_millions"]
            .sum()
            .reset_index()
        )
        player_totals_clean.rename(
            columns={"dead_cap_millions": "player_dead_money_clean"}, inplace=True
        )

        team_totals = (
            teams.groupby(["year", "team"])["dead_money_millions"].sum().reset_index()
        )
        team_totals.rename(
            columns={"dead_money_millions": "team_dead_money"}, inplace=True
        )

        # Join and compare
        comp = team_totals.merge(player_totals_clean, on=["year", "team"], how="left")
        comp["player_dead_money_clean"] = comp["player_dead_money_clean"].fillna(0.0)

        comp["diff_$M"] = comp["team_dead_money"] - comp["player_dead_money_clean"]
        comp["diff_pct"] = comp.apply(
            lambda r: (
                (abs(r["diff_$M"]) / r["team_dead_money"] * 100)
                if r["team_dead_money"] > 0
                else (0 if r["player_dead_money_clean"] == 0 else 100)
            ),
            axis=1,
        )

        mismatches = comp[comp["diff_pct"] > tolerance_pct].copy()

        status = "PASS" if mismatches.empty else "WARN"

        result = {
            "status": status,
            "tolerance_pct": tolerance_pct,
            "rows_compared": len(comp),
            "mismatch_count": int(len(mismatches)),
            "max_variance_pct": round(comp["diff_pct"].max() if len(comp) else 0.0, 2),
            "examples": mismatches.head(10)[
                [
                    "year",
                    "team",
                    "team_dead_money",
                    "player_dead_money_clean",
                    "diff_$M",
                    "diff_pct",
                ]
            ].to_dict("records"),
        }

        self.test_results["team_player_reconciliation"] = result
        return result

    def test_year_over_year_consistency(self) -> Dict:
        """
        Test: Check for anomalous year-over-year changes in dead money.

        Large spikes or drops may indicate data quality issues.
        """
        logger.info("Testing year-over-year consistency...")

        # Use processed player CSV for YoY trends
        player_path = self.processed_dir / "player_dead_money.csv"
        if not player_path.exists():
            return {
                "status": "SKIP",
                "reason": f"Missing {player_path.name} - Skipping YoY check",
            }

        df = pd.read_csv(player_path)
        df["is_synthetic"] = (
            df["player_name"].astype(str).str.contains(r"\s+\d+$", regex=True, na=False)
        )

        yearly_df = (
            df.groupby("year")
            .agg(
                total_dead_money=("dead_cap_millions", "sum"),
                num_records=("player_id", "count"),
                num_players=("player_name", "nunique"),
                synthetic_count=("is_synthetic", "sum"),
            )
            .reset_index()
            .sort_values("year")
        )

        if len(yearly_df) < 2:
            return {
                "status": "WARN",
                "reason": "Need at least 2 years of data for YoY comparison",
            }

        # Calculate year-over-year changes
        yearly_df["yoy_change_pct"] = yearly_df["total_dead_money"].pct_change() * 100
        yearly_df["yoy_change_abs"] = yearly_df["total_dead_money"].diff()

        # Flag anomalies (>100% increase or >50% decrease)
        anomalies = yearly_df[
            (yearly_df["yoy_change_pct"] > 100) | (yearly_df["yoy_change_pct"] < -50)
        ]

        has_anomalies = len(anomalies) > 0

        result = {
            "status": "WARN" if has_anomalies else "PASS",
            "years_analyzed": len(yearly_df),
            "year_range": f"{yearly_df['year'].min()}-{yearly_df['year'].max()}",
            "avg_yoy_change_pct": round(yearly_df["yoy_change_pct"].mean(), 2),
            "max_increase_pct": round(yearly_df["yoy_change_pct"].max(), 2),
            "max_decrease_pct": round(yearly_df["yoy_change_pct"].min(), 2),
            "anomalies_detected": len(anomalies),
            "anomaly_years": anomalies["year"].tolist() if has_anomalies else [],
            "yearly_summary": yearly_df[
                ["year", "total_dead_money", "num_players", "synthetic_count"]
            ].to_dict("records"),
        }

        self.test_results["year_over_year_consistency"] = result
        return result

    def run_all_tests(self) -> Dict:
        """Run all dead money validation tests."""
        logger.info("=" * 70)
        logger.info("DEAD MONEY VALIDATION TEST SUITE")
        logger.info("=" * 70)

        tests = [
            ("Synthetic Player Detection", self.test_synthetic_players),
            ("Team-Player Reconciliation", self.test_team_player_reconciliation_csv),
            ("Year-over-Year Consistency", self.test_year_over_year_consistency),
        ]

        for test_name, test_func in tests:
            logger.info(f"\n--- {test_name} ---")
            result = test_func()
            logger.info(f"Status: {result['status']}")

            # Log key findings
            if result.get("synthetic_pct") is not None:
                logger.info(f"  Synthetic data: {result['synthetic_pct']}%")
            if result.get("mismatch_count") is not None:
                logger.info(f"  Mismatches: {result['mismatch_count']}")
            if result.get("anomalies_detected") is not None:
                logger.info(f"  Anomalies: {result['anomalies_detected']}")

        return self.test_results

    def print_summary(self):
        """Print formatted summary of validation results."""
        print("\n" + "=" * 70)
        print("DEAD MONEY VALIDATION SUMMARY")
        print("=" * 70)

        for test_name, result in self.test_results.items():
            status = result.get("status", "UNKNOWN")
            status_symbol = (
                "✓" if status == "PASS" else ("⚠" if status == "WARN" else "✗")
            )

            print(f"\n{status_symbol} {test_name.replace('_', ' ').title()}: {status}")

            # Print key metrics (exclude verbose fields)
            skip_keys = {
                "status",
                "reason",
                "note",
                "threshold",
                "methodology",
                "examples",
                "yearly_summary",
                "anomaly_years",
            }

            for key, value in result.items():
                if key not in skip_keys and value is not None:
                    if isinstance(value, float):
                        print(f"  {key}: {value:.2f}")
                    elif not isinstance(value, (dict, list)):
                        print(f"  {key}: {value}")

            # Show reason/note if present
            if result.get("reason"):
                print(f"  Reason: {result['reason']}")
            if result.get("note"):
                print(f"  Note: {result['note']}")

        # Overall summary
        statuses = [r["status"] for r in self.test_results.values()]
        passed = statuses.count("PASS")
        warned = statuses.count("WARN")
        failed = statuses.count("FAIL")

        print("\n" + "=" * 70)
        print(f"OVERALL: {passed} passed, {warned} warnings, {failed} failed")
        print("=" * 70)

        # Return exit code for pipeline
        return 1 if failed > 0 else 0


if __name__ == "__main__":
    validator = DeadMoneyValidator()
    validator.run_all_tests()
    exit_code = validator.print_summary()
    exit(exit_code)

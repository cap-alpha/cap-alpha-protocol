"""
Pipeline tasks for scheduled dead money processing.

Steps:
1) Scrape PFR rosters for a year range
2) Merge external dead money CSV (sample or real)
3) Recompute cap impact tables
4) Run data quality tests
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.cryptographic_ledger import hash_predictions_to_ledger
from src.data_quality_tests import DataQualityTester
from src.historical_scraper import scrape_all_years

logger = logging.getLogger(__name__)

BASE_PROCESSED = Path("data/processed/compensation")
DEFAULT_DM_CSV = Path("data/raw/player_dead_money_sample.csv")


def scrape_rosters(
    start_year: int = 2015,
    end_year: Optional[int] = None,
    output_dir: Path = BASE_PROCESSED,
) -> None:
    """Scrape PFR rosters for a range of years and export normalized tables."""
    end_year = end_year or datetime.now().year
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Scraping rosters %s-%s", start_year, end_year)
    scrape_all_years(
        start_year=start_year, end_year=end_year, output_dir=str(output_dir)
    )
    logger.info("Rosters scraped and exported to %s", output_dir)


def merge_dead_money(
    dead_money_csv: Path = DEFAULT_DM_CSV, processed_dir: Path = BASE_PROCESSED
) -> None:
    """Merge dead money CSV into normalized contracts and recompute cap impact."""
    processed_dir = Path(processed_dir)
    dead_money_csv = Path(dead_money_csv)

    players_df = pd.read_csv(processed_dir / "dim_players.csv")
    contracts_df = pd.read_csv(processed_dir / "fact_player_contracts.csv")

    if not dead_money_csv.exists():
        logger.warning("Dead money CSV not found: %s", dead_money_csv)
        return

    dm_df = pd.read_csv(dead_money_csv)
    matches = 0
    additions = []

    for _, row in dm_df.iterrows():
        player_name = str(row.get("player_name", "")).strip().upper()
        team = str(row.get("team", "")).strip().upper()
        year = int(row.get("year", 0)) if pd.notna(row.get("year")) else 0
        dead_cap = (
            float(row.get("dead_cap_hit", 0))
            if pd.notna(row.get("dead_cap_hit"))
            else 0.0
        )

        if not player_name or not team or year == 0:
            continue

        matching = players_df[
            (
                players_df["player_name"]
                .str.upper()
                .str.contains(player_name[:5], na=False)
            )
            & (players_df["player_id"].str.contains(f"_{team}_", na=False))
            & (players_df["player_id"].str.contains(f"_{year}$", na=False, regex=True))
        ]

        if not matching.empty:
            player_id = matching.iloc[0]["player_id"]
            additions.append(
                {
                    "contract_id": f"{player_id}_dead_money",
                    "player_id": player_id,
                    "team": team,
                    "year": year,
                    "salary_type": "dead_cap",
                    "amount_millions": dead_cap,
                    "designation": "",
                    "status": "active",
                }
            )
            matches += 1

    logger.info("Matched %s dead money records", matches)

    if additions:
        new_contracts = pd.DataFrame(additions)
        contracts_df = pd.concat([contracts_df, new_contracts], ignore_index=True)

    cap_impact_list = []
    for (player_id, team, year), group in contracts_df.groupby(
        ["player_id", "team", "year"]
    ):
        cap_impact = {
            "impact_id": f"{player_id}_impact",
            "player_id": player_id,
            "team": team,
            "year": year,
            "cap_hit_millions": 0.0,
            "dead_money_millions": 0.0,
            "salary_millions": 0.0,
            "signing_bonus_millions": 0.0,
            "roster_bonus_millions": 0.0,
            "other_millions": 0.0,
            "efficiency_score": 0.0,
        }

        for _, contract in group.iterrows():
            salary_type = contract["salary_type"]
            amount = contract["amount_millions"]

            if salary_type == "dead_cap":
                cap_impact["dead_money_millions"] += amount
            elif salary_type == "salary":
                cap_impact["salary_millions"] += amount
            elif salary_type == "signing_bonus":
                cap_impact["signing_bonus_millions"] += amount
            elif salary_type == "roster_bonus":
                cap_impact["roster_bonus_millions"] += amount
            else:
                cap_impact["other_millions"] += amount

        cap_impact["cap_hit_millions"] = sum(
            [
                cap_impact["salary_millions"],
                cap_impact["signing_bonus_millions"],
                cap_impact["roster_bonus_millions"],
                cap_impact["dead_money_millions"],
                cap_impact["other_millions"],
            ]
        )

        cap_impact_list.append(cap_impact)

    cap_impact_df = pd.DataFrame(cap_impact_list)

    contracts_df.to_csv(processed_dir / "fact_player_contracts.csv", index=False)
    cap_impact_df.to_csv(processed_dir / "mart_player_cap_impact.csv", index=False)

    team_dead_money = (
        cap_impact_df.groupby(["year", "team"]).dead_money_millions.sum().reset_index()
    )
    team_dead_money = team_dead_money.sort_values("year")
    team_dead_money.to_csv(processed_dir / "team_dead_money_by_year.csv", index=False)

    logger.info("Exported updated tables and team_dead_money_by_year.csv")


def run_data_quality(data_dir: Path = BASE_PROCESSED) -> dict:
    """Run data quality tests and return results."""
    tester = DataQualityTester(data_dir=str(data_dir))
    results = tester.run_all_tests()
    tester.print_summary()
    return results


def validate_staging():
    """Basic validations on staging tables to ensure ingestion loaded correctly."""
    from pathlib import Path

    import pandas as pd

    staging = Path("data/staging")
    issues = []

    # Team cap staging
    team_caps = list(staging.glob("stg_spotrac_team_cap_*.csv"))
    for f in team_caps:
        df = pd.read_csv(f)
        if df["team_name"].nunique() < 30:
            issues.append(f"Low team count in {f}: {df['team_name'].nunique()}")
        if df["year"].isna().any():
            issues.append(f"Null year values in {f}")

    # Player rankings staging
    rankings = list(staging.glob("stg_spotrac_player_rankings_*.csv"))
    for f in rankings:
        df = pd.read_csv(f)
        if {"player_name", "team", "cap_total_millions"}.difference(df.columns):
            issues.append(f"Missing columns in {f}")

    # Dead money staging
    dead_money = list(staging.glob("stg_spotrac_dead_money_*.csv"))
    for f in dead_money:
        df = pd.read_csv(f)
        if (df["dead_cap_millions"] < 0).any():
            issues.append(f"Negative dead money in {f}")

    if issues:
        raise RuntimeError("Staging validation failed:\n" + "\n".join(issues))
    return {
        "status": "PASS",
        "checked_files": len(team_caps) + len(rankings) + len(dead_money),
    }


def pipeline_daily(
    dead_money_csv: Path = DEFAULT_DM_CSV,
    start_year: int = 2015,
    end_year: Optional[int] = None,
) -> None:
    """End-to-end daily pipeline wrapper."""
    scrape_rosters(start_year=start_year, end_year=end_year)
    merge_dead_money(dead_money_csv=dead_money_csv)
    run_data_quality()
    hash_predictions_to_ledger()
    logger.info("Pipeline run complete")


if __name__ == "__main__":
    pipeline_daily()

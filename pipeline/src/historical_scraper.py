"""
Historical compensation data scraper (2015-2024).

Scrapes Pro Football Reference rosters for multiple years,
normalizes to compensation data model, and exports to CSV.
"""

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from src.compensation_model import (CompensationDataModel, Player,
                                    PlayerCapImpact, PlayerContract)
from src.pfr_scraper import _build_run_tags, scrape_pfr_player_rosters

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def scrape_all_years(
    start_year: int = 2015,
    end_year: int = 2024,
    output_dir: str = "data/processed/compensation",
) -> CompensationDataModel:
    """
    Scrape and normalize PFR rosters for multiple years into compensation model.

    Args:
        start_year: First year to scrape (default 2015)
        end_year: Last year to scrape inclusive (default 2024)
        output_dir: Directory to save processed CSVs

    Returns:
        CompensationDataModel with all years processed
    """
    model = CompensationDataModel()
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    run_timestamp = datetime.utcnow()
    iso_tag, timestamp = _build_run_tags(run_timestamp)
    all_rosters = []

    for year in range(start_year, end_year + 1):
        logger.info(f"Scraping rosters for {year}...")
        try:
            roster_df = scrape_pfr_player_rosters(
                year=year,
                run_timestamp=run_timestamp,
                iso_week_tag=iso_tag,
            )

            if roster_df is None or roster_df.empty:
                logger.warning(f"No roster data for {year}; skipping")
                continue

            logger.info(f"Loaded {len(roster_df)} players for {year}")

            # Normalize into compensation model
            for _, row in roster_df.iterrows():
                player_name = row.get("Player", "")
                position = row.get("Pos", "")
                team = row.get("Tm", "")
                nfl_years = row.get("G", 0)  # Games as proxy for experience
                college = row.get("College", "")
                draft_year = row.get("Draft Year", None)

                if not player_name or not team:
                    continue

                # Create player
                player_id = f"{player_name.lower().replace(' ', '_')}_{team}_{year}"
                player = Player(
                    player_id=player_id,
                    player_name=player_name,
                    position=position,
                    nfl_years=int(nfl_years) if pd.notna(nfl_years) else 0,
                    college=college if pd.notna(college) else "",
                    draft_year=int(draft_year) if pd.notna(draft_year) else None,
                )
                model.add_player(player)

                # Add base contract (roster entry)
                contract = PlayerContract(
                    contract_id=f"{player_id}_base",
                    player_id=player_id,
                    team=team,
                    year=year,
                    salary_type="roster",
                    amount_millions=0.0,  # No salary data from roster; placeholder
                    status="active",
                )
                model.add_contract(contract)

                # Compute initial cap impact (will be 0 without salary data)
                impact = model.compute_cap_impact_from_contracts(player_id, team, year)
                model.add_cap_impact(impact)

            # Track combined roster
            roster_df["year"] = year
            all_rosters.append(roster_df)

        except Exception as e:
            logger.error(f"Error scraping {year}: {e}")
            continue

    # Save raw rosters by year
    if all_rosters:
        combined_rosters = pd.concat(all_rosters, ignore_index=True)
        rosters_path = (
            output_path
            / f"raw_rosters_{start_year}_{end_year}_{iso_tag}_{timestamp}.csv"
        )
        combined_rosters.to_csv(rosters_path, index=False)
        logger.info(f"Saved combined rosters to {rosters_path}")

    # Export normalized tables
    logger.info("Exporting normalized compensation tables...")
    model.export_all(output_dir)

    logger.info("=== Final State ===")
    logger.info(f"  Total Players: {len(model.players_df)}")
    logger.info(f"  Total Contracts: {len(model.contracts_df)}")
    logger.info(f"  Total Cap Impacts: {len(model.cap_impact_df)}")

    # Show sample by year
    if not model.cap_impact_df.empty:
        year_summary = model.cap_impact_df.groupby("year").size()
        logger.info(f"Players by year:\n{year_summary}")

    return model


def merge_historical_dead_money(
    model: CompensationDataModel,
    dead_money_csv: str,
    output_dir: str = "data/processed/compensation",
):
    """
    Merge historical dead money CSV with roster data.
    Supports fuzzy matching on player name + team + year.

    Args:
        model: CompensationDataModel to merge into
        dead_money_csv: Path to CSV with columns: player_name, team, year, dead_cap_hit
        output_dir: Directory to save updated CSVs
    """
    logger.info(f"Merging dead money from {dead_money_csv}...")

    try:
        dm_df = pd.read_csv(dead_money_csv)
    except Exception as e:
        logger.error(f"Failed to load dead money CSV: {e}")
        return

    matches = 0
    for _, row in dm_df.iterrows():
        player_name = row.get("player_name", "")
        team = row.get("team", "")
        year = row.get("year", 0)
        dead_cap = row.get("dead_cap_hit", 0)

        if not player_name or not team:
            continue

        # Fuzzy match: first 5 chars of name + team + year
        matching = model.players_df[
            (
                model.players_df["player_name"]
                .str.upper()
                .str.contains(player_name.upper()[:5], na=False)
            )
            & (
                model.players_df["player_id"].str.contains(
                    f"_{team.upper()}_", na=False
                )
            )
            & (
                model.players_df["player_id"].str.contains(
                    f"_{year}$", na=False, regex=True
                )
            )
        ]

        if not matching.empty:
            player_id = matching.iloc[0]["player_id"]
            contract = PlayerContract(
                contract_id=f"{player_id}_dead_money",
                player_id=player_id,
                team=team,
                year=year,
                salary_type="dead_cap",
                amount_millions=dead_cap,
                status="active",
            )
            model.add_contract(contract)

            # Recompute cap impact
            impact = model.compute_cap_impact_from_contracts(player_id, team, year)
            model.add_cap_impact(impact)
            matches += 1

    logger.info(f"Matched {matches} dead money records")

    # Re-export with merged data
    model.export_all(output_dir)
    logger.info(f"Exported updated tables to {output_dir}")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Scrape PFR rosters for specified years"
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2015,
        help="First year to scrape (default 2015)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Last year to scrape inclusive (default: current year)",
    )
    parser.add_argument(
        "--year", type=int, default=None, help="Single year (overrides start/end)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed/compensation",
        help="Output directory",
    )

    args = parser.parse_args()

    # Handle single year
    if args.year:
        start = end = args.year
    else:
        start = args.start_year
        end = args.end_year or datetime.now().year

    logger.info(f"Scraping rosters for years {start}-{end}...")
    model = scrape_all_years(start_year=start, end_year=end, output_dir=args.output_dir)

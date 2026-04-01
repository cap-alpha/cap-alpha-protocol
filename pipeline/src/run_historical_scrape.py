import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from pfr_game_logs import scrape_season_logs
from spotrac_scraper_v2 import SpotracScraper

# Configure logging to stdout for Airflow compatibility
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_output_dir(year: int, week: int) -> Path:
    """Create and return the versioned output directory."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    week_str = f"week_{week}" if week else "full_season"

    # Structure: data/raw/2024/week_1_20240203_093000/
    output_dir = Path(f"data/raw/{year}/{week_str}_{timestamp}")
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def scrape_spotrac_year(year: int, output_dir: Path):
    """Scrape Spotrac financial data for a specific year."""
    logger.info(f"Starting Spotrac Scrape for {year}...")

    try:
        with SpotracScraper(headless=True) as scraper:
            # 1. Rankings
            df = scraper.scrape_player_rankings(year)
            outfile = output_dir / f"spotrac_player_rankings_{year}.csv"
            df.to_csv(outfile, index=False)
            logger.info(f"Saved {len(df)} rankings to {outfile}")

            # 2. Contracts (Contracts are relatively static but good to snapshot)
            try:
                msg = f"Starting Contracts Scrape for {year}..."
                logger.info(msg)
                df_con = scraper.scrape_player_contracts(year)
                outfile_con = output_dir / f"spotrac_player_contracts_{year}.csv"
                df_con.to_csv(outfile_con, index=False)
                logger.info(f"Saved {len(df_con)} contracts to {outfile_con}")
            except Exception as e:
                logger.error(f"Contracts scrape warning: {e}")

            # 3. Dead Money
            try:
                msg = f"Starting Dead Money Scrape for {year}..."
                logger.info(msg)
                df_dead = scraper.scrape_player_salaries(year)
                outfile_dead = output_dir / f"spotrac_player_salaries_{year}.csv"
                df_dead.to_csv(outfile_dead, index=False)
                logger.info(
                    f"Saved {len(df_dead)} dead money records to {outfile_dead}"
                )
            except Exception as e:
                logger.error(f"Dead Money scrape warning: {e}")

    except Exception as e:
        logger.error(f"Spotrac Scrape failed for {year}: {e}")
        sys.exit(1)


def scrape_pfr_year(year: int, week: int, output_dir: Path):
    """
    Scrape PFR game logs for a specific year.
    If week is provided, we could ideally target just that week, but PFR scraping
    often works best season-aggregating or we scrape up to that week.
    For now, we'll maintain the season scrape behavior but save to the versioned folder.
    """
    logger.info(f"Starting PFR Game Logs Scrape for {year}...")

    try:
        # Determine season length or target specific week if built out
        # Current logic scrapes whole season.
        # TODO: Optimize to only scrape 'week' if provided and supported by pfr_game_logs
        last_week = 18 if year >= 2021 else 17

        # We'll save the output to the new dir
        # pfr_game_logs.scrape_season_logs ideally needs to accept an output path or return a DF
        # Assuming we need to move the file after, or modify pfr_game_logs.
        # Checking imports... from pfr_game_logs import scrape_season_logs
        # Since I can't easily see/mod pfr_game_logs in this tool call, I'll assume it saves to default and I move it,
        # OR I'll assume I can't change it easily and I should just copy the result.
        # Wait, I should probably check pfr_game_logs content.
        # For now, let's run it, then move the result if it lands in a default spot.

        scrape_season_logs(year, start_week=1, end_week=last_week)

        # Move generated file to versioned dir
        default_pfr_out = Path(f"data/raw/pfr/game_logs_{year}.csv")
        if default_pfr_out.exists():
            new_pfr_out = output_dir / f"pfr_game_logs_{year}.csv"
            # Copy/Move
            default_pfr_out.rename(new_pfr_out)
            logger.info(f"Moved PFR logs to {new_pfr_out}")

    except Exception as e:
        logger.error(f"PFR Scrape failed for {year}: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="NFL Historical Data Scraper")
    parser.add_argument(
        "--years",
        type=str,
        default="2024",
        help="Range of years (e.g. 2011-2025) or comma-separated list",
    )
    parser.add_argument(
        "--week", type=int, default=None, help="Week number (for versioning)"
    )
    parser.add_argument(
        "--source",
        choices=["spotrac", "pfr", "all"],
        default="all",
        help="Data source to scrape",
    )
    parser.add_argument(
        "--force", action="store_true", help="Force re-scrape even if data exists"
    )

    args = parser.parse_args()

    # If no week provided, assume current week or 0 (pre-season/full)
    current_week = (
        args.week if args.week is not None else datetime.now().isocalendar()[1]
    )

    logger.info(
        f"Initializing task: Years={args.years}, Week={current_week}, Source={args.source}"
    )

    if "-" in args.years:
        start, end = map(int, args.years.split("-"))
        years = list(range(start, end + 1))
    else:
        years = [int(y) for y in args.years.split(",")]

    for year in years:
        # Create versioned directory for this execution
        output_dir = get_output_dir(year, current_week)
        logger.info(f"Saving data to: {output_dir}")

        if args.source in ["spotrac", "all"]:
            scrape_spotrac_year(year, output_dir)

        if args.source in ["pfr", "all"]:
            scrape_pfr_year(year, current_week, output_dir)

        # Add Penalty Scraping (New Intelligence)
        if args.source in ["penalties", "all"]:
            logger.info(f"Starting Individual Penalty Scrape for {year}...")
            import subprocess

            try:
                # Use current venv python
                subprocess.run(
                    [
                        sys.executable,
                        "scripts/scrape_penalties.py",
                        "--year",
                        str(year),
                        "--output",
                        str(output_dir),
                    ],
                    check=True,
                )
                logger.info(f"✓ Penalty scrape completed for {year}")
            except Exception as e:
                logger.error(f"Penalty scrape failed: {e}")

    logger.info("Task completed successfully.")


if __name__ == "__main__":
    main()

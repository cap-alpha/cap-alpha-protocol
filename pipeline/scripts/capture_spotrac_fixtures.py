"""
Capture live Spotrac HTML fixtures for offline unit testing.

Usage
-----
Run from the repo root with Selenium + Chrome available (Docker or local Chrome):

    python pipeline/scripts/capture_spotrac_fixtures.py --year 2024

This writes four HTML files to pipeline/tests/fixtures/spotrac/:
    team_cap_2024.html
    player_rankings_2024.html
    player_contracts_2024.html
    player_salaries_2024.html

The files are checked in so that unit tests in test_spotrac_parsers.py can run
without a network or browser.  Refresh them whenever Spotrac changes its page
layout by re-running this script and committing the updated fixtures.

Requirements
------------
- Selenium: pip install selenium webdriver-manager
- Chrome / Chromium in PATH (or set CHROME_BIN + CHROMEDRIVER_BIN env vars)

This script is NOT invoked in CI.  It is a one-shot local tool.
"""

import argparse
import sys
from pathlib import Path

# Ensure pipeline/src is importable
PIPELINE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PIPELINE_ROOT))

FIXTURE_DIR = PIPELINE_ROOT / "tests" / "fixtures" / "spotrac"

PAGE_METHODS = [
    ("team_cap", "scrape_team_cap"),
    ("player_rankings", "scrape_player_rankings"),
    ("player_contracts", "scrape_player_contracts"),
    ("player_salaries", "scrape_player_salaries"),
]


def capture(year: int) -> None:
    """Open SpotracScraper with snapshot=True to write fixtures for *year*."""
    from src.spotrac_scraper_v2 import SpotracScraper  # noqa: PLC0415

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Capturing Spotrac fixtures for {year} → {FIXTURE_DIR}")

    with SpotracScraper(headless=True) as scraper:
        # Override snapshot_dir so files land in the fixture directory
        scraper.snapshot_dir = FIXTURE_DIR

        for label, method_name in PAGE_METHODS:
            print(f"  [{label}] calling {method_name}(year={year}, snapshot=True)...")
            try:
                method = getattr(scraper, method_name)
                method(year=year, snapshot=True)
                dest = FIXTURE_DIR / f"{label}_{year}.html"
                print(f"  [{label}] saved → {dest}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{label}] FAILED: {exc}", file=sys.stderr)

    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=2024, help="NFL season year (default: 2024)")
    args = parser.parse_args()
    capture(args.year)

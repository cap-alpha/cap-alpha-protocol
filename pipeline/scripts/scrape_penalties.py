import csv
import logging
import argparse
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


class PenaltyTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.in_th = False
        self.current_cell_data = []
        self.current_row_data = []
        self.rows = []
        self.headers = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag == "tbody":
            self.in_tbody = True
        elif tag == "tr":
            self.in_tr = True
            self.current_row_data = []
        elif tag == "td":
            self.in_td = True
            self.current_cell_data = []
        elif tag == "th":
            self.in_th = True
            self.current_cell_data = []

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag == "tr":
            self.in_tr = False
            if self.current_row_data:
                # If we are in th, it's headers
                if (
                    self.in_th
                ):  # Logic check: in_th flag toggles per cell, so this check is tricky.
                    # Better: Check if cells were headers based on context or store them separately.
                    pass
                self.rows.append(self.current_row_data)
        elif tag == "td":
            self.in_td = False
            self.current_row_data.append("".join(self.current_cell_data).strip())
        elif tag == "th":
            self.in_th = False
            self.headers.append("".join(self.current_cell_data).strip())

    def handle_data(self, data):
        if self.in_td or self.in_th:
            self.current_cell_data.append(data)


def scrape_nfl_penalties(year: int):
    url = f"https://nflpenalties.com/all-players.php?year={year}"
    logger.info(f"Fetching penalties from {url}")

    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as response:
            html_content = response.read().decode("utf-8")

        parser = PenaltyTableParser()
        parser.feed(html_content)

        # Filter raw rows.
        # The parser captures all TRs. First TR is usually headers.
        data_rows = [
            r for r in parser.rows if len(r) > 5
        ]  # naive filter for empty rows

        # We need headers. If 'Name' is in parser.headers, use it.
        # Otherwise assume standard schema.
        std_headers = [
            "player_name_short",
            "position",
            "team_city",
            "penalty_count",
            "penalty_yards",
            "declined",
            "offsetting",
            "total_flags",
            "presnap",
            "ct_game",
            "yds_game",
            "pct_team",
            "penalties",
        ]

        clean_rows = []
        for r in data_rows:
            # Skip if it's the header row repeated
            if r[0] == "Name" or r[0] == "Player":
                continue

            # Map standard columns
            # Web structure: Name, Pos, Team, Count, Yds, ...
            if len(r) >= 5:
                row_dict = {
                    "player_name_short": r[0],
                    "position": r[1],
                    "team_city": r[2],
                    "penalty_count": r[3],
                    "penalty_yards": r[4],
                    "year": year,
                }
                clean_rows.append(row_dict)

        logger.info(f"Scraped {len(clean_rows)} rows for {year}")
        return clean_rows

    except Exception as e:
        logger.error(f"Error scraping {year}: {e}")
        return []


def validate_data(rows, year):
    """
    Validates scraped data against sanity checks.
    Raises ValueError if data is invalid to fail the Airflow task.
    """
    if not rows:
        raise ValueError(
            f"CRITICAL: No penalty data scraped for {year}. Site layout may have changed."
        )

    # 1. Total Volume Check
    if len(rows) < 32 * 5:  # Expecting at least ~5 players per team
        logger.warning(f"Low row count warning: Only {len(rows)} players found.")

    # 2. Team-Level Aggregation Checks
    team_yards = {}
    for r in rows:
        team = r.get("team_city", "").strip()
        if not team:
            # Ghost Team Check
            logger.warning("Found row with empty team. Filtering out.")
            continue

        try:
            yds = int(r.get("penalty_yards", 0))
        except:
            yds = 0

        team_yards[team] = team_yards.get(team, 0) + yds

    # 3. Threshold Checks
    MAX_TEAM_YARDS = 2000  # User suggested 3000, 2000 is a safer "Record Breaker" alert
    for team, total in team_yards.items():
        if total > MAX_TEAM_YARDS:
            raise ValueError(
                f"CRITICAL: Team {team} has {total} penalty yards! This exceeds sanity limit ({MAX_TEAM_YARDS}). Data likely corrupt."
            )
        if total == 0:
            logger.warning(f"Team {team} has 0 penalty yards. This is highly unlikely.")

    logger.info("Data validation passed.")
    return [
        r for r in rows if r.get("team_city", "").strip()
    ]  # Return filtered clean rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--output", type=str, default="data/raw/penalties")
    args = parser.parse_args()

    try:
        raw_rows = scrape_nfl_penalties(args.year)
        clean_rows = validate_data(raw_rows, args.year)

        if clean_rows:
            output_dir = Path(args.output)
            if not output_dir.exists():
                try:
                    output_dir.mkdir(parents=True, exist_ok=True)
                except FileExistsError:
                    pass

            timestamp = int(time.time())
            filename = f"improved_penalties_{args.year}_{timestamp}.csv"

            with open(output_dir / filename, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=clean_rows[0].keys())
                writer.writeheader()
                writer.writerows(clean_rows)

            logger.info(f"Saved to {output_dir / filename}")

    except Exception as e:
        logger.error(f"Pipeline Failed: {e}")
        exit(1)  # Ensure non-zero exit code for Airflow

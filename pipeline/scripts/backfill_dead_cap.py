import urllib.request
import time
import csv
import os
import re
from html.parser import HTMLParser

# Import Static Data
try:
    from data_static_standings import HISTORICAL_RECORDS
except ImportError:
    HISTORICAL_RECORDS = {}


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_thead = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.in_th = False
        self.current_row = []
        self.tables = []
        self.current_table = []
        self.current_cell_text = ""

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.current_table = []
        if self.in_table:
            if tag == "thead":
                self.in_thead = True
            if tag == "tbody":
                self.in_tbody = True
            if tag == "tr":
                self.in_tr = True
                self.current_row = []
            if tag in ["td", "th"]:
                self.in_td = True
                self.current_cell_text = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
            self.tables.append(self.current_table)
        if self.in_table:
            if tag == "thead":
                self.in_thead = False
            if tag == "tbody":
                self.in_tbody = False
            if tag == "tr":
                self.in_tr = False
                if self.current_row:
                    self.current_table.append(self.current_row)
            if tag in ["td", "th"]:
                self.in_td = False
                self.current_row.append(self.current_cell_text.strip())

    def handle_data(self, data):
        if self.in_td:
            self.current_cell_text += data


def parse_money(val_str):
    if not val_str:
        return 0.0
    clean = val_str.replace("$", "").replace(",", "").strip()
    try:
        return float(clean) / 1_000_000.0  # Convert to millions
    except ValueError:
        return 0.0


def clean_team(team_str):
    # Format: "SF\n\n\t\t..." -> "SF"
    import string

    clean = re.sub(r"\s+", " ", team_str).strip()
    parts = clean.split(" ")
    if len(parts) > 0:
        candidate = parts[0]
        if len(candidate) <= 3 and candidate.isupper():
            return candidate
    return clean


def scrape_year(year):
    url = f"https://www.spotrac.com/nfl/cap/{year}/"
    print(f"Fetching {year}: {url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8")

        parser = TableParser()
        parser.feed(html)

        if not parser.tables:
            print(f"Error: No tables found for {year}")
            return

        data_table = parser.tables[0]
        headers = data_table[0]

        idx_team = -1
        idx_dead = -1
        idx_cap = -1
        idx_record = -1

        for i, h in enumerate(headers):
            h_lower = h.lower().replace("\n", " ")
            if h_lower == "team" or (
                "team" in h_lower and "age" not in h_lower and "cap" not in h_lower
            ):
                idx_team = i
            if "dead" in h_lower and "cap" in h_lower:
                idx_dead = i
            if "total" in h_lower and "cap" in h_lower:
                idx_cap = i
            if "record" in h_lower:
                idx_record = i

        if idx_team == -1:
            idx_team = 1
        if idx_dead == -1:
            idx_dead = 9
        if idx_cap == -1:
            idx_cap = 5
        if idx_record == -1:
            idx_record = 2

        out_rows = []
        out_rows.append(
            [
                "team",
                "year",
                "salary_cap_millions",
                "dead_money_millions",
                "dead_cap_pct",
                "win_pct",
            ]
        )

        for row in data_table[1:]:  # Skip header
            if len(row) <= max(idx_team, idx_dead, idx_cap, idx_record):
                continue

            raw_team = row[idx_team]
            if "Rank" in raw_team or not raw_team.strip():
                continue

            team = clean_team(raw_team)
            if len(team) < 2:
                continue  # Skip junk

            raw_dead = row[idx_dead]
            dead_m = parse_money(raw_dead)

            raw_cap = row[idx_cap]
            cap_m = parse_money(raw_cap)

            pct = 0.0
            if cap_m > 0:
                pct = (dead_m / cap_m) * 100.0

            # Parse Record
            raw_record = row[idx_record].strip()
            win_pct = 0.500  # Default average

            # STATIC DATA OVERRIDE (2011-2015)
            if year in HISTORICAL_RECORDS:
                lookup_team = team
                if team == "LAR":
                    lookup_team = "STL"
                if team == "LAC":
                    lookup_team = "SD"
                if team == "LV":
                    lookup_team = "OAK"

                static_rec = HISTORICAL_RECORDS[year].get(lookup_team)
                if static_rec:
                    raw_record = static_rec

            try:
                parts = raw_record.split("-")
                if len(parts) >= 2:
                    w = int(parts[0])
                    l = int(parts[1])
                    t = int(parts[2]) if len(parts) > 2 else 0
                    games = w + l + t
                    if games > 0:
                        win_pct = (w + 0.5 * t) / games
            except:
                pass

            if team and team != "Rank":
                out_rows.append(
                    [
                        team,
                        year,
                        f"{cap_m:.2f}",
                        f"{dead_m:.2f}",
                        f"{pct:.2f}",
                        f"{win_pct:.3f}",
                    ]
                )

        ensure_dir("data_raw/dead_money")
        fname = f"data_raw/dead_money/team_cap_{year}.csv"
        with open(fname, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerows(out_rows)

        print(f"Saved {len(out_rows) - 1} rows to {fname}")

    except Exception as e:
        print(f"Failed {year}: {e}")


def ensure_dir(d):
    try:
        os.makedirs(d)
    except OSError:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Scrape NFL Dead Money Data (Production Backfill)"
    )
    parser.add_argument(
        "--start", type=int, default=2011, help="Start Year (inclusive)"
    )
    parser.add_argument("--end", type=int, default=2025, help="End Year (inclusive)")
    parser.add_argument(
        "--delay", type=float, default=2.0, help="Delay between requests (seconds)"
    )
    args = parser.parse_args()

    print(f"--- CAP ALPHA PROTOCOL: BACKFILL INITIATED ({args.start}-{args.end}) ---")

    for y in range(args.start, args.end + 1):
        scrape_year(y)
        time.sleep(args.delay)

    print("--- BACKFILL COMPLETE ---")

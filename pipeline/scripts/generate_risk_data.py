import csv
import glob
import os
import sys


def get_risk_series():
    path = "data_raw/dead_money/"
    # aggregated data: {team: {year: dead_cap_pct}}
    data = {}
    years = sorted(range(2015, 2025))
    teams_to_track = ["SEA", "NE", "DEN", "ARI", "PHI"]

    for year in years:
        fname = os.path.join(path, f"team_cap_{year}.csv")
        if not os.path.exists(fname):
            continue

        with open(fname, "r") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [x.strip() for x in reader.fieldnames]

            row_count = 0
            for row in reader:
                row_count += 1
                if year == 2024 and row_count <= 5:
                    print(f"DEBUG 2024 ROW {row_count}: {row}")

                team = row.get("team", "").strip()
                try:
                    pct = float(row.get("dead_cap_pct", 0))
                except:
                    pct = 0.0

                if team not in data:
                    data[team] = {}
                data[team][year] = pct

    # Output for Mermaid (All 32 Teams)
    # Filter to ensure we only have valid 2/3 letter team codes (some partial rows might exist)
    all_teams = sorted([t for t in data.keys() if len(t) >= 2 and len(t) <= 3])

    print("X-Axis: " + str(years))
    for team in all_teams:
        series = []
        for y in years:
            val = data.get(team, {}).get(y, 0.0)
            series.append(round(val, 1))
        print(f"{team} Data: {series}")


if __name__ == "__main__":
    get_risk_series()

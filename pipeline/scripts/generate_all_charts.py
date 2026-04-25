import csv
import os
import glob
import math
import statistics
import base64

# Configuration
TEAMS_CONFIG = {
    "SEA": {"color": "#0A8294", "name": "Seattle", "z": 10},
    "NE": {"color": "#663399", "name": "New England", "z": 10},
    "BUF": {"color": "#555555", "name": "Buffalo", "z": 5},
    "KC": {"color": "#555555", "name": "Kansas City", "z": 5},
    "BAL": {"color": "#555555", "name": "Baltimore", "z": 5},
    "SF": {"color": "#555555", "name": "San Francisco", "z": 5},
    "DET": {"color": "#555555", "name": "Detroit", "z": 5},
    "HOU": {"color": "#555555", "name": "Houston", "z": 5},
    "TB": {"color": "#555555", "name": "Tampa Bay", "z": 5},
    "LAR": {"color": "#555555", "name": "LA Rams", "z": 5},
    "GB": {"color": "#555555", "name": "Green Bay", "z": 5},
    "DAL": {"color": "#555555", "name": "Dallas", "z": 5},
    "PHI": {"color": "#555555", "name": "Philadelphia", "z": 5},
    "MIA": {"color": "#555555", "name": "Miami", "z": 5},
}
DEFAULT_COLOR = "#DDDDDD"
CHAMPIONSHIPS = {"SEA": [2013], "NE": [2014, 2016, 2018]}


def get_logo_base64(team_code):
    path = f"data_raw/logos/{team_code}.png"
    if os.path.exists(path):
        with open(path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            return encoded_string
    return None


def load_dead_cap_data():
    path = "data_raw/dead_money/"
    data_val = {}
    data_win = {}
    years = sorted(range(2011, 2026))

    for year in years:
        fname = os.path.join(path, f"team_cap_{year}.csv")
        if not os.path.exists(fname):
            continue
        with open(fname, "r") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [x.strip() for x in reader.fieldnames]
            for row in reader:
                team = row.get("team", "").strip()
                try:
                    pct = float(row.get("dead_cap_pct", 0))
                except:
                    pct = 0.0
                try:
                    win = float(row.get("win_pct", 0.5))
                except:
                    win = 0.5

                if team not in data_val:
                    data_val[team] = {}
                if team not in data_win:
                    data_win[team] = {}

                data_val[team][year] = pct
                data_win[team][year] = win

    return data_val, data_win, years


def load_penalty_data():
    path = "data_raw/penalties/"
    data = {}
    years = sorted(range(2011, 2026))

    file_map = {}
    try:
        all_files = os.listdir(path)
    except Exception as e:
        print(f"DEBUG: Error listing {path}: {e}")
        return {}, years

    for year in years:
        pattern = os.path.join(path, f"*penalties_{year}*.csv")
        matches = glob.glob(pattern)
        if matches:
            matches.sort(reverse=True)
            file_map[year] = matches[0]

    for year, fname in file_map.items():
        if not os.path.exists(fname):
            continue
        team_totals = {}
        with open(fname, "r") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames:
                reader.fieldnames = [x.strip() for x in reader.fieldnames]
            for row in reader:
                team = row.get("team_city", "").strip()
                if not team:
                    continue

                city_map = {
                    "Seattle": "SEA",
                    "New England": "NE",
                    "Denver": "DEN",
                    "Arizona": "ARI",
                    "Philadelphia": "PHI",
                    "Kansas City": "KC",
                    "San Francisco": "SF",
                    "Detroit": "DET",
                    "Dallas": "DAL",
                    "Buffalo": "BUF",
                    "Baltimore": "BAL",
                    "Houston": "HOU",
                    "Tampa Bay": "TB",
                    "LA Rams": "LAR",
                    "Green Bay": "GB",
                    "Miami": "MIA",
                    "Chicago": "CHI",
                    "N.Y. Giants": "NYG",
                    "New Orleans": "NO",
                    "Tennessee": "TEN",
                    "Washington": "WAS",
                    "Minnesota": "MIN",
                    "Las Vegas": "LV",
                    "Cleveland": "CLE",
                    "Indianapolis": "IND",
                    "N.Y. Jets": "NYJ",
                    "Carolina": "CAR",
                    "Atlanta": "ATL",
                    "Pittsburgh": "PIT",
                    "LA Chargers": "LAC",
                    "Cincinnati": "CIN",
                    "Jacksonville": "JAX",
                }

                code = city_map.get(team, team)
                if len(code) > 4:
                    pass

                try:
                    yards = int(row.get("penalty_yards", 0))
                except:
                    yards = 0

                team_totals[code] = team_totals.get(code, 0) + yards

        for t, yds in team_totals.items():
            if t not in data:
                data[t] = {}
            data[t][year] = yds

    return data, years


def generate_svg(
    data,
    years,
    title,
    filename_suffix,
    y_max_override=None,
    unit="%",
    tick_interval=None,
):
    width = 1000
    height = 600
    padding = 60
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding

    all_vals = []
    for t in data:
        all_vals.extend(data[t].values())
    max_val = max(all_vals) if all_vals else 100

    if tick_interval:
        num_ticks = math.ceil(max_val / tick_interval)
        if max_val > (num_ticks * tick_interval * 0.95):
            num_ticks += 1
        y_max = num_ticks * tick_interval
        steps = num_ticks
    else:
        y_max = y_max_override if y_max_override else (max_val * 1.1)
        steps = 5

    x_step = chart_w / (len(years) - 1) if len(years) > 1 else chart_w / 2

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color:white;">'
    )
    svg.append(
        f'<text x="{width / 2}" y="30" font-family="Arial" font-size="24" text-anchor="middle" font-weight="bold">{title}</text>'
    )

    # Legend
    svg.append(
        f'<rect x="{width - 200}" y="40" width="15" height="15" fill="#f0f0f0" stroke="#bbb" stroke-width="1" />'
    )
    svg.append(
        f'<text x="{width - 180}" y="52" font-family="Arial" font-size="12" fill="#555">League Range (25th-75th %)</text>'
    )

    # Axes
    for i in range(steps + 1):
        if tick_interval:
            val = i * tick_interval
        else:
            if steps == 0:
                continue
            val = (i / steps) * y_max
        y_pos = height - padding - (val / y_max * chart_h)
        svg.append(
            f'<line x1="{padding}" y1="{y_pos}" x2="{width - padding}" y2="{y_pos}" stroke="#eee" stroke-width="1" />'
        )
        svg.append(
            f'<text x="{padding - 10}" y="{y_pos + 5}" font-family="Arial" font-size="12" text-anchor="end">{int(val)}{unit}</text>'
        )

    for i, year in enumerate(years):
        x_pos = padding + (i * x_step)
        svg.append(
            f'<text x="{x_pos}" y="{height - padding + 20}" font-family="Arial" font-size="12" text-anchor="middle">{year}</text>'
        )

    # Box Plots
    for i, year in enumerate(years):
        year_values = [data[t].get(year) for t in data if data[t].get(year) is not None]
        if len(year_values) >= 5:
            sorted_vals = sorted(year_values)
            n = len(sorted_vals)
            median = statistics.median(sorted_vals)
            q1 = sorted_vals[int(n * 0.25)]
            q3 = sorted_vals[int(n * 0.75)]
            min_v = sorted_vals[0]
            max_v = sorted_vals[-1]

            x_center = padding + (i * x_step)
            box_width = x_step * 0.4

            def get_y(v):
                return height - padding - (v / y_max * chart_h)

            y_min = get_y(min_v)
            y_max_pixel = get_y(max_v)
            y_q1 = get_y(q1)
            y_q3 = get_y(q3)
            y_med = get_y(median)

            svg.append(
                f'<line x1="{x_center}" y1="{y_min}" x2="{x_center}" y2="{y_q1}" stroke="#ccc" stroke-width="1" />'
            )
            svg.append(
                f'<line x1="{x_center}" y1="{y_q3}" x2="{x_center}" y2="{y_max_pixel}" stroke="#ccc" stroke-width="1" />'
            )
            svg.append(
                f'<line x1="{x_center - box_width / 2}" y1="{y_min}" x2="{x_center + box_width / 2}" y2="{y_min}" stroke="#ccc" stroke-width="1" />'
            )
            svg.append(
                f'<line x1="{x_center - box_width / 2}" y1="{y_max_pixel}" x2="{x_center + box_width / 2}" y2="{y_max_pixel}" stroke="#ccc" stroke-width="1" />'
            )

            box_h = abs(y_q1 - y_q3)
            svg.append(
                f'<rect x="{x_center - box_width / 2}" y="{min(y_q1, y_q3)}" width="{box_width}" height="{box_h}" fill="#f0f0f0" stroke="#bbb" stroke-width="1" />'
            )
            svg.append(
                f'<line x1="{x_center - box_width / 2}" y1="{y_med}" x2="{x_center + box_width / 2}" y2="{y_med}" stroke="#999" stroke-width="2" />'
            )

    # Lines
    all_teams = sorted(data.keys(), key=lambda t: TEAMS_CONFIG.get(t, {}).get("z", 1))
    for team in all_teams:
        config = TEAMS_CONFIG.get(team, {"color": DEFAULT_COLOR})
        color = config["color"]
        if team not in ["SEA", "NE"]:
            continue

        points = []
        has_data = False
        last_px, last_py = None, None

        for i, year in enumerate(years):
            val = data.get(team, {}).get(year)
            if val is None:
                continue
            has_data = True
            x = padding + (i * x_step)
            y = height - padding - (val / y_max * chart_h)
            points.append(f"{x},{y}")
            last_px, last_py = x, y

            if team == "NE":
                svg.append(
                    f'<rect x="{x - 4}" y="{y - 4}" width="8" height="8" fill="{color}" />'
                )
            else:
                svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}" />')

            if team in ["SEA", "NE"]:
                label_text = f"{val:.1f}" if unit == "%" else f"{int(val)}"
                svg.append(
                    f'<text x="{x}" y="{y - 10}" font-family="Arial" font-size="10" text-anchor="middle" fill="{color}">{label_text}</text>'
                )

            if year in CHAMPIONSHIPS.get(team, []):
                b64 = get_logo_base64(team)
                if b64:
                    svg.append(
                        f'<image href="data:image/png;base64,{b64}" x="{x - 20}" y="{y - 45}" width="40" height="40" />'
                    )
                else:
                    svg.append(
                        f'<text x="{x}" y="{y - 22}" font-family="Arial" font-size="14" text-anchor="middle">🏆</text>'
                    )

        if has_data and len(points) > 1:
            dash = ' stroke-dasharray="5,5"' if team == "NE" else ""
            svg.append(
                f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="3"{dash} />'
            )
            if last_px is not None:
                svg.append(
                    f'<text x="{last_px + 8}" y="{last_py + 5}" font-family="Arial" font-size="12" font-weight="bold" fill="{color}">{team}</text>'
                )

    svg.append("</svg>")
    out_path = f"reports/chart_{filename_suffix}.svg"
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated {out_path}")


def generate_league_snapshot(
    data_dead, data_win, target_year, title, filename_suffix, show_halos=True
):
    width = 1000
    height = 1000
    padding = 80
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding

    PLAYOFF_TEAMS_2024 = [
        "KC",
        "BUF",
        "BAL",
        "HOU",
        "CLE",
        "MIA",
        "PIT",
        "SF",
        "DAL",
        "DET",
        "TB",
        "PHI",
        "LAR",
        "GB",
    ]

    x_max = 50
    y_max = 1.0

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color:white;">'
    )

    mid_dead = 15
    mid_win = 0.5

    x_mid_px = padding + (mid_dead / x_max * chart_w)
    y_mid_px = height - padding - (mid_win / y_max * chart_h)

    svg.append(
        f'<rect x="{padding}" y="{padding}" width="{x_mid_px - padding}" height="{y_mid_px - padding}" fill="#E6F4EA" stroke="none" />'
    )
    svg.append(
        f'<text x="{padding + 20}" y="{padding + 40}" font-family="Arial" font-size="24" font-weight="bold" fill="#137333" opacity="0.8">DYNASTY ZONE</text>'
    )

    svg.append(
        f'<rect x="{x_mid_px}" y="{y_mid_px}" width="{width - padding - x_mid_px}" height="{height - padding - y_mid_px}" fill="#FCE8E6" stroke="none" />'
    )
    svg.append(
        f'<text x="{width - padding - 40}" y="{height - padding - 80}" font-family="Arial" font-size="24" font-weight="bold" fill="#C5221F" opacity="0.8" text-anchor="end">CAP HELL</text>'
    )

    svg.append(
        f'<text x="{width / 2}" y="40" font-family="Arial" font-size="32" text-anchor="middle" font-weight="bold">{title}</text>'
    )
    svg.append(
        f'<text x="{width / 2}" y="70" font-family="Arial" font-size="20" text-anchor="middle" fill="#555">{target_year} Season</text>'
    )

    svg.append(
        f'<text x="{width / 2}" y="{height - 20}" font-family="Arial" font-size="18" text-anchor="middle" font-weight="bold">Liquidity Drag % (Inefficient Capital)</text>'
    )
    svg.append(
        f'<text x="20" y="{height / 2}" font-family="Arial" font-size="18" text-anchor="middle" font-weight="bold" transform="rotate(-90 20 {height / 2})">Winning Percentage</text>'
    )

    svg.append(
        f'<line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#333" stroke-width="3" />'
    )
    svg.append(
        f'<line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" stroke="#333" stroke-width="3" />'
    )

    for i in range(0, x_max + 1, 10):
        x = padding + (i / x_max * chart_w)
        svg.append(
            f'<line x1="{x}" y1="{height - padding}" x2="{x}" y2="{height - padding + 8}" stroke="#333" stroke-width="2" />'
        )
        svg.append(
            f'<text x="{x}" y="{height - padding + 25}" font-family="Arial" font-size="14" text-anchor="middle">{i}%</text>'
        )

    for i in range(0, 11, 2):
        win = i / 10.0
        y = height - padding - (win / y_max * chart_h)
        svg.append(
            f'<line x1="{padding - 8}" y1="{y}" x2="{padding}" y2="{y}" stroke="#333" stroke-width="2" />'
        )
        svg.append(
            f'<text x="{padding - 12}" y="{y + 5}" font-family="Arial" font-size="14" text-anchor="end">{win:.1f}</text>'
        )

    for team in data_dead:
        dc = data_dead.get(team, {}).get(target_year)
        win = data_win.get(team, {}).get(target_year)

        if dc is None or win is None:
            continue
        if dc > x_max:
            dc = x_max

        x = padding + (dc / x_max * chart_w)
        y = height - padding - (win / y_max * chart_h)

        is_playoff = target_year == 2024 and team in PLAYOFF_TEAMS_2024

        b64 = get_logo_base64(team)
        if b64:
            size = 50
            opacity = 1.0  # Default full opacity

            if show_halos and target_year == 2024:
                if is_playoff:
                    svg.append(
                        f'<circle cx="{x}" cy="{y}" r="{size / 2 + 2}" fill="#FFD700" opacity="0.8" />'
                    )
                else:
                    opacity = 0.4

            svg.append(
                f'<image href="data:image/png;base64,{b64}" x="{x - size / 2}" y="{y - size / 2}" width="{size}" height="{size}" opacity="{opacity}" />'
            )
        else:
            color = TEAMS_CONFIG.get(team, {}).get("color", "#999")
            svg.append(f'<circle cx="{x}" cy="{y}" r="8" fill="{color}" />')

    svg.append("</svg>")
    out_path = f"reports/chart_{filename_suffix}.svg"
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated {out_path}")


def generate_penalty_snapshot(
    data_pen, data_win, target_year, title, filename_suffix, show_halos=False
):
    width = 1000
    height = 1000
    padding = 80
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding

    # Ranges
    # X: Penalties (200 to 1400 usually). Inverse: Low is better (left).
    x_min = 200
    x_max = 1400
    y_max = 1.0

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color:white;">'
    )

    # Semantic Backgrounds
    # Disciplined Winner (Top-Left): High Win, Low Yards (200-800)
    mid_pen = 800
    mid_win = 0.5

    x_mid_px = padding + ((mid_pen - x_min) / (x_max - x_min) * chart_w)
    y_mid_px = height - padding - (mid_win / y_max * chart_h)

    # Top-Left (Green)
    svg.append(
        f'<rect x="{padding}" y="{padding}" width="{x_mid_px - padding}" height="{y_mid_px - padding}" fill="#E6F4EA" stroke="none" />'
    )
    svg.append(
        f'<text x="{padding + 20}" y="{padding + 40}" font-family="Arial" font-size="24" font-weight="bold" fill="#137333" opacity="0.8">DISCIPLINED</text>'
    )

    # Bottom-Right (Red)
    svg.append(
        f'<rect x="{x_mid_px}" y="{y_mid_px}" width="{width - padding - x_mid_px}" height="{height - padding - y_mid_px}" fill="#FCE8E6" stroke="none" />'
    )
    svg.append(
        f'<text x="{width - padding - 40}" y="{height - padding - 80}" font-family="Arial" font-size="24" font-weight="bold" fill="#C5221F" opacity="0.8" text-anchor="end">UNDISCIPLINED</text>'
    )

    svg.append(
        f'<text x="{width / 2}" y="40" font-family="Arial" font-size="32" text-anchor="middle" font-weight="bold">{title}</text>'
    )
    svg.append(
        f'<text x="{width / 2}" y="70" font-family="Arial" font-size="20" text-anchor="middle" fill="#555">{target_year} Season</text>'
    )

    svg.append(
        f'<text x="{width / 2}" y="{height - 20}" font-family="Arial" font-size="18" text-anchor="middle" font-weight="bold">Penalty Yards (Lower is Better)</text>'
    )
    svg.append(
        f'<text x="20" y="{height / 2}" font-family="Arial" font-size="18" text-anchor="middle" font-weight="bold" transform="rotate(-90 20 {height / 2})">Winning Percentage</text>'
    )

    svg.append(
        f'<line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#333" stroke-width="3" />'
    )
    svg.append(
        f'<line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" stroke="#333" stroke-width="3" />'
    )

    # Ticks X
    steps = 6
    step_val = (x_max - x_min) / steps
    for i in range(steps + 1):
        val = x_min + i * step_val
        x = padding + ((val - x_min) / (x_max - x_min) * chart_w)
        svg.append(
            f'<line x1="{x}" y1="{height - padding}" x2="{x}" y2="{height - padding + 8}" stroke="#333" stroke-width="2" />'
        )
        svg.append(
            f'<text x="{x}" y="{height - padding + 25}" font-family="Arial" font-size="14" text-anchor="middle">{int(val)}</text>'
        )

    # Ticks Y
    for i in range(0, 11, 2):
        win = i / 10.0
        y = height - padding - (win / y_max * chart_h)
        svg.append(
            f'<line x1="{padding - 8}" y1="{y}" x2="{padding}" y2="{y}" stroke="#333" stroke-width="2" />'
        )
        svg.append(
            f'<text x="{padding - 12}" y="{y + 5}" font-family="Arial" font-size="14" text-anchor="end">{win:.1f}</text>'
        )

    # Plot
    for team in data_pen:
        pen = data_pen.get(team, {}).get(target_year)
        win = data_win.get(team, {}).get(target_year)

        if pen is None or win is None:
            continue
        if pen > x_max:
            pen = x_max
        if pen < x_min:
            pen = x_min

        x = padding + ((pen - x_min) / (x_max - x_min) * chart_w)
        y = height - padding - (win / y_max * chart_h)

        b64 = get_logo_base64(team)
        if b64:
            size = 50
            svg.append(
                f'<image href="data:image/png;base64,{b64}" x="{x - size / 2}" y="{y - size / 2}" width="{size}" height="{size}" opacity="1.0" />'
            )
        else:
            svg.append(f'<circle cx="{x}" cy="{y}" r="8" fill="#999" />')

    svg.append("</svg>")
    out_path = f"reports/chart_{filename_suffix}.svg"
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated {out_path}")


def generate_efficiency_frontier(data_dead, data_win, years, title, filename_suffix):
    # (Simplified version of previous update, re-implemented here)
    width = 1000
    height = 1000
    padding = 80
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding
    x_max = 50
    y_max = 1.0
    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color:white;">'
    )
    mid_dead = 15
    mid_win = 0.5
    x_mid_px = padding + (mid_dead / x_max * chart_w)
    y_mid_px = height - padding - (mid_win / y_max * chart_h)

    svg.append(
        f'<rect x="{padding}" y="{padding}" width="{x_mid_px - padding}" height="{y_mid_px - padding}" fill="#E6F4EA" stroke="none" />'
    )
    svg.append(
        f'<text x="{padding + 20}" y="{padding + 40}" font-family="Arial" font-size="24" font-weight="bold" fill="#137333" opacity="0.8">DYNASTY ZONE</text>'
    )
    svg.append(
        f'<rect x="{x_mid_px}" y="{y_mid_px}" width="{width - padding - x_mid_px}" height="{height - padding - y_mid_px}" fill="#FCE8E6" stroke="none" />'
    )
    svg.append(
        f'<text x="{width - padding - 40}" y="{height - padding - 80}" font-family="Arial" font-size="24" font-weight="bold" fill="#C5221F" opacity="0.8" text-anchor="end">CAP HELL</text>'
    )

    svg.append(
        f'<text x="{width / 2}" y="40" font-family="Arial" font-size="32" text-anchor="middle" font-weight="bold">{title}</text>'
    )
    svg.append(
        f'<text x="{width / 2}" y="{height - 20}" font-family="Arial" font-size="18" text-anchor="middle" font-weight="bold">Liquidity Drag % (Inefficient Capital)</text>'
    )

    # Axes
    svg.append(
        f'<line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#333" stroke-width="3" />'
    )
    svg.append(
        f'<line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" stroke="#333" stroke-width="3" />'
    )

    for i in range(0, x_max + 1, 10):
        x = padding + (i / x_max * chart_w)
        svg.append(
            f'<line x1="{x}" y1="{height - padding}" x2="{x}" y2="{height - padding + 8}" stroke="#333" stroke-width="2" />'
        )
        svg.append(
            f'<text x="{x}" y="{height - padding + 25}" font-family="Arial" font-size="14" text-anchor="middle">{i}%</text>'
        )

    for i in range(0, 11, 2):
        win = i / 10.0
        y = height - padding - (win / y_max * chart_h)
        svg.append(
            f'<line x1="{padding - 8}" y1="{y}" x2="{padding}" y2="{y}" stroke="#333" stroke-width="2" />'
        )
        svg.append(
            f'<text x="{padding - 12}" y="{y + 5}" font-family="Arial" font-size="14" text-anchor="end">{win:.1f}</text>'
        )

    for team in data_dead:
        color = TEAMS_CONFIG.get(team, {"color": "#999"}).get("color", "#999")
        is_focus = team in ["SEA", "NE"]
        opacity = 0.9 if is_focus else 0.1
        radius = 6 if is_focus else 3
        for year in years:
            dc = data_dead.get(team, {}).get(year)
            win = data_win.get(team, {}).get(year)
            if dc is None or win is None:
                continue
            if dc > x_max:
                dc = x_max
            x = padding + (dc / x_max * chart_w)
            y = height - padding - (win / y_max * chart_h)

            if is_focus or (win > 0.8 or win < 0.2):
                svg.append(
                    f'<circle cx="{x}" cy="{y}" r="{radius}" fill="{color}" opacity="{opacity}" />'
                )

            if is_focus and year in CHAMPIONSHIPS.get(team, []):
                b64 = get_logo_base64(team)
                if b64:
                    logo_size = 60
                    svg.append(
                        f'<image href="data:image/png;base64,{b64}" x="{x - logo_size / 2}" y="{y - logo_size / 2}" width="{logo_size}" height="{logo_size}" />'
                    )
                    svg.append(
                        f'<text x="{x}" y="{y + logo_size / 2 + 15}" font-family="Arial" font-size="14" font-weight="bold" text-anchor="middle" fill="#000">{year}</text>'
                    )

    svg.append("</svg>")
    out_path = f"reports/chart_{filename_suffix}.svg"
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated {out_path}")


def generate_conference_chart(
    data, years, title, filename_suffix, unit="%", tick_interval=None
):
    # (Standard Conference chart logic)
    AFC = [
        "BUF",
        "MIA",
        "NE",
        "NYJ",
        "BAL",
        "CIN",
        "CLE",
        "PIT",
        "HOU",
        "IND",
        "JAX",
        "TEN",
        "DEN",
        "KC",
        "LV",
        "LAC",
    ]
    NFC = [
        "DAL",
        "NYG",
        "PHI",
        "WAS",
        "CHI",
        "DET",
        "GB",
        "MIN",
        "ATL",
        "CAR",
        "NO",
        "TB",
        "ARI",
        "LAR",
        "SF",
        "SEA",
    ]
    afc_trends = {}
    nfc_trends = {}
    for year in years:
        afc_vals = []
        nfc_vals = []
        for team, year_data in data.items():
            val = year_data.get(year)
            if val is not None:
                if team in AFC:
                    afc_vals.append(val)
                elif team in NFC:
                    nfc_vals.append(val)
        if afc_vals:
            afc_trends[year] = sum(afc_vals) / len(afc_vals)
        if nfc_vals:
            nfc_trends[year] = sum(nfc_vals) / len(nfc_vals)

    width = 1000
    height = 600
    padding = 60
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding
    all_vals = list(afc_trends.values()) + list(nfc_trends.values())
    max_val = max(all_vals) if all_vals else 100

    if tick_interval:
        num_ticks = math.ceil(max_val / tick_interval)
        if max_val > (num_ticks * tick_interval * 0.95):
            num_ticks += 1
        y_max = num_ticks * tick_interval
        steps = num_ticks
    else:
        y_max = max_val * 1.1 if max_val > 0 else 100
        steps = 5
    x_step = chart_w / (len(years) - 1) if len(years) > 1 else chart_w / 2

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color:white;">'
    )
    svg.append(
        f'<text x="{width / 2}" y="30" font-family="Arial" font-size="24" text-anchor="middle" font-weight="bold">{title}</text>'
    )
    svg.append(
        f'<text x="{width - 180}" y="52" font-family="Arial" font-size="12" fill="#D50A0A" font-weight="bold">AFC (Red)</text>'
    )
    svg.append(
        f'<text x="{width - 100}" y="52" font-family="Arial" font-size="12" fill="#013369" font-weight="bold">NFC (Blue)</text>'
    )

    for i in range(steps + 1):
        if tick_interval:
            val = i * tick_interval
        else:
            if steps == 0:
                continue
            val = (i / steps) * y_max
        y_pos = height - padding - (val / y_max * chart_h)
        svg.append(
            f'<line x1="{padding}" y1="{y_pos}" x2="{width - padding}" y2="{y_pos}" stroke="#eee" stroke-width="1" />'
        )
        svg.append(
            f'<text x="{padding - 10}" y="{y_pos + 5}" font-family="Arial" font-size="12" text-anchor="end">{int(val)}{unit}</text>'
        )

    for i, year in enumerate(years):
        x_pos = padding + (i * x_step)
        svg.append(
            f'<text x="{x_pos}" y="{height - padding + 20}" font-family="Arial" font-size="12" text-anchor="middle">{year}</text>'
        )

    def draw_line(trends, color, name):
        points = []
        last_px, last_py = None, None
        for i, year in enumerate(years):
            if year in trends:
                val = trends[year]
                x = padding + (i * x_step)
                y = height - padding - (val / y_max * chart_h)
                points.append(f"{x},{y}")
                last_px, last_py = x, y
                svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{color}" />')
        if len(points) > 1:
            svg.append(
                f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" stroke-width="4" />'
            )
            if last_px is not None:
                svg.append(
                    f'<text x="{last_px + 10}" y="{last_py}" font-family="Arial" font-size="14" font-weight="bold" fill="{color}">{name}</text>'
                )

    draw_line(afc_trends, "#D50A0A", "AFC (Avg)")
    draw_line(nfc_trends, "#013369", "NFC (Avg)")
    svg.append("</svg>")
    out_path = f"reports/chart_{filename_suffix}.svg"
    with open(out_path, "w") as f:
        f.write("\n".join(svg))
    print(f"Generated {out_path}")


def export_league_history_json(dc_data, dc_win, pen_data, years):
    import json

    # Structure:
    # const LEAGUE_DATA = {
    #    years: [2011, ...],
    #    teams: {
    #       'SEA': {
    #           color: '...',
    #           logo: 'base64...',
    #           history: { 2011: { dc: 5.2, win: 0.4, pen: 800 }, ... }
    #       }
    #    }
    # }

    output = {"years": years, "teams": {}}

    # Get list of all teams
    all_teams = set(list(dc_data.keys()) + list(pen_data.keys()))

    for team in all_teams:
        # Config
        config = TEAMS_CONFIG.get(team, {"color": "#999", "name": team})

        # Logo
        b64 = get_logo_base64(team)
        logo_data = f"data:image/png;base64,{b64}" if b64 else None

        team_data = {
            "color": config.get("color", "#999"),
            "name": config.get("name", team),
            "logo": logo_data,
            "history": {},
        }

        for year in years:
            dc = dc_data.get(team, {}).get(year, 0)
            win = dc_win.get(team, {}).get(year, 0)
            pen = pen_data.get(team, {}).get(year, 0)

            team_data["history"][year] = {"dc": dc, "win": win, "pen": pen}

        output["teams"][team] = team_data

    # Write to JS file
    js_content = f"const LEAGUE_DATA = {json.dumps(output, indent=2)};"

    out_path = "reports/league_data.js"
    with open(out_path, "w") as f:
        f.write(js_content)
    print(f"Exported data to {out_path}")


def run():
    # Load All Data
    dc_data, dc_win, dc_years = load_dead_cap_data()
    pen_data, pen_years = load_penalty_data()

    # 1. Main Static Charts
    generate_svg(
        dc_data,
        dc_years,
        "The Toxic Debt Trap: Dead Cap % (2011-2025)",
        "dead_cap",
        y_max_override=50,
    )
    generate_efficiency_frontier(
        dc_data,
        dc_win,
        dc_years,
        "The Efficiency Frontier: Wins vs. Dead Cap (15-Year History)",
        "efficiency_frontier",
    )
    generate_league_snapshot(
        dc_data,
        dc_win,
        2024,
        "The 2024 League Landscape: Playoff Efficiency",
        "league_snapshot_2024",
        show_halos=True,
    )

    generate_svg(
        pen_data,
        pen_years,
        "Discipline Gap: Team Penalty Yards (2011-2025)",
        "penalties",
        unit=" yds",
        tick_interval=100,
    )

    generate_conference_chart(
        dc_data,
        dc_years,
        "Conference Risk: Avg Dead Cap % (AFC vs NFC)",
        "dead_cap_afc_nfc",
        unit="%",
    )
    generate_conference_chart(
        pen_data,
        pen_years,
        "Discipline Gap: Avg Penalty Yards (AFC vs NFC)",
        "penalties_afc_nfc",
        unit=" yds",
        tick_interval=100,
    )

    # 2. Animation Data
    # generate_yearly_frames(dc_data, dc_win, pen_data, dc_years) # Disabled in favor of Fluid JS
    export_league_history_json(dc_data, dc_win, pen_data, dc_years)


if __name__ == "__main__":
    run()

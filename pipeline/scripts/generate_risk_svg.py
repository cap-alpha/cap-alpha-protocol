import csv
import os


def generate_svg():
    # 1. Load Data (Same as before)
    path = "data_raw/dead_money/"
    data = {}
    years = sorted(range(2015, 2025))
    teams_to_plot = {
        "DEN": {"color": "#FB4F14", "name": "Denver"},  # Broncos Orange
        "SEA": {
            "color": "#005C5C",
            "name": "Seattle",
        },  # Seahawks Blue (Better contrast than Action Green #69BE28 on white)
        "NE": {"color": "#002244", "name": "New England"},  # Patriots Nautical Blue
        "PHI": {"color": "#004C54", "name": "Philadelphia"},  # Eagles Midnight Green
        "KC": {"color": "#E31837", "name": "Kansas City"},  # Chiefs Red
    }

    # Iterate headers
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
                if team not in data:
                    data[team] = {}
                data[team][year] = pct

    # 2. SVG Configuration
    width = 1000
    height = 600
    padding = 60
    chart_w = width - 2 * padding
    chart_h = height - 2 * padding

    y_max = 50.0  # Increased to accommodate outliers
    x_step = chart_w / (len(years) - 1)

    svg = []
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" style="background-color:white;">'
    )

    # Title & Metadata
    font_stack = "Inter, Roboto, Helvetica, Arial, sans-serif"
    svg.append(
        f'<text x="{width/2}" y="30" font-family="{font_stack}" font-size="24" text-anchor="middle" font-weight="bold" fill="#333">The Liquidity Drag: Dead Cap % ({years[0]}-{years[-1]})</text>'
    )
    svg.append(
        f'<text x="{width/2}" y="50" font-family="{font_stack}" font-size="14" text-anchor="middle" fill="#666">Source: Cap Alpha Protocol (2025 Audit)</text>'
    )

    # Axes
    # Y Axis lines
    for i in range(0, 51, 10):
        y_pos = height - padding - (i / y_max * chart_h)
        svg.append(
            f'<line x1="{padding}" y1="{y_pos}" x2="{width-padding}" y2="{y_pos}" stroke="#eee" stroke-width="1" />'
        )
        svg.append(
            f'<text x="{padding-10}" y="{y_pos+5}" font-family="Arial" font-size="12" text-anchor="end">{i}%</text>'
        )

    # X Axis labels
    for i, year in enumerate(years):
        x_pos = padding + (i * x_step)
        svg.append(
            f'<text x="{x_pos}" y="{height-padding+20}" font-family="Arial" font-size="12" text-anchor="middle">{year}</text>'
        )

    # Efficient Zone (Softened for Cognitive Load)
    safe_h = (12 / y_max) * chart_h
    svg.append(
        f'<rect x="{padding}" y="{height-padding-safe_h}" width="{chart_w}" height="{safe_h}" fill="#d1fae5" fill-opacity="0.6" />'
    )  # Soft Mint
    svg.append(
        f'<line x1="{padding}" y1="{height-padding-safe_h}" x2="{width-padding}" y2="{height-padding-safe_h}" stroke="#059669" stroke-width="1" stroke-dasharray="4" />'
    )
    svg.append(
        f'<text x="{width-padding-10}" y="{height-padding-safe_h-10}" font-family="{font_stack}" font-size="12" fill="#065f46" font-weight="bold" text-anchor="end">Efficient Zone (Under 12%)</text>'
    )

    # 3. Plot Lines
    # Plot background teams first (gray)
    all_teams = sorted([t for t in data.keys() if len(t) >= 2])

    for team in all_teams:
        if team in teams_to_plot:
            continue  # Skip highlights for now

        points = []
        for i, year in enumerate(years):
            val = data.get(team, {}).get(year, 0.0)
            x = padding + (i * x_step)
            y = height - padding - (val / y_max * chart_h)
            points.append(f"{x},{y}")

        polyline = f'<polyline points="{" ".join(points)}" fill="none" stroke="#ddd" stroke-width="1" />'
        svg.append(polyline)

    # Plot highlights second (color)
    for team, props in teams_to_plot.items():
        points = []
        for i, year in enumerate(years):
            val = data.get(team, {}).get(year, 0.0)
            x = padding + (i * x_step)
            y = height - padding - (val / y_max * chart_h)
            points.append(f"{x},{y}")

            # Draw Data Point
            svg.append(f'<circle cx="{x}" cy="{y}" r="4" fill="{props["color"]}" />')

            # Annotate final point
            if i == len(years) - 1:
                svg.append(
                    f'<text x="{x+5}" y="{y}" font-family="Arial" font-size="12" font-weight="bold" fill="{props["color"]}">{team} {val:.1f}%</text>'
                )

        polyline = f'<polyline points="{" ".join(points)}" fill="none" stroke="{props["color"]}" stroke-width="3" />'
        svg.append(polyline)

    svg.append("</svg>")

    with open("reports/team_risk_history.svg", "w") as f:
        f.write("\n".join(svg))
    print("Generated reports/team_risk_history.svg")


if __name__ == "__main__":
    generate_svg()

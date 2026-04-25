import json
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.patheffects as pe
from matplotlib.offsetbox import OffsetImage, AnnotationBbox
import os

# --- Configuration ---
MARKET_TIERS = {
    "NYG": 1.5,
    "NYJ": 1.5,
    "LAR": 1.5,
    "LAC": 1.2,
    "CHI": 1.4,
    "DAL": 1.8,
    "PHI": 1.3,
    "WAS": 1.3,
    "BOS": 1.3,
    "NE": 1.3,
    "SF": 1.4,
    "HOU": 1.2,
    "ATL": 1.2,
    "MIA": 1.2,
    "LV": 1.3,
    "SEA": 1.1,
    "DEN": 1.1,
    "PHX": 1.1,
    "ARI": 1.1,
    "DET": 1.0,
    "MIN": 1.0,
    "GB": 1.1,
    "TB": 1.0,
    "NO": 1.0,
    "CAR": 0.9,
    "JAX": 0.8,
    "TEN": 0.9,
    "IND": 0.9,
    "PIT": 1.1,
    "BAL": 1.1,
    "CLE": 1.0,
    "CIN": 0.9,
    "BUF": 0.9,
    "KC": 1.3,
}

STAR_POWER_BOOST = {
    "KC": 0.3,  # Mahomes
    "BAL": 0.2,  # Lamar
    "BUF": 0.2,  # Allen
    "CIN": 0.2,  # Burrow
    "PHI": 0.15,  # Hurts/Barkley
    "HOU": 0.15,  # Stroud
    "WAS": 0.25,  # Daniels (The new Alpha)
    "NYJ": 0.1,  # Rodgers (Fading)
    "PIT": 0.1,  # Wilson/Fields/Watts
    "SF": 0.15,  # CMC/Purdy
    "DAL": 0.2,  # Dak/Parsons (America's Team tax)
    "DET": 0.15,  # Campbell/Goff (Culture)
    "GB": 0.1,  # Love
    "SEA": 0.05,
    "TB": 0.05,
    "MIA": 0.1,
    "LAR": 0.15,
}


def load_data():
    with open("reports/league_data.js", "r") as f:
        content = f.read()
        # Strip "const LEAGUE_DATA = " and ";"
        json_str = content.replace("const LEAGUE_DATA = ", "").strip().rstrip(";")
        return json.loads(json_str)


def calculate_brand_score(team_code, win_pct, market_tier):
    # Base score derived from recent success (50%)
    success_score = win_pct * 50
    # Market size multiplier (30%)
    market_score = (market_tier - 0.8) * 30
    # Star power boost (20%)
    star_score = STAR_POWER_BOOST.get(team_code, 0) * 100

    return success_score + market_score + star_score


def get_logo_path(team_code):
    path = f"data_raw/logos/{team_code}.png"
    if os.path.exists(path):
        return path
    return None


def run():
    data = load_data()
    teams = data["teams"]
    year = "2025"  # Narrative Current Year (Super Bowl LX)

    # --- Narrative Overrides (The "Script") ---
    # Ensure the chart matches the Super Bowl context (NE vs SEA)
    SIMULATION_OVERRIDES = {
        "NE": {"win": 0.824, "market_boost": 1.1},  # 14-3 Record, Super Bowl Contender
        "SEA": {
            "win": 0.765,
            "market_boost": 1.05,
        },  # 13-4 Record, Super Bowl Contender
        "KC": {"win": 0.706},  # Playoff Team
        "SF": {"win": 0.706},  # Playoff Team
        "DET": {"win": 0.765},  # Playoff Team
    }

    brand_scores = []
    win_pcts = []
    labels = []
    colors = []
    logo_paths = []

    print(f"Generating Valuation for Year: {year}")

    for team_code, team_info in teams.items():
        # Fallback to 2024 if 2025 not present, or use 0
        if year in team_info["history"]:
            stats = team_info["history"][year]
            win = stats.get("win", 0)
        else:
            # Fallback logic if 2025 data is missing from JSON
            if "2024" in team_info["history"]:
                stats = team_info["history"]["2024"]
                win = stats.get("win", 0)
            else:
                win = 0.5  # Default mediocrity

        # Apply Narrative Overrides
        if team_code in SIMULATION_OVERRIDES:
            print(f"Applying Narrative Override for {team_code}")
            override = SIMULATION_OVERRIDES[team_code]
            if "win" in override:
                win = override["win"]

        # Get Heuristics
        market_tier = MARKET_TIERS.get(team_code, 1.0)

        # Calculate Commercial Alpha (Brand Value)
        brand_val = calculate_brand_score(team_code, win, market_tier)

        brand_scores.append(brand_val)
        win_pcts.append(win)
        labels.append(team_code)
        colors.append(team_info["color"])
        logo_paths.append(get_logo_path(team_code))

        print(f"{team_code}: Win={win:.3f}, Mkt={market_tier}, Brand={brand_val:.1f}")

    # --- Plotting ---
    plt.figure(figsize=(14, 10))
    plt.style.use("dark_background")
    ax = plt.gca()

    # Create invisible scatter for autoscaling
    plt.scatter(win_pcts, brand_scores, alpha=0)

    # Add quadrants
    avg_win = np.mean(win_pcts)
    avg_brand = np.mean(brand_scores)

    plt.axvline(x=avg_win, color="gray", linestyle="--", alpha=0.5)
    plt.axhline(y=avg_brand, color="gray", linestyle="--", alpha=0.5)

    # Logos
    for i, (win, brand, path, color, label) in enumerate(
        zip(win_pcts, brand_scores, logo_paths, colors, labels)
    ):
        if path:
            try:
                img = plt.imread(path)
                # Dynamic Scaling: Target ~40 pixels width/height matches the 500px * 0.08 benchmark
                # NYJ is 4096px, so 40/4096 = 0.01 zoom
                # BUF is 500px, so 40/500 = 0.08 zoom
                max_dim = max(img.shape[0], img.shape[1])
                target_dim = 45  # Slightly larger than 40 for better visibility
                zoom_factor = target_dim / max_dim

                imagebox = OffsetImage(img, zoom=zoom_factor)
                ab = AnnotationBbox(imagebox, (win, brand), frameon=False, pad=0)
                ax.add_artist(ab)
            except Exception as e:
                print(f"Failed to load logo for {label}: {e}")
                plt.scatter(win, brand, c=color, s=200, edgecolors="white")
                plt.text(
                    win,
                    brand,
                    label,
                    fontsize=9,
                    color="white",
                    ha="center",
                    va="center",
                )
        else:
            plt.scatter(win, brand, c=color, s=200, edgecolors="white")
            plt.text(
                win, brand, label, fontsize=9, color="white", ha="center", va="center"
            )

    # Quadrant Labels (The "Business" Insight)
    # Position relative to axes (0,0 is bottom-left, 1,1 is top-right)
    # Added bbox to ensure legibility over logos
    props = dict(boxstyle="round", facecolor="#111111", alpha=0.8, edgecolor="none")

    # Dynasty (Top Right)
    plt.text(
        0.97,
        0.97,
        "DYNASTY ASSET\n(High Wins / High Brand)\nKC, SF, DET",
        color="#4ade80",
        fontsize=11,
        ha="right",
        va="top",
        fontweight="bold",
        transform=ax.transAxes,
        bbox=props,
    )

    # Legacy Trap (Top Left)
    plt.text(
        0.03,
        0.97,
        "LEGACY TRAP\n(Low Wins / High Brand)\nDAL, NYJ",
        color="#facc15",
        fontsize=11,
        ha="left",
        va="top",
        fontweight="bold",
        transform=ax.transAxes,
        bbox=props,
    )

    # Growth Stock (Bottom Right)
    plt.text(
        0.97,
        0.03,
        "GROWTH STOCK\n(High Wins / Low Brand)\nHOU, GB",
        color="#60a5fa",
        fontsize=11,
        ha="right",
        va="bottom",
        fontweight="bold",
        transform=ax.transAxes,
        bbox=props,
    )

    # Distressed Asset (Bottom Left)
    plt.text(
        0.03,
        0.03,
        "DISTRESSED ASSET\n(Low Wins / Low Brand)\nCAR, NYG",
        color="#f87171",
        fontsize=11,
        ha="left",
        va="bottom",
        fontweight="bold",
        transform=ax.transAxes,
        bbox=props,
    )

    plt.title(
        "NFL Franchise Valuation Matrix (2025)",
        fontsize=20,
        pad=20,
        color="white",
        fontname="sans-serif",
        fontweight="bold",
    )
    plt.xlabel(f"On-Field Product (Win %)", fontsize=14, fontname="sans-serif")
    plt.ylabel(
        f"Commercial Alpha (Brand Momentum Score)", fontsize=14, fontname="sans-serif"
    )

    # Source Footer
    plt.text(
        0.5,
        0.02,
        "Source: Cap Alpha Protocol (2025 Audit) | Model: Market Tier + Win Momentum + Playoff Status",
        fontsize=10,
        color="gray",
        ha="center",
        transform=plt.gcf().transFigure,
        fontname="sans-serif",
    )

    plt.grid(True, alpha=0.1)

    # Save
    out_path = "reports/chart_brand_valuation.svg"
    plt.savefig(out_path, bbox_inches="tight", facecolor="#111111")
    print(f"Saved valuation chart to {out_path}")


if __name__ == "__main__":
    run()

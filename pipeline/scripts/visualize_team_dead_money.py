"""
Visualize Dead Money Trends Across NFL Teams (2015-2024)
"""

import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import glob

# NFL team colors (primary color for each team)
TEAM_COLORS = {
    "ARI": "#97233F",
    "ATL": "#A71930",
    "BAL": "#241773",
    "BUF": "#00338D",
    "CAR": "#0085CA",
    "CHI": "#0B162A",
    "CIN": "#FB4F14",
    "CLE": "#311D00",
    "DAL": "#041E42",
    "DEN": "#FB4F14",
    "DET": "#0076B6",
    "GB": "#203731",
    "HOU": "#03202F",
    "IND": "#002C5F",
    "JAX": "#006778",
    "KC": "#E31837",
    "LA": "#003594",
    "LAC": "#0080C6",
    "LAR": "#003594",
    "LV": "#000000",
    "MIA": "#008E97",
    "MIN": "#4F2683",
    "NE": "#002244",
    "NO": "#D3BC8D",
    "NYG": "#0B2265",
    "NYJ": "#125740",
    "OAK": "#000000",
    "PHI": "#004C54",
    "PIT": "#FFB612",
    "SD": "#0080C6",
    "SEA": "#002244",
    "SF": "#AA0000",
    "STL": "#003594",
    "TB": "#D50A0A",
    "TEN": "#0C2340",
    "WAS": "#5A1414",
}


def load_team_cap_data(data_dir="data/raw"):
    """Load all team cap CSV files and combine into single DataFrame"""
    files = glob.glob(f"{data_dir}/spotrac_team_cap_*_*.csv")

    # Get the most recent file for each year
    year_files = {}
    for f in files:
        # Extract year from filename
        parts = Path(f).stem.split("_")
        year = int(parts[3])
        if year not in year_files or f > year_files[year]:
            year_files[year] = f

    # Load and combine
    dfs = []
    for year, filepath in sorted(year_files.items()):
        df = pd.read_csv(filepath)
        df["year"] = year
        dfs.append(df)
        print(
            f"✓ Loaded {year}: {len(df)} teams, ${df['dead_money_millions'].sum():.1f}M total dead money"
        )

    combined = pd.concat(dfs, ignore_index=True)
    print(
        f"\n✅ Combined: {len(combined)} team-year records ({combined['year'].min()}-{combined['year'].max()})"
    )

    return combined


def create_stacked_bar_chart(
    df, output_path="notebooks/outputs/dead_money_stacked_by_team.html"
):
    """Create stacked bar chart showing dead money by team and year"""

    # Pivot data for stacking
    pivot = df.pivot(index="year", columns="team", values="dead_money_millions")
    pivot = pivot.fillna(0)

    # Sort teams by total dead money (highest first)
    team_totals = pivot.sum().sort_values(ascending=False)
    pivot = pivot[team_totals.index]

    # Create stacked bar chart
    fig = go.Figure()

    for team in pivot.columns:
        color = TEAM_COLORS.get(team, "#888888")

        fig.add_trace(
            go.Bar(
                name=team,
                x=pivot.index,
                y=pivot[team],
                marker_color=color,
                hovertemplate=f"<b>{team}</b><br>"
                + "Year: %{x}<br>"
                + "Dead Money: $%{y:.1f}M<br>"
                + "<extra></extra>",
            )
        )

    # Calculate total dead money per year for annotation
    totals = pivot.sum(axis=1)

    fig.update_layout(
        title={
            "text": "NFL Liquidity Drag by Team (2015-2024)<br><sub>Stacked by Team</sub>",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Year",
        yaxis_title="Dead Money (Millions USD)",
        barmode="stack",
        hovermode="closest",
        template="plotly_white",
        height=700,
        width=1200,
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1,
            xanchor="left",
            x=1.02,
            font=dict(size=9),
        ),
        xaxis=dict(tickmode="linear", tick0=pivot.index.min(), dtick=1),
        yaxis=dict(tickprefix="$", ticksuffix="M"),
    )

    # Add total annotations above each bar
    for year in pivot.index:
        fig.add_annotation(
            x=year,
            y=totals[year],
            text=f"${totals[year]:.0f}M",
            showarrow=False,
            yshift=10,
            font=dict(size=10, color="black"),
        )

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path))
    print(f"\n✅ Saved to: {output_path}")

    return fig


def create_grouped_bar_chart(
    df, output_path="notebooks/outputs/dead_money_yearly_trend.html"
):
    """Create grouped/line chart showing overall trend"""

    # Aggregate by year
    yearly = (
        df.groupby("year")
        .agg({"dead_money_millions": ["sum", "mean", "std"]})
        .reset_index()
    )
    yearly.columns = ["year", "total_dead_money", "avg_per_team", "std_dev"]

    fig = go.Figure()

    # Total dead money bar
    fig.add_trace(
        go.Bar(
            name="Total League Dead Money",
            x=yearly["year"],
            y=yearly["total_dead_money"],
            marker_color="#AA0000",
            yaxis="y",
            hovertemplate="Year: %{x}<br>Total: $%{y:.1f}M<extra></extra>",
        )
    )

    # Average per team line
    fig.add_trace(
        go.Scatter(
            name="Avg Per Team",
            x=yearly["year"],
            y=yearly["avg_per_team"],
            mode="lines+markers",
            line=dict(color="#0080C6", width=3),
            marker=dict(size=8),
            yaxis="y2",
            hovertemplate="Year: %{x}<br>Avg: $%{y:.1f}M per team<extra></extra>",
        )
    )

    fig.update_layout(
        title={
            "text": "NFL Dead Money Trends (2015-2024)<br><sub>Total League vs Average Per Team</sub>",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Year",
        template="plotly_white",
        height=600,
        width=1000,
        hovermode="x unified",
        yaxis=dict(
            title="Total League Liquidity Drag (Millions USD)",
            tickprefix="$",
            ticksuffix="M",
            side="left",
        ),
        yaxis2=dict(
            title="Average Per Team (Millions USD)",
            tickprefix="$",
            ticksuffix="M",
            overlaying="y",
            side="right",
        ),
        xaxis=dict(tickmode="linear", tick0=yearly["year"].min(), dtick=1),
    )

    # Save
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path))
    print(f"✅ Saved to: {output_path}")

    return fig


if __name__ == "__main__":
    print("Loading team cap data...\n")
    df = load_team_cap_data()

    print("\nGenerating visualizations...\n")

    # Stacked bar chart by team
    fig1 = create_stacked_bar_chart(df)

    # Yearly trend chart
    fig2 = create_grouped_bar_chart(df)

    print("\n" + "=" * 60)
    print("Dead Money Summary (2015-2024)")
    print("=" * 60)

    yearly_summary = df.groupby("year")["dead_money_millions"].agg(
        ["sum", "mean", "min", "max"]
    )
    print(yearly_summary.to_string())

    print("\n" + "=" * 60)
    print("Top 10 Teams by Total Dead Money (2015-2024)")
    print("=" * 60)
    team_totals = (
        df.groupby("team")["dead_money_millions"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )
    for i, (team, total) in enumerate(team_totals.items(), 1):
        print(f"{i:2d}. {team:3s}: ${total:6.1f}M")

    print("\n✅ Done!")

from src.db_manager import DBManager
import pandas as pd
import json
import os
from pathlib import Path


def export_dashboard_data(db_path: str, output_path: str):
    con = DBManager()

    # Identify the 'High-Alpha' and 'High-Risk' players
    query = """
    SELECT 
        player_name, team, year, position,
        ROUND(cap_hit_millions, 2) as cap_hit,
        ROUND(ml_fair_market_value, 2) as ml_fmv,
        ROUND(ml_risk_score, 3) as risk_score,
        ROUND(availability_rating, 2) as availability,
        ROUND(combined_roi_score, 2) as roi
    FROM fact_player_efficiency
    WHERE year = 2025
    ORDER BY ml_risk_score DESC
    """
    df = con.execute(query).df()

    # Team aggregation
    team_query = """
    SELECT 
        team,
        AVG(ml_risk_score) as avg_risk,
        SUM(cap_hit_millions) as total_cap,
        COUNT(*) as roster_count
    FROM fact_player_efficiency
    WHERE year = 2025
    GROUP BY team
    ORDER BY avg_risk DESC
    """
    teams_df = con.execute(team_query).df()

    data = {
        "timestamp": pd.Timestamp.now().isoformat(),
        "players": df.to_dict(orient="records"),
        "teams": teams_df.to_dict(orient="records"),
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"✓ Dashboard data exported to {output_path}")
    con.close()


if __name__ == "__main__":
    db_path = os.getenv("DB_PATH", "data/nfl_data.db")
    output_dir = Path("dashboard/data")
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        test_file = output_dir / ".write_test"
        test_file.touch()
        test_file.unlink()
    except (PermissionError, OSError):
        output_dir = Path("/tmp/dashboard_data")
        output_dir.mkdir(parents=True, exist_ok=True)

    export_dashboard_data(db_path, output_dir / "latest_audit.json")

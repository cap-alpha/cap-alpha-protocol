
from src.db_manager import DBManager
import pandas as pd

DB_PATH = "data/nfl_data.db"

def present_value(year):
    con = DBManager()
    
    print(f"\n==================== {year} SEASON AUDIT ====================")
    print(f"🏆 Top 10 'High Value' Players ({year}) - High Production, Low Cap Hit")
    print("-" * 80)
    
    query = f"""
    SELECT DISTINCT
        player_name, 
        team, 
        position, 
        cap_hit_millions, 
        fair_market_value,
        ied_overpayment,
        value_metric_proxy
    FROM fact_player_efficiency
    WHERE year = {year} 
      AND games_played >= 10
      AND cap_hit_millions > 0.5
    ORDER BY value_metric_proxy DESC
    LIMIT 10
    """
    
    df = con.execute(query).df()
    print(df.to_string(index=False))
    
    print(f"\n☢️ 'The Time Bombs' - Highest EDCE (Dead Cap Risk) ({year})")
    print("-" * 80)
    query_risk = f"""
    SELECT DISTINCT
        player_name, 
        team, 
        position, 
        age,
        potential_dead_cap_millions,
        edce_risk
    FROM fact_player_efficiency
    WHERE year = {year} 
      AND potential_dead_cap_millions > 5
    ORDER BY edce_risk DESC
    LIMIT 10
    """
    df_risk = con.execute(query_risk).df()
    print(df_risk.to_string(index=False))
    
    con.close()

if __name__ == "__main__":
    # Run for the full 10-year range (including current SB season 2025)
    for y in range(2015, 2026):
        try:
            present_value(y)
        except Exception as e:
            print(f"Skipping {y}: {e}")



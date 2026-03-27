from src.db_manager import DBManager
import pandas as pd

DB_PATH = "data/nfl_belichick.db"
con = DBManager()

print("--- ARIZONA CARDINALS: HIGH-RISK CONSTRUCITON (2024/2025) ---")
# Check 2024/2025 High Risk Players
query = """
SELECT 
    player_name, 
    position, 
    year,
    cap_hit_millions, 
    potential_dead_cap_millions, 
    age, 
    edce_risk,
    ied_overpayment
FROM fact_player_efficiency 
WHERE team = 'ARI' 
  AND year IN (2024, 2025)
ORDER BY potential_dead_cap_millions DESC 
LIMIT 15;
"""
df = con.query(query).df()
print(df.to_string())

# Team level aggregate
print("\n--- TEAM AGGREGATE RISK ---")
team_query = """
SELECT 
    team, 
    year, 
    SUM(cap_hit_millions) as total_cap, 
    SUM(potential_dead_cap_millions) as total_dead_exposure,
    AVG(edce_risk) as avg_risk_index
FROM fact_player_efficiency 
WHERE team = 'ARI'
GROUP BY 1, 2
ORDER BY 2;
"""
print(con.query(team_query).df().to_string())
con.close()

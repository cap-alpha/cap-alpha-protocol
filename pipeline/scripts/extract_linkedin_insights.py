from src.db_manager import DBManager
import pandas as pd

con = DBManager()

print("--- TOP OVERPAID PLAYERS (Gap between Cap Hit and Fair Market Value) ---")
overpaid = con.execute("""
    SELECT player_name, team, position, cap_hit_millions, fair_market_value, ied_overpayment 
    FROM fact_player_efficiency 
    WHERE year = 2024 AND cap_hit_millions > 5
    ORDER BY ied_overpayment DESC 
    LIMIT 10
""").df()
print(overpaid)

print("\n--- REVENUE LIFT vs CAP HIT (ROI STARS) ---")
# Finding players who generate more revenue than they cost
roi = con.execute("""
    SELECT player_name, team, cap_hit_millions, popularity_score, (popularity_score * 0.1) as est_revenue_lift_M
    FROM fact_player_efficiency 
    WHERE year = 2024 AND popularity_score > 0
    ORDER BY (popularity_score * 0.1) / NULLIF(cap_hit_millions, 0) DESC
    LIMIT 10
""").df()
print(roi)

print("\n--- DEAD MONEY RISK FRONTIER ---")
risk = con.execute("""
    SELECT player_name, team, potential_dead_cap_millions, edce_risk, age
    FROM fact_player_efficiency 
    WHERE year = 2024
    ORDER BY edce_risk DESC 
    LIMIT 10
""").df()
print(risk)

con.close()

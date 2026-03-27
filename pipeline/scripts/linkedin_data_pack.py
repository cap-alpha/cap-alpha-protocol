from src.db_manager import DBManager
import pandas as pd

con = DBManager()

# 1. Team Aggregate Risk (Top 10 most efficient vs wasteful teams)
team_stats = con.execute("""
    SELECT 
        team, 
        ROUND(SUM(cap_hit_millions), 1) as total_cap_hit_M,
        ROUND(AVG(ied_overpayment), 1) as avg_overpayment_per_player,
        COUNT(*) as roster_count
    FROM fact_player_efficiency 
    WHERE year = 2025
    GROUP BY 1
    ORDER BY avg_overpayment_per_player DESC
""").df()

# 3. Merch ROI (Who sells the most jerseys for the least salary)
merch_roi = con.execute("""
    SELECT 
        player_name, 
        team, 
        merch_rank, 
        cap_hit_millions,
        ROUND((51 - merch_rank) / NULLIF(cap_hit_millions, 0), 2) as efficiency_score
    FROM fact_player_efficiency 
    WHERE year = 2025 AND merch_rank <= 50
    ORDER BY efficiency_score DESC
    LIMIT 10
""").df()

print("TEAM VULNERABILITY RANKINGS:")
print(team_stats.head(10))
print("\nNFL MERCHANDISE ROI KINGS (Highest Rank per Dollar):")
print(merch_roi)

con.close()

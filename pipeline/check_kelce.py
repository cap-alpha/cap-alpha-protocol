from src.db_manager import DBManager
con = DBManager()
try:
    print(con.execute("SELECT year, team, predicted_risk_score FROM prediction_results WHERE player_name ILIKE '%Kelce%' ORDER BY year DESC").fetchall())
except Exception as e:
    print("prediction_results not found:", e)

try:
    print(con.execute("SELECT MAX(year) FROM silver_spotrac_contracts").fetchall())
except Exception as e:
    pass

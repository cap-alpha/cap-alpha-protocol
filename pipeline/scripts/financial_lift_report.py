from src.db_manager import DBManager
import pandas as pd
from tabulate import tabulate

def generate_report(year: int = 2025):
    con = DBManager()
    
    # Check if table exists
    tables = con.execute("SELECT table_name FROM information_schema.tables WHERE table_name = 'fact_player_efficiency'").fetchall()
    if not tables:
        print("Error: fact_player_efficiency table not found.")
        con.close()
        return

    query = f"""
    SELECT 
        player_name,
        team,
        position,
        cap_hit_millions as cap_M,
        total_penalty_yards as penalties,
        fair_market_value as fair_val_M,
        financial_lift_total_M as off_field_M,
        combined_roi_score as total_roi
    FROM fact_player_efficiency 
    WHERE year = {year}
    ORDER BY total_roi DESC 
    LIMIT 25
    """
    
    df = con.sql(query).df()
    
    print(f"\n--- Top 25 VALUE KINGS (Football Efficiency + Off-Field Impact) - {year} ---")
    print(tabulate(df, headers='keys', tablefmt='github', showindex=False))
    
    # Discipline Audit
    penalty_query = f"""
    SELECT 
        player_name,
        team,
        total_penalty_yards as yds,
        total_penalty_count as count,
        cap_hit_millions as cap_M,
        (total_penalty_yards / 10.0) as theoretical_loss_M
    FROM fact_player_efficiency 
    WHERE year = {year} AND total_penalty_yards > 50
    ORDER BY theoretical_loss_M DESC
    LIMIT 10
    """
    
    print(f"\n--- DISCIPLINE AUDIT: Top 10 Value Killers (Penalty Attribution) - {year} ---")
    print(tabulate(con.sql(penalty_query).df(), headers='keys', tablefmt='github', showindex=False))
    
    con.close()

if __name__ == "__main__":
    generate_report(year=2025)
    generate_report(year=2024)

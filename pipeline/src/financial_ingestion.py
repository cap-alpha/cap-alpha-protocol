import duckdb
import pandas as pd
from pathlib import Path

def load_team_financials(con: duckdb.DuckDBPyConnection, file_path: Path):
    """
    Loads Team Financials CSV into DuckDB silver layer.
    """
    if not file_path.exists():
        print(f"Warning: Financial data file not found at {file_path}")
        return

    print(f"Loading Financials from {file_path}")
    con.execute(f"""
        CREATE OR REPLACE TABLE silver_team_finance AS 
        SELECT * FROM read_csv_auto('{file_path}', header=True)
    """)

def load_player_merch(con: duckdb.DuckDBPyConnection, file_path: Path):
    """
    Loads Player Merch CSV into DuckDB silver layer.
    """
    if not file_path.exists():
        print(f"Warning: Merch data file not found at {file_path}")
        return
    
    print(f"Loading Merch Rank from {file_path}")
    con.execute(f"""
        CREATE OR REPLACE TABLE silver_player_merch AS 
        SELECT * FROM read_csv_auto('{file_path}', header=True)
    """)

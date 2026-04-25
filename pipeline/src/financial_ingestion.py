from pathlib import Path

import pandas as pd


def load_team_financials(db, file_path: Path):
    """
    Loads Team Financials CSV into BigQuery silver layer.
    """
    if not file_path.exists():
        print(f"Warning: Financial data file not found at {file_path}")
        return

    print(f"Loading Financials from {file_path}")
    df = pd.read_csv(file_path)
    db.execute(
        "CREATE OR REPLACE TABLE silver_team_finance AS SELECT * FROM df",
        {"df": df},
    )


def load_player_merch(db, file_path: Path):
    """
    Loads Player Merch CSV into BigQuery silver layer.
    """
    if not file_path.exists():
        print(f"Warning: Merch data file not found at {file_path}")
        return

    print(f"Loading Merch Rank from {file_path}")
    df = pd.read_csv(file_path)
    db.execute(
        "CREATE OR REPLACE TABLE silver_player_merch AS SELECT * FROM df",
        {"df": df},
    )

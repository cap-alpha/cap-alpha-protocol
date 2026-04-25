import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from src.db_manager import DBManager
import pandas as pd


def inspect():
    db = DBManager()
    print("\n=== Tables ===")
    tables = db.fetch_df(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
    )
    print(tables)

    for table in tables["table_name"]:
        print(f"\n--- {table} ---")
        try:
            schema = db.fetch_df(f"DESCRIBE {table}")
            print(schema[["column_name", "column_type"]])

            # Show one row
            print(f"Sample:")
            print(db.fetch_df(f"SELECT * FROM {table} LIMIT 1"))
        except Exception as e:
            print(f"Error describing {table}: {e}")


if __name__ == "__main__":
    inspect()

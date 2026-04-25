from src.db_manager import DBManager
import pandas as pd
import os

# Try to find the database
db_paths = ["nfl_dead_money.duckdb", "data/nfl_data.db", "data/nfl_dead_money.duckdb"]
DB_PATH = None
for p in db_paths:
    if os.path.exists(p):
        DB_PATH = p
        break

if not DB_PATH:
    print("Could not find database file!")
    exit(1)

print(f"Using database: {DB_PATH}")


def run_query():
    con = DBManager()

    # Simple table listing
    print("\n--- Tables ---")
    try:
        tables = con.execute("SHOW TABLES").fetchall()
        print([t[0] for t in tables])
    except Exception as e:
        print(f"Error listing tables: {e}")

    # Search for OBJ and others in known tables or likely tables
    # First, let's see which tables have 'player' column or similar

    target_players = [
        "%Beckham%",
        "%Mahomes%",
        "%Riley%Moss%",
        "%Carlton%Davis%",
        "%Jayden%Daniels%",
        "%Saquon%Barkley%",
    ]

    # Heuristic: look for tables with 'contract' or 'stat' or 'penalty' in name
    # We'll filter the tables list
    likely_tables = [
        t[0]
        for t in tables
        if any(
            x in t[0]
            for x in ["contract", "stat", "penalty", "risk", "audit", "frontier"]
        )
    ]

    for table in likely_tables:
        print(f"\nScanning table: {table}")
        try:
            # check columns
            cols = [c[0] for c in con.execute(f"DESCRIBE {table}").fetchall()]
            print(f"Columns: {cols}")

            player_col = next((c for c in cols if "player" in c or "name" in c), None)
            if player_col:
                print(f"Querying {table} for players...")
                conditions = " OR ".join(
                    [f"{player_col} LIKE '{p}'" for p in target_players]
                )
                query = f"SELECT * FROM {table} WHERE {conditions} LIMIT 20"
                df = con.execute(query).df()
                if not df.empty:
                    print(df.to_string())
                else:
                    print("No matches found.")
            else:
                print(f"No player column found in {table}")

        except Exception as e:
            print(f"Error querying {table}: {e}")

    con.close()


if __name__ == "__main__":
    run_query()

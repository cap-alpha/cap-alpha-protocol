import duckdb
import os

token = os.environ.get("MOTHERDUCK_TOKEN")
con = duckdb.connect(f"md:?motherduck_token={token}")

print("Databases:")
print(con.execute("SELECT database_name FROM information_schema.schemata").fetchall())

try:
    print("Fetching overall stats from nfl_data.fact_player_efficiency...")
    result = con.execute("SELECT MAX(year), COUNT(*) FROM nfl_data.main.fact_player_efficiency").fetchall()
    print(f"Max Year: {result[0][0]}, Total Rows: {result[0][1]}")
except Exception as e:
    print("Error querying nfl_data:", e)

try:
    print("Fetching overall stats from fact_player_efficiency (default db)...")
    result = con.execute("SELECT MAX(year), COUNT(*) FROM fact_player_efficiency").fetchall()
    print(f"Max Year: {result[0][0]}, Total Rows: {result[0][1]}")
except Exception as e:
    print("Error querying default:", e)


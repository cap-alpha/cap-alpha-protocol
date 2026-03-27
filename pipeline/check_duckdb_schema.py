import duckdb
con = duckdb.connect("/Users/andrewsmith/portfolio/nfl-dead-money/data/nfl_data.db", read_only=True)
print("--- SCHEMA ---")
for t in ["prediction_results", "media_lag_metrics", "audit_ledger_blocks", "audit_ledger_entries"]:
    print(f"\n[{t}]")
    try:
        for col in con.execute(f"DESCRIBE {t}").fetchall():
            print(f"{col[0]}: {col[1]}")
    except Exception as e:
        print(e)

#!/usr/bin/env python3
"""
Batch ingestion script for all historical years.
Uses the Medallion bronze layer as source.
"""
from src.db_manager import DBManager
import subprocess
import sys
from pathlib import Path

# Years with available data
YEARS = list(range(2011, 2026))  # 2011-2025

# Fresh database path
DB_PATH = "/tmp/nfl_medallion.db"

def main():
    print(f"🚀 Starting batch ingestion to {DB_PATH}")
    print(f"   Years: {YEARS[0]}-{YEARS[-1]} ({len(YEARS)} years)")
    print()
    
    # Remove old DB to start fresh
    db_file = Path(DB_PATH)
    if db_file.exists():
        db_file.unlink()
        print(f"   🗑️  Removed old database")
    
    successful = []
    failed = []
    
    for year in YEARS:
        print(f"📅 Ingesting {year}...", end=" ", flush=True)
        result = subprocess.run(
            [sys.executable, "scripts/medallion_pipeline.py", "--year", str(year)],
            capture_output=True,
            text=True,
            env={"DB_PATH": DB_PATH, "PYTHONPATH": ".", "PATH": "/usr/bin:/bin"}
        )
        
        if result.returncode == 0:
            print("✅")
            successful.append(year)
        else:
            print(f"❌")
            failed.append(year)
            # Show brief error
            if "No file found" in result.stderr or "No file found" in result.stdout:
                print(f"      ⚠️  Missing data files for {year}")
            else:
                print(f"      Error: {result.stderr[:200] if result.stderr else result.stdout[:200]}")
    
    print()
    print(f"✅ Successfully ingested: {len(successful)} years")
    if failed:
        print(f"❌ Failed: {failed}")
    
    # Show final row counts
    print()
    print("📊 Final table row counts:")
    import duckdb
    con = DBManager()
    tables = con.execute("SHOW TABLES").fetchall()
    for (table,) in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"   {table}: {count:,} rows")
    con.close()

if __name__ == "__main__":
    main()

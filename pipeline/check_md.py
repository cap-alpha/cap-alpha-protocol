import os
from src.db_manager import DBManager

print("MOTHERDUCK_TOKEN in env:", bool(os.getenv("MOTHERDUCK_TOKEN")))

try:
    db = DBManager()
    print("Connected to DB:", db.db_path)
    # Check tables
    res = db.fetch_df("SHOW TABLES")
    print("\nTables found:")
    print(res)
except Exception as e:
    print("Database error:", e)

from src.db_manager import DBManager
import os

token = os.environ.get("MOTHERDUCK_TOKEN")
if not token:
    print("NO MOTHERDUCK TOKEN")
    exit(1)

con = DBManager()
print("MAX YEAR:")
print(con.execute("SELECT MAX(year) FROM fact_player_efficiency").fetchone())
print("MEDIA COUNT:")
print(con.execute("SELECT COUNT(*) FROM raw_media_mentions").fetchone())

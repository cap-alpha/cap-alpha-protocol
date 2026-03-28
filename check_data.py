import os
import sys
# Add pipeline path
sys.path.append(os.path.join(os.getcwd(), 'pipeline'))
from dotenv import load_dotenv
load_dotenv()
from src.db_manager import DBManager
import pandas as pd

import warnings
warnings.filterwarnings('ignore')

db = DBManager()

queries = {
    "1. Bronze Contracts (OTC) - Ensure Scrape Finished": "SELECT COUNT(*) as count, MAX(_ingestion_timestamp) as latest_ingestion FROM bronze_overthecap_contracts",
    "2. Silver Contracts - Complete Column Hydration Check": "SELECT player_name, team, position, cap_hit_millions, dead_cap_millions, base_salary_millions, guaranteed_money_millions FROM silver_spotrac_contracts WHERE year = 2026 ORDER BY cap_hit_millions DESC LIMIT 5",
    "3. Gold Fact Table (fact_player_efficiency) Validation": "SELECT player_name, team, year, games_played, total_tds, cap_hit_millions, dead_cap_millions FROM fact_player_efficiency WHERE year = 2026 ORDER BY total_tds DESC LIMIT 5",
    "4. Proof of Freshness: Joe Flacco on the Bengals (CIN)": "SELECT player_name, team, year, cap_hit_millions, guaranteed_money_millions FROM fact_player_efficiency WHERE player_name LIKE '%Joe Flacco%' AND year = 2026"
}

markdown_output = []

for name, q in queries.items():
    try:
        res = db.fetch_df(q)
        out = f"### {name}\\n```sql\\n{q}\\n```\\n{res.to_markdown(index=False)}\\n"
        print(out)
        markdown_output.append(out)
    except Exception as e:
        err = f"### {name}\\n```sql\\n{q}\\n```\\n**Error**: {e}\\n"
        print(err)
        markdown_output.append(err)

with open("check_output.md", "w") as f:
    f.write("\\n".join(markdown_output))

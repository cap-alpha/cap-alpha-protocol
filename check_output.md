### 1. Bronze Contracts (OTC) - Ensure Scrape Finished\n```sql\nSELECT COUNT(*) as count, MAX(_ingestion_timestamp) as latest_ingestion FROM bronze_overthecap_contracts\n```\n|   count | latest_ingestion                 |
|--------:|:---------------------------------|
|   31703 | 2026-03-28 00:51:15.667096+00:00 |\n\n### 2. Silver Contracts - Complete Column Hydration Check\n```sql\nSELECT player_name, team, position, cap_hit_millions, dead_cap_millions, base_salary_millions, guaranteed_money_millions FROM silver_spotrac_contracts WHERE year = 2026 ORDER BY cap_hit_millions DESC LIMIT 5\n```\n| player_name   | team   | position   |   cap_hit_millions |   dead_cap_millions |   base_salary_millions |   guaranteed_money_millions |
|:--------------|:-------|:-----------|-------------------:|--------------------:|-----------------------:|----------------------------:|
| Josh Allen    | BUF    | None       |             52.5   |                   0 |                    nan |                           0 |
| Jalen Hurts   | PHI    | None       |             51.5   |                   0 |                    nan |                           0 |
| Jordan Love   | GB     | None       |             49.9   |                   0 |                    nan |                           0 |
| Brock Purdy   | SF     | None       |             46.996 |                   0 |                    nan |                           0 |
| Dak Prescott  | DAL    | None       |             45     |                   0 |                    nan |                           0 |\n\n### 3. Gold Fact Table (fact_player_efficiency) Validation\n```sql\nSELECT player_name, team, year, games_played, total_tds, cap_hit_millions, dead_cap_millions FROM fact_player_efficiency WHERE year = 2026 ORDER BY total_tds DESC LIMIT 5\n```\n| player_name   | team   |   year |   games_played |   total_tds |   cap_hit_millions |   dead_cap_millions |
|:--------------|:-------|-------:|---------------:|------------:|-------------------:|--------------------:|
| Isaac Seumalo | ARI    |   2026 |              0 |           0 |                6.5 |                   0 |
| Mack Wilson   | ARI    |   2026 |              0 |           0 |                0   |                   0 |
| Denzel Burke  | ARI    |   2026 |              0 |           0 |                0   |                   0 |
| Elijah Jones  | ARI    |   2026 |              0 |           0 |                0   |                   0 |
| Kyler Murray  | ARI    |   2026 |              0 |           0 |               36.8 |                   0 |\n\n### 4. Proof of Freshness: Joe Flacco on the Bengals (CIN)\n```sql\nSELECT player_name, team, year, cap_hit_millions, guaranteed_money_millions FROM fact_player_efficiency WHERE player_name LIKE '%Joe Flacco%' AND year = 2026\n```\n| player_name   | team   |   year |   cap_hit_millions |   guaranteed_money_millions |
|:--------------|:-------|-------:|-------------------:|----------------------------:|
| Joe Flacco    | CIN    |   2026 |                  0 |                           0 |\n
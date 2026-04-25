# SP27-5: Data Anomalies & Remediation TODOs

**Generated**: 2026-04-24
**Sprint**: Sprint 27 — Historical Data Hydration & Rigorous Asset Validation

---

## Summary

BigQuery audit run on `nfl_dead_money` dataset (project: `my-project-1525668581184`).

### Tables present (14 total)
| Table | Row count | Year range |
|---|---|---|
| silver_spotrac_contracts | 54,870 | 2011–2026 |
| fact_player_efficiency | 54,870 | 2011–2026 |
| staging_feature_matrix | 54,870 | 2011–2026 |
| silver_pfr_game_logs | 15 | 2015–2025 |
| silver_player_metadata | ~0 (empty) | — |
| silver_spotrac_salaries | unknown | — |
| silver_spotrac_rankings | unknown | — |
| silver_player_merch | unknown | — |
| silver_team_finance | unknown | — |
| audit_ledger_blocks | — | — |
| audit_ledger_entries | — | — |
| immutable_prediction_ledger | — | — |
| prediction_results | — | — |

---

## Anomalies Found

### A1 — No Bronze Layer Tables [HIGH]
Zero tables with a `bronze_` prefix exist. Data was loaded directly into silver.
Per the medallion architecture spec, raw ingested data should land in bronze first.

**TODO**: Implement bronze landing tables. Add `bronze_spotrac_contracts`, `bronze_pfr_game_logs`, etc. Silver transforms should read from bronze.

---

### A2 — `silver_pfr_game_logs` Critically Sparse [HIGH]
Only **15 rows** in the game logs table. A full NFL season has 272+ regular-season games with ~50+ player log entries each. Expected: 100,000+ rows for 2011–2025.

This table is referenced by the planned `game_outcome` resolver (issue #191).

**TODO**: Re-run the PFR game log scraper to backfill all QB/player game logs from 2011–2025. See `pipeline/src/pfr_game_logs.py`.

---

### A3 — `silver_player_metadata` Empty [HIGH]
Zero rows returned for any player query. This table should contain player biographical data (DOB, position, team history).

**TODO**: Backfill player metadata. See `pipeline/src/pfr_profile_scraper.py` and `pipeline/src/master_player_records.py`.

---

### A4 — `bronze_sportsdataio_players` Missing [HIGH]
The `resolve_daily.py` draft_pick resolver queries `bronze_sportsdataio_players` which does not exist in the dataset. This causes all draft_pick resolutions to fail.

**TODO**: Ingest SportsDataIO players endpoint into BQ as `bronze_sportsdataio_players`. See `pipeline/src/sportsdataio_client.py`.

---

### A5 — NULL Cap Figures in `silver_spotrac_contracts` [MEDIUM]
Several rows have NULL `cap_hit_millions` and `dead_cap_millions`. Spot check on Joe Flacco:
- 2026 CIN row: cap_hit_millions = NULL (future year, expected)
- 2012 BAL rows: some NULLs where figures weren't scraped

**TODO**: Audit NULL rates per year. If pre-2015 data has high NULL rates, consider either re-scraping or marking rows as `data_quality = LOW`.

---

### A6 — Mixed Player Name Results ("Mike Flacco") [LOW]
Queries for "Flacco" return both Joe Flacco (QB) and Mike Flacco (TE). This is correct behavior but confirms player disambiguation is needed.

**TODO**: Add `player_id` foreign key to silver tables so lookups are by unique ID, not fuzzy name.

---

## Joe Flacco Validation (SP27-4)

Data matches known career history:
| Year | Team | Age | Cap Hit ($M) | Verdict |
|---|---|---|---|---|
| 2012 | BAL | 27 | 8.0 | ✓ (rookie deal year 5) |
| 2015 | BAL | 30 | 14.55 | ✓ (post-extension) |
| 2022 | NYJ | 37 | 3.39 | ✓ (backup QB) |
| 2026 | CIN | 40 | NULL | ✓ (future, not yet signed) |

All ages, teams, and cap figures match publicly known career data.

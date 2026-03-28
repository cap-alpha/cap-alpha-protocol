# Execution Tasks: Medallion Architecture Bronze Refactor

- [x] **Task 1: Infrastructure Enhancement**
    - [x] Add `append_dataframe_to_table` in `pipeline/src/db_manager.py` capable of loading DFs into BigQuery with `_ingestion_timestamp`.
- [x] **Task 2: Ingestion Layer (Silver to Bronze Refactor)**
    - [x] Update `BronzeLayer` in `pipeline/scripts/medallion_pipeline.py` to bypass `read_csv` and actively trigger scraping modules.
    - [x] Inject `_ingestion_timestamp` during scrape.
    - [x] Stream results to BigQuery `bronze_` tables in append mode.
- [x] **Task 3: Transformation Layer (Silver/Gold Update)**
    - [x] Refactor `SilverLayer` to read directly from newly created `bronze_` tables via `db.fetch_df(SELECT * FROM bronze_X WHERE _ingestion_timestamp = MAX)`.
    - [x] Validate `GoldLayer` (`fact_player_efficiency`) logic with the new Silver inputs.
- [x] **Task 4: Production Run (Today's Data)**
    - [x] Run `python pipeline/scripts/medallion_pipeline.py --year 2026`.
    - [x] Troubleshoot and resolve any anti-bot 403s regarding Spotrac (switching data sources or bypassing).
- [x] **Task 5: End-to-End Validation**
    - [x] Ensure BQ console reflects structured tables.
    - [x] Create `walkthrough.md`.

*Agent Quota Estimate Estimate*: This refactor and full pipeline run requires one highly capable engineering agent running autonomously in a single prolonged loop (~10-15 steps). No multi-agent spawn is strictly required to accomplish the baseline code edits, saving overhead.

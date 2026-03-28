# Medallion Pipeline Refactor: Direct-to-Bronze BigQuery Ingestion

Based on your feedback, we are eliminating the intermediate CSV storage layer. The scrapers will push data directly into BigQuery `bronze_` tables. We will also implement versioning. 

## To Answer Your Question: Versioning in BigQuery
Yes, they can be versioned very similarly to Apache Iceberg. BigQuery offers two native ways to handle this without maintaining complex external delta logs:
1. **Append-Only Event Sourcing (The standard approach):** We don't overwrite the bronze tables. Instead, every time a scraper runs, we append the dataframe to the `bronze_` table with a new `_ingestion_timestamp` column. This creates an auditable, append-only ledger where you can easily backtest "what did the raw data look like on Jan 5th?".
2. **Native BigQuery Time Travel & Snapshots:** BigQuery natively stores the history of all changes to a table (typically 7-day time travel). If we need long-term physical snapshots, we can trigger BigQuery Table Snapshots after major scrapes.

*We will go with Option 1 (Append-Only with Timestamps), as it provides the most Iceberg-like querying experience (`SELECT * FROM bronze_spotrac WHERE _ingestion_timestamp = MAX(...)`).*

---

## Proposed Changes

### 1. Refactor Scraper Outputs (`pipeline/src/spotrac_scraper_v2.py` / `scrape_pfr.py`)
Instead of the scrapers exclusively dumping `.csv` files locally via `pd.to_csv()`, we will decouple the I/O. The scrapers will return the Pandas DataFrames directly to the orchestration script.

### 2. Refactor `BronzeLayer` direct Ingestion (`medallion_pipeline.py`)
We will rewrite the `BronzeLayer` class to orchestrate the scrapers and invoke `DBManager`'s dataframe upload using an append strategy.

#### [MODIFY] `pipeline/scripts/medallion_pipeline.py`
```python
class BronzeLayer:
    def __init__(self, db: DBManager):
        self.db = db

    def ingest_spotrac_contracts(self, year: int):
        from src.spotrac_scraper_v2 import SpotracScraper
        
        with SpotracScraper(headless=True) as scraper:
            df = scraper.scrape_player_contracts(year)
            
            # Add Iceberg-like versioning column
            df['_ingestion_timestamp'] = pd.Timestamp.utcnow()
            
            # BigQuery Append (via a direct load job rather than DELETE/INSERT)
            # We will expose a method in DBManager to handle append vs truncate
            self.db.append_dataframe_to_table(df, "bronze_spotrac_contracts")
```

### 3. Refactor `SilverLayer` Querying
The `SilverLayer` will now pull the *latest* version of the truth from the Bronze tables using a Window function or a simple `MAX(_ingestion_timestamp)` filter:

```sql
WITH latest_raw AS (
    SELECT *
    FROM bronze_spotrac_contracts
    WHERE _ingestion_timestamp = (
        SELECT MAX(_ingestion_timestamp) 
        FROM bronze_spotrac_contracts 
        WHERE year = {year}
    )
    AND year = {year}
)
...
```

### 4. `DBManager` Enhancements
#### [MODIFY] `pipeline/src/db_manager.py`
We will add a helper method `self.db.append_dataframe_to_table(df, "table_name")` which utilizes BigQuery's `client.load_table_from_dataframe(..., job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND"))`.

---

## User Review Required
> [!IMPORTANT]
> - By transitioning to direct BigQuery ingestion, you will need active internet/GCP access to run local tests.
> - The Append-Only strategy means the `bronze_` tables will grow over time. Since storage is cheap, this shouldn't impact compute costs unless you query the full table constantly.
> 
> Are you ready to begin execution?

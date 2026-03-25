import os
import sys
import logging
import duckdb
import json
import decimal
from google.cloud import bigquery
from google.oauth2 import service_account

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

import argparse

def sync():
    parser = argparse.ArgumentParser(description="Sync local DuckDB to Google BigQuery and/or Frontend JSON.")
    parser.add_argument("--year", type=int, help="Specific year to dump for frontend (default: latest in DB).")
    parser.add_argument("--skip-bigquery", action="store_true", help="Skip syncing to BigQuery cloud.")
    parser.add_argument("--skip-json", action="store_true", help="Skip dumping JSON for frontend.")
    args = parser.parse_args()

    project_id = os.getenv("GCP_PROJECT_ID")
    local_db = os.getenv("DB_PATH", "data/duckdb/nfl_production.db")
    dataset_id = "nfl_dead_money"
    
    if not os.path.exists(local_db):
        logger.error(f"Local database not found at {local_db}")
        sys.exit(1)

    # 1. JSON Bridge
    if not args.skip_json:
        try:
            logger.info("Starting JSON Bridge Sync (Frontend Hydration)...")
            dump_con = duckdb.connect(local_db, read_only=True)
            tables = dump_con.execute("SELECT table_name FROM information_schema.tables").fetchall()
            table_names = [t[0] for t in tables]
            
            if "fact_player_efficiency" not in table_names:
                 logger.warning("Gold layer table 'fact_player_efficiency' not found in local DB. Skipping JSON dump.")
            else:
                target_year = args.year
                if not target_year:
                    res_year = dump_con.execute("SELECT MAX(year) FROM fact_player_efficiency").fetchone()
                    target_year = res_year[0] if res_year and res_year[0] else 2025
                    logger.info(f"Detected latest season: {target_year}")

                dump_query = f"SELECT * FROM fact_player_efficiency WHERE year = {target_year}"
                res = dump_con.execute(dump_query)
                columns = [desc[0] for desc in res.description]
                rows = res.fetchall()
                
                cleaned_records = []
                for row in rows:
                    record = {}
                    for col_name, val in zip(columns, row):
                        if isinstance(val, decimal.Decimal):
                            val = float(val)
                        record[col_name] = val
                    cleaned_records.append(record)
                    
                output_path = os.path.join("web", "data", "roster_dump.json")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w') as f:
                    json.dump(cleaned_records, f)
                logger.info(f"✓ Dumped {len(cleaned_records)} records to {output_path}")
            dump_con.close()
        except Exception as e:
            logger.error(f"Failed during JSON dump: {e}")

    # 2. BigQuery Sync
    if not args.skip_bigquery:
        if not project_id:
            logger.error("GCP_PROJECT_ID missing. Cannot sync to BigQuery.")
            sys.exit(1)
            
        logger.info(f"Connecting to BigQuery (Project: {project_id})...")
        
        credentials_json = os.environ.get('GCP_SERVICE_ACCOUNT_JSON')
        if credentials_json:
            credentials_dict = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_dict)
            client = bigquery.Client(project=project_id, credentials=credentials)
        else:
            client = bigquery.Client(project=project_id)
            
        dataset_ref = client.dataset(dataset_id)
        try:
            client.get_dataset(dataset_ref)
            logger.info(f"Dataset {dataset_id} confirmed active.")
        except Exception:
            client.create_dataset(bigquery.Dataset(dataset_ref))
            logger.info(f"Dataset {dataset_id} automatically generated.")

        dump_con = duckdb.connect(local_db, read_only=True)
        tables = dump_con.execute("SELECT table_name FROM information_schema.tables").fetchall()

        for table in tables:
            table_name = table[0]
            logger.info(f"Extracting {table_name} matrix into Pandas dataframe...")
            df = dump_con.execute(f"SELECT * FROM {table_name}").df()
            
            table_ref = f"{project_id}.{dataset_id}.{table_name}"
            # Force BigQuery replacement payload matching the MotherDuck truncation overwrite
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
            
            logger.info(f"Pushing table {table_name} to GCP...")
            job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
            job.result()
            
            logger.info(f"✓ Merged {len(df)} records into exactly: {table_ref}")
            
        dump_con.close()
        logger.info("=== Full Medallion Pipeline Migration Confirmed ===")

if __name__ == "__main__":
    sync()

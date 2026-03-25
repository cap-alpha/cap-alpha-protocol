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
            
            # Prevent PyArrow Parquet serialization hangs on nested JSON structs
            for col in df.columns:
                if df[col].dtype == 'object':
                    df[col] = df[col].astype(str)
            
            # Identify merge keys dynamically based on typical DDL
            merge_keys = []
            if 'player_name' in df.columns and 'team' in df.columns and 'year' in df.columns:
                merge_keys = ['player_name', 'team', 'year']
            elif 'team' in df.columns and 'year' in df.columns:
                merge_keys = ['team', 'year']
            elif 'year' in df.columns:
                merge_keys = ['year']
            elif 'team' in df.columns:
                merge_keys = ['team']
                
            if not merge_keys:
                # Force BigQuery replacement payload fallback
                job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                logger.info(f"Pushing table {table_name} to GCP (Fallback TRUNCATE)...")
                job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
                job.result()
                logger.info(f"✓ Replaced {len(df)} records into exactly: {table_ref}")
            else:
                # Deduplicate based on keys to prevent MERGE failure
                df = df.drop_duplicates(subset=merge_keys)
                temp_table_ref = f"{project_id}.{dataset_id}.{table_name}_temp"
                job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                client.load_table_from_dataframe(df, temp_table_ref, job_config=job_config).result()
                
                columns = df.columns.tolist()
                join_cond = " AND ".join([f"T.{k} = S.{k}" for k in merge_keys])
                update_cols = [col for col in columns if col not in merge_keys]
                
                if update_cols:
                    update_cond = ", ".join([f"{col} = S.{col}" for col in update_cols])
                    merge_query = f"""
                        MERGE `{table_ref}` T
                        USING `{temp_table_ref}` S
                        ON {join_cond}
                        WHEN MATCHED THEN
                            UPDATE SET {update_cond}
                        WHEN NOT MATCHED THEN
                            INSERT ({", ".join(columns)})
                            VALUES ({", ".join([f"S.{col}" for col in columns])})
                    """
                else:
                    merge_query = f"""
                        MERGE `{table_ref}` T
                        USING `{temp_table_ref}` S
                        ON {join_cond}
                        WHEN NOT MATCHED THEN
                            INSERT ({", ".join(columns)})
                            VALUES ({", ".join([f"S.{col}" for col in columns])})
                    """

                try:
                    # Check if table exists
                    client.get_table(table_ref)
                    logger.info(f"Merging table {table_name} into GCP using keys {merge_keys}...")
                    client.query(merge_query).result()
                except Exception:
                    logger.info(f"Table {table_name} not found, creating via TRUNCATE...")
                    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                    client.load_table_from_dataframe(df, table_ref, job_config=job_config).result()
                    
                client.delete_table(temp_table_ref, not_found_ok=True)
                logger.info(f"✓ Upserted {len(df)} records into: {table_ref}")
            
        dump_con.close()
        logger.info("=== Full Medallion Pipeline Migration Confirmed ===")

if __name__ == "__main__":
    sync()

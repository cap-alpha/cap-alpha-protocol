import os

import duckdb
import pandas as pd
from google.cloud import bigquery


def main():
    print("Starting Historical Bulk Load from DuckDB to BigQuery (Chunked)...")
    duckdb_path = "/app/data/duckdb/nfl_production.db"
    if not os.path.exists(duckdb_path):
        print(f"Error: {duckdb_path} not found.")
        return

    con = duckdb.connect(duckdb_path, read_only=True)
    tables_df = con.execute("SHOW TABLES").df()
    tables = tables_df["name"].tolist()

    target_tables = [
        t
        for t in tables
        if t.startswith("silver_")
        or t.startswith("fact_")
        or t.startswith("prediction_")
        or t == "staging_feature_matrix"
    ]

    print(f"Found {len(target_tables)} tables to migrate.")

    project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
    bq = bigquery.Client(project=project_id)
    dataset_id = "nfl_dead_money"

    for table_name in target_tables:
        print(f"\nProcessing {table_name}...")
        df = con.execute(f"SELECT * FROM {table_name}").df()

        if df.empty:
            print(f"-> Table {table_name} is empty. Skipping.")
            continue

        # Clean Pandas DF types for BQ
        df.columns = df.columns.astype(str).str.replace(
            r"[^a-zA-Z0-9_]", "_", regex=True
        )
        for col in df.columns:
            if str(df[col].dtype) == "object":
                df[col] = df[col].astype(str)
                df.loc[df[col] == "nan", col] = None
            elif str(df[col].dtype).startswith("datetime64"):
                df[col] = df[col].dt.strftime("%Y-%m-%d %H:%M:%S")
                df.loc[df[col].isna(), col] = None

        table_ref = f"{bq.project}.{dataset_id}.{table_name}"

        # Determine chunking strategy
        has_year = "year" in df.columns or "season" in df.columns
        has_team = (
            "team" in df.columns or "team_id" in df.columns or "team_name" in df.columns
        )

        first_chunk = True

        if has_year and has_team:
            year_col = "year" if "year" in df.columns else "season"
            team_col = (
                "team"
                if "team" in df.columns
                else ("team_id" if "team_id" in df.columns else "team_name")
            )
            print(f"-> Chunking by {year_col} and {team_col}...")

            groups = df.groupby([year_col, team_col])
            print(f"-> Found {len(groups)} chunks.")

            for (yr, tm), chunk_df in groups:
                if chunk_df.empty:
                    continue
                disp = "WRITE_TRUNCATE" if first_chunk else "WRITE_APPEND"
                first_chunk = False
                job_config = bigquery.LoadJobConfig(write_disposition=disp)

                print(f"   -> Uploading {yr} {tm} ({len(chunk_df)} rows)...")
                try:
                    job = bq.load_table_from_dataframe(
                        chunk_df, table_ref, job_config=job_config
                    )
                    job.result()
                except Exception as e:
                    print(f"   -> FAILED uploading chunk {yr} {tm}: {e}")

        elif has_year:
            year_col = "year" if "year" in df.columns else "season"
            print(f"-> Chunking by {year_col} only...")
            groups = df.groupby(year_col)
            for yr, chunk_df in groups:
                disp = "WRITE_TRUNCATE" if first_chunk else "WRITE_APPEND"
                first_chunk = False
                job_config = bigquery.LoadJobConfig(write_disposition=disp)

                print(f"   -> Uploading {yr} ({len(chunk_df)} rows)...")
                try:
                    job = bq.load_table_from_dataframe(
                        chunk_df, table_ref, job_config=job_config
                    )
                    job.result()
                except Exception as e:
                    print(f"   -> FAILED uploading chunk {yr}: {e}")

        elif has_team:
            team_col = (
                "team"
                if "team" in df.columns
                else ("team_id" if "team_id" in df.columns else "team_name")
            )
            print(f"-> Chunking by {team_col} only...")
            groups = df.groupby(team_col)
            for tm, chunk_df in groups:
                disp = "WRITE_TRUNCATE" if first_chunk else "WRITE_APPEND"
                first_chunk = False
                job_config = bigquery.LoadJobConfig(write_disposition=disp)

                print(f"   -> Uploading {tm} ({len(chunk_df)} rows)...")
                try:
                    job = bq.load_table_from_dataframe(
                        chunk_df, table_ref, job_config=job_config
                    )
                    job.result()
                except Exception as e:
                    print(f"   -> FAILED uploading chunk {tm}: {e}")

        else:
            # Fallback row batching
            batch_size = 5000
            print(f"-> Chunking by {batch_size} rows...")
            for i in range(0, len(df), batch_size):
                chunk_df = df.iloc[i : i + batch_size]
                disp = "WRITE_TRUNCATE" if first_chunk else "WRITE_APPEND"
                first_chunk = False
                job_config = bigquery.LoadJobConfig(write_disposition=disp)

                print(f"   -> Uploading rows {i} to {i+len(chunk_df)}...")
                try:
                    job = bq.load_table_from_dataframe(
                        chunk_df, table_ref, job_config=job_config
                    )
                    job.result()
                except Exception as e:
                    print(f"   -> FAILED uploading rows {i}: {e}")

        print(f"-> Successfully Bulk-Loaded {table_name}!")


if __name__ == "__main__":
    main()

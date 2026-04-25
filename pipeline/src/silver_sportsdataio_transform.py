import logging

import pandas as pd
from db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_silver_transformation():
    """
    Transforms raw JSON from bronze_sportsdataio_players
    into the canonical silver_player_metadata table.
    """
    logger.info(
        "Starting Silver Transformation: SportsData.io -> silver_player_metadata"
    )

    with DBManager() as db:
        # 1. Read Bronze Data
        query = f"SELECT * FROM `{db.project_id}.{db.dataset_id}.bronze_sportsdataio_players`"
        df_bronze = db.fetch_df(query)
        logger.info(f"Loaded {len(df_bronze)} records from Bronze.")

        # 2. Transform to match silver_player_metadata schema
        # Expected: full_name, birth_date, college, draft_round, draft_pick, experience_years

        df_silver = pd.DataFrame()

        # In SportsData.io, 'Name' contains the full name.
        # Sometimes 'FirstName' and 'LastName' are preferred for robustness.
        df_silver["full_name"] = df_bronze["Name"]

        # Clean BirthDate (Comes as 1984-08-10T00:00:00)
        df_silver["birth_date"] = pd.to_datetime(
            df_bronze["BirthDate"], errors="coerce"
        ).dt.strftime("%Y-%m-%d")

        df_silver["college"] = df_bronze["College"]
        df_silver["experience_years"] = (
            pd.to_numeric(df_bronze["Experience"], errors="coerce")
            .fillna(0)
            .astype(int)
        )

        # SportsDataIO doesn't always provide draft_round directly in this endpoint. We pad with NULL/NaN
        # Or if it's there (DraftRound / DraftPick), map it:
        if "DraftRound" in df_bronze.columns:
            df_silver["draft_round"] = (
                pd.to_numeric(df_bronze["DraftRound"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
            df_silver["draft_pick"] = (
                pd.to_numeric(df_bronze["DraftPick"], errors="coerce")
                .fillna(0)
                .astype(int)
            )
        else:
            df_silver["draft_round"] = 0
            df_silver["draft_pick"] = 0

        # We also want to capture the PhotoUrl and current Team and Position so we can inject that into downstream!
        # The schema.yaml for silver_player_metadata didn't explicitly list PhotoUrl, but we must add it for the frontend regressions!
        df_silver["team"] = df_bronze["Team"]
        df_silver["position"] = df_bronze["Position"]
        df_silver["photo_url"] = df_bronze["PhotoUrl"]
        df_silver["status"] = df_bronze["Status"]  # Active, Inactive, etc.

        # 3. Write to Silver Table
        table_ref = f"{db.project_id}.{db.dataset_id}.silver_player_metadata"
        logger.info(f"Writing {len(df_silver)} transformed records to {table_ref}...")

        from google.cloud import bigquery

        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")

        # Sanitize object types
        for col in df_silver.columns:
            if df_silver[col].dtype == "object":
                df_silver[col] = df_silver[col].astype(str)

        # Fix NaNs representing strings from coerced pandas types
        df_silver.replace("nan", "", inplace=True)
        df_silver.replace("None", "", inplace=True)

        job = db.client.load_table_from_dataframe(
            df_silver, table_ref, job_config=job_config
        )
        job.result()
        logger.info("Silver Transformation Complete.")


if __name__ == "__main__":
    run_silver_transformation()

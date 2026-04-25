import hashlib
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from src.db_manager import DBManager

logger = logging.getLogger(__name__)


def generate_surrogate_keys(df: pd.DataFrame) -> pd.DataFrame:
    """Generates contract_id and player_id deterministically for SCD tracking."""
    if df is None or df.empty:
        return df

    def make_contract_id(row):
        s = f"{row.get('player_name', '')}_{row.get('team', '')}_{row.get('year', '')}".lower().encode(
            "utf-8"
        )
        return hashlib.md5(s).hexdigest()

    def make_player_id(row):
        s = f"{row.get('player_name', '')}".lower().encode("utf-8")
        return hashlib.md5(s).hexdigest()

    df["contract_id"] = df.apply(make_contract_id, axis=1)
    df["player_id"] = df.apply(make_player_id, axis=1)
    return df


def execute_scd2_merge(
    db: DBManager, df: pd.DataFrame, target_table: str = "silver_spotrac_contracts"
):
    """
    Executes an Immutable SCD Type 2 Ledger append.
    Uses BigQuery MERGE to sunset old records (is_current=false) and append active ones.
    """
    if df is None or df.empty:
        logger.warning("Empty dataframe provided to execute_scd2_merge.")
        return

    # Add default SCD metrics for the incoming payloads before loading to staging
    df["effective_start_date"] = pd.Timestamp.utcnow()
    df["effective_end_date"] = pd.NaT  # Null
    df["is_current"] = True
    df["system_ingest_time"] = pd.Timestamp.utcnow()

    # Strictly isolate single definitive snapshot per surrogate key per batch
    df = df.drop_duplicates(subset=["contract_id"], keep="last")

    # Create a staging table name
    stg_table = f"{target_table}_stg_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Push df directly to BigQuery Staging Table
    db.append_dataframe_to_table(df, stg_table)
    full_target = f"{db.project_id}.{db.dataset_id}.{target_table}"
    full_stg = f"{db.project_id}.{db.dataset_id}.{stg_table}"

    # BigQuery MERGE Statement
    merge_sql = f"""
    -- Step 1: Update existing records to sunset them if a new payload for the same contract_id arrives
    MERGE `{full_target}` T
    USING `{full_stg}` S
    ON T.contract_id = S.contract_id AND T.is_current = TRUE
    WHEN MATCHED THEN
      UPDATE SET 
        T.effective_end_date = CURRENT_TIMESTAMP(),
        T.is_current = FALSE;
    """

    # We must run the INSERT as a separate statement or a nested array approach since BigQuery
    # MERGE does not allow a matched row to simultaneously update the old row AND insert the new one in a single pass.
    # Therefore, we sunset the old row in MERGE and then INSERT all incoming rows directly below to build the ledger history!

    insert_sql = f"""
    -- Step 2: Append all strictly incoming rows as the new 'Current' truth
    INSERT INTO `{full_target}` (
        contract_id, player_id, player_name, team, year, position, 
        cap_hit_millions, dead_cap_millions, signing_bonus_millions, 
        guaranteed_money_millions, total_contract_value_millions, 
        base_salary_millions, prorated_bonus_millions, roster_bonus_millions, 
        guaranteed_salary_millions, age, 
        effective_start_date, effective_end_date, is_current, system_ingest_time
    )
    SELECT 
        contract_id, player_id, player_name, team, year, position, 
        cap_hit_millions, dead_cap_millions, signing_bonus_millions, 
        guaranteed_money_millions, total_contract_value_millions, 
        base_salary_millions, prorated_bonus_millions, roster_bonus_millions, 
        guaranteed_salary_millions, age, 
        SAFE_CAST(effective_start_date AS TIMESTAMP), SAFE_CAST(effective_end_date AS TIMESTAMP), is_current, SAFE_CAST(system_ingest_time AS TIMESTAMP)
    FROM `{full_stg}`;
    """

    drop_stg = f"DROP TABLE IF EXISTS `{full_stg}`;"

    try:
        logger.info(
            f"Executing SCD Type 2 MERGE for {len(df)} rows into {target_table}..."
        )
        db.execute(merge_sql)
        db.execute(insert_sql)
        db.execute(drop_stg)
        logger.info(f"SCD Type 2 Load Complete for {target_table}.")
    except Exception as e:
        logger.error(f"Failed SCD2 execution: {e}")
        db.execute(drop_stg)
        raise e

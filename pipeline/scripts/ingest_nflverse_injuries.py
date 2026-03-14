import pandas as pd
import logging
import os
import sys

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from pipeline.src.db_manager import DBManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def ingest_historical_injuries():
    """
    Downloads the nflverse injuries parquet files by year and persists 
    the raw text strings to the Medallion Bronze layer in MotherDuck.
    """
    logger.info("Downloading nflverse historical injury data by year...")
    dfs = []
    
    for year in range(2018, 2025):
        url = f"https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{year}.parquet"
        logger.info(f"Fetching {year} from {url}...")
        try:
            df_year = pd.read_parquet(url)
            dfs.append(df_year)
        except Exception as e:
            logger.error(f"Failed to fetch {year}: {e}")
            
    if not dfs:
        logger.error("No injury data acquired.")
        return False
        
    try:
        df_injuries = pd.concat(dfs, ignore_index=True)
        logger.info(f"Successfully aggregated {len(df_injuries)} injury records for 2018-2024.")
        
        # Display sample columns
        logger.info(f"Columns discovered: {df_injuries.columns.tolist()}")
        
        # We want to keep the raw string columns focused on status and injury type
        
        db = DBManager()
        
        # Create a bronze table for raw injuries
        logger.info("Persisting raw unstructured injury strings to MotherDuck: bronze_layer.nflverse_injuries")
        db.execute("CREATE SCHEMA IF NOT EXISTS bronze_layer")
        db.execute(
            "CREATE OR REPLACE TABLE bronze_layer.nflverse_injuries AS SELECT * FROM df_injuries", 
            {"df_injuries": df_injuries}
        )
        
        logger.info("✅ Successfully hydrated bronze_layer.nflverse_injuries")
        return True

    except Exception as e:
        logger.error(f"Failed to process and insert nflverse injury data: {e}")
        return False

if __name__ == "__main__":
    ingest_historical_injuries()

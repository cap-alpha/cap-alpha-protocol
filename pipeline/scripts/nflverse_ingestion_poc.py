import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def ingest_nflverse_contracts():
    """
    POC: Ingest player contracts from the nflverse GitHub release.
    This bypasses Selenium/Scraping entirely and uses open-source datasets.
    """
    URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/player_contracts.parquet"

    logger.info(f"Downloading nflverse contract data from {URL}...")
    try:
        df = pd.read_parquet(URL)
        logger.info(f"Successfully ingested {len(df)} contract records.")

        # Display sample columns for verification
        logger.info(f"Columns: {df.columns.tolist()}")

        # Filter for recent year to show relevance
        if "season" in df.columns:
            recent = df[df["season"] >= 2024]
            logger.info(f"Found {len(recent)} records for 2024+.")

        return df
    except Exception as e:
        logger.error(f"Failed to ingest nflverse data: {e}")
        return None


if __name__ == "__main__":
    df = ingest_nflverse_contracts()
    if df is not None:
        # Save a sample to verify structure
        df.head(10).to_csv("data/nflverse_contracts_sample.csv", index=False)
        print("\n✅ POC SUCCESS: Sample saved to data/nflverse_contracts_sample.csv")

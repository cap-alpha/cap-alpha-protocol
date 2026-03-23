"""
manual_backfill.py 
Specifically designed to hydrate missing recent years (e.g. 2025/2026) directly into the Medallion Architecture
without having to re-run the entire 2011-2024 massive ingestion suite.
"""
import argparse
import subprocess
import logging
import sys
from src.data_validation import get_current_nfl_year

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    current_year = get_current_nfl_year()
    # If the current year is 2026, default backfill is 2024, 2025, 2026
    default_years = ",".join(str(y) for y in range(max(2024, current_year - 2), current_year + 1))
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=str, default=default_years, help="Comma separated years to backfill")
    args = parser.parse_args()
    
    years = [int(y.strip()) for y in args.years.split(',')]
    
    for y in years:
        logger.info(f"🚀 Hydrating Year {y}...")
        cmd = f"export PYTHONPATH=$PYTHONPATH:. && {sys.executable} pipeline/scripts/medallion_pipeline.py --year {y} --skip-gold"
        try:
            subprocess.run(cmd, shell=True, check=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Failed to hydrate year {y}")
            sys.exit(e.returncode)
        
    logger.info("🛠️ Building Gold Layer from new Bronze/Silver tables...")
    cmd_gold = f"export PYTHONPATH=$PYTHONPATH:. && {sys.executable} pipeline/scripts/medallion_pipeline.py --year {max(years)} --gold-only"
    try:
        subprocess.run(cmd_gold, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("❌ Failed to build Gold Layer")
        sys.exit(e.returncode)
        
    logger.info(f"✅ Backfill Complete for years: {years}")

if __name__ == "__main__":
    main()

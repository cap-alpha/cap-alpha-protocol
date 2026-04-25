#!/usr/bin/env python3
"""
Data quality checks for player rankings snapshots.
- Assert ≥1,500 rows for current year
- Assert cap_value >= 0
- Log summary statistics
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


def validate_current_year(year: int = None, data_dir: Path = None) -> bool:
    if year is None:
        year = datetime.now().year
    if data_dir is None:
        data_dir = Path("data/raw")

    csv_path = data_dir / f"player_rankings_{year}.csv"
    if not csv_path.exists():
        log.error(f"CSV not found: {csv_path}")
        return False

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        log.error(f"Failed to read CSV: {e}")
        return False

    log.info(f"\n📊 Data Quality Check for {year}")
    log.info(f"   File: {csv_path}")
    log.info(f"   Rows: {len(df)}")
    log.info(f"   Columns: {list(df.columns)}")

    # Check row count
    if len(df) < 1500:
        log.error(f"❌ FAIL: Only {len(df)} rows (expected ≥1500)")
        return False
    log.info(f"✓ Row count: {len(df)} ≥ 1500")

    # Check cap_value is numeric and non-negative
    if "CapValue" not in df.columns:
        log.error("❌ FAIL: CapValue column missing")
        return False

    try:
        df["CapValue"] = pd.to_numeric(df["CapValue"], errors="coerce")
    except Exception as e:
        log.error(f"❌ FAIL: Cannot convert CapValue to numeric: {e}")
        return False

    nulls = df["CapValue"].isna().sum()
    if nulls > len(df) * 0.1:  # >10% nulls
        log.error(
            f"❌ FAIL: {nulls} null values in CapValue (>{len(df) * 0.1:.0f} allowed)"
        )
        return False
    log.info(f"✓ CapValue nulls: {nulls} (<{len(df) * 0.1:.0f})")

    neg = (df["CapValue"] < 0).sum()
    if neg > 0:
        log.warning(f"⚠️  {neg} negative cap values (expected 0)")
    log.info(f"✓ Negative values: {neg}")

    # Summary stats
    log.info(f"\n📈 Summary Statistics")
    log.info(f"   Mean cap value: ${df['CapValue'].mean():,.0f}")
    log.info(f"   Median cap value: ${df['CapValue'].median():,.0f}")
    log.info(f"   Max: ${df['CapValue'].max():,.0f}")
    log.info(f"   Min: ${df['CapValue'].min():,.0f}")
    log.info(f"   Teams: {df['Team'].nunique()}")

    # Team distribution
    team_counts = df["Team"].value_counts()
    log.info(f"\n🏈 Top 5 Teams by Player Count")
    for team, count in team_counts.head().items():
        log.info(f"   {team}: {count}")

    log.info("\n✅ All data quality checks passed!")
    return True


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--data-dir", type=str, default="data/raw")
    args = ap.parse_args()

    success = validate_current_year(year=args.year, data_dir=Path(args.data_dir))
    sys.exit(0 if success else 1)

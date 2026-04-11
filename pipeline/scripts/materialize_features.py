#!/usr/bin/env python3
"""
Materialize Features Pipeline

This script is the dedicated pipeline step for materializing features into the
BigQuery-backed Feature Store. It should be run after ingestion and before training.

Pipeline Order:
1. medallion_pipeline.py (Bronze -> Silver -> Gold)
2. materialize_features.py (Gold -> Feature Store)  <- THIS SCRIPT
3. train_model.py (Feature Store -> Model)

Usage:
    python scripts/materialize_features.py [--validate-only]
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db_manager import DBManager
from src.feature_store import FeatureStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def materialize_all_features(validate_only: bool = False):
    """
    Materialize all features into the Feature Store.

    Args:
        validate_only: If True, only validate existing features without re-materializing
    """
    db = DBManager()
    store = FeatureStore(db=db)

    # Initialize schema (idempotent)
    store.initialize_schema()

    if validate_only:
        logger.info("=== Validation Only Mode ===")
        is_valid = store.validate_temporal_integrity()
        stats = store.get_feature_stats()
        print("\n=== Feature Store Statistics ===")
        print(stats)
        return is_valid

    # Step 1: Materialize Lag Features (critical for preventing leakage)
    logger.info("=== Step 1: Materializing Lag Features ===")
    store.materialize_lag_features(source_table="fact_player_efficiency")

    # Step 2: Materialize Interaction Features
    logger.info("=== Step 2: Materializing Interaction Features ===")
    store.materialize_interaction_features(source_table="fact_player_efficiency")

    # Step 3: Validate Temporal Integrity
    logger.info("=== Step 3: Validating Temporal Integrity ===")
    is_valid = store.validate_temporal_integrity()

    # Step 4: Report Statistics
    stats = store.get_feature_stats()
    print("\n=== Feature Store Statistics ===")
    print(stats)

    # Step 5: Sample verification
    logger.info("=== Step 4: Sample Point-in-Time Check ===")
    sample = db.fetch_df("""
        SELECT player_name, prediction_year, feature_name, feature_value, valid_from
        FROM feature_values
        WHERE feature_name = 'total_tds_lag_1'
        ORDER BY RAND()
        LIMIT 5
    """)
    print("\nSample lag_1 features (valid_from should be prediction_year - 1):")
    print(sample)

    if is_valid:
        logger.info("Feature materialization complete. Zero temporal violations.")
    else:
        logger.error("Feature materialization complete but violations detected!")

    return is_valid


def main():
    parser = argparse.ArgumentParser(
        description="Materialize features into Feature Store"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Only validate existing features without re-materializing",
    )
    args = parser.parse_args()

    success = materialize_all_features(validate_only=args.validate_only)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

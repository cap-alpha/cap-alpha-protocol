"""
Feature Store: Point-in-Time Feature Management

This module provides a DuckDB-based feature store that prevents temporal data leakage
by ensuring features are retrieved with strict point-in-time semantics.

Key Concepts:
- Every feature value has a `valid_from` date (when the feature became known)
- Point-in-time queries ensure we only retrieve features available at prediction time
- Prevents future leakage by construction, not post-hoc validation

Usage:
    from src.feature_store import FeatureStore

    store = FeatureStore()
    store.initialize_schema()

    # Materialize features
    store.materialize_lag_features(source_table='fact_player_efficiency')

    # Retrieve for training (point-in-time)
    features = store.get_training_matrix(as_of_year=2024)
"""

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from src.config_loader import get_db_path
from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = get_db_path()


class FeatureStore:
    """DuckDB-based Feature Store with point-in-time semantics."""

    def __init__(self, db_path: str = DB_PATH, read_only: bool = False):
        self.db = DBManager(db_path)
        self.con = self.db.con
        self.read_only = read_only

    def initialize_schema(self):
        """Create feature store tables if they don't exist."""
        if self.read_only:
            logger.info("Database is read-only. Skipping schema initialization.")
            return

        logger.info("Initializing Feature Store schema...")

        # Feature Registry: Metadata about each feature
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS feature_registry (
                feature_name VARCHAR PRIMARY KEY,
                feature_type VARCHAR,  -- 'lag', 'derived', 'raw', 'interaction'
                source_column VARCHAR,
                lag_periods INTEGER,
                description VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Feature Values: The actual feature data with temporal validity
        # Changed: valid_from is DATE, added valid_until
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS feature_values (
                entity_key VARCHAR,           -- player_name||'_'||year
                player_name VARCHAR,
                prediction_year INTEGER,      -- Year we're making a prediction for
                feature_name VARCHAR,
                feature_value DOUBLE,
                valid_from DATE,              -- Date feature became known
                valid_until DATE,             -- Date feature became superseded (NULL if current)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (entity_key, feature_name, valid_from)
            )
        """)

        # Create index for efficient point-in-time queries
        self.con.execute("""
            CREATE INDEX IF NOT EXISTS idx_feature_pit 
            ON feature_values (player_name, valid_from, valid_until)
        """)

        logger.info("✓ Feature Store schema initialized.")

    def register_feature(
        self,
        feature_name: str,
        feature_type: str,
        source_column: str = None,
        lag_periods: int = None,
        description: str = None,
    ):
        """Register a feature in the registry."""
        self.con.execute(
            """
            INSERT OR REPLACE INTO feature_registry 
            (feature_name, feature_type, source_column, lag_periods, description)
            VALUES (?, ?, ?, ?, ?)
        """,
            [feature_name, feature_type, source_column, lag_periods, description],
        )

    def materialize_lag_features(self, source_table: str = "fact_player_efficiency"):
        """
        Materialize lag features with strict point-in-time semantics.

        For each (player, year) pair, compute lag_1, lag_2, lag_3 features.
        Validity Rule: Data from Season Y is valid from (Y+1)-02-15.
        """
        logger.info(f"Materializing lag features from {source_table}...")

        # Define which columns to compute lags for
        lag_columns = [
            "total_pass_yds",
            "total_rush_yds",
            "total_rec_yds",
            "total_tds",
            "games_played",
            "cap_hit_millions",
            "dead_cap_millions",
            "age",
        ]

        # Clear existing lag features
        self.con.execute("""
            DELETE FROM feature_values 
            WHERE feature_name LIKE '%_lag_%'
        """)

        # Register and materialize each lag feature
        for col in lag_columns:
            # Check if column exists in source
            cols_df = self.con.execute(f"DESCRIBE {source_table}").df()
            if col not in cols_df["column_name"].values:
                logger.warning(f"Column {col} not in {source_table}, skipping.")
                continue

            for lag in [1, 2, 3]:
                feature_name = f"{col}_lag_{lag}"

                # Register the feature
                self.register_feature(
                    feature_name=feature_name,
                    feature_type="lag",
                    source_column=col,
                    lag_periods=lag,
                    description=f"{col} from {lag} year(s) prior",
                )

                # Materialize with strict temporal semantics
                # Lag 1: Target Year 2024. Source Year 2023.
                # Valid From: 2024-02-15 (After 2023 season ends)
                # Valid Until: 2025-02-15 (When 2024 season data becomes available)

                self.con.execute(f"""
                    INSERT INTO feature_values (entity_key, player_name, prediction_year, 
                                                feature_name, feature_value, valid_from, valid_until)
                    SELECT 
                        target.player_name || '_' || target.year as entity_key,
                        target.player_name,
                        target.year as prediction_year,
                        '{feature_name}' as feature_name,
                        source.{col} as feature_value,
                        -- Validity Logic:
                        -- If source year is Y, data is known in Feb of Y+1
                        -- Example: 2022 stats known 2023-02-15.
                        -- Valid for predicting 2023 season (which starts Sept 2023).
                        make_date(source.year + 1, 2, 15) as valid_from,
                        make_date(source.year + 2, 2, 15) as valid_until
                    FROM {source_table} target
                    INNER JOIN {source_table} source
                        ON target.player_name = source.player_name
                        AND source.year = target.year - {lag}
                    WHERE source.{col} IS NOT NULL
                    ON CONFLICT (entity_key, feature_name, valid_from) DO UPDATE 
                        SET feature_value = EXCLUDED.feature_value,
                            valid_until = EXCLUDED.valid_until
                """)

        # Log summary
        count = self.con.execute("SELECT COUNT(*) FROM feature_values").fetchone()[0]
        logger.info(f"✓ Materialized {count:,} feature values in store.")

    def materialize_interaction_features(
        self, source_table: str = "fact_player_efficiency"
    ):
        """Materialize derived/interaction features."""
        logger.info("Materializing interaction features...")

        interactions = [
            (
                "age_cap_interaction",
                "age * cap_hit_millions",
                "Age × Cap Hit interaction",
            ),
            ("experience_risk", "draft_round * age", "Draft round × Age risk"),
        ]

        for feature_name, formula, description in interactions:
            self.register_feature(
                feature_name=feature_name,
                feature_type="interaction",
                description=description,
            )

            try:
                # Interactions are instantaneous for the target year (derived from other features normally)
                # But here we are deriving from raw source table for simplicity.
                # These are "known" when the component parts are known.
                # Assuming these are static traits or current contract info known at start of league year.
                # We'll set valid_from to March 1st of the year (start of league year approx).

                self.con.execute(f"""
                    INSERT INTO feature_values (entity_key, player_name, prediction_year, 
                                                feature_name, feature_value, valid_from, valid_until)
                    SELECT 
                        player_name || '_' || year as entity_key,
                        player_name,
                        year as prediction_year,
                        '{feature_name}' as feature_name,
                        {formula} as feature_value,
                        make_date(year, 3, 15) as valid_from, -- known mid-March (League Year)
                        make_date(year + 1, 3, 15) as valid_until
                    FROM {source_table}
                    WHERE {formula.split('*')[0].strip()} IS NOT NULL
                    ON CONFLICT (entity_key, feature_name, valid_from) DO UPDATE 
                        SET feature_value = EXCLUDED.feature_value
                """)
            except Exception as e:
                logger.warning(f"Could not compute {feature_name}: {e}")

        count = self.con.execute("""
            SELECT COUNT(*) FROM feature_values 
            WHERE feature_name IN ('age_cap_interaction', 'experience_risk')
        """).fetchone()[0]
        logger.info(f"✓ Materialized {count:,} interaction features.")

    def get_training_matrix(
        self, as_of_date: date, min_year: int = 2015
    ) -> pd.DataFrame:
        """
        Get feature matrix for training with strict point-in-time semantics as of a SINGLE date.
        Useful for Inference or specific backtest folds.

        Args:
            as_of_date: The 'knowledge cutoff' date. We only use data valid on or before this date.
            min_year: Minimum prediction year to include

        Returns:
            DataFrame with player_name, year, and pivoted features
        """
        logger.info(f"Retrieving training matrix (as of {as_of_date})...")

        # Pivot features to wide format with point-in-time constraint
        query = f"""
            WITH base AS (
                SELECT DISTINCT player_name, year 
                FROM fact_player_efficiency 
                WHERE year >= {min_year}
            ),
            pit_features AS (
                SELECT 
                    fv.player_name,
                    fv.prediction_year,
                    fv.feature_name,
                    fv.feature_value
                FROM feature_values fv
                WHERE fv.prediction_year >= {min_year}
                  AND fv.valid_from <= '{as_of_date}' -- Known by cutoff
                  AND (fv.valid_until > '{as_of_date}' OR fv.valid_until IS NULL) -- Not yet superseded
            )
            SELECT 
                b.player_name,
                b.year,
                pf.feature_name,
                pf.feature_value
            FROM base b
            LEFT JOIN pit_features pf
                ON b.player_name = pf.player_name
                AND b.year = pf.prediction_year
        """

        df = self.con.execute(query).df()

        if df.empty:
            logger.warning("No features found. Run materialize_* methods first.")
            return df

        # Pivot to wide format
        pivot_df = df.pivot_table(
            index=["player_name", "year"],
            columns="feature_name",
            values="feature_value",
            aggfunc="first",
        ).reset_index()

        # Flatten column names
        pivot_df.columns = [
            col if isinstance(col, str) else col for col in pivot_df.columns
        ]

        logger.info(
            f"✓ Retrieved {len(pivot_df):,} rows × {len(pivot_df.columns)} features"
        )
        return pivot_df

    def get_historical_features(
        self, min_year: int = 2015, max_year: int = 2025
    ) -> pd.DataFrame:
        """
        Get feature matrix for Batch Training (Diagonal Join).

        Reconstructs what was known at the start of EACH season (Sept 1st) for that season.
        Unlike get_training_matrix (which uses one as_of_date), this uses a dynamic
        as_of_date = make_date(prediction_year, 9, 1).

        Args:
            min_year: Start year
            max_year: End year
        """
        logger.info(
            f"Retrieving historical features (Diagonal Join {min_year}-{max_year})..."
        )

        query = f"""
            WITH base AS (
                SELECT DISTINCT player_name, year 
                FROM fact_player_efficiency 
                WHERE year BETWEEN {min_year} AND {max_year}
            ),
            pit_features AS (
                SELECT 
                    fv.player_name,
                    fv.prediction_year,
                    fv.feature_name,
                    fv.feature_value
                FROM feature_values fv
                WHERE fv.prediction_year BETWEEN {min_year} AND {max_year}
                  -- DIAGONAL JOIN LOGIC:
                  -- Valid at the start of the prediction season (Sept 1st)
                  AND fv.valid_from <= make_date(fv.prediction_year, 9, 1)
                  AND (fv.valid_until > make_date(fv.prediction_year, 9, 1) OR fv.valid_until IS NULL)
            )
            SELECT 
                b.player_name,
                b.year,
                pf.feature_name,
                pf.feature_value
            FROM base b
            LEFT JOIN pit_features pf
                ON b.player_name = pf.player_name
                AND b.year = pf.prediction_year
        """

        df = self.con.execute(query).df()

        if df.empty:
            logger.warning("No features found.")
            return df

        pivot_df = df.pivot_table(
            index=["player_name", "year"],
            columns="feature_name",
            values="feature_value",
            aggfunc="first",
        ).reset_index()

        pivot_df.columns = [
            col if isinstance(col, str) else col for col in pivot_df.columns
        ]

        logger.info(f"✓ Retrieved {len(pivot_df):,} rows (Historical Batch)")
        return pivot_df

    def validate_temporal_integrity(self) -> bool:
        """
        Validate that no feature values violate point-in-time constraints.

        Rule: valid_from must be < season start date of prediction_year.
        Assuming season starts Sept 1st.
        """
        logger.info("🔍 Validating temporal integrity...")

        violations = self.con.execute("""
            SELECT COUNT(*) 
            FROM feature_values fv
            JOIN feature_registry fr ON fv.feature_name = fr.feature_name
            WHERE fr.feature_type = 'lag'
              -- Violation if 'known' date is AFTER the season starts
              AND fv.valid_from >= make_date(fv.prediction_year, 9, 1)
        """).fetchone()[0]

        if violations == 0:
            logger.info("✅ Temporal integrity PASSED: Zero violations.")
            return True
        else:
            logger.error(
                f"❌ Temporal integrity FAILED: {violations} violations found!"
            )

            # Show sample violations
            samples = self.con.execute("""
                SELECT fv.player_name, fv.prediction_year, fv.feature_name, fv.valid_from
                FROM feature_values fv
                JOIN feature_registry fr ON fv.feature_name = fr.feature_name
                WHERE fr.feature_type = 'lag'
                  AND fv.valid_from >= make_date(fv.prediction_year, 9, 1)
                LIMIT 5
            """).df()
            logger.error(f"Sample violations:\n{samples}")
            return False

    def get_feature_stats(self) -> pd.DataFrame:
        """Get summary statistics about the feature store."""
        return self.con.execute("""
            SELECT 
                fr.feature_type,
                COUNT(DISTINCT fv.feature_name) as num_features,
                COUNT(*) as num_values,
                MIN(fv.prediction_year) as min_year,
                MAX(fv.prediction_year) as max_year
            FROM feature_values fv
            JOIN feature_registry fr ON fv.feature_name = fr.feature_name
            GROUP BY fr.feature_type
            ORDER BY fr.feature_type
        """).df()


if __name__ == "__main__":
    # Demo usage
    store = FeatureStore()
    store.initialize_schema()
    store.materialize_lag_features()
    store.materialize_interaction_features()

    # Validate
    store.validate_temporal_integrity()

    # Show stats
    print("\n=== Feature Store Statistics ===")
    print(store.get_feature_stats())

    # Get training matrix for 2024 season (as of start of season)
    matrix = store.get_training_matrix(as_of_date=date(2024, 9, 1))
    print(f"\nTraining matrix shape: {matrix.shape}")

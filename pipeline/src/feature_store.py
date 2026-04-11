"""
Feature Store: Point-in-Time Feature Management

This module provides a BigQuery-based feature store that prevents temporal data leakage
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
    features = store.get_training_matrix(as_of_date=date(2024, 9, 1))
"""

import logging
from datetime import date
from typing import Optional

import pandas as pd

from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FeatureStore:
    """BigQuery-based Feature Store with point-in-time semantics."""

    def __init__(self, db: Optional[DBManager] = None, read_only: bool = False):
        self.db = db or DBManager()
        self.read_only = read_only

    def initialize_schema(self):
        """Create feature store tables if they don't exist."""
        if self.read_only:
            logger.info("Read-only mode. Skipping schema initialization.")
            return

        logger.info("Initializing Feature Store schema...")

        # Feature Registry: Metadata about each feature
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS feature_registry (
                feature_name STRING NOT NULL,
                feature_type STRING,
                source_column STRING,
                lag_periods INT64,
                description STRING,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Feature Values: The actual feature data with temporal validity
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS feature_values (
                entity_key STRING,
                player_name STRING,
                prediction_year INT64,
                feature_name STRING,
                feature_value FLOAT64,
                valid_from DATE,
                valid_until DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        logger.info("Feature Store schema initialized.")

    def register_feature(
        self,
        feature_name: str,
        feature_type: str,
        source_column: str = None,
        lag_periods: int = None,
        description: str = None,
    ):
        """Register a feature in the registry (upsert via MERGE)."""
        self.db.execute(f"""
            MERGE INTO feature_registry AS target
            USING (
                SELECT
                    '{feature_name}' AS feature_name,
                    '{feature_type}' AS feature_type,
                    {_bq_str(source_column)} AS source_column,
                    {_bq_int(lag_periods)} AS lag_periods,
                    {_bq_str(description)} AS description
            ) AS src
            ON target.feature_name = src.feature_name
            WHEN MATCHED THEN UPDATE SET
                feature_type = src.feature_type,
                source_column = src.source_column,
                lag_periods = src.lag_periods,
                description = src.description
            WHEN NOT MATCHED THEN INSERT
                (feature_name, feature_type, source_column, lag_periods, description)
                VALUES (src.feature_name, src.feature_type, src.source_column,
                        src.lag_periods, src.description)
        """)

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

        # Get available columns from source table
        cols_df = self.db.fetch_df(f"""
            SELECT column_name
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE table_name = '{source_table}'
        """)
        available_cols = set(cols_df["column_name"].values)

        # Clear existing lag features
        self.db.execute("""
            DELETE FROM feature_values
            WHERE feature_name LIKE '%_lag_%'
        """)

        # Register and materialize each lag feature
        for col in lag_columns:
            if col not in available_cols:
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
                self.db.execute(f"""
                    INSERT INTO feature_values
                        (entity_key, player_name, prediction_year,
                         feature_name, feature_value, valid_from, valid_until)
                    SELECT
                        CONCAT(target.player_name, '_', CAST(target.year AS STRING))
                            AS entity_key,
                        target.player_name,
                        target.year AS prediction_year,
                        '{feature_name}' AS feature_name,
                        source.{col} AS feature_value,
                        DATE(source.year + 1, 2, 15) AS valid_from,
                        DATE(source.year + 2, 2, 15) AS valid_until
                    FROM {source_table} target
                    INNER JOIN {source_table} source
                        ON target.player_name = source.player_name
                        AND source.year = target.year - {lag}
                    WHERE source.{col} IS NOT NULL
                """)

        # Log summary
        count = self.db.execute(
            "SELECT COUNT(*) AS cnt FROM feature_values"
        ).fetchone()[0]
        logger.info(f"Materialized {count:,} feature values in store.")

    def materialize_interaction_features(
        self, source_table: str = "fact_player_efficiency"
    ):
        """Materialize derived/interaction features."""
        logger.info("Materializing interaction features...")

        interactions = [
            (
                "age_cap_interaction",
                "age * cap_hit_millions",
                "Age x Cap Hit interaction",
            ),
            ("experience_risk", "draft_round * age", "Draft round x Age risk"),
        ]

        for feature_name, formula, description in interactions:
            self.register_feature(
                feature_name=feature_name,
                feature_type="interaction",
                description=description,
            )

            try:
                first_operand = formula.split("*")[0].strip()
                self.db.execute(f"""
                    INSERT INTO feature_values
                        (entity_key, player_name, prediction_year,
                         feature_name, feature_value, valid_from, valid_until)
                    SELECT
                        CONCAT(player_name, '_', CAST(year AS STRING))
                            AS entity_key,
                        player_name,
                        year AS prediction_year,
                        '{feature_name}' AS feature_name,
                        {formula} AS feature_value,
                        DATE(year, 3, 15) AS valid_from,
                        DATE(year + 1, 3, 15) AS valid_until
                    FROM {source_table}
                    WHERE {first_operand} IS NOT NULL
                """)
            except Exception as e:
                logger.warning(f"Could not compute {feature_name}: {e}")

        count = self.db.execute("""
            SELECT COUNT(*) AS cnt FROM feature_values
            WHERE feature_name IN ('age_cap_interaction', 'experience_risk')
        """).fetchone()[0]
        logger.info(f"Materialized {count:,} interaction features.")

    def get_training_matrix(
        self, as_of_date: date, min_year: int = 2015
    ) -> pd.DataFrame:
        """
        Get feature matrix for training with strict point-in-time semantics as of a SINGLE date.

        Args:
            as_of_date: The 'knowledge cutoff' date. Only data valid on or before this date.
            min_year: Minimum prediction year to include

        Returns:
            DataFrame with player_name, year, and pivoted features
        """
        logger.info(f"Retrieving training matrix (as of {as_of_date})...")

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
                  AND fv.valid_from <= '{as_of_date}'
                  AND (fv.valid_until > '{as_of_date}' OR fv.valid_until IS NULL)
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

        df = self.db.fetch_df(query)

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
            f"Retrieved {len(pivot_df):,} rows x {len(pivot_df.columns)} features"
        )
        return pivot_df

    def get_historical_features(
        self, min_year: int = 2015, max_year: int = 2025
    ) -> pd.DataFrame:
        """
        Get feature matrix for Batch Training (Diagonal Join).

        Reconstructs what was known at the start of EACH season (Sept 1st) for that season.
        Unlike get_training_matrix (which uses one as_of_date), this uses a dynamic
        as_of_date = DATE(prediction_year, 9, 1).

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
                  AND fv.valid_from <= DATE(fv.prediction_year, 9, 1)
                  AND (fv.valid_until > DATE(fv.prediction_year, 9, 1)
                       OR fv.valid_until IS NULL)
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

        df = self.db.fetch_df(query)

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

        logger.info(f"Retrieved {len(pivot_df):,} rows (Historical Batch)")
        return pivot_df

    def validate_temporal_integrity(self) -> bool:
        """
        Validate that no feature values violate point-in-time constraints.

        Rule: valid_from must be < season start date of prediction_year.
        Assuming season starts Sept 1st.
        """
        logger.info("Validating temporal integrity...")

        violations = self.db.execute("""
            SELECT COUNT(*) AS cnt
            FROM feature_values fv
            JOIN feature_registry fr ON fv.feature_name = fr.feature_name
            WHERE fr.feature_type = 'lag'
              AND fv.valid_from >= DATE(fv.prediction_year, 9, 1)
        """).fetchone()[0]

        if violations == 0:
            logger.info("Temporal integrity PASSED: Zero violations.")
            return True
        else:
            logger.error(f"Temporal integrity FAILED: {violations} violations found!")

            # Show sample violations
            samples = self.db.fetch_df("""
                SELECT fv.player_name, fv.prediction_year,
                       fv.feature_name, fv.valid_from
                FROM feature_values fv
                JOIN feature_registry fr ON fv.feature_name = fr.feature_name
                WHERE fr.feature_type = 'lag'
                  AND fv.valid_from >= DATE(fv.prediction_year, 9, 1)
                LIMIT 5
            """)
            logger.error(f"Sample violations:\n{samples}")
            return False

    def get_feature_stats(self) -> pd.DataFrame:
        """Get summary statistics about the feature store."""
        return self.db.fetch_df("""
            SELECT
                fr.feature_type,
                COUNT(DISTINCT fv.feature_name) AS num_features,
                COUNT(*) AS num_values,
                MIN(fv.prediction_year) AS min_year,
                MAX(fv.prediction_year) AS max_year
            FROM feature_values fv
            JOIN feature_registry fr ON fv.feature_name = fr.feature_name
            GROUP BY fr.feature_type
            ORDER BY fr.feature_type
        """)


def _bq_str(val: Optional[str]) -> str:
    """Format a Python string as a BigQuery string literal, or NULL."""
    if val is None:
        return "CAST(NULL AS STRING)"
    escaped = val.replace("'", "\\'")
    return f"'{escaped}'"


def _bq_int(val: Optional[int]) -> str:
    """Format a Python int as a BigQuery INT64 literal, or NULL."""
    if val is None:
        return "CAST(NULL AS INT64)"
    return str(int(val))

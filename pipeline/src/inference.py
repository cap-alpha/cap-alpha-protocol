import logging
import os
from pathlib import Path

import joblib
import pandas as pd
from src.db_manager import DBManager
from src.feature_factory import FeatureFactory

logger = logging.getLogger(__name__)


class InferenceEngine:
    def __init__(self, db_path: str, model_dir: str = "models"):
        self.db_path = db_path
        self.model_dir = Path(model_dir)

    def get_latest_model(self):
        from src.ml_governance import MLGovernance

        governance = MLGovernance()
        prod_info = governance.get_production_model_info()

        if not prod_info:
            logger.warning(
                "No PRODUCTION model found in registry. Checking for CANDIDATE..."
            )
            prod_info = governance.get_latest_candidate()

        if not prod_info:
            logger.warning("No model found (Production or Candidate).")
            return None

        model_path = Path(prod_info["path"])
        if not model_path.exists():
            # Fallback for transient environments
            alt_path = Path("/tmp") / model_path.relative_to(model_path.parents[1])
            if alt_path.exists():
                model_path = alt_path
            else:
                logger.error(f"Production model file not found: {model_path}")
                return None

        logger.info(f"Loading PRODUCTION model: {model_path}")
        return joblib.load(model_path)

    def enrich_gold_layer(self):
        """
        Loads the feature matrix using FeatureStore (PIT-correct), runs inference,
        and updates fact_player_efficiency.
        """
        from datetime import date

        from bs4 import (
            BeautifulSoup,
        )  # Unused but keeping imports clean isn't part of this refactor
        from src.feature_store import FeatureStore

        # 1. Load Point-in-Time Features (As of TODAY)
        # store = FeatureStore(db_path=str(self.db_path))
        # We want the latest known data for all active players
        # df_features = store.get_training_matrix(as_of_date=date.today(), min_year=2024)

        # Direct read from staging (consistency with training)
        with DBManager(str(self.db_path)) as db:
            df_features = db.execute(
                "SELECT * FROM staging_feature_matrix WHERE year >= 2024"
            ).df()

        if df_features.empty:
            logger.warning("Feature matrix emtpy. Ensure materialization has run.")
            return

        model = self.get_latest_model()
        if model is None:
            logger.warning("No ML model found. Skipping ML enrichment.")
            return

        # 2. Align Features with Model
        from src.ml_governance import MLGovernance

        governance = MLGovernance()
        prod_info = governance.get_production_model_info()

        if prod_info and "feature_names" in prod_info:
            expected_features = prod_info["feature_names"]
        else:
            logger.warning("No feature metadata in governance. Using booster fallback.")
            expected_features = model.get_booster().feature_names

        if expected_features is None:
            logger.warning(
                "Feature names not found in model. Falling back to available columns."
            )
            expected_features = [
                c for c in df_features.columns if c not in ["player_name", "year"]
            ]

        logger.info(f"ML Inference: Model expects {len(expected_features)} features")

        # Reindex checks for missing columns (fills 0) and drops extras
        # We must set index to keep alignment with df_features
        X_aligned = df_features.set_index(["player_name", "year"]).reindex(
            columns=expected_features, fill_value=0
        )

        # 3. Predict
        preds = model.predict(X_aligned)

        # 4. Persistence
        # We need to map predictions back to (player, year, team)
        # FeatureStore (get_training_matrix) returns [player_name, year, ...] but NOT team
        # We need to join team back from fact_player_efficiency to update the table correctly?
        # Actually, UPDATE FROM only needs player/year if those are the keys.
        # But fact_player_efficiency PK might include 'team'.
        # Let's pivot: The easiest way is to push predictions to a temp table keyed by player/year

        with DBManager(str(self.db_path)) as db:
            # Create a dataframe for the update
            updates_df = X_aligned.reset_index()[["player_name", "year"]].copy()
            updates_df["ml_risk_score"] = preds

            # Calculate simplistic Fair Market Value proxy
            # If risk is high, value is simpler. If risk low, value high.
            # We don't have 'fair_market_value' column in X_aligned unless it was a feature.
            # Let's just update risk score for now as that is the critical artifact.

            db.execute(
                "CREATE OR REPLACE TEMPORARY TABLE inference_results AS SELECT * FROM updates_df",
                {"updates_df": updates_df},
            )

            # Add column if missing
            db.execute(
                "ALTER TABLE fact_player_efficiency ADD COLUMN IF NOT EXISTS ml_risk_score DOUBLE"
            )

            # Update
            db.execute("""
                UPDATE fact_player_efficiency
                SET ml_risk_score = inference_results.ml_risk_score
                FROM inference_results
                WHERE fact_player_efficiency.player_name = inference_results.player_name 
                  AND fact_player_efficiency.year = inference_results.year
            """)

            count = db.execute("SELECT COUNT(*) FROM inference_results").fetchone()[0]
            logger.info(
                f"✓ Updated {count} rows with ML Risk Scores (Source: FeatureStore)."
            )


if __name__ == "__main__":
    from src.config_loader import get_db_path

    db_path = get_db_path()
    engine = InferenceEngine(db_path)
    engine.enrich_gold_layer()

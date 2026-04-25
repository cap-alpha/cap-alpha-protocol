import logging

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp
from src.ml_governance import MLGovernance

logger = logging.getLogger(__name__)


class RedTeamEvaluator:
    def __init__(self, config_path="config/ml_config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.thresholds = self.config["validation"]["thresholds"]
        self.governance = MLGovernance(config_path)

    def evaluate_model(self, model, X_train, y_train, X_test, y_test, metrics):
        """
        Rigorous evaluation of a candidate model.
        """
        logger.info("🛡️  Starting Red Team Evaluation...")

        # 1. Metric Validation
        r2 = metrics.get("r2", 0)
        rmse = metrics.get("rmse", 999)

        if r2 < self.thresholds["min_r2"]:
            logger.error(
                f"❌ R2 Score {r2:.4f} is below threshold {self.thresholds['min_r2']}"
            )
            return False

        if rmse > self.thresholds["max_rmse"]:
            logger.error(
                f"❌ RMSE {rmse:.4f} is above threshold {self.thresholds['max_rmse']}"
            )
            return False

        logger.info("✅ Statistical thresholds passed.")

        # 2. Concept/Data Drift Check (Simple Feature KS-Test)
        # We compare test set distribution against training set for key features
        drifted_features = []
        for col in X_train.columns[:10]:  # Check first 10 primary features for speed
            stat, p_value = ks_2samp(X_train[col], X_test[col])
            if p_value < self.thresholds["max_drift_p_value"]:
                drifted_features.append(col)

        if drifted_features:
            logger.warning(f"⚠️  Feature Drift detected in: {drifted_features}")
            if self.config["validation"]["red_team"]["fail_on_drift"]:
                return False
        else:
            logger.info("✅ No significant feature drift detected.")

        # 3. Model Registration as Candidate
        # (Actually registration happens in train_model, this just returns results)

        logger.info("🏆 Red Team Evaluation: PASSED")
        return True

    def validate_and_promote(self, candidate_path):
        """
        Final gate for promotion.
        """
        # In a real system, this might run more production-parity data checks
        logger.info(f"Finalizing authorization for {candidate_path}...")
        return self.governance.promote_to_production(candidate_path)

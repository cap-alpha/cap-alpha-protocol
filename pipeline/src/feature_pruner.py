import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LassoCV
from sklearn.preprocessing import StandardScaler

from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
from src.config_loader import get_db_path

DB_PATH = get_db_path()


class FeaturePruner:
    def __init__(self, db_path=DB_PATH):
        self.con = DBManager()

    def prune_with_l1(self, target_col="edce_risk"):
        """Use Lasso (L1) regularization to identify and keep only significant features."""
        logger.info(f"Pruning features using L1 (Lasso) targeting {target_col}...")

        # 1. Load Data
        df = self.con.execute("SELECT * FROM staging_feature_matrix").df()

        # 2. Cleanup (Drop non-features)
        skip_cols = [
            "player_name",
            "year",
            "experience_years",
            "edce_risk",
            "fair_market_value",
            "ied_overpayment",
            "value_metric_proxy",
        ]
        X_raw = df.drop(columns=[c for c in skip_cols if c in df.columns])

        # Robustly convert to numeric and drop non-numeric columns
        X = X_raw.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
        X = X.fillna(0)

        y = df[target_col].fillna(0)

        # Handle NAs in features
        X = X.fillna(0)

        # 3. Standardize
        logger.info(
            f"Feature matrix columns: {X.columns.tolist()[:5]}... ({len(X.columns)} total)"
        )
        non_numeric = X.select_dtypes(exclude=[np.number]).columns
        if not non_numeric.empty:
            logger.error(f"Non-numeric columns found in X: {non_numeric.tolist()}")
            X = X.drop(columns=non_numeric)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # 4. LassoCV
        lasso = LassoCV(cv=5, random_state=42, max_iter=10000).fit(X_scaled, y)

        # 5. Identify Selected Features
        coef = pd.Series(lasso.coef_, index=X.columns)
        selected_features = coef[coef != 0].index.tolist()

        logger.info(
            f"✓ L1 Pruning complete. Kept {len(selected_features)} features out of {X.shape[1]}."
        )
        logger.info(
            f"Top Features: {coef.abs().sort_values(ascending=False).head(10).index.tolist()}"
        )

        return selected_features, coef

    def analyze_components(self, n_components=10):
        """Perform Principal Component Analysis to understand data variance."""
        logger.info(f"Performing PCA (n_components={n_components})...")

        df = self.con.execute("SELECT * FROM staging_feature_matrix").df()
        skip_cols = [
            "player_name",
            "year",
            "experience_years",
            "edce_risk",
            "fair_market_value",
            "ied_overpayment",
            "value_metric_proxy",
        ]
        X_raw = df.drop(columns=[c for c in skip_cols if c in df.columns])

        # Robustly convert to numeric
        X = (
            X_raw.apply(pd.to_numeric, errors="coerce")
            .dropna(axis=1, how="all")
            .fillna(0)
        )

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        pca = PCA(n_components=n_components)
        pca.fit(X_scaled)

        explained_var = np.sum(pca.explained_variance_ratio_)
        logger.info(
            f"✓ PCA Complete. Top {n_components} components explain {explained_var:.2%} of variance."
        )

        return pca


if __name__ == "__main__":
    pruner = FeaturePruner()
    selected, coefs = pruner.prune_with_l1()
    pca = pruner.analyze_components()

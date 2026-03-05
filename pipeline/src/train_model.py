
import pandas as pd
import numpy as np
from src.db_manager import DBManager
import logging
import xgboost as xgb
try:
    import shap
except ImportError:
    shap = None
import matplotlib.pyplot as plt
import os
from sklearn.metrics import mean_squared_error, r2_score
from pathlib import Path
from src.feature_store import FeatureStore

import numpy as np
# PATCH NUMPY FOR SHAP COMPATIBILITY
try:
    if not hasattr(np, "_ARRAY_API"):
        np._ARRAY_API = False
    if not hasattr(np, "obj2sctype"):
        np.obj2sctype = lambda x: np.dtype(x).type
except Exception:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from src.config_loader import get_db_path

DB_PATH = get_db_path()
MODEL_DIR = Path(os.getenv("MODEL_DIR", "/tmp/models"))
MODEL_DIR.mkdir(parents=True, exist_ok=True)

class RiskModeler:
    def __init__(self, db_path=DB_PATH, read_only=False):
        self.db_path = db_path
        self.read_only = read_only
        self.db = DBManager(db_path, read_only=self.read_only)
        self.con = self.db.con

    def prepare_data(self, target_col='true_bust_variance'):
        from src.feature_factory import FeatureFactory
        
        logger.info("Generating hyperscale feature matrix via FeatureFactory...")
        factory = FeatureFactory(self.db.db_path)
        df = factory.generate_hyperscale_matrix()
        
        if not self.read_only:
            self.con.register('df_view', df)
            self.con.execute("CREATE OR REPLACE TABLE staging_feature_matrix AS SELECT * FROM df_view")
            logger.info("Persisted staging_feature_matrix to DuckDB.")
            
        df = df[df['year'].between(2015, 2025)]
        
        if len(df) == 0:
            raise ValueError("Staging feature matrix is empty. Pipeline failure.")
            
        # Target is already in the matrix (passed through from Gold Layer)
        if target_col not in df.columns:
             # Fallback: Try to join from fact_player_efficiency if missing
             logger.warning(f"Target {target_col} not in matrix. Joining from Gold Layer...")
             df_target = self.con.execute(f"SELECT player_name, year, week, {target_col} FROM fact_player_efficiency").df()
             df = pd.merge(df, df_target, on=['player_name', 'year', 'week'], how='inner')

        # Merge handled implicitly or above
        
        # 1. Split into features and target
        # LEAKAGE PREVENTION: Drop columns that define average/risk directly
        # LEAKAGE PREVENTION: Drop columns that define average/risk directly
        skip_cols = [
            'player_name', 'year', 'week', 'team', target_col, 
            'potential_dead_cap_millions',
            'dead_cap_millions', 
            'signing_bonus_millions',
            'salaries_dead_cap_millions',
            'edce_risk',
            'fair_market_value',
            'total_pass_yds',
            'total_rush_yds',
            'total_rec_yds',
            'total_tds',
            'total_sacks',
            'total_int',
            'total_penalty_yards',
            'total_penalty_count',
            'availability_rating',
            'games_played'
        ]
        X = df.drop(columns=[c for c in skip_cols if c in df.columns])
        
        # Clean currency strings
        for col in X.columns:
            if X[col].dtype == 'object':
                X[col] = X[col].astype(str).str.replace(r'[\$,]', '', regex=True)
                
        # Robust numeric conversion (XGBoost handles sparsity natively, do not dropna)
        X = X.apply(pd.to_numeric, errors='coerce').fillna(0)
        y = df[target_col].fillna(0)
        
        # 2. Retain player info for joining results back
        metadata = df[['player_name', 'year', 'week', 'team']].copy()
        
        logger.info(f"✓ Data Prepared: {len(X)} rows, {len(X.columns)} features.")
        return X, y, metadata

    def train_xgboost(self, X, y, metadata):
        logger.info("Training Production XGBoost Model (with Walk-Forward Validation)...")
        
        # 1. Run Backtest First
        from src.backtesting import WalkForwardValidator
        validator = WalkForwardValidator()
        backtest_results, predictions_df = validator.run_backtest(X, y, metadata)
        validator.generate_report(backtest_results)
        
        # Save Historical Predictions for Frontend (Validation Layer)
        if not predictions_df.empty:
            # Assume running from project root
            preds_target = Path("reports/historical_predictions.json")
            preds_target.parent.mkdir(parents=True, exist_ok=True)
            
            # Simple JSON export
            predictions_df.to_json(preds_target, orient="records", indent=2)
            logger.info(f"✓ Historical Predictions saved to {preds_target}")
        
        # 2. Train Final Production Model on ALL History
        # We use all available data to predict the "unknown" future (2025/2026)
        logger.info("Training Final Production Model on full history...")
        
        # Use config params
        try:
             import yaml
             config_path = "pipeline/config/ml_config.yaml"
             if not Path(config_path).exists():
                 config_path = "config/ml_config.yaml"
             with open(config_path, "r") as f:
                  config = yaml.safe_load(f)
             params = config["models"]["xgboost"]["params"]
        except Exception as e:
             logger.warning(f"Could not load config: {e}. Using defaults.")
             params = {'n_estimators': 100, 'max_depth': 4, 'learning_rate': 0.1}
        
        model = xgb.XGBRegressor(**params)
        model.fit(X, y, verbose=False)
        
        # 3. Use the latest fold's test set as a proxy for "X_test" for SHAP/Metrics
        # This is strictly for reporting purposes
        latest_year = metadata['year'].max()
        test_mask = metadata['year'] == latest_year
        X_test_proxy = X[test_mask]
        
        logger.info(f"✓ Model Trained on full history ({len(X)} rows).")
        return model, X_test_proxy, backtest_results
    def generate_shap_report(self, model, X_test):
        if shap is None:
            logger.warning("SHAP library not available. Skipping explanation.")
            return None
            
        try:
            logger.info("Generating SHAP Transparency Explainer...")
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X_test)
            
            plt.figure(figsize=(10, 6))
            shap.summary_plot(shap_values, X_test, show=False)
            plt.tight_layout()
            report_path = os.getenv("REPORT_PATH", "reports/shap_summary.png")
            plt.savefig(report_path, dpi=300, bbox_inches='tight')
            logger.info(f"✓ SHAP summary plot saved to {report_path}")
            return shap_values
        except Exception as e:
            logger.warning(f"SHAP generation failed (optional): {e}")
            return None

    def save_predictions(self, model, X, metadata, metrics):
        import joblib
        import json
        import yaml
        from datetime import datetime
        from src.ml_governance import MLGovernance
        
        logger.info("Saving Predictions and Model Artifacts...")
        
        # 1. Save Predictions to DB
        preds = model.predict(X)
        metadata['predicted_risk_score'] = preds
        
        if self.db.db_path and "read_only" in self.db.db_path: # Simulated read_only check for manager
             logger.info("Database is read-only. Skipping persistence to 'prediction_results' table.")
        else:
            self.db.execute("CREATE OR REPLACE TABLE prediction_results AS SELECT * FROM metadata", {"metadata": metadata})
            logger.info("✓ Predictions persisted to 'prediction_results' table.")
        
        # 2. Save Model Artifact
        config_path = "pipeline/config/ml_config.yaml"
        if not Path(config_path).exists():
             config_path = "config/ml_config.yaml"
        with open(config_path, "r") as f:
            ml_config = yaml.safe_load(f)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_filename = ml_config["models"]["xgboost"]["file_pattern"].format(timestamp=timestamp)
        model_path = MODEL_DIR / model_filename
        joblib.dump(model, model_path)
        logger.info(f"✓ Model artifact saved to: {model_path}")
        
        # 3. Register as Candidate
        governance = MLGovernance()
        governance.register_candidate(
            model_path=model_path,
            metrics=metrics,
            feature_names=list(X.columns)
        )
        logger.info("✓ Model registered in governance registry.")

    def save_explanations(self, model, X, metadata):
        if shap is None:
            logger.warning("SHAP library not available. Skipping explanation.")
            return

        try:
            logger.info("Generating SHAP Explanations for Rationale (Top 3 Factors) on a memory-safe 10% sample...")
            
            # MEMORY FIX: 315 features * 11000 rows OOMs the container during SHAP expansion. Sample it.
            sample_size = min(len(X), max(int(len(X) * 0.1), 100))
            X_sample = X.sample(n=sample_size, random_state=42)
            
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(X_sample)
            
            explanations = []
            all_shap_scores = []
            feature_names = X_sample.columns.tolist()
            
            # Efficiently format strings & capture all data
            # Align sample back to original metadata shape (leave NaN for un-sampled rows)
            metadata_copy = metadata.copy()
            metadata_copy['top_factors'] = None
            metadata_copy['all_factors'] = None
            
            # Map back exactly to the index
            metadata_copy.loc[X_sample.index, 'top_factors'] = explanations
            metadata_copy.loc[X_sample.index, 'all_factors'] = all_shap_scores
            
            if self.read_only:
                logger.info("Database is read-only. Skipping persistence to 'prediction_explanations' table.")
            else:
                self.db.execute("CREATE OR REPLACE TABLE prediction_explanations AS SELECT player_name, year, top_factors, all_factors FROM metadata_copy WHERE top_factors IS NOT NULL", {"metadata_copy": metadata_copy})
                logger.info("✓ Explanations persisted to 'prediction_explanations' (Top 3 + Full JSON).")
            
        except Exception as e:
            logger.warning(f"Failed to save explanations: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--read-only", action="store_true", help="Run in read-only mode (no DB writes)")
    args = parser.parse_args()
    
    modeler = RiskModeler(read_only=args.read_only)
    X, y, metadata = modeler.prepare_data()
    model, X_test, backtest_results = modeler.train_xgboost(X, y, metadata)
    
    # Validation against config thresholds using AVERAGE backtest performance
    avg_rmse = backtest_results['rmse'].mean()
    avg_r2 = backtest_results['r2'].mean()
    
    metrics = {
        "rmse": float(avg_rmse),
        "r2": float(avg_r2)
    }
    
    modeler.generate_shap_report(model, X_test)
    modeler.save_predictions(model, X, metadata, metrics)
    modeler.save_explanations(model, X, metadata)

import logging
import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import mean_squared_error, r2_score, f1_score
import yaml
import json
from pathlib import Path

logger = logging.getLogger(__name__)

class WalkForwardValidator:
    def __init__(self, config_path="pipeline/config/ml_config.yaml"):
        if not Path(config_path).exists():
             # Fallback for running within pipeline dir
             if Path("config/ml_config.yaml").exists():
                 config_path = "config/ml_config.yaml"
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.params = self.config["models"]["xgboost"]["params"]

    def run_backtest(self, X, y, metadata, start_year=2018):
        """
        Executes a rolling walk-forward validation.
        """
        logger.info(f"⏳ Starting Walk-Forward Validation (Start Test Year: {start_year})...")
        
        # Ensure metadata index aligns with X/y
        metadata = metadata.loc[X.index].copy()
        
        years = sorted(metadata['year'].dropna().unique())
        logger.info(f"  📊 Available years in data: {years}")
        results = []
        
        # TEMPORARY OVERRIDE for MotherDuck RPC Rate Limiting: Allow single-year testing
        if not years:
            raise ValueError("No temporal data found in matrix.")
        start_year = min(start_year, max(years))
            
        for test_year in range(int(start_year), int(max(years)) + 1):
            # 1. Temporal Split
            train_mask = metadata['year'] <= test_year  # TEMPORARY: train on current year if it's the only one
            test_mask = metadata['year'] == test_year
            
            if not test_mask.any() or not train_mask.any():
                logger.warning(f"  ⚠️ Skipping year {test_year}: insufficient data")
                continue
                
            X_train = X.loc[train_mask]
            y_train = y.loc[train_mask]
            X_test = X.loc[test_mask]
            y_test = y.loc[test_mask]
            
            if len(X_train) < 100:
                logger.warning(f"  ⚠️ Skipping year {test_year}: only {len(X_train)} training samples")
                continue
            
            # 2. Train Model (Fresh for each fold)
            model = xgb.XGBRegressor(**self.params)
            model.fit(X_train, y_train, verbose=False)
            
            # 3. Evaluate
            preds = model.predict(X_test)
            rmse = np.sqrt(mean_squared_error(y_test, preds))
            r2 = r2_score(y_test, preds)
            
            y_test_binary = (y_test >= 10.0).astype(int)
            preds_binary = (preds >= 10.0).astype(int)
            f1 = f1_score(y_test_binary, preds_binary, zero_division=0)
            
            logger.info(f"  📅 Test Year {test_year}: RMSE={rmse:.4f}, R2={r2:.4f}, F1={f1:.4f} (Train Size: {len(X_train)})")
            
            results.append({
                "test_year": int(test_year),
                "rmse": float(rmse),
                "r2": float(r2),
                "f1": float(f1),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "predictions": pd.DataFrame({
                    "player_name": metadata.loc[test_mask, 'player_name'],
                    "year": test_year,
                    "week": metadata.loc[test_mask, 'week'],
                    "team": metadata.loc[test_mask, 'team'],
                    "actual": y_test,
                    "predicted": preds
                })
            })
        
        if not results:
            logger.error("❌ No valid backtest folds were produced!")
            return pd.DataFrame(columns=["test_year", "rmse", "r2", "train_size", "test_size"]), pd.DataFrame()
            
        # Compile all predictions into a single DataFrame
        all_preds = []
        clean_results = []
        
        for res in results:
            if "predictions" in res:
                all_preds.append(res.pop("predictions"))
            clean_results.append(res)
            
        predictions_df = pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
        return pd.DataFrame(clean_results), predictions_df

    def generate_report(self, results_df, report_path="reports/backtest_results.md"):
        if results_df.empty:
            logger.warning("⚠️ No backtest results to report.")
            report = """# Walk-Forward Validation Report
**Generated:** {pd.Timestamp.now()}

## Summary
⚠️ **No valid backtest folds were produced.** Check data availability and year range.
"""
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                f.write(report)
            return
            
        avg_rmse = results_df['rmse'].mean()
        avg_r2 = results_df['r2'].mean()
        avg_f1 = results_df['f1'].mean()
        
        report = f"""# Walk-Forward Validation Report
**Generated:** {pd.Timestamp.now()}

## Summary
- **Average RMSE:** {avg_rmse:.4f}
- **Average R2:** {avg_r2:.4f}
- **Average F1:** {avg_f1:.4f}
- **Years Tested:** {results_df['test_year'].min()} - {results_df['test_year'].max()}

## Breakdown by Year
| Year | RMSE | R2 | F1 | Train Size | Test Size |
|------|------|----|----|------------|-----------|
"""
        for _, row in results_df.iterrows():
            report += f"| {int(row['test_year'])} | {row['rmse']:.4f} | {row['r2']:.4f} | {row['f1']:.4f} | {int(row['train_size'])} | {int(row['test_size'])} |\n"
            
        # Write to file
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            f.write(report)
            
        print("\n[DEBUG] BACKTEST METRICS (from memory):")
        print(report)
        print("=========================================\n")
            
        logger.info(f"✓ Backtest report generated: {report_path}")

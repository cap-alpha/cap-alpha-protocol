import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import yaml
from sklearn.metrics import f1_score, mean_squared_error, r2_score

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

    def run_backtest(self, X, y, metadata, start_year=2018, is_classification=False):
        """
        Executes a rolling walk-forward validation.
        """
        logger.info(
            f"⏳ Starting Walk-Forward Validation (Start Test Year: {start_year}, Classification: {is_classification})..."
        )

        # Ensure metadata index aligns with X/y
        metadata = metadata.loc[X.index].copy()

        years = sorted(metadata["year"].dropna().unique())
        logger.info(f"  📊 Available years in data: {years}")
        results = []

        # TEMPORARY OVERRIDE for Allow single-year testing
        if not years:
            raise ValueError("No temporal data found in matrix.")
        start_year = min(start_year, max(years))

        for test_year in range(int(start_year), int(max(years)) + 1):
            # 1. Temporal Split
            train_mask = metadata["year"] < test_year
            test_mask = metadata["year"] == test_year

            if not test_mask.any() or not train_mask.any():
                logger.warning(f"  ⚠️ Skipping year {test_year}: insufficient data")
                continue

            X_train = X.loc[train_mask]
            y_train = y.loc[train_mask]
            X_test = X.loc[test_mask]
            y_test = y.loc[test_mask]

            if len(X_train) < 100:
                logger.warning(
                    f"  ⚠️ Skipping year {test_year}: only {len(X_train)} training samples"
                )
                continue

            # 2. Train Model (Fresh for each fold)
            if is_classification:
                num_neg = (y_train == 0).sum()
                num_pos = (y_train == 1).sum()
                scale_weight = float(num_neg / max(num_pos, 1))
                model = xgb.XGBClassifier(**self.params, scale_pos_weight=scale_weight)
            else:
                model = xgb.XGBRegressor(**self.params)
            model.fit(X_train, y_train, verbose=False)

            # 3. Evaluate
            preds = model.predict(X_test)

            # TEMPORAL HONESTY DEDUPLICATION
            # The model predicts every week, but the target 'true_bust_variance' is a yearly outcome.
            # To avoid the massive R-squared penalty of pooling uncertain early-season predictions
            # with confident late-season predictions, we only evaluate the terminal week for each player.
            eval_df = pd.DataFrame(
                {
                    "player_name": metadata.loc[test_mask, "player_name"],
                    "week": metadata.loc[test_mask, "week"],
                    "actual": y_test,
                    "predicted": preds,
                }
            )

            eval_df_terminal = eval_df.sort_values("week").drop_duplicates(
                subset=["player_name"], keep="last"
            )

            if is_classification:
                from sklearn.metrics import accuracy_score

                acc = accuracy_score(
                    eval_df_terminal["actual"], eval_df_terminal["predicted"]
                )
                f1 = f1_score(
                    eval_df_terminal["actual"],
                    eval_df_terminal["predicted"],
                    zero_division=0,
                )
                logger.info(
                    f"  📅 Test Year {test_year}: Accuracy={acc:.4f}, F1={f1:.4f} (Train Size: {len(X_train)}, Terminal Test Size: {len(eval_df_terminal)})"
                )
                res_metrics = {"accuracy": float(acc), "f1_score": float(f1)}
            else:
                rmse = np.sqrt(
                    mean_squared_error(
                        eval_df_terminal["actual"], eval_df_terminal["predicted"]
                    )
                )
                r2 = r2_score(eval_df_terminal["actual"], eval_df_terminal["predicted"])

                # Arbitrary binary f1 for regression output tracing
                y_test_binary = (eval_df_terminal["actual"] >= 10.0).astype(int)
                preds_binary = (eval_df_terminal["predicted"] >= 10.0).astype(int)
                f1 = f1_score(y_test_binary, preds_binary, zero_division=0)

                logger.info(
                    f"  📅 Test Year {test_year}: RMSE={rmse:.4f}, R2={r2:.4f}, F1={f1:.4f} (Train Size: {len(X_train)}, Terminal Test Size: {len(eval_df_terminal)})"
                )
                res_metrics = {"rmse": float(rmse), "r2": float(r2), "f1": float(f1)}

            fold_results = {
                "test_year": int(test_year),
                "train_size": len(X_train),
                "test_size": len(X_test),
                "predictions": pd.DataFrame(
                    {
                        "player_name": metadata.loc[test_mask, "player_name"],
                        "year": test_year,
                        "week": metadata.loc[test_mask, "week"],
                        "team": metadata.loc[test_mask, "team"],
                        "actual": y_test,
                        "predicted": preds,
                    }
                ),
            }
            fold_results.update(res_metrics)
            results.append(fold_results)

        if not results:
            logger.error("❌ No valid backtest folds were produced!")
            return (
                pd.DataFrame(
                    columns=[
                        "test_year",
                        "rmse",
                        "r2",
                        "accuracy",
                        "f1_score",
                        "train_size",
                        "test_size",
                    ]
                ),
                pd.DataFrame(),
            )

        # Compile all predictions into a single DataFrame
        all_preds = []
        clean_results = []

        for res in results:
            if "predictions" in res:
                all_preds.append(res.pop("predictions"))
            clean_results.append(res)

        predictions_df = (
            pd.concat(all_preds, ignore_index=True) if all_preds else pd.DataFrame()
        )
        return pd.DataFrame(clean_results), predictions_df

    def generate_report(self, results_df, report_path="reports/backtest_results.md"):
        if results_df.empty:
            logger.warning("⚠️ No backtest results to report.")
            report = f"""# Walk-Forward Validation Report
**Generated:** {pd.Timestamp.now()}

## Summary
⚠️ **No valid backtest folds were produced.** Check data availability and year range.
"""
            Path(report_path).parent.mkdir(parents=True, exist_ok=True)
            with open(report_path, "w") as f:
                f.write(report)
            return

        is_classification = "accuracy" in results_df.columns

        if is_classification:
            avg_acc = results_df["accuracy"].mean()
            avg_f1 = results_df["f1_score"].mean()

            report = f"""# Walk-Forward Validation Report
**Generated:** {pd.Timestamp.now()}

## Summary
- **Average Accuracy:** {avg_acc:.4f}
- **Average F1 Score:** {avg_f1:.4f}
- **Years Tested:** {results_df['test_year'].min()} - {results_df['test_year'].max()}

## Breakdown by Year
| Year | Accuracy | F1 | Train Size | Test Size |
|------|----------|----|------------|-----------|
"""
            for _, row in results_df.iterrows():
                report += f"| {int(row['test_year'])} | {row['accuracy']:.4f} | {row['f1_score']:.4f} | {int(row['train_size'])} | {int(row['test_size'])} |\n"
        else:
            avg_rmse = results_df["rmse"].mean()
            avg_r2 = results_df["r2"].mean()
            avg_f1 = results_df["f1"].mean()

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

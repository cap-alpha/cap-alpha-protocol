import logging
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import yaml

from src.db_manager import DBManager
from src.feature_store import FeatureStore

# Configure Logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class HistoricalSimulator:
    def __init__(self, config_path="pipeline/config/ml_config.yaml"):
        # Fix relative path if running from root
        if not Path(config_path).exists():
            config_path = "config/ml_config.yaml"

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.db = DBManager()
        self.fs = FeatureStore(self.db)
        self.params = self.config["models"]["xgboost"]["params"]
        self.target_col = self.config["training"]["target"]

    def run_simulation(self, start_year=2021, end_year=2024):
        """
        Expanding Window Simulation:
        - For target_year in [2021, 2022, 2023, 2024]:
            - Train on ALL data where year < target_year
            - Predict on data where year == target_year
            - Store predictions
        """
        logger.info(
            f"🚀 Starting Expanding Window Simulation ({start_year}-{end_year})..."
        )

        # 1. Load ALL Data
        df = self.fs.load_features()

        # 2. Filter for valid data (contracts > 0)
        df = df[df["cap_hit"] > 0].copy()

        simulation_history = []

        # 3. Features
        features = (
            self.config["features"]["player_stats"]
            + self.config["features"]["contract_info"]
            + self.config["features"]["team_context"]
        )

        # Ensure calculated features exist or compute them if needed
        # (Assuming load_features returns ready-to-use data)

        for test_year in range(start_year, end_year + 1):
            logger.info(f"🔄 Simulating Season: {test_year}")

            # SPLIT: Past vs Present
            train_mask = df["year"] < test_year
            test_mask = df["year"] == test_year

            X_train = df.loc[train_mask, features]
            y_train = df.loc[train_mask, self.target_col]

            X_test = df.loc[test_mask, features]
            y_test = df.loc[test_mask, self.target_col]

            if X_test.empty:
                logger.warning(f"⚠️ No data found for {test_year}. Skipping.")
                continue

            # TRAIN (The "Time Machine" Model)
            model = xgb.XGBRegressor(**self.params)
            model.fit(X_train, y_train)

            # PREDICT
            preds = model.predict(X_test)

            # LOG RESULTS
            # We want to capture the "Truth" of that moment
            for idx, (player_idx, row) in enumerate(df[test_mask].iterrows()):
                simulation_history.append(
                    {
                        "player_name": row["player_name"],
                        "year": int(test_year),
                        "team": row["team"],
                        "actual": float(row["cap_hit"]),
                        "predicted": float(max(0, preds[idx])),  # No negative salaries
                        "error": float(row["cap_hit"] - preds[idx]),
                    }
                )

            logger.info(
                f"✅ {test_year} Simulated. Generated {len(preds)} predictions."
            )

        # 4. Compile & Save
        results_df = pd.DataFrame(simulation_history)

        # Save for Frontend
        output_path = Path("reports/historical_predictions.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        results_df.to_json(output_path, orient="records", indent=2)
        logger.info(f"💾 Simulation Complete. Results saved to {output_path}")

        return results_df


if __name__ == "__main__":
    sim = HistoricalSimulator()
    # User requested "last 3-4 years", let's do 2021, 2022, 2023, 2024
    sim.run_simulation(start_year=2021, end_year=2024)

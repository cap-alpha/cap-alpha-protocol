import pandas as pd
import numpy as np
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from src.db_manager import DBManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(name)s:%(message)s')
logger = logging.getLogger(__name__)

def run_diagnostics():
    with DBManager() as db:
        logger.info("Fetching Gold Matrix (`fact_player_efficiency`) for Diagnostic Analysis...")
        try:
            df = db.execute("SELECT * FROM fact_player_efficiency").df()
        except Exception as e:
            logger.error(f"Failed to query fact_player_efficiency: {e}")
            return

        logger.info(f"Loaded {len(df)} rows.")

        print("\n" + "="*50)
        print("🎯 TARGET DIAGNOSTICS & STATISTICAL ASSERTIONS")
        print("="*50)

        # 1. Target A: Absolute Dollar Variance (The Control/Failure)
        mean_true = df['true_bust_variance'].mean()
        std_true = df['true_bust_variance'].std()
        print(f"\n[Target A: true_bust_variance] => Absolute Dollar Variance")
        print(f"Mean:   ${mean_true:,.2f}M")
        print(f"StdDev: ${std_true:,.2f}M")
        print(f"Skew:   {df['true_bust_variance'].skew():.2f}")
        print(f"Kurt:   {df['true_bust_variance'].kurtosis():.2f}")
        
        # 2. Target B: Dimensionless Efficiency Ratio
        # Need to clean infs and NAs
        ratio_clean = df['efficiency_ratio'].replace([np.inf, -np.inf], np.nan).dropna()
        print(f"\n[Target B: efficiency_ratio] => Dimensionless ROI Multiplier")
        print(f"Mean:   {ratio_clean.mean():.4f}x")
        print(f"Median: {ratio_clean.median():.4f}x")
        print(f"StdDev: {ratio_clean.std():.4f}")
        print(f"Skew:   {ratio_clean.skew():.2f} (Targeting < |2.0| for normal decay)")
        print(f"Kurt:   {ratio_clean.kurtosis():.2f} (Targeting < 3.0 to avoid fat tails)")

        # 3. Target C: Binary Classification Balance
        print(f"\n[Target C: is_bust_binary] => Underperformance Boolean (Threshold: 0.70x ROI)")
        vc = df['is_bust_binary'].value_counts(normalize=True) * 100
        print(f"Class 1 (Busts):    {vc.get(1, 0):.2f}%")
        print(f"Class 0 (Success):  {vc.get(0, 0):.2f}%")

        # 4. Positional Volatility Analysis
        print("\n[Positional Variance Analysis] => Which roles have the wildest ROI swings?")
        pos_var = df.groupby('position')['efficiency_ratio'].std().sort_values(ascending=False).head(10)
        print(pos_var)

if __name__ == "__main__":
    run_diagnostics()

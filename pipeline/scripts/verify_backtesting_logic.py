from src.db_manager import DBManager
import pandas as pd
import numpy as np
import logging
from src.train_model import RiskModeler
import os
import shutil

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEMP_DB = "/tmp/nfl_verify.db"

def create_synthetic_data():
    if os.path.exists(TEMP_DB):
        os.remove(TEMP_DB)
        
    con = DBManager()
    
    # Create synthetic features
    n_rows = 1000
    df = pd.DataFrame({
        'player_name': [f'Player_{i}' for i in range(n_rows)],
        'year': np.random.choice(range(2018, 2026), n_rows),
        'team': 'NE',
        'experience_years': np.random.randint(1, 10, n_rows),
        'edce_risk': np.random.rand(n_rows),
        'fair_market_value': np.random.rand(n_rows) * 100,
        'ied_overpayment': np.random.rand(n_rows) * 10,
        'value_metric_proxy': np.random.rand(n_rows),
        'age': np.random.randint(21, 35, n_rows),
        'feature_1': np.random.rand(n_rows),
        'feature_2': np.random.rand(n_rows)
    })
    
    con.execute("CREATE TABLE staging_feature_matrix AS SELECT * FROM df")
    con.close()
    logger.info(f"Created synthetic DB at {TEMP_DB}")

def main():
    create_synthetic_data()
    
    # Override DB_PATH
    os.environ["DB_PATH"] = TEMP_DB
    
    logger.info("Initializing RiskModeler...")
    modeler = RiskModeler(db_path=TEMP_DB)
    
    logger.info("Preparing Data...")
    X, y, metadata = modeler.prepare_data()
    
    logger.info("Training with Walk-Forward Validation...")
    model, _, results = modeler.train_xgboost(X, y, metadata)
    
    print("\n--- Verification Results ---")
    print(results)
    
    if len(results) > 0:
        print("\n✅ Verification SUCCESS: Backtesting produced results.")
    else:
        print("\n❌ Verification FAILED: No results returned.")
        exit(1)

if __name__ == "__main__":
    main()

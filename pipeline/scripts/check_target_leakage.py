import pandas as pd
import numpy as np
import xgboost as xgb
import sys
from pathlib import Path
import logging

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from src.train_model import RiskModeler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_leakage():
    logger.info("Initializing RiskModeler to check for Target Leakage...")
    modeler = RiskModeler(read_only=True)
    
    # 1. Prepare Data
    X, y, metadata = modeler.prepare_data()
    
    # 2. Train a quick model
    logger.info(f"Training XGBoost on {len(X)} rows to assess feature importance...")
    model = xgb.XGBRegressor(n_estimators=50, max_depth=4, learning_rate=0.1)
    model.fit(X, y)
    
    # 3. Analyze Feature Importances
    importances = model.feature_importances_
    df_imp = pd.DataFrame({'feature': X.columns, 'importance': importances})
    df_imp = df_imp.sort_values('importance', ascending=False)
    
    logger.info("\n====== TOP 15 FEATURES BY IMPORTANCE ======")
    print(df_imp.head(15).to_string(index=False))
    
    # 4. Leakage Heuristic Check
    # If the top feature holds > 50% importance, or top 2 hold > 80%, flag it.
    top_1_imp = df_imp.iloc[0]['importance']
    top_2_imp = df_imp.iloc[0:2]['importance'].sum()
    
    logger.info("\n====== TARGET LEAKAGE ANALYSIS ======")
    if top_1_imp > 0.50:
        logger.error(f"🚨 EXTREME LEAKAGE RISK: '{df_imp.iloc[0]['feature']}' accounts for {top_1_imp*100:.1f}% of model splits!")
        sys.exit(1)
    elif top_2_imp > 0.80:
        logger.warning(f"⚠️ POTENTIAL LEAKAGE: Top 2 features account for {top_2_imp*100:.1f}% of splits.")
    else:
        logger.info("✅ Feature importance looks distributed normally. No single feature dominates >50%.")
        
    # Check for direct correlations
    logger.info("\n====== CORRELATION CHECK ======")
    corrs = []
    for col in df_imp.head(10)['feature']:
        corr = np.corrcoef(X[col], y)[0, 1]
        corrs.append({'feature': col, 'correlation_with_target': corr})
    
    df_corr = pd.DataFrame(corrs)
    print(df_corr.to_string(index=False))
    
    for c in corrs:
        if abs(c['correlation_with_target']) > 0.85:
            logger.error(f"🚨 EXTREME LEAKAGE RISK: '{c['feature']}' has a {c['correlation_with_target']:.3f} correlation with target!")
            sys.exit(1)
            
    logger.info("✅ No features have > 0.85 direct linear correlation with the target.")
    return 0

if __name__ == "__main__":
    check_leakage()

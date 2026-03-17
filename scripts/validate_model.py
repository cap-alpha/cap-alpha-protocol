import duckdb
import pandas as pd
import os
import argparse
from sklearn.metrics import root_mean_squared_error, mean_absolute_error, accuracy_score

from dotenv import load_dotenv

def get_db_connection():
    """Connect to MotherDuck using the environment token."""
    load_dotenv('.env')
    token = os.environ.get("MOTHERDUCK_TOKEN")
    if not token:
        # Fallback to a local db if absolutely necessary, but Motherduck is the source of truth
        print("WARNING: MOTHERDUCK_TOKEN not found. Trying local db.")
        return duckdb.connect("data/duckdb/nfl_data.db")
    
    # Use md: connection string
    return duckdb.connect(f"md:nfl_dead_money?motherduck_token={token}")

def run_temporal_validation(db):
    """
    Executes the Walk-Forward (Expanding Window) validation.
    For each prediction made in Year Y, it joins against the ACTUAL 'risk_score' and 'cap_hit_millions' in Year Y.
    (Note: The model might be predicting Year Y performance based on Year Y-1 data.)
    """
    
    print("\n==================================================")
    print(" CAP ALPHA PROTOCOL - TEMPORAL VALIDATION ENGINE")
    print("==================================================\n")

    print(f"Fetching predictions and ground truth from the Data Lake...")

    # We want to join prediction_results (what the model predicted for Year Y)
    # with fact_player_efficiency (the actual empirical results for Year Y).
    
    query = """
    SELECT 
        p.year,
        p.player_name,
        p.predicted_risk_score,
        p.high_uncertainty_flag,
        f.is_bust_binary as actual_risk_score,
        f.cap_hit_millions as actual_cap_hit
    FROM 
        prediction_results p
    INNER JOIN 
        fact_player_efficiency f ON p.player_name = f.player_name AND p.year = f.year
    -- Ensure we only evaluate the final prediction for that year (e.g. max week)
    WHERE p.week = (SELECT MAX(week) FROM prediction_results p2 WHERE p2.year = p.year)
    ORDER BY 
        p.year ASC;
    """
    
    try:
        df = db.execute(query).df()
    except Exception as e:
        print(f"Failed to execute validation query: {e}")
        return
        
    if df.empty:
        print("No overlapping data found between predictions and facts.")
        return
        
    print(f"Retrieved {len(df)} intersecting validation records.\n")
    
    years = sorted(df['year'].unique())
    
    total_samples = len(df)
    
    print("WALK-FORWARD VALIDATION RESULTS BY SEASON")
    print("-" * 65)
    print(f"{'Season':<10} | {'Samples':<10} | {'Risk Acc.':<15} | {'High Uncertainty %':<20}")
    print("-" * 65)
    
    all_actuals = []
    all_preds = []
    
    for year in years:
        year_df = df[df['year'] == year]
        
        # Binary Classification Accuracy for Risk Score
        # Model predicts 1 (High Risk) or 0 (Low Risk).
        # We need to binarize the actual risk score (which is 0-1 continuous) 
        # Assume actual risk > 0.7 is a "Bust/High Risk"
        actual_binary = (year_df['actual_risk_score'] > 0.7).astype(int)
        pred_binary = year_df['predicted_risk_score'].astype(int)
        
        accuracy = accuracy_score(actual_binary, pred_binary)
        
        uncertain_pct = (year_df['high_uncertainty_flag'] == 1).mean() * 100
        
        print(f"{year:<10} | {len(year_df):<10} | {accuracy*100:^13.1f}% | {uncertain_pct:^18.1f}%")
        
        all_actuals.extend(actual_binary)
        all_preds.extend(pred_binary)
        
    print("-" * 65)
    
    overall_acc = accuracy_score(all_actuals, all_preds)
    print(f"\nOVERALL TEMPORAL ACCURACY: {overall_acc*100:.2f}% (N={total_samples})")
    
    if overall_acc > 0.8:
        print("Validation Status: PASSED")
    elif overall_acc > 0.6:
        print("Validation Status: WARNING (Degradation Detected)")
    else:
        print("Validation Status: FAILED (Severe Rot Leakage)")
        

if __name__ == "__main__":
    db = get_db_connection()
    run_temporal_validation(db)

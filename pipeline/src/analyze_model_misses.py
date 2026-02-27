import json
import pandas as pd
from pathlib import Path

def analyze_misses():
    repo_root = Path(__file__).resolve().parent.parent.parent
    data_path = repo_root / "reports" / "historical_predictions.json"
    
    try:
        with open(data_path, 'r') as f:
            raw_data = json.load(f)
            
        for p in raw_data:
            p['delta'] = p['actual'] - p['predicted']
            
        sorted_data = sorted(raw_data, key=lambda x: x['delta'])
        false_positives = pd.DataFrame(sorted_data[:50])
        
        sorted_data_desc = sorted(raw_data, key=lambda x: x['delta'], reverse=True)
        false_negatives = pd.DataFrame(sorted_data_desc[:50])
            
    except Exception as e:
        print(f"❌ Failed to load local predictions: {e}")
        return
        
    repo_root = Path("/Users/andrewsmith/Documents/portfolio/nfl-dead-money")
    
    # Round metrics for display
    try:
        for col in ['actual', 'predicted', 'delta']:
            if col in false_positives.columns:
                false_positives[col] = pd.to_numeric(false_positives[col], errors='coerce').round(2)
            if col in false_negatives.columns:
                false_negatives[col] = pd.to_numeric(false_negatives[col], errors='coerce').round(2)
    except Exception as e:
        print(f"Warning: Could not round metrics: {e}")
        
    report = f"""# Cap Alpha Model Miss Analysis 
This diagnostic report details the worst prediction misses from the XGBoost Walk-Forward validation, sorting them into clear categories for manual review and architecture tuning.

## Top 50 False Positives (Model Called 'Bust', Player Was 'Safe')
These are players the ML model identified as toxic or high-risk, but who ultimately generated minimal dead money or performed well. 
*Diagnostic check: Is the model over-weighing injury history? Is it failing to understand cheap QB extensions?*

{false_positives[['player_name', 'year', 'week', 'team', 'predicted', 'actual', 'delta']].to_markdown(index=False)}

## Top 50 False Negatives (Model Called 'Safe', Player Was 'Bust')
These are players the ML model believed were stable, highly-efficient assets extending their prime, but who catastrophicly failed and generated massive dead money liability.
*Diagnostic check: Were these isolated ACL tears? Or is the model completely missing a common degradation cliff (e.g. RBs after age 28)?*

{false_negatives[['player_name', 'year', 'week', 'team', 'predicted', 'actual', 'delta']].to_markdown(index=False)}
"""
    
    report_path = repo_root / "reports" / "model_miss_analysis.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
        
    print(f"✅ Diagnostic model miss report generated at {report_path}")

if __name__ == "__main__":
    analyze_misses()

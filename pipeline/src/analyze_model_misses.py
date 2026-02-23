import json
import pandas as pd
from pathlib import Path

def analyze_misses():
    # Fetch the backtest predictions exported from Walk-Forward Validation via the API proxy
    import urllib.request
    
    try:
        req = urllib.request.Request("http://localhost:3000/api/misses")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"❌ Failed to fetch misses from API: {e}")
        return
        
    repo_root = Path("/Users/andrewsmith/Documents/portfolio/nfl-dead-money")
    
    false_positives = pd.DataFrame(data['falsePositives'])
    false_negatives = pd.DataFrame(data['falseNegatives'])
    
    # Round metrics for display
    for col in ['actual', 'predicted', 'delta']:
        false_positives[col] = false_positives[col].round(2)
        false_negatives[col] = false_negatives[col].round(2)
        
    report = f"""# Cap Alpha Model Miss Analysis 
This diagnostic report details the worst prediction misses from the XGBoost Walk-Forward validation, sorting them into clear categories for manual review and architecture tuning.

## Top 50 False Positives (Model Called 'Bust', Player Was 'Safe')
These are players the ML model identified as toxic or high-risk, but who ultimately generated minimal dead money or performed well. 
*Diagnostic check: Is the model over-weighing injury history? Is it failing to understand cheap QB extensions?*

{false_positives[['player_name', 'year', 'team', 'predicted', 'actual', 'delta']].to_markdown(index=False)}

## Top 50 False Negatives (Model Called 'Safe', Player Was 'Bust')
These are players the ML model believed were stable, highly-efficient assets extending their prime, but who catastrophicly failed and generated massive dead money liability.
*Diagnostic check: Were these isolated ACL tears? Or is the model completely missing a common degradation cliff (e.g. RBs after age 28)?*

{false_negatives[['player_name', 'year', 'team', 'predicted', 'actual', 'delta']].to_markdown(index=False)}
"""
    
    report_path = repo_root / "pipeline" / "reports" / "model_miss_analysis.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write(report)
        
    print(f"✅ Diagnostic model miss report generated at {report_path}")

if __name__ == "__main__":
    analyze_misses()

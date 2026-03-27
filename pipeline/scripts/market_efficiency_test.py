from src.db_manager import DBManager
import pandas as pd
import statsmodels.api as sm
import numpy as np

DB_PATH = "data/nfl_belichick.db"
OUTPUT_FILE = "reports/market_efficiency_findings.md"

def run_efficiency_test():
    con = DBManager()
    
    print("Running Market Efficiency Test on 15 Years of Data...")
    
    # 1. Prepare the Panel Data
    # We need: Contract Value (Target), Production Metrics (Controls), Penalty Metrics (Treatment)
    query = """
    WITH lagged_performance AS (
        SELECT 
            player_name,
            year,
            position,
            cap_hit_millions,
            total_penalty_yards,
            -- Controls
            games_played,
            (COALESCE(total_pass_yds,0) + COALESCE(total_rush_yds,0) + COALESCE(total_rec_yds,0)) as total_production_yards,
            experience_years,
            -- Lagged Penalty (Did they have penalties in previous year?)
            LAG(total_penalty_yards) OVER (PARTITION BY player_name ORDER BY year) as prev_penalty_yards,
            -- Lagged Production (Did they play?)
            LAG(games_played) OVER (PARTITION BY player_name ORDER BY year) as prev_games
        FROM fact_player_efficiency
        WHERE position IN ('CB', 'WR', 'OL', 'DL') 
    )
    SELECT * FROM lagged_performance 
    WHERE prev_penalty_yards IS NOT NULL 
    AND prev_games > 0
    AND cap_hit_millions > 1.0 
    """
    
    df = con.execute(query).df()
    
    # Robust numeric conversion
    numeric_cols = ['cap_hit_millions', 'prev_games', 'total_production_yards', 'experience_years', 'prev_penalty_yards']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
    df = df[df['cap_hit_millions'] > 0] # Avoid log(0) errors
    
    results_md = "# Market Efficiency Audit: The Disciplinary Pricing Test\n\n"
    
    # 2. RUN REGRESSION 1: Does the market discount for penalties?
    
    features = ['prev_games', 'total_production_yards', 'experience_years', 'prev_penalty_yards']
    target = 'cap_hit_millions'
    
    # Log transform target 
    y = np.log(df[target])
    X = df[features]
    X = sm.add_constant(X)
    
    model_pricing = sm.OLS(y, X).fit()
    
    results_md += "## Test 1: Does the Market 'Price In' Discipline?\n"
    results_md += f"**Hypothesis**: High previous penalties should correlate with LOWER salary (Negative Coefficient).\n\n"
    results_md += f"**Observations**: {len(df)}\n"
    results_md += f"**R-squared**: {model_pricing.rsquared:.3f}\n\n"
    results_md += "| Feature | Coefficient | P-Value | Interpretation |\n"
    results_md += "|---|---|---|---|\n"
    
    for term in features:
        coef = model_pricing.params[term]
        pval = model_pricing.pvalues[term]
        interp = "Significant" if pval < 0.05 else "Not Significant"
        results_md += f"| {term} | {coef:.4f} | {pval:.4f} | {interp} |\n"
        
    penalty_coef = model_pricing.params['prev_penalty_yards']
    penalty_pval = model_pricing.pvalues['prev_penalty_yards']
    
    if penalty_pval < 0.05 and penalty_coef < 0:
        conclusion_1 = "✅ **Market is EFFICIENT**: Teams actively discount players with high penalty history."
    else:
        conclusion_1 = "❌ **Market is INEFFICIENT**: Teams DO NOT significantly discount salary for disciplinary issues."
        
    results_md += f"\n**Conclusion**: {conclusion_1}\n\n"
    
    # 3. RUN REGRESSION 2: Do penalties predict future value decline?
    # (Simplified test: Correlation between penalty_yards and NEXT year's Games/Production)
    
    results_md += "## Test 2: Do Penalties Predict Future Decline?\n"
    query_risk = """
    SELECT 
        player_name,
        total_penalty_yards,
        games_played as current_games,
        LEAD(games_played) OVER (PARTITION BY player_name ORDER BY year) as next_year_games
    FROM fact_player_efficiency
    WHERE position IN ('CB', 'WR', 'OL', 'DL')
    """
    df_risk = con.execute(query_risk).df().dropna()
    df_risk['games_change'] = df_risk['next_year_games'] - df_risk['current_games']
    
    X_risk = sm.add_constant(df_risk['total_penalty_yards'])
    y_risk = df_risk['games_change']
    
    model_risk = sm.OLS(y_risk, X_risk).fit()
    
    risk_coef = model_risk.params['total_penalty_yards']
    risk_pval = model_risk.pvalues['total_penalty_yards']
    
    results_md += f"**Hypothesis**: High penalties predict a steeper decline in availability (Negative Games Change).\n\n"
    results_md += f"| Feature | Coefficient | P-Value |\n|---|---|---|\n"
    results_md += f"| Total Penalty Yards | {risk_coef:.4f} | {risk_pval:.4f} |\n\n"
    
    if risk_pval < 0.05 and risk_coef < 0:
        conclusion_2 = "✅ **True Risk Vector**: High penalties are a leading indicator of availability decline."
    else:
        conclusion_2 = "❌ **Noise**: Penalties do not reliably predict decline."
        
    results_md += f"**Conclusion**: {conclusion_2}\n\n"
    
    # FINAL SYNTHESIS
    results_md += "## Strategic Synthesis\n"
    if "INEFFICIENT" in conclusion_1 and "True Risk" in conclusion_2:
        results_md += "**💎 THE SMOKING GUN FOUND**: Penalties predict decline, but the market DOES NOT price them in. This is a massive arbitrage opportunity."
    elif "EFFICIENT" in conclusion_1:
         results_md += "**Market is Efficient**: The market correctly prices disciplinary risk. No arbitrage available."
    else:
        results_md += "**Inconclusive**: Further position-specific modeling required."

    with open(OUTPUT_FILE, "w") as f:
        f.write(results_md)
        
    print(f"Analysis Complete. Results saved to {OUTPUT_FILE}")
    print(conclusion_1)
    print(conclusion_2)

if __name__ == "__main__":
    run_efficiency_test()

from src.db_manager import DBManager
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from pathlib import Path

# Use a sleek dark theme
plt.style.use('dark_background')

DB_PATH = "data/nfl_belichick.db"
OUTPUT_PATH = "reports/real_discipline_frontier.png"

def generate_frontier_plot():
    con = DBManager()
    
    # Query the 2025 Gold Layer
    query = """
    SELECT 
        player_name, 
        team,
        cap_hit_millions, 
        combined_roi_score,
        total_penalty_yards,
        edce_risk
    FROM fact_player_efficiency 
    WHERE year = 2025 
    AND cap_hit_millions > 0
    AND combined_roi_score IS NOT NULL
    """
    df = con.execute(query).df()
    
    # Cap the ROI for better visualization (extreme outliers squash the chart)
    df['combined_roi_score_capped'] = df['combined_roi_score'].clip(upper=df['combined_roi_score'].quantile(0.95))
    
    plt.figure(figsize=(14, 10))
    
    # Scatter plot: X=Cap Hit, Y=ROI, Color=Risk
    scatter = plt.scatter(
        df['cap_hit_millions'], 
        df['combined_roi_score_capped'], 
        c=df['edce_risk'], 
        cmap='RdYlGn_r', # Red for high risk, Green for low
        alpha=0.6,
        edgecolors='white',
        linewidth=0.5,
        s=df['cap_hit_millions'] * 5 + 20 # Size based on cap hit
    )
    
    # 1. Define interesting players to highlight
    highlights = [
        {"name": "Saquon Barkley", "color": "#00ffcc", "va": "bottom"},
        {"name": "Jayden Daniels", "color": "#00ffcc", "va": "top"},
        {"name": "Brock Purdy", "color": "#00ffcc", "va": "bottom"},
        {"name": "Riley Moss", "color": "#ff4d4d", "va": "top"},
        {"name": "Jawaan Taylor", "color": "#ff4d4d", "va": "bottom"},
        {"name": "Chris Jones", "color": "#ff4d4d", "va": "top"}
    ]
    
    for h in highlights:
        player_data = df[df['player_name'] == h['name']]
        if not player_data.empty:
            row = player_data.iloc[0]
            plt.annotate(
                h['name'], 
                (row['cap_hit_millions'], row['combined_roi_score_capped']),
                xytext=(8, 8) if h['va'] == 'bottom' else (8, -15),
                textcoords='offset points',
                color='white',
                fontweight='bold',
                fontsize=12,
                bbox=dict(boxstyle='round,pad=0.3', fc=h['color'], alpha=0.3, ec='white', lw=1),
                arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0.1', color='white')
            )

    # 2. Add Zone Labels
    plt.text(df['cap_hit_millions'].max() * 0.1, df['combined_roi_score_capped'].max() * 0.9, 
             "THE ALPHA ZONE\n(High Efficiency, Low Risk)", color="#00ffcc", fontsize=16, fontweight='bold', alpha=0.8)
    
    plt.text(df['cap_hit_millions'].max() * 0.7, df['combined_roi_score_capped'].min() * 1.1, 
             "THE TOXIC DEBT ZONE\n(Ineligible ROI, High Risk)", color="#ff4d4d", fontsize=16, fontweight='bold', alpha=0.8)

    # 3. Aesthetics
    plt.xlabel("Cap Hit (Millions $)", fontsize=14, fontweight='bold', color='gray')
    plt.ylabel("Combined ROI Score (Football + Commercial)", fontsize=14, fontweight='bold', color='gray')
    plt.title("THE 2025 DISCIPLINE FRONTIER: Realized ROI vs. Cap Exposure", fontsize=22, fontweight='bold', pad=30)
    
    # Colorbar for Risk
    cbar = plt.colorbar(scatter)
    cbar.set_label('EDCE Risk Score', rotation=270, labelpad=20, fontsize=12, fontweight='bold')
    
    plt.grid(True, linestyle='--', alpha=0.2)
    sns.despine()
    
    plt.tight_layout()
    plt.savefig(OUTPUT_PATH, dpi=300)
    print(f"✓ Real data frontier plot generated at {OUTPUT_PATH}")
    con.close()

if __name__ == "__main__":
    generate_frontier_plot()

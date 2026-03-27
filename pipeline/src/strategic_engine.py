
from src.db_manager import DBManager
import pandas as pd
import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class StrategicEngine:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.con = None

    def _connect(self):
        if self.con is None:
            self.con = DBManager()

    def get_team_metrics(self, year: int = 2025) -> pd.DataFrame:
        """
        Aggregate team-level risk and efficiency metrics.
        """
        self._connect()
        query = f"""
            WITH team_stats AS (
                SELECT 
                    f.team,
                    AVG(p.predicted_risk_score) as avg_risk,
                    AVG(f.fair_market_value) as avg_efficiency,
                    SUM(f.cap_hit_millions) as total_cap,
                    SUM(p.predicted_risk_score * f.cap_hit_millions) as total_weighted_risk,
                    COUNT(*) as roster_size
                FROM fact_player_efficiency f
                JOIN prediction_results p 
                  ON f.player_name = p.player_name AND f.year = p.year AND f.team = p.team
                WHERE f.year = {year}
                GROUP BY f.team
            ),
            top_risks AS (
                SELECT 
                    p.team, 
                    p.player_name, 
                    p.predicted_risk_score,
                    f.position,
                    ROW_NUMBER() OVER (PARTITION BY p.team ORDER BY p.predicted_risk_score DESC) as rnk
                FROM prediction_results p
                JOIN fact_player_efficiency f ON p.player_name = f.player_name AND p.year = f.year AND p.team = f.team
                WHERE p.year = {year}
            ),
            position_risk AS (
                SELECT 
                    f.team,
                    f.position,
                    SUM(p.predicted_risk_score) as positional_toxicity,
                    ROW_NUMBER() OVER (PARTITION BY f.team ORDER BY SUM(p.predicted_risk_score) DESC) as pos_rnk
                FROM fact_player_efficiency f
                JOIN prediction_results p 
                  ON f.player_name = p.player_name AND f.year = p.year AND f.team = p.team
                WHERE f.year = {year}
                GROUP BY f.team, f.position
            )
            SELECT 
                ts.*,
                tr.player_name as anchor_risk_player,
                tr.predicted_risk_score as anchor_risk_score,
                tr.position as anchor_risk_position,
                pr.position as top_risk_position
            FROM team_stats ts
            LEFT JOIN top_risks tr ON ts.team = tr.team AND tr.rnk = 1
            LEFT JOIN position_risk pr ON ts.team = pr.team AND pr.pos_rnk = 1
            ORDER BY ts.avg_risk DESC
        """
        return self.con.execute(query).df()

    def check_succession_plan(self, team: str, position: str) -> Optional[str]:
        """
        Check if a team has recently invested high draft capital (Rounds 1-3) 
        in a specific position over the last 2 years.
        """
        if not position:
            return None
            
        # Normalize position groups for draft matching
        # e.g. 'LT'/'RT' -> 'OT', 'FS'/'SS' -> 'S', 'OLB'/'ILB' -> 'LB'
        pos_map = {
            'LT': 'OT', 'RT': 'OT', 
            'FS': 'S', 'SS': 'S', 
            'OLB': 'LB', 'ILB': 'LB',
            'EDGE': 'DE', # Handle edge cases
        }
        search_pos = pos_map.get(position, position)
        
        # We query the silver_pfr_draft_history table if it exists
        try:
            # Check if table exists first using self.con (duckdb)
            table_exists = self.con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'silver_pfr_draft_history'").fetchone()[0]
            if not table_exists:
                return None

            query = f"""
                SELECT player_name, round, year
                FROM silver_pfr_draft_history
                WHERE team = '{team}' 
                  AND (position = '{search_pos}' OR position = '{position}')
                  AND round <= 3
                  AND year >= 2023
                ORDER BY year DESC, round ASC
                LIMIT 1
            """
            result = self.con.execute(query).fetchone()
            if result:
                player, rnd, yr = result
                return f"{player} (Rd {rnd}, {yr})"
        except Exception as e:
            logger.warning(f"Successor check failed: {e}")
            return None
            
        return None

    def check_fa_signings(self, team: str, position: str) -> Optional[str]:
        """
        Check if a team has signed a 'Big Splash' Free Agent (>$10M APY) 
        at the specific position in the current year (2025).
        """
        if not position:
            return None
            
        try:
             # Normalize position groups (similar to draft logic)
            pos_map = {
                'LT': 'OT', 'RT': 'OT', 
                'FS': 'S', 'SS': 'S', 
                'OLB': 'LB', 'ILB': 'LB',
                'EDGE': 'DE',
            }
            search_pos = pos_map.get(position, position)

            # Query silver_spotrac_contracts
            # We assume year_signed is available as 'year_signed' or we derive it.
            # Based on scraper, we have 'year' as the roster year, but we need to check 'year_signed' if available
            # or infer it. Let's assume we look for contracts valid in 2025 with high AAV that are 'active'.
            
            # Actually, looking at ingest, we load 'silver_spotrac_contracts'.
            # Let's check for year_signed=2025 and avg_value > 10.
            
            query = f"""
                SELECT player
                FROM silver_spotrac_contracts
                WHERE team = '{team}' 
                  AND (pos = '{search_pos}' OR pos = '{position}')
                  AND year_signed = 2025
                  AND avg_value_millions > 10.0
                LIMIT 1
            """
            result = self.con.execute(query).fetchone()
            if result:
                return f"{result[0]} (FA '25)"
                
        except Exception as e:
            logger.warning(f"FA Splash check failed: {e}")
            return None
        return None

    def prescribe(self, row: pd.Series) -> Tuple[str, str]:
        """
        Strategic Prescription Logic.
        Returns (prescription_text, draft_priority_text)
        """
        # Strategic Prescription
        if row['avg_risk'] > 0.6 and row['avg_efficiency'] < 0.5:
            strat = "🛑 **EMERGENCY PURGE**: High toxic dead-money risk paired with non-existent performance efficiency. Recommend mass veteran releases."
        elif row['avg_risk'] > 0.4:
            strat = "⚠️ **STRUCTURAL REBALANCING**: Significant cap-at-risk. Focus on draft-led replacement for aging veterans ({}).".format(row['anchor_risk_player'])
        elif row['avg_efficiency'] > 1.2:
            strat = "🚀 **AGGRESSIVE EXPANSION**: High-efficiency roster with low overall risk. Team has a window to acquire 'Blue Chips'."
        else:
            strat = "⚖️ **SELECTIVE OPTIMIZATION**: Balanced profile. Maintain current trajectory, focus on surgical upgrades."
        
        # Tactical Draft Priority with Multimodal Context
        draft_pos = row['top_risk_position'] or row['anchor_risk_position']
        
        fa_solution = self.check_fa_signings(row['team'], draft_pos) if pd.notna(draft_pos) else None
        successor = self.check_succession_plan(row['team'], draft_pos) if pd.notna(draft_pos) and not fa_solution else None
        
        if fa_solution:
            draft = f"**FA Solution Acquired**: {fa_solution} signed in Free Agency to replace {row['anchor_risk_player']}."
        elif successor:
            draft = f"**Develop Successor**: {successor} is already on-roster to replace {row['anchor_risk_player']}."
        elif pd.isna(draft_pos):
            draft = "Best Player Available (BPA)"
        else:
            draft = f"**{draft_pos}** (To replace aging {row['anchor_risk_player']} profile)"
            
        return strat, draft

    def generate_audit_report(self, report_path: str, year: int = 2025):
        """
        Generate the full strategic audit markdown report.
        """
        df = self.get_team_metrics(year)
        if df.empty:
            logger.error(f"No team metrics found for year {year}.")
            return

        # Apply prescriptions
        results = df.apply(self.prescribe, axis=1, result_type='expand')
        df['prescription'] = results[0]
        df['draft_priority'] = results[1]

        with open(report_path, 'w') as f:
            f.write(f"# 📑 NFL Team Strategic Audit: {year} Prescriptive Intelligence\n\n")
            f.write("> **Analysis Basis**: Machine-Learned Risk Frontier (XGBoost) vs. Value-Metric Efficiency. N=32 Teams.\n\n")
            
            f.write("## 🏛️ League-Wide Strategy Matrix\n\n")
            
            for _, row in df.iterrows():
                f.write(f"### {row['team']}\n")
                f.write(f"- **Risk Profile**: {row['avg_risk']:.3f} (Rank: {df[df['avg_risk'] > row['avg_risk']].count()['avg_risk'] + 1}/32)\n")
                f.write(f"- **Efficiency Quotient**: {row['avg_efficiency']:.2f}\n")
                f.write(f"- **Anchor Risk**: {row['anchor_risk_player']} (Score: {row['anchor_risk_score']:.2f})\n")
                f.write(f"- **Strategic Prescription**: {row['prescription']}\n")
                f.write(f"- **Draft Priority**: {row['draft_priority']}\n\n")
                f.write("---\n\n")

            f.write("\n\n> [!TIP]\n")
            f.write("> **Definition of Risk**: This score represents the longitudinal probability (24-month horizon) that a contract's dead money will exceed its realized performance value.\n")

        logger.info(f"✓ Strategic Audit generated at {report_path}")

    def close(self):
        if self.con:
            self.con.close()
            self.con = None

    def __del__(self):
        self.close()

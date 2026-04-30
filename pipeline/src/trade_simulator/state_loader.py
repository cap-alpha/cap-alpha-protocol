"""
Trade Simulator: State Loader (DuckDB Integration)
Author: Cap Alpha Protocol

Objective: Hydrate the 'LeagueState' from the production DuckDB.
Logic:
1. TeamState:
   - Cap Space = $255M (2025 Cap) - SUM(Cap Hit)
   - Roster Value = SUM(AV)
   - Needs = 1.0 - (TeamPosVal / LeagueAvgPosVal)
2. Market Players:
   - All active players with contracts in 2025.
"""

from typing import Dict, List

import pandas as pd
from google.api_core.exceptions import NotFound

from src.db_manager import DBManager

from .state import LeagueState, TeamState


class StateLoader:
    def __init__(self, db_path: str, year: int = 2025, min_cap_hit: float = None):
        self.con = DBManager()
        self.year = year
        self.SALARY_CAP = 255.0  # Millions (Should be dynamic map in future)

        # Dynamic Threshold: Default to ~0.75% of Cap if not specified
        # 2025 Example: 255 * 0.0075 = 1.91M (Close to the 2.0M heuristic)
        if min_cap_hit is None:
            self.min_cap_hit = self.SALARY_CAP * 0.0075
        else:
            self.min_cap_hit = min_cap_hit

    def load_league_state(self) -> LeagueState:
        print(f"🏈 Loading League State from BigQuery (Year: {self.year})...")

        # 1. Load Financials (Cap Space)
        fin_query = f"""
            SELECT 
                team, 
                SUM(cap_hit_millions) as used_cap
            FROM silver_spotrac_contracts
            WHERE year = {self.year} AND team IS NOT NULL
            GROUP BY team
        """
        df_fin = self.con.execute(fin_query).df().set_index("team")

        # 2. Load Roster Value (AV)
        val_query = f"""
            SELECT 
                team,
                SUM(1 - predicted_risk_score) as roster_quality
            FROM prediction_results
            WHERE year = {self.year}
            GROUP BY team
        """
        df_val = self.con.execute(val_query).df().set_index("team")

        # 3. Calculate Positional Needs (The "Gap Analysis")
        pos_query = f"""
            SELECT 
                p.team,
                c.position,
                SUM(1 - p.predicted_risk_score) as pos_quality
            FROM prediction_results p
            JOIN silver_spotrac_contracts c 
              ON p.player_name = c.player_name 
              AND p.year = c.year
            WHERE p.year = {self.year}
            GROUP BY p.team, c.position
        """
        df_pos = self.con.execute(pos_query).df()

        # Calculate League Averages per Position
        league_avgs = df_pos.groupby("position")["pos_quality"].mean().to_dict()

        # Build Team States
        teams: Dict[str, TeamState] = {}
        all_teams = df_fin.index.unique()

        for team in all_teams:
            # Cap Space
            used = df_fin.loc[team, "used_cap"] if team in df_fin.index else 0
            space = self.SALARY_CAP - used

            # Value
            val = df_val.loc[team, "roster_quality"] if team in df_val.index else 0

            # Needs Calculation
            needs = {}
            team_pos_df = df_pos[df_pos["team"] == team]
            for _, row in team_pos_df.iterrows():
                pos = row["position"]
                my_val = row["pos_quality"]
                avg_val = league_avgs.get(pos, 1.0)

                # If below average, Need > 0.5. If above, Need < 0.5.
                # Normalized: 1 - (My / Avg*1.5) ... bounded 0-1
                # Simple logic: Ratio
                ratio = my_val / (avg_val + 1e-6)
                severity = max(0.0, 1.0 - ratio)  # If I have 0.5 of Avg, Severity = 0.5
                if severity > 0.2:  # Only register significant needs
                    needs[pos] = severity

            teams[team] = TeamState(
                name=team, cap_space=space, needs=needs, roster_value=val
            )

        state = LeagueState(teams)

        # 4. Hydrate Market Players (The "Trade Block")
        player_query = f"""
            WITH caps AS (
                SELECT 
                    player_name, 
                    team, 
                    position, 
                    SUM(cap_hit_millions) as cap_hit_millions
                FROM silver_spotrac_contracts
                WHERE year = {self.year}
                GROUP BY player_name, team, position
            ),

            risk AS (
                SELECT player_name, MAX(predicted_risk_score) as predicted_risk_score
                FROM prediction_results
                WHERE year = {self.year}
                GROUP BY player_name
            ),
            expl AS (
                -- Left join to explanations (might not exist yet if model training is pending)
                SELECT player_name, top_factors
                FROM prediction_explanations
                WHERE year = {self.year}
            )
            SELECT 
                c.player_name as name,
                c.team,
                c.position,
                c.cap_hit_millions as cap_hit,
                (1 - r.predicted_risk_score) * 10 as value, -- 0-10 Scale
                e.top_factors
            FROM caps c
            JOIN risk r ON c.player_name = r.player_name
            LEFT JOIN expl e ON c.player_name = e.player_name
            WHERE c.cap_hit_millions >= {self.min_cap_hit}
        """

        # Handle case where table doesn't exist yet (during CI or early init)
        try:
            df_players = self.con.execute(player_query).df()
        except NotFound:
            # Fallback if explanation table missing
            print("⚠️ 'prediction_explanations' table missing. Skipping risk factors.")
            fallback_query = (
                player_query.replace(
                    "LEFT JOIN expl e ON c.player_name = e.player_name", ""
                )
                .replace(",\n                e.top_factors", "")
                .replace(
                    "expl AS (\n                -- Left join to explanations (might not exist yet if model training is pending)\n                SELECT player_name, top_factors\n                FROM prediction_explanations\n                WHERE year = {self.year}\n            )",
                    "",
                )
            )
            # This replacement is messy, simpler to just re-define or use a flag.
            # Actually, let's just use the original query and catch error.
            # Re-defining for clarity in fallback:
            qm = f"""
            WITH caps AS (
                SELECT 
                    player_name, team, position, SUM(cap_hit_millions) as cap_hit_millions
                FROM silver_spotrac_contracts
                WHERE year = {self.year}
                GROUP BY player_name, team, position
            ),
            risk AS (
                SELECT player_name, MAX(predicted_risk_score) as predicted_risk_score
                FROM prediction_results
                WHERE year = {self.year}
                GROUP BY player_name
            )
            SELECT 
                c.player_name as name, c.team, c.position, c.cap_hit_millions as cap_hit,
                (1 - r.predicted_risk_score) * 10 as value
            FROM caps c
            JOIN risk r ON c.player_name = r.player_name
            WHERE c.cap_hit_millions >= {self.min_cap_hit}
            """
            df_players = self.con.execute(qm).df()
            df_players["top_factors"] = None

        # Convert to dictionary list
        market = []
        for idx, row in df_players.iterrows():
            market.append(
                {
                    "id": f"p_{idx}",
                    "name": row["name"],
                    "team": row["team"],
                    "position": row["position"],
                    "value": row["value"],
                    "cap_hit": row["cap_hit"],
                    "risk_factors": (
                        row["top_factors"]
                        if "top_factors" in row and pd.notna(row["top_factors"])
                        else None
                    ),
                }
            )

        state.market_players = market
        print(f"✅ Loaded {len(teams)} Teams and {len(market)} Tradeable Assets.")

        return state

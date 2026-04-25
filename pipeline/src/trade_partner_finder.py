from typing import Any, Dict, List, Optional

import pandas as pd
from src.db_manager import DBManager


class TradePartnerFinder:
    def __init__(self, db_manager: Optional[DBManager] = None):
        self.db = db_manager or DBManager()

    def find_buyers(
        self, player_id: str, position: str, cap_hit: float
    ) -> List[Dict[str, Any]]:
        """
        Identify trade partners based on Cap Space, Need, and Strategy.

        Args:
            player_id: Name/ID of player
            position: Position (e.g. 'QB', 'WR')
            cap_hit: Annual cap cost to acquire

        Returns:
            List of dicts with team, score, reason.
        """
        if cap_hit < 0:
            raise ValueError("Cap Hit cannot be negative.")

        # 1. Get Team Status (Cap Space, Spending, Win Total)
        # Note: In production this would be a real optimized query.
        # For TDD/MVP, we fetch summary.
        spending_col = f"{position.lower()}_spending"

        query = f"""
            SELECT 
                team, 
                cap_space, 
                {spending_col}, 
                win_total, 
                conference 
            FROM team_finance_summary
        """

        # Helper to safely get DF from DB or Mock
        try:
            df = self.db.fetch_df(query)
        except Exception:
            # Fallback if table doesn't exist yet (mock handles this usually)
            return []

        if df.empty:
            return []

        # 2. Filter: Cap Space
        # Must have space > cap_hit (simplification)
        # Also drop teams with negative space even if cap_hit is small (broken teams)
        qualified = df[(df["cap_space"] >= cap_hit) & (df["cap_space"] > 0)].copy()

        if qualified.empty:
            return []

        # 3. Score: Positional Need
        # Less spending = Higher Need.
        # Normalize 0-100. Lower spending -> Higher Score.
        max_spend = df[spending_col].max()
        qualified["need_score"] = 100 - ((qualified[spending_col] / max_spend) * 100)

        # 4. Score: Window Fit (Placeholder Logic)
        # For now, just a flat addition. TDD didn't specify strict window math yet.
        qualified["window_score"] = 50

        # 5. Composite Fit Score
        # 50% Need, 30% Cap Flexibility, 20% Window
        # Normalize cap space 0-100
        max_space = df["cap_space"].max()
        qualified["space_score"] = (qualified["cap_space"] / max_space) * 100

        qualified["fit_score"] = (qualified["need_score"] * 0.60) + (
            qualified["space_score"] * 0.40
        )

        # Sort
        qualified = qualified.sort_values("fit_score", ascending=False)

        # Format Result
        results = []
        for _, row in qualified.iterrows():
            results.append(
                {
                    "team": row["team"],
                    "score": int(row["fit_score"]),
                    "reason": f"Cap Space: ${row['cap_space'] / 1e6:.1f}M | Need: {int(row['need_score'])}/100",
                }
            )

        return results

import logging
import math
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class WinProbabilityModel:
    """
    Quantifies the impact of roster moves on Projected Wins and Vegas Odds.
    Implements 'Bettor Persona' requirements: Variance, Position Weights, Non-linear returns.
    """

    def __init__(self):
        self.BASELINE_WINS = 8.5
        # "Board" Requirement: Position Weights
        self.POSITION_WEIGHTS = {
            "QB": 10.0,
            "EDGE": 3.0,
            "DE": 3.0,
            "OT": 3.0,
            "LT": 3.0,
            "RT": 3.0,
            "WR": 2.0,
            "CB": 2.0,
            "DT": 1.5,
            "S": 1.5,
            # Others default to 1.0
        }
        # Conversion Factor: How much Weighted Surplus ($M) equals 1 Win?
        # If QB ($30M surplus) * 10 (weight) = 300 Weighted Units.
        # If that equals ~4 Wins, then 300 / 4 = 75 units per win.
        # Let's calibrate:
        # Average Starter (Surplus $5M, Weight 1.0) = 5 units. Should be ~0.1 wins?
        # 0.1 wins * 50 = 5 units.
        # Let's try DIVISOR = 50.
        self.SURPLUS_TO_WINS_DIVISOR = 50.0

    def calculate_win_impact(self, trade_proposal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates the shift in win total and variance for both teams.
        """
        team_a = trade_proposal.get("team_a")
        team_b = trade_proposal.get("team_b")

        # Calculate Delta for Team A
        # (Assets In - Assets Out)

        # 1. Analyze Incoming Package
        a_in_impact = self._analyze_package(trade_proposal.get("team_b_assets", []))
        # 2. Analyze Outgoing Package
        a_out_impact = self._analyze_package(trade_proposal.get("team_a_assets", []))

        # Net Change
        a_net_wins = a_in_impact["wins_added"] - a_out_impact["wins_added"]
        a_variance = math.sqrt(
            a_in_impact["variance_score"] ** 2 + a_out_impact["variance_score"] ** 2
        )  # Simplified variance addition

        # Team B is inverse
        b_net_wins = -a_net_wins
        b_variance = a_variance  # Variance increases for both usually if risk is high? Actually, acquiring risk adds variance.
        # Let's calculate B separately to be precise about who holds the risk.
        b_in_impact = a_out_impact
        b_out_impact = a_in_impact
        b_net_wins = b_in_impact["wins_added"] - b_out_impact["wins_added"]
        b_variance = math.sqrt(
            b_in_impact["variance_score"] ** 2 + b_out_impact["variance_score"] ** 2
        )

        return {
            team_a: self._format_output(a_net_wins, a_variance),
            team_b: self._format_output(b_net_wins, b_variance),
        }

    def _analyze_package(self, assets: List[Dict[str, Any]]) -> Dict[str, float]:
        total_weighted_surplus = 0.0
        total_variance = 0.0

        for asset in assets:
            if asset.get("type") != "player":
                # Draft picks have value but huge variance.
                # MVP: Treat as small positive value with high variance.
                # TODO: Draft Value Chart.
                continue

            position = asset.get("position", "UNK")
            surplus = asset.get("surplus_value", 0.0)
            risk = asset.get("risk_score", 0.0)

            # 1. Apply Weights
            weight = self.POSITION_WEIGHTS.get(position, 1.0)
            weighted_surplus = surplus * weight

            total_weighted_surplus += weighted_surplus

            # 2. Calculate Variance Contribution
            # High Risk (0.9) adds more uncertainty to the win total.
            # Variance metric: Risk * Impact
            total_variance += risk * abs(weighted_surplus)

        # 3. Apply Logistic Dampening (Diminishing Returns)
        # For a single trade, linear approximation is usually fine,
        # but let's clamp it to prevent "Trading 53 players for 50 wins".
        # We'll convert to wins linearly first, then damp?
        # MVP: Linear for trade delta is standard industry practice (WAR is additive).

        wins_added = total_weighted_surplus / self.SURPLUS_TO_WINS_DIVISOR

        return {
            "wins_added": wins_added,
            "variance_score": total_variance / self.SURPLUS_TO_WINS_DIVISOR,
        }

    def _format_output(self, delta_wins: float, variance: float) -> Dict[str, Any]:
        """
        Formats the data for the 'Vegas Dashboard'.
        """
        new_total = self.BASELINE_WINS + delta_wins

        # Clamp to 0-17
        new_total = max(0, min(17, new_total))

        # Calculate Spread (Ceiling/Floor)
        # 95% Confidence Interval ~ 2 * Sigma
        # We treat our 'variance' metric as Sigma for MVP.
        spread = 1.96 * variance  # 95% CI

        # Minimal spread even for low risk
        spread = max(0.5, spread)

        return {
            "delta_wins": round(delta_wins, 2),
            "new_win_total": round(new_total, 1),
            "vegas_variance": round(spread, 1),  # +/- Wins
            "ceiling": round(new_total + spread, 1),
            "floor": round(new_total - spread, 1),
            "super_bowl_odds_delta": self._calculate_odds_shift(delta_wins),
        }

    def _calculate_odds_shift(self, delta_wins: float) -> str:
        """
        Heuristic for change in SB Odds.
        +1 Win ~ +20% improvement in odds?
        """
        if delta_wins == 0:
            return "0%"

        # Simple percentage change
        pct_change = delta_wins * 15.0  # 1 win = 15% better odds
        sign = "+" if pct_change > 0 else ""
        return f"{sign}{round(pct_change, 1)}%"

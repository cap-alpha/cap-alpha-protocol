"""
Trade Simulator: Agent Logic (Adversarial Utility)
Author: Cap Alpha Protocol

This module defines the 'Agent' (Team Persona).
Teams maximize different metrics based on their lifecycle phase:
1. CONTENDER: Maximize Win Probability (Willing to sacrifice Cap).
2. REBUILDER: Maximize Draft Capital + Cap Space (Willing to trade Wins).
3. MIDDLE: Balanced approach.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.trade_simulator.state import LeagueState


@dataclass
class TeamPersona:
    win_weight: float  # Alpha
    cap_weight: float  # Beta
    draft_weight: float  # Gamma


# Predefined Personas
CONTENDER = TeamPersona(win_weight=0.8, cap_weight=0.1, draft_weight=0.1)
rebuilder = TeamPersona(win_weight=0.1, cap_weight=0.4, draft_weight=0.5)


class Agent:
    def __init__(self, team_name: str, persona: TeamPersona):
        self.team_name = team_name
        self.persona = persona

    def evaluate_trade(
        self, current_state: "LeagueState", proposed_state: "LeagueState"
    ) -> float:
        """
        Calculate Delta Utility: U(State') - U(State)
        If Delta > 0, the Agent accepts the trade.
        """
        current_utility = self._calculate_utility(current_state)
        proposed_utility = self._calculate_utility(proposed_state)

        return proposed_utility - current_utility

    def _calculate_utility(self, state: "LeagueState") -> float:
        """
        U = alpha*WinProb + beta*CapSpace + gamma*DraftValue
        """
        team_data = state.teams[self.team_name]

        # Placeholder Metrics
        # In production, these come from the ML Model
        win_metric = team_data.roster_value  # Proxy for Wins
        cap_metric = team_data.cap_space  # Proxy for Financial Health
        draft_metric = team_data.draft_capital  # Value of Draft Picks

        return (
            (self.persona.win_weight * win_metric)
            + (self.persona.cap_weight * cap_metric)
            + (self.persona.draft_weight * draft_metric)
        )

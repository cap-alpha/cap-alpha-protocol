"""
Player compensation data model and normalization utilities.

Three-table schema:
  - players: dimension table with player info
  - player_contracts: fact table with annual contract breakdowns
  - player_cap_impact: mart table with computed cap metrics
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Player:
    """Player dimension record."""

    player_id: str
    player_name: str
    position: str
    nfl_years: int = 0
    college: str = ""
    draft_year: Optional[int] = None


@dataclass
class PlayerContract:
    """Individual contract component (salary, bonus, dead money, etc)."""

    contract_id: str
    player_id: str
    team: str
    year: int
    salary_type: str  # 'base_salary', 'signing_bonus', 'dead_cap', 'roster_bonus', etc
    amount_millions: float
    designation: Optional[str] = None  # 'pre_june1', 'post_june1', 'void_year', 'trade'
    status: str = "active"  # 'active', 'voided', 'cut', 'released'


@dataclass
class PlayerCapImpact:
    """Computed cap impact for player/year."""

    impact_id: str
    player_id: str
    team: str
    year: int
    cap_hit_millions: float
    dead_money_millions: float
    salary_millions: float
    signing_bonus_millions: float
    roster_bonus_millions: float
    other_millions: float = 0.0
    efficiency_score: Optional[float] = None  # cap_hit / games_played or wins_produced


class CompensationDataModel:
    """Manages player compensation data in normalized schema."""

    def __init__(self):
        self.players_df = pd.DataFrame(
            columns=[
                "player_id",
                "player_name",
                "position",
                "nfl_years",
                "college",
                "draft_year",
            ]
        )
        self.contracts_df = pd.DataFrame(
            columns=[
                "contract_id",
                "player_id",
                "team",
                "year",
                "salary_type",
                "amount_millions",
                "designation",
                "status",
            ]
        )
        self.cap_impact_df = pd.DataFrame(
            columns=[
                "impact_id",
                "player_id",
                "team",
                "year",
                "cap_hit_millions",
                "dead_money_millions",
                "salary_millions",
                "signing_bonus_millions",
                "roster_bonus_millions",
                "other_millions",
                "efficiency_score",
            ]
        )

    def add_player(self, player: Player) -> None:
        """Add or update player record."""
        new_row = pd.DataFrame(
            [
                {
                    "player_id": player.player_id,
                    "player_name": player.player_name,
                    "position": player.position,
                    "nfl_years": player.nfl_years,
                    "college": player.college,
                    "draft_year": player.draft_year,
                }
            ]
        )
        self.players_df = pd.concat(
            [self.players_df, new_row], ignore_index=True
        ).drop_duplicates(subset=["player_id"], keep="last")

    def add_contract(self, contract: PlayerContract) -> None:
        """Add contract component."""
        new_row = pd.DataFrame(
            [
                {
                    "contract_id": contract.contract_id,
                    "player_id": contract.player_id,
                    "team": contract.team,
                    "year": contract.year,
                    "salary_type": contract.salary_type,
                    "amount_millions": contract.amount_millions,
                    "designation": contract.designation,
                    "status": contract.status,
                }
            ]
        )
        self.contracts_df = pd.concat([self.contracts_df, new_row], ignore_index=True)

    def add_cap_impact(self, impact: PlayerCapImpact) -> None:
        """Add computed cap impact."""
        new_row = pd.DataFrame(
            [
                {
                    "impact_id": impact.impact_id,
                    "player_id": impact.player_id,
                    "team": impact.team,
                    "year": impact.year,
                    "cap_hit_millions": impact.cap_hit_millions,
                    "dead_money_millions": impact.dead_money_millions,
                    "salary_millions": impact.salary_millions,
                    "signing_bonus_millions": impact.signing_bonus_millions,
                    "roster_bonus_millions": impact.roster_bonus_millions,
                    "other_millions": impact.other_millions,
                    "efficiency_score": impact.efficiency_score,
                }
            ]
        )
        self.cap_impact_df = pd.concat(
            [self.cap_impact_df, new_row], ignore_index=True
        ).drop_duplicates(subset=["impact_id"], keep="last")

    def compute_cap_impact_from_contracts(
        self, player_id: str, team: str, year: int
    ) -> PlayerCapImpact:
        """Aggregate contracts into a cap impact record."""
        player_contracts = self.contracts_df[
            (self.contracts_df["player_id"] == player_id)
            & (self.contracts_df["team"] == team)
            & (self.contracts_df["year"] == year)
        ]

        cap_hit = player_contracts["amount_millions"].sum()
        dead_money = player_contracts[player_contracts["salary_type"] == "dead_cap"][
            "amount_millions"
        ].sum()
        salary = player_contracts[player_contracts["salary_type"] == "base_salary"][
            "amount_millions"
        ].sum()
        signing_bonus = player_contracts[
            player_contracts["salary_type"] == "signing_bonus"
        ]["amount_millions"].sum()
        roster_bonus = player_contracts[
            player_contracts["salary_type"] == "roster_bonus"
        ]["amount_millions"].sum()
        other = cap_hit - (salary + signing_bonus + roster_bonus + dead_money)

        impact_id = f"{player_id}_{team}_{year}"
        impact = PlayerCapImpact(
            impact_id=impact_id,
            player_id=player_id,
            team=team,
            year=year,
            cap_hit_millions=cap_hit,
            dead_money_millions=dead_money,
            salary_millions=salary,
            signing_bonus_millions=signing_bonus,
            roster_bonus_millions=roster_bonus,
            other_millions=other,
        )
        return impact

    def export_players(self, path: str) -> None:
        """Save players dimension to CSV."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.players_df.to_csv(path, index=False)

    def export_contracts(self, path: str) -> None:
        """Save contracts fact table to CSV."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.contracts_df.to_csv(path, index=False)

    def export_cap_impact(self, path: str) -> None:
        """Save cap impact mart to CSV."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.cap_impact_df.to_csv(path, index=False)

    def export_all(self, base_dir: str = "data/processed/compensation") -> None:
        """Export all tables."""
        self.export_players(f"{base_dir}/dim_players.csv")
        self.export_contracts(f"{base_dir}/fact_player_contracts.csv")
        self.export_cap_impact(f"{base_dir}/mart_player_cap_impact.csv")

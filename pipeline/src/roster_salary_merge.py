"""
Merge PFR rosters with Spotrac player salaries.

Combines roster metadata (position, age, college) with salary data
to create complete player profiles for analysis.
"""

import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEAM_MAPPING = {
    "ARI": "ARI",
    "ATL": "ATL",
    "BAL": "BAL",
    "BUF": "BUF",
    "CAR": "CAR",
    "CHI": "CHI",
    "CIN": "CIN",
    "CLE": "CLE",
    "DAL": "DAL",
    "DEN": "DEN",
    "DET": "DET",
    "GNB": "GB",
    "HOU": "HOU",
    "IND": "IND",
    "JAX": "JAX",
    "KAN": "KC",
    "LAC": "LAC",
    "LAR": "LAR",
    "LVR": "LV",
    "MIA": "MIA",
    "MIN": "MIN",
    "NWE": "NE",
    "NOR": "NO",
    "NYG": "NYG",
    "NYJ": "NYJ",
    "PHI": "PHI",
    "PIT": "PIT",
    "SFO": "SF",
    "SEA": "SEA",
    "TAM": "TB",
    "TEN": "TEN",
    "WAS": "WAS",
}


def fuzzy_match_player(
    name: str,
    team: str,
    year: int,
    candidates_df: pd.DataFrame,
    threshold: float = 0.75,
) -> Optional[pd.Series]:
    """
    Fuzzy match a player by name, team, and year.

    Args:
        name: Player name to match
        team: Team code
        year: Season year
        candidates_df: DataFrame of potential matches with 'player_name', 'team', 'year'
        threshold: Minimum similarity ratio (0-1)

    Returns:
        Best matching row or None
    """
    # Map team code if needed (PFR -> Spotrac)
    spotrac_team = TEAM_MAPPING.get(team.upper(), team.upper())

    # Filter candidates by team and year
    candidates = candidates_df[
        (candidates_df["team"].str.upper() == spotrac_team)
        & (candidates_df["year"] == year)
    ].copy()

    if candidates.empty:
        return None

    # Calculate similarity scores
    def similarity(target: str, candidate: str) -> float:
        return SequenceMatcher(None, target.lower(), candidate.lower()).ratio()

    candidates["similarity"] = candidates["player_name"].apply(
        lambda x: similarity(name, x)
    )

    best_match = candidates.loc[candidates["similarity"].idxmax()]

    if best_match["similarity"] >= threshold:
        return best_match

    return None


def merge_rosters_and_salaries(
    rosters_path: str,
    salaries_path: str,
    output_path: str,
    match_threshold: float = 0.75,
) -> pd.DataFrame:
    """
    Merge PFR rosters with Spotrac player salaries.

    Args:
        rosters_path: Path to raw_rosters CSV
        salaries_path: Path to spotrac_player_salaries CSV
        output_path: Where to save merged data
        match_threshold: Fuzzy match threshold (0-1)

    Returns:
        Merged DataFrame
    """
    logger.info("Loading rosters...")
    rosters = pd.read_csv(rosters_path)

    logger.info("Loading salaries...")
    salaries = pd.read_csv(salaries_path)

    # Standardize column names
    if "Player" in rosters.columns:
        rosters.rename(columns={"Player": "player_name"}, inplace=True)
    if "Tm" in rosters.columns:
        rosters.rename(columns={"Tm": "team"}, inplace=True)

    logger.info(f"Rosters: {len(rosters):,} records")
    logger.info(f"Salaries: {len(salaries):,} records")

    # Initialize salary columns in rosters
    rosters["salary_millions"] = None
    rosters["cap_hit_millions"] = None
    rosters["dead_cap_millions"] = None
    rosters["total_contract_value_millions"] = None
    rosters["guaranteed_money_millions"] = None
    rosters["signing_bonus_millions"] = None
    rosters["contract_length_years"] = None
    rosters["years_remaining"] = None
    rosters["salary_match_score"] = None

    # Track matches
    matched = 0
    unmatched = 0

    # Try to match each roster player to salary data
    for idx, roster_row in rosters.iterrows():
        player_name = roster_row.get("player_name", "")
        team = roster_row.get("team", "")
        year = roster_row.get("year", 0)

        if not player_name or not team or not year:
            continue

        # Try fuzzy match
        match = fuzzy_match_player(
            name=player_name,
            team=team,
            year=year,
            candidates_df=salaries,
            threshold=match_threshold,
        )

        if match is not None:
            rosters.at[idx, "salary_millions"] = match.get("salary_millions", None)
            rosters.at[idx, "cap_hit_millions"] = match.get("cap_hit_millions", None)
            rosters.at[idx, "dead_cap_millions"] = match.get("dead_cap_millions", None)
            rosters.at[idx, "total_contract_value_millions"] = match.get(
                "total_contract_value_millions", None
            )
            rosters.at[idx, "guaranteed_money_millions"] = match.get(
                "guaranteed_money_millions", None
            )
            rosters.at[idx, "signing_bonus_millions"] = match.get(
                "signing_bonus_millions", None
            )
            rosters.at[idx, "contract_length_years"] = match.get(
                "contract_length_years", None
            )
            rosters.at[idx, "years_remaining"] = match.get("years_remaining", None)
            rosters.at[idx, "salary_match_score"] = match.get("similarity", None)
            matched += 1
        else:
            unmatched += 1

    match_rate = (matched / len(rosters) * 100) if len(rosters) > 0 else 0

    logger.info(f"✓ Matched: {matched:,} ({match_rate:.1f}%)")
    logger.info(f"✗ Unmatched: {unmatched:,}")

    # Save merged data
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rosters.to_csv(output_path, index=False)

    logger.info(f"✓ Saved merged data to {output_path}")

    # Print summary
    with_salary = rosters[rosters["total_contract_value_millions"].notna()]
    logger.info(f"\nContract Data Summary:")
    logger.info(f"  Records with contract data: {len(with_salary)}")
    if len(with_salary) > 0:
        avg_val = with_salary["total_contract_value_millions"].mean()
        total_val = with_salary["total_contract_value_millions"].sum()
        logger.info(f"  Avg total value: ${avg_val:.1f}M")
        logger.info(f"  Total contract value: ${total_val:.1f}M")

    return rosters


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print(
            "Usage: python src/roster_salary_merge.py <rosters_csv> <salaries_csv> <output_csv>"
        )
        sys.exit(1)

    rosters_path = sys.argv[1]
    salaries_path = sys.argv[2]
    output_path = sys.argv[3]

    merge_rosters_and_salaries(rosters_path, salaries_path, output_path)

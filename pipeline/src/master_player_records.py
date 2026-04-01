#!/usr/bin/env python3
"""
Master Player Records: Source of Truth for ALL NFL Players

Strategy:
1. PFR rosters are the canonical list (~1,700 active players per year)
2. Lookup contract data (Spotrac, Over The Cap) for each player
3. Join rosters + contracts into single master record
4. No "synthetic" players - every record is a real person

This ensures:
- Complete coverage of all ~1,700 NFL players per year
- Standardized names from official roster
- Easy to identify which players have contracts vs missing data
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fuzzywuzzy import fuzz, process

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed" / "compensation"


def load_pfr_rosters(year: int = 2024) -> pd.DataFrame:
    """Load PFR roster for given year"""
    roster_file = RAW_DIR / "pfr" / f"rosters_{year}.csv"

    if not roster_file.exists():
        logger.warning(f"Roster file not found: {roster_file}")
        return pd.DataFrame()

    df = pd.read_csv(roster_file)
    logger.info(
        f"✓ Loaded PFR roster {year}: {len(df)} players from {df['team'].nunique()} teams"
    )

    return df


def load_contract_data(year: int = 2024) -> pd.DataFrame:
    """Load contract data - prioritize historical dead money (complete) over curated"""

    # Try comprehensive dead money dataset first (has ALL players historically)
    dead_money_file = PROCESSED_DIR / "player_dead_money.csv"
    if dead_money_file.exists():
        df = pd.read_csv(dead_money_file)
        df = df[df["year"] == year]
        if len(df) > 0:
            logger.info(f"✓ Loaded dead money data {year}: {len(df)} players")
            return df

    # Fall back to curated contract files (partial data, high-salary players)
    contract_files = list(RAW_DIR.glob(f"spotrac_player_contracts_{year}_curated*.csv"))

    if not contract_files:
        logger.warning(f"No contract files found for {year}")
        return pd.DataFrame()

    # Use most recent file
    contract_file = sorted(contract_files)[-1]
    df = pd.read_csv(contract_file)
    logger.info(
        f"✓ Loaded curated contract data {year}: {len(df)} contracts from {contract_file.name}"
    )

    return df


def normalize_player_name(name: str) -> str:
    """Normalize player name for matching"""
    if pd.isna(name):
        return ""

    # Remove extra whitespace
    name = str(name).strip()

    # Handle common abbreviations/variations
    replacements = {
        "Jr.": "Jr",
        "Sr.": "Sr",
        "II": "II",
        "III": "III",
        "IV": "IV",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    return name.lower()


def fuzzy_match_player(
    roster_name: str, contract_name: str, threshold: int = 85
) -> bool:
    """Check if two player names match using fuzzy matching"""
    roster_normalized = normalize_player_name(roster_name)
    contract_normalized = normalize_player_name(contract_name)

    # Exact match
    if roster_normalized == contract_normalized:
        return True

    # Fuzzy match
    ratio = fuzz.ratio(roster_normalized, contract_normalized)
    return ratio >= threshold


def match_contracts_to_roster(
    roster_df: pd.DataFrame, contract_df: pd.DataFrame, year: int = 2024
) -> pd.DataFrame:
    """
    Match contract data to roster using:
    1. Exact (player_name, team) match
    2. Fuzzy match on name if team matches
    3. Manual fallback list

    Returns: Roster with contract data joined, flagging unmatched players
    """

    # Standardize column names
    roster_df = roster_df.copy()
    contract_df = contract_df.copy()

    # Normalize names for matching
    roster_df["_name_normalized"] = roster_df["Player"].apply(normalize_player_name)
    contract_df["_name_normalized"] = contract_df["player_name"].apply(
        normalize_player_name
    )

    # Select available columns from contract data
    contract_cols = ["_name_normalized", "player_name", "team", "position"]
    for col in [
        "total_contract_value_millions",
        "guaranteed_money_millions",
        "signing_bonus_millions",
        "contract_length_years",
        "years_remaining",
        "cap_hit_millions",
        "dead_cap_millions",
        "dead_cap_hit",
    ]:
        if col in contract_df.columns:
            contract_cols.append(col)

    contract_cols = [c for c in contract_cols if c in contract_df.columns]

    # Try exact match first: (name, team)
    matched = roster_df.merge(
        contract_df[contract_cols],
        left_on=["_name_normalized", "team"],
        right_on=["_name_normalized", "team"],
        how="left",
        indicator=True,
        suffixes=("", "_contract"),
    )

    matched.drop("_name_normalized", axis=1, inplace=True)

    # Track matches
    exact_matches = (matched["_merge"] == "both").sum()
    logger.info(f"  Exact matches (name + team): {exact_matches}/{len(roster_df)}")

    # For unmatched, try fuzzy match by team
    unmatched_mask = matched["_merge"] == "left_only"
    unmatched_indices = matched[unmatched_mask].index

    fuzzy_matches = 0
    for idx in unmatched_indices:
        roster_player = matched.loc[idx, "Player"]
        roster_team = matched.loc[idx, "team"]

        # Find contracts for same team
        team_contracts = contract_df[contract_df["team"] == roster_team]

        if len(team_contracts) == 0:
            continue

        # Find closest match by name
        best_match = None
        best_score = 0

        for _, contract_row in team_contracts.iterrows():
            score = fuzz.ratio(
                normalize_player_name(roster_player),
                normalize_player_name(contract_row["player_name"]),
            )

            if score > best_score and score >= 85:  # 85% threshold
                best_score = score
                best_match = contract_row

        if best_match is not None:
            # Update matched row with contract data
            matched.loc[idx, "player_name"] = best_match["player_name"]
            matched.loc[idx, "position"] = best_match["position"]
            matched.loc[idx, "total_contract_value_millions"] = best_match[
                "total_contract_value_millions"
            ]
            matched.loc[idx, "guaranteed_money_millions"] = best_match[
                "guaranteed_money_millions"
            ]
            matched.loc[idx, "signing_bonus_millions"] = best_match[
                "signing_bonus_millions"
            ]
            matched.loc[idx, "contract_length_years"] = best_match[
                "contract_length_years"
            ]
            matched.loc[idx, "years_remaining"] = best_match["years_remaining"]
            matched.loc[idx, "cap_hit_millions"] = best_match["cap_hit_millions"]
            matched.loc[idx, "_merge"] = "both"
            fuzzy_matches += 1

    logger.info(
        f"  Fuzzy matches (85%+ name similarity): {fuzzy_matches}/{unmatched_mask.sum()}"
    )

    # Mark contract status
    matched["has_contract"] = matched["_merge"] == "both"
    matched["contract_match_type"] = matched["_merge"].map(
        {"both": "matched", "left_only": "unmatched"}
    )

    # Clean up
    matched.drop("_merge", axis=1, inplace=True)

    return matched


def build_master_player_records(year: int = 2024) -> pd.DataFrame:
    """
    Build master player records combining:
    - All players from PFR rosters (source of truth)
    - Contract data where available
    - Enrichment flags
    """

    logger.info(f"\n{'='*70}")
    logger.info(f"MASTER PLAYER RECORDS FOR {year}")
    logger.info(f"{'='*70}\n")

    # Load data
    roster_df = load_pfr_rosters(year)
    contract_df = load_contract_data(year)

    if roster_df.empty:
        logger.error(f"No roster data for {year}")
        return pd.DataFrame()

    logger.info(f"\n1. Matching contracts to rosters...")
    master = match_contracts_to_roster(roster_df, contract_df, year)

    # Summary statistics
    logger.info(f"\n2. Master Player Records Summary:")
    logger.info(f"  Total players in roster: {len(master)}")
    logger.info(f"  Players with contract data: {master['has_contract'].sum()}")
    logger.info(f"  Players without contract: {(~master['has_contract']).sum()}")
    logger.info(
        f"  Contract coverage: {master['has_contract'].sum()/len(master)*100:.1f}%"
    )

    # By team
    logger.info(f"\n3. Teams Represented:")
    team_summary = (
        master.groupby("team")
        .agg({"Player": "count", "has_contract": "sum"})
        .rename(columns={"Player": "roster_size", "has_contract": "with_contracts"})
    )

    team_summary["coverage_pct"] = (
        team_summary["with_contracts"] / team_summary["roster_size"] * 100
    ).round(1)
    team_summary = team_summary.sort_values("coverage_pct", ascending=False)

    logger.info(
        f"  Teams with 100% contract coverage: {(team_summary['coverage_pct'] == 100).sum()}/32"
    )
    logger.info(
        f"  Average coverage per team: {team_summary['coverage_pct'].mean():.1f}%"
    )

    # Show lowest coverage teams
    logger.info(f"\n  Teams with lowest contract coverage:")
    for team, row in team_summary.tail(5).iterrows():
        logger.info(
            f"    {team}: {row['coverage_pct']:.0f}% ({row['with_contracts']:.0f}/{row['roster_size']:.0f})"
        )

    # By position
    logger.info(f"\n4. Coverage by Position:")
    pos_summary = (
        master.groupby("Pos")
        .agg({"Player": "count", "has_contract": "sum"})
        .rename(columns={"Player": "roster_count", "has_contract": "with_contracts"})
    )

    pos_summary["coverage_pct"] = (
        pos_summary["with_contracts"] / pos_summary["roster_count"] * 100
    ).round(1)
    pos_summary = pos_summary.sort_values("coverage_pct", ascending=False)

    for pos, row in pos_summary.iterrows():
        logger.info(
            f"  {pos:4s}: {row['coverage_pct']:5.1f}% ({row['with_contracts']:.0f}/{row['roster_count']:.0f})"
        )

    # Add year column if not present
    if "year" not in master.columns:
        master["year"] = year

    # Standardize column order
    output_cols = [
        "Player",
        "team",
        "Pos",
        "Age",
        "G",
        "GS",
        "Yrs",
        "AV",
        "player_name",
        "position",
        "total_contract_value_millions",
        "guaranteed_money_millions",
        "signing_bonus_millions",
        "contract_length_years",
        "years_remaining",
        "cap_hit_millions",
        "has_contract",
        "contract_match_type",
        "year",
    ]

    # Only include columns that exist
    output_cols = [c for c in output_cols if c in master.columns]
    master = master[output_cols]

    return master


def save_master_records(master_df: pd.DataFrame, year: int = 2024) -> Path:
    """Save master player records to CSV"""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    week = datetime.now().strftime("%Y-W%U")

    output_file = PROCESSED_DIR / f"master_player_records_{year}_{week}_{timestamp}.csv"

    master_df.to_csv(output_file, index=False)
    logger.info(f"\n✅ Master player records saved: {output_file.name}")
    logger.info(f"   Rows: {len(master_df)}")
    logger.info(f"   Columns: {len(master_df.columns)}")

    return output_file


def main():
    """Build and save master player records for 2024"""
    import sys

    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2024

    master = build_master_player_records(year)

    if not master.empty:
        save_master_records(master, year)
    else:
        logger.error(f"Failed to build master records for {year}")
        sys.exit(1)


if __name__ == "__main__":
    main()

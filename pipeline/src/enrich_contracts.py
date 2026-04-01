import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def clean_doubled_name(name: str) -> str:
    """Fix instances where the scraper pulls 'Tom BradyTom Brady' instead of 'Tom Brady'"""
    if not isinstance(name, str) or not name:
        return ""
    parts = name.strip().split()
    if len(parts) >= 3 and parts[0] == parts[-1]:
        return " ".join(parts[1:])
    mid_idx = len(name) // 2
    if len(name) % 2 == 0:
        if name[:mid_idx] == name[mid_idx:]:
            return name[:mid_idx]
    if len(parts) >= 2:
        mid_words = len(parts) // 2
        if len(parts) % 2 == 0:
            if parts[:mid_words] == parts[mid_words:]:
                return " ".join(parts[:mid_words])
    return name


def enrich_overthecap_contracts(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """
    Transforms Bronze OverTheCap contract payloads into the Silver Contract standard.
    """
    if df is None or df.empty:
        logger.warning("Empty dataframe provided to enrich_overthecap_contracts.")
        return df

    # 1. Clean identity
    if "player_name" in df.columns:
        df["player_name"] = df["player_name"].apply(clean_doubled_name)

    # 2. Extract core columns mapped to the Standard Schema
    if "year_cap_hit_millions" in df.columns:
        df["cap_hit_millions"] = df["year_cap_hit_millions"].fillna(0.0)
    else:
        df["cap_hit_millions"] = 0.0

    if "guaranteed_money_millions" in df.columns:
        df["dead_cap_millions"] = df["guaranteed_money_millions"].fillna(0.0)
    else:
        df["dead_cap_millions"] = 0.0

    if "signing_bonus_millions" in df.columns:
        df["signing_bonus_millions"] = df["signing_bonus_millions"].fillna(0.0)
    else:
        df["signing_bonus_millions"] = 0.0

    if "total_value_millions" in df.columns:
        df["total_contract_value_millions"] = df["total_value_millions"].fillna(0.0)
    else:
        df["total_contract_value_millions"] = 0.0

    # 3. Fill missing fields not supplied by OTC but required by downstream Gold facts
    required_cols = [
        "age",
        "base_salary_millions",
        "prorated_bonus_millions",
        "roster_bonus_millions",
        "guaranteed_salary_millions",
    ]
    for col in required_cols:
        if col not in df.columns:
            df[col] = None

    # Cast fields safely to prep for BQ ingestion
    cast_dict = {
        "age": "Int64",
        "base_salary_millions": "float64",
        "prorated_bonus_millions": "float64",
        "roster_bonus_millions": "float64",
        "guaranteed_salary_millions": "float64",
    }

    for col, dtype in cast_dict.items():
        if col in df.columns:
            try:
                df[col] = df[col].astype(dtype)
            except Exception as e:
                logger.warning(f"Failed to cast {col} to {dtype}: {e}")

    # Create dummy ID placeholders for upstream generation
    if "contract_id" not in df.columns:
        df["contract_id"] = None
    if "player_id" not in df.columns:
        df["player_id"] = None

    return df

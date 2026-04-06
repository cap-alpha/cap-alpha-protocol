"""
Functions for calculating player value metrics.
"""

import numpy as np
import pandas as pd


def calculate_value_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Efficiency and Value Deltas for players.

    Expected columns:
    - total_contract_value_millions
    - contract_length_years
    - performance_av (or AV)
    """
    df = df.copy()

    # Calculate APY (Average Per Year)
    # Using total_contract_value / contract_length
    if (
        "total_contract_value_millions" in df.columns
        and "contract_length_years" in df.columns
    ):
        df["salary_apy"] = (
            df["total_contract_value_millions"] / df["contract_length_years"]
        )

    # Simple efficiency metric: AV per Million APY
    if "performance_av" in df.columns and "salary_apy" in df.columns:
        # Avoid division by zero
        df["efficiency_av_per_million"] = df["performance_av"] / df[
            "salary_apy"
        ].replace(0, np.nan)
    elif "AV" in df.columns and "salary_apy" in df.columns:
        df["efficiency_av_per_million"] = df["AV"] / df["salary_apy"].replace(0, np.nan)

    return df


def calculate_edce(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate Expected Dead Cap Exposure (EDCE).

    EDCE = Probability_of_Decline * Potential_Dead_Cap

    Risk Factors (Prototype):
    - Age-based sigmoid curve.
    - Position-specific thresholds (RB=28, WR/DB=30, Others=32).
    """
    df = df.copy()

    # helper sigmoid
    def sigmoid(x, k=1):
        return 1 / (1 + np.exp(-k * x))

    # 1. Define Risk Thresholds
    thresholds = {
        "RB": 28,
        "WR": 30,
        "CB": 30,
        "S": 30,
        "LB": 30,
        "TE": 31,
        "QB": 35,
        "OL": 32,
        "DL": 32,
    }

    # Map threshold
    # Default to 32 if pos not found
    df["risk_age_threshold"] = df["position"].map(thresholds).fillna(32)

    # 2. Calculate Age Delta (Age - Threshold)
    # If Age is missing, assume 25 (Low Risk) for safety
    age_filled = df["age"].fillna(25)
    df["age_delta"] = age_filled - df["risk_age_threshold"]

    # 3. Probability of Decline (Sigmoid)
    # k=0.5 -> smooth curve. k=1 -> steeper.
    # At Age == Threshold, Prob = 0.5
    df["prob_decline"] = sigmoid(df["age_delta"], k=0.8)

    # 4. Exposure Basis
    # Use dead_cap_current. If 0, fallback to guaranteed_m as proxy for "potential dead cap"
    # (Since dead_cap_current is strictly "if cut NOW", which implies accelerating guarantees)
    df["exposure_basis"] = df["dead_cap_current"]
    mask_zero_dead = df["exposure_basis"] == 0
    df.loc[mask_zero_dead, "exposure_basis"] = df.loc[mask_zero_dead, "guaranteed_m"]

    # 5. Calculate EDCE
    df["EDCE"] = df["prob_decline"] * df["exposure_basis"]

    return df


def calculate_ied(df: pd.DataFrame, dollars_per_av: float = 2.0) -> pd.DataFrame:
    """
    Calculate Inefficient Expenditure Delta (IED).

    IED = Cap_Hit - Fair_Market_Value
    Fair_Market_Value = Performance_AV * $/AV_Benchmark

    Positive IED = Overpaid (Inefficient)
    Negative IED = Underpaid (Value)
    """
    df = df.copy()

    # Ensure cols exist
    if "performance_av" in df.columns:
        av_col = "performance_av"
    elif "AV_Proxy" in df.columns:
        av_col = "AV_Proxy"
    else:
        # Cannot calculate without performance
        df["IED"] = 0.0
        return df

    if "cap_hit_millions" not in df.columns:
        df["IED"] = 0.0
        return df

    # Calculate Fair Value
    # Default $2M per AV is a rough NFL average (e.g. 255M Cap / ~120 AV for MVP = ~2M?)
    # Actually MVP is usually ~15-20 AV. $50M / 20 = $2.5M/AV.
    # Replacement level is 0-2 AV.
    df["fair_value_m"] = df[av_col] * dollars_per_av

    # Calculate IED
    df["IED"] = df["cap_hit_millions"] - df["fair_value_m"]

    return df

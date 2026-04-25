import pandas as pd
import glob
import logging

logging.basicConfig(level=logging.INFO)


def test_join():
    print("🚀 Feasibility Test: Joining Spotrac & PFR Data (2023)...")

    # 1. Load Spotrac 2023 Contracts
    spotrac_files = glob.glob("data/raw/spotrac_player_contracts_2023*.csv")
    if not spotrac_files:
        print("❌ Spotrac 2023 file not found.")
        return
    df_s = pd.read_csv(spotrac_files[0])

    # 2. Load PFR 2023 Game Logs
    pfr_files = glob.glob("data/raw/pfr/game_logs_2023.csv")
    if not pfr_files:
        print("❌ PFR 2023 file not found.")
        return
    df_p = pd.read_csv(pfr_files[0])

    # Simple normalization: Trim and Lowercase
    def clean_doubled_name(name):
        if not isinstance(name, str):
            return name
        parts = name.strip().split()
        if len(parts) < 2:
            return name
        if len(parts) >= 3 and parts[0] == parts[-1]:
            return " ".join(parts[1:])
        mid = len(parts) // 2
        if len(parts) % 2 == 0:
            if parts[:mid] == parts[mid:]:
                return " ".join(parts[:mid])
        return name

    df_s["player_name_clean"] = (
        df_s["player_name"].apply(clean_doubled_name).str.lower().str.strip()
    )
    # Handle both doubled names (if pre-patch) and PFR's flattened multi-index header
    pfr_col = (
        "Unnamed: 0_level_0_Player"
        if "Unnamed: 0_level_0_Player" in df_p.columns
        else "Player"
    )
    df_p["Player_clean"] = (
        df_p[pfr_col].str.lower().str.strip().str.replace("*", "").str.replace("+", "")
    )

    # Check for Mahomes, Josh Allen, etc.
    top_stars = ["patrick mahomes", "josh allen", "lamar jackson", "tyreek hill"]

    print("\n--- Match Verification ---")
    for star in top_stars:
        in_s = star in df_s["player_name_clean"].values
        in_p = star in df_p["Player_clean"].values
        status = "✅ MATCH" if in_s and in_p else "❌ MISS"
        print(
            f"{star.capitalize():<20} | Spotrac: {in_s:<5} | PFR: {in_p:<5} | Result: {status}"
        )

    # Merge stats
    merged = pd.merge(df_s, df_p, left_on="player_name_clean", right_on="Player_clean")
    print(f"\nTotal Merged Records (Uniques): {merged['player_name_clean'].nunique()}")
    print(f"Sample Merged Columns: {merged.columns.tolist()[:10]}")


if __name__ == "__main__":
    test_join()

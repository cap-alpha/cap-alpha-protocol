import pandas as pd
from pathlib import Path


def debug_cleaning():
    f = sorted(Path("data_raw").glob("spotrac_player_contracts_2024_*.csv"))[-1]
    print(f"Loading {f}")
    df = pd.read_csv(f)

    def clean_redundant_name(name):
        if not isinstance(name, str):
            return ""
        parts = name.split()
        if len(parts) >= 3 and parts[0].lower() == parts[-1].lower():
            return " ".join(parts[1:])
        return name

    df["clean_player_name"] = df["player_name"].apply(clean_redundant_name)
    df["clean_name"] = (
        df["clean_player_name"].str.lower().str.replace(".", "").str.strip()
    )

    kyler = df[df["player_name"].str.contains("Kyler")]
    print("\nKyler Rows:")
    print(
        kyler[
            [
                "player_name",
                "clean_player_name",
                "clean_name",
                "guaranteed_money_millions",
            ]
        ]
    )


if __name__ == "__main__":
    debug_cleaning()

import pandas as pd
from pathlib import Path


def inspect():
    # Load latest contract file
    f = sorted(
        Path("data_raw").glob("spotrac_player_contracts_2024_*.csv"),
        key=lambda f: f.stat().st_mtime,
    )[-1]
    print(f"Reading {f.name}")
    df = pd.read_csv(f)

    kyler = df[df["player_name"].str.contains("Kyler", case=False)]
    if kyler.empty:
        print("No Kyler found in CSV?!")
        return

    raw_name = kyler.iloc[0]["player_name"]
    print(f"Raw Name: '{raw_name}'")

    # Apply logic
    def clean_redundant_name(name):
        if not isinstance(name, str):
            return ""
        parts = name.split()
        # If 3+ parts and first == last (case-insensitive), drop first
        if len(parts) >= 3 and parts[0].lower() == parts[-1].lower():
            return " ".join(parts[1:])
        return name

    cleaned_step1 = clean_redundant_name(raw_name)
    print(f"Step 1: '{cleaned_step1}'")

    final = cleaned_step1.lower().replace(".", "").strip()
    print(f"Final: '{final}'")

    if final == "kyler murray":
        print("MATCHES expectation.")
    else:
        print("DOES NOT MATCH 'kyler murray'")


if __name__ == "__main__":
    inspect()

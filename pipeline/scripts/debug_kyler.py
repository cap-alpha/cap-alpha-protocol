import pandas as pd
from src.config import DATA_PROCESSED_DIR


def debug():
    path = DATA_PROCESSED_DIR / "canonical_player_timeline.parquet"
    df = pd.read_parquet(path)

    kyler = df[(df["clean_name"] == "kyler murray") & (df["season"] == 2024)]
    print("\nKyler 2024 Record:")
    if kyler.empty:
        print("Not Found!")
    else:
        print(kyler.iloc[0].to_dict())

    if "guaranteed_m" in df.columns:
        print(f"\nGuaranteed M Column stats: {df['guaranteed_m'].sum()}")
        print("First 5 matches with guarantees:")
        print(
            df[df["guaranteed_m"] > 0][["clean_name", "season", "guaranteed_m"]].head()
        )
    else:
        print("\nGuaranteed M Column MISSING")


if __name__ == "__main__":
    debug()

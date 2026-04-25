import pandas as pd
from src.config import DATA_PROCESSED_DIR


def validate():
    path = DATA_PROCESSED_DIR / "canonical_player_timeline.parquet"
    if not path.exists():
        print(f"File not found: {path}")
        return

    df = pd.read_parquet(path)

    print(f"Total Rows: {len(df)}")
    print(df.head())

    # Check nulls
    print("\nNull Counts:")
    print(df.isnull().sum())

    # Check Required Columns for Contract Details
    required_cols = ["guaranteed_m", "dead_cap_current"]
    for col in required_cols:
        if col not in df.columns:
            print(f"FAIL: Missing column {col}")
        else:
            print(f"PASS: Column {col} exists.")
            # Check for non-zero values
            non_zeros = df[df[col] > 0]
            print(
                f"  Rows with {col} > 0: {len(non_zeros)} ({len(non_zeros)/len(df):.1%})"
            )

    # Check ID stability
    # select a player
    mahomes = df[df["clean_name"] == "patrick mahomes"]
    print("\nPatrick Mahomes ID check:")
    cols_to_show = ["season", "player_id", "cap_hit", "AV_Proxy"] + [
        c for c in required_cols if c in df.columns
    ]
    print(mahomes[cols_to_show])

    unique_ids = mahomes["player_id"].nunique()
    if unique_ids == 1:
        print("PASS: Mahomes has consistent ID.")
    else:
        print(f"FAIL: Mahomes has {unique_ids} IDs.")

    # Check Coverage
    perf_coverage = len(df[df["AV_Proxy"] > 0]) / len(df)
    print(f"\nPerformance Coverage: {perf_coverage:.1%}")


if __name__ == "__main__":
    validate()

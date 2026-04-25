import json
import pandas as pd
import sys
from collections import Counter


def audit_roster(file_path):
    print(f"🔍 Starting Data Quality Audit on: {file_path}")

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ File not found: {file_path}")
        return

    df = pd.DataFrame(data)

    # 1. Basic Counts
    print(f"📊 Total Records: {len(df)}")

    # 2. Check for Duplicates (Player + Team)
    print("\n--- 👯 Duplicate Check ---")
    df["key"] = df["player_name"] + "_" + df["team"]
    dupes = df[df.duplicated(subset=["key"], keep=False)]
    if not dupes.empty:
        print(f"⚠️ Found {len(dupes)} duplicate entries:")
        print(
            dupes[["player_name", "team", "position"]]
            .sort_values("player_name")
            .head(10)
            .to_string()
        )
    else:
        print("✅ No duplicates found.")

    # 3. Check for $0 or Null Values in Critical Fields
    print("\n--- 💸 Value Integrity Check ---")
    critical_cols = ["cap_hit_millions", "fair_market_value", "ml_risk_score"]
    for col in critical_cols:
        zeros = df[df[col] == 0]
        nulls = df[df[col].isnull()]
        print(f"{col}: {len(zeros)} zeros, {len(nulls)} nulls")
        if len(zeros) > 0:
            print(f"   Sample Zeros: {zeros['player_name'].head(3).tolist()}")

    # 4. Outlier Detection (Negative FMV)
    print("\n--- 📉 Outlier Detection ---")
    neg_fmv = df[df["fair_market_value"] < 0]
    if not neg_fmv.empty:
        print(f"⚠️ Found {len(neg_fmv)} players with Negative FMV:")
        print(neg_fmv[["player_name", "fair_market_value", "team"]].head().to_string())
    else:
        print("✅ No negative FMV values found.")

    # 5. Logical Inconsistencies (High Cap, Low FMV)
    print("\n--- 🧠 Logic Check (High Cap, Low FMV) ---")
    # Players getting paid > $20M but FMV < $10M (Potential dead money candidates or data errors)
    overpaid = df[(df["cap_hit_millions"] > 20) & (df["fair_market_value"] < 10)]
    if not overpaid.empty:
        print(
            f"⚠️ Found {len(overpaid)} potential 'Dead Money' candidates (Cap > 20M, FMV < 10M):"
        )
        print(
            overpaid[["player_name", "cap_hit_millions", "fair_market_value"]]
            .sort_values("cap_hit_millions", ascending=False)
            .head(10)
            .to_string()
        )
    else:
        print("✅ No extreme overpay outliers found.")

    # 6. Specific Star Check
    print("\n--- ⭐ Star Player Check ---")
    stars = [
        "Micah Parsons",
        "Patrick Mahomes",
        "Josh Allen",
        "T.J. Watt",
        "Myles Garrett",
    ]
    print(
        df[df["player_name"].isin(stars)][
            [
                "player_name",
                "team",
                "cap_hit_millions",
                "fair_market_value",
                "ml_risk_score",
            ]
        ].to_string()
    )


if __name__ == "__main__":
    # Check both locations, prefer 'data/' for pipeline context
    import os

    if os.path.exists("data/roster_dump.json"):
        audit_roster("data/roster_dump.json")
    else:
        audit_roster("web/data/roster_dump.json")

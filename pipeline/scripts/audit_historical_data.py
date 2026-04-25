import pandas as pd
import glob
import os
import re
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Heuristic list of 2024/2025 "future" players to detect anachronism leakages
# If these appear in 2015-2020 files, we have a routing bug.
FUTURE_PLAYERS = [
    "Caleb Williams",
    "Jayden Daniels",
    "Drake Maye",
    "Marvin Harrison Jr.",
    "Brixson Cloud",
    "Kyler Murray",
    "Justin Jefferson",
    "Breece Hall",
]

# NFL Salary Cap history for sanity checks (approximate)
SALARY_CAPS = {
    2015: 143.28,
    2016: 155.27,
    2017: 167.0,
    2018: 177.2,
    2019: 188.2,
    2020: 198.2,
    2021: 182.5,
    2022: 208.2,
    2023: 224.8,
    2024: 255.4,
}


def audit_file(filepath):
    """Run integrity checks on a single CSV file."""
    df = pd.read_csv(filepath)
    filename = os.path.basename(filepath)

    # Extract year from filename (e.g., spotrac_player_contracts_2015_...)
    year_match = re.search(r"_(20\d{2})_", filename)
    if not year_match:
        return
    year = int(year_match.group(1))

    results = {
        "file": filename,
        "year": year,
        "rows": len(df),
        "null_names": df["player_name"].isnull().sum(),
        "anachronisms": [],
        "financial_audit": "PASS",
    }

    # 1. Anachronism Check (Heuristic)
    if year < 2020:
        found = [
            p
            for p in FUTURE_PLAYERS
            if df["player_name"].astype(str).str.contains(p, case=False, na=False).any()
        ]
        results["anachronisms"] = found

    # 2. Null Checks on critical columns
    critical_cols = ["player_name", "team", "year"]
    for col in critical_cols:
        if col in df.columns and df[col].isnull().any():
            results[f"null_{col}"] = df[col].isnull().sum()

    # 3. Financial Sanity Check (for Rankings/Contracts)
    if "cap_hit_millions" in df.columns:
        total_cap = df.groupby("team")["cap_hit_millions"].sum().max()
        official_cap = SALARY_CAPS.get(year, 255)
        # We allow some buffer for dead money/injured reserve (e.g. 150% of cap)
        if total_cap > official_cap * 1.5:
            results["financial_audit"] = (
                f"FAIL (Max Team Cap {total_cap:.1f}M > {official_cap}M)"
            )

    return results


def run_audit():
    logger.info("🚀 Starting Deep Data Quality Audit...")
    raw_dir = "data/raw"
    files = glob.glob(f"{raw_dir}/spotrac*.csv")

    audit_reports = []
    for f in sorted(files):
        report = audit_file(f)
        if report:
            audit_reports.append(report)

    # Summary of findings
    df_audit = pd.DataFrame(audit_reports)

    # Check for failures
    anachronism_failures = df_audit[df_audit["anachronisms"].map(len) > 0]
    financial_failures = df_audit[
        df_audit["financial_audit"].str.contains("FAIL", na=False)
    ]

    if not anachronism_failures.empty:
        logger.error(f"❌ ANACHRONISM DETECTED in {len(anachronism_failures)} files!")
        print(anachronism_failures[["file", "anachronisms"]])
    else:
        logger.info("✅ No anachronisms detected in verified files.")

    if not financial_failures.empty:
        logger.warning(
            f"⚠️ FINANCIAL OUTLIERS detected in {len(financial_failures)} files."
        )
        print(financial_failures[["file", "financial_audit"]])
    else:
        logger.info("✅ Financial sanity checks passed.")

    # Null Check Summary
    logger.info(f"📊 Audit complete for {len(df_audit)} files.")
    print(df_audit[["file", "rows", "null_names", "financial_audit"]].to_string())


if __name__ == "__main__":
    run_audit()

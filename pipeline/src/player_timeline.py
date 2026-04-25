import hashlib
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from src.config import DATA_PROCESSED_DIR, DATA_RAW_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CanonicalPlayerTimeline:
    """
    Builds the 'Canonical Player Timeline' - the single source of truth for all player-seasons.

    Responsibilities:
    1. Ingest Raw Data (Spotrac Financials + PFR Performance).
    2. Mint Canonical Player IDs (Issue 2.4).
    3. Resolve Name/Entity Collisions.
    4. Guard against Future Leakage (Issue 2.5) by strictly associating data to its season.
    """

    def __init__(self):
        self.raw_dir = DATA_RAW_DIR
        self.out_dir = DATA_PROCESSED_DIR

    def _mint_player_id(self, name_clean: str) -> str:
        """
        Generate a deterministic 12-char ID from the player's cleaned name.
        TODO: Improve collision resistance with DOB/College if available.
        """
        return hashlib.md5(name_clean.encode("utf-8")).hexdigest()[:12]

    def load_financials(self) -> pd.DataFrame:
        """Load and normalize all historical Spotrac files."""
        # This logic mimics etl_transform but is formalized here
        # For now, we reuse the pattern but structure it for the timeline
        files = sorted(self.raw_dir.glob("spotrac_player_rankings_*.csv"))
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f)
                # Correctly extract year from filename: spotrac_player_rankings_2024_...
                # pattern: spotrac_player_rankings_YEAR_...
                import re

                match = re.search(r"spotrac_player_rankings_(\d{4})", f.name)
                if match:
                    year = int(match.group(1))
                else:
                    # Fallback to splitting if regex fails (though regex is safer)
                    # format: spotrac_player_rankings_2024_...
                    year = int(f.stem.split("_")[3])

                df["season"] = year
                dfs.append(df)
            except Exception as e:
                logger.warning(f"Error loading {f}: {e}")

        if not dfs:
            return pd.DataFrame()

        fin = pd.concat(dfs, ignore_index=True)
        # Normalize
        fin["cap_hit"] = np.nan

        if "cap_hit_millions" in fin.columns:
            fin["cap_hit"] = fin["cap_hit"].fillna(fin["cap_hit_millions"])

        # Fix: Map total_contract_value_millions to cap_hit if it exists
        # (Spotrac rankings often name the primary value column as total_contract_value even if it's cap hit)
        if "total_contract_value_millions" in fin.columns:
            fin["cap_hit"] = fin["cap_hit"].fillna(fin["total_contract_value_millions"])

        if "value" in fin.columns:
            # Fallback parsing
            parsed_value = (
                fin["value"]
                .replace(r"[$,]", "", regex=True)
                .apply(pd.to_numeric, errors="coerce")
                / 1_000_000
            )
            fin["cap_hit"] = fin["cap_hit"].fillna(parsed_value)

        # Ensure Age exists
        if "age" not in fin.columns:
            fin["age"] = np.nan

        fin["clean_name"] = (
            fin["player_name"].str.lower().str.replace(".", "").str.strip()
        )
        fin["cap_hit"] = fin["cap_hit"].fillna(0)

        return fin[["clean_name", "season", "team", "position", "cap_hit", "age"]]

    def load_performance(self) -> pd.DataFrame:
        """Load and normalize all historical PFR files."""
        # PFR Game Logs usually
        # We need a consolidated "Season Stats" view.
        # Ideally, we would process game logs into season aggregates here.
        # For simplicity in this step, we can use the game_logs CSVs and agg.
        files = sorted(self.raw_dir.glob("pfr/game_logs_*.csv"))
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f)
                year = int(f.stem.split("_")[-1])
                df["season"] = year
                # clean headers
                df.columns = [c if "Player" not in c else "Player" for c in df.columns]
                dfs.append(df)
            except Exception as e:
                logger.warning(f"Error loading {f}: {e}")

        if not dfs:
            return pd.DataFrame()

        perf = pd.concat(dfs, ignore_index=True)

        # --- Logic from etl_transform.py ---
        if "fantasy_points" not in perf.columns:
            # Helper to safely get numeric cols
            def safe_get(df, col, weight):
                return pd.to_numeric(df.get(col, 0), errors="coerce").fillna(0) * weight

            # Offensive Scoring
            perf["fantasy_points_off"] = (
                safe_get(perf, "Passing_Yds", 0.04)
                + safe_get(perf, "Passing_TD", 4)
                + safe_get(perf, "Rushing_Yds", 0.1)
                + safe_get(perf, "Rushing_TD", 6)
                + safe_get(perf, "Receiving_Yds", 0.1)
                + safe_get(perf, "Receiving_TD", 6)
                - safe_get(perf, "Passing_Int", 2)
            )

            # Defensive Scoring (IDP) - Robust Column Lookup
            def get_col(df, candidates):
                for c in candidates:
                    if c in df.columns:
                        return pd.to_numeric(df[c], errors="coerce").fillna(0)
                return 0.0

            perf["fantasy_points_def"] = (
                (get_col(perf, ["Def Interceptions_Int", "Int"]) * 6)
                + (get_col(perf, ["Tackles_Solo", "Solo"]) * 1)
                + (get_col(perf, ["Tackles_Ast", "Ast"]) * 0.5)
                + (get_col(perf, ["Fumbles_FF", "FF"]) * 3)
                + (get_col(perf, ["Unnamed: 7_level_0_Sk", "Sk", "Sacks"]) * 4)
                + (get_col(perf, ["Def Interceptions_PD", "PD"]) * 1)
            )

            perf["fantasy_points"] = (
                perf["fantasy_points_off"] + perf["fantasy_points_def"]
            )

        # Aggregate to Season Level
        agg = perf.groupby(["Player", "season"])["fantasy_points"].sum().reset_index()
        agg["AV_Proxy"] = agg["fantasy_points"] / 25
        agg["clean_name"] = agg["Player"].str.lower().str.replace(".", "").str.strip()

        return agg[["season", "clean_name", "AV_Proxy", "fantasy_points"]]

    def load_contract_details(self) -> pd.DataFrame:
        """Load detailed contract structure for ALL years available."""
        # Fix: Sort by modification time to get the absolute latest file
        files = sorted(
            self.raw_dir.glob("spotrac_player_contracts_*.csv"),
            key=lambda f: f.stat().st_mtime,
        )

        if not files:
            logger.warning("No detailed contract files found.")
            return pd.DataFrame()

        dfs = []
        for f in files:
            try:
                # Extract year from filename: spotrac_player_contracts_2024_...
                import re

                match = re.search(r"spotrac_player_contracts_(\d{4})_", f.name)
                if match:
                    # We only want the LATEST file for each year if duplicates exist
                    # But verifying that is complex if we just glob.
                    # Simpler: Load all, let the timeline build handle dedup or we handle it here.
                    # Actually, the scraping logic appends timestamp.
                    # We should group by year and take latest.
                    pass

                # Check if it's the latest for that year?
                # For now, let's just load them. Ideally we organize by year.
            except:
                continue

        # Better approach: Group files by year, take latest
        from collections import defaultdict

        year_files = defaultdict(list)
        for f in files:
            match = re.search(r"spotrac_player_contracts_(\d{4})_", f.name)
            if match:
                year_files[int(match.group(1))].append(f)

        dfs = []
        for year, year_file_list in year_files.items():
            # Fix: Sort by time to ensure we get the latest scrape, not the alphabetically last (which might be _test)
            latest = sorted(year_file_list, key=lambda f: f.stat().st_mtime)[-1]
            logger.info(f"Loading contract details for {year} from {latest.name}...")
            try:
                df = pd.read_csv(latest)

                # Fix: Spotrac scrape sometimes returns "Last First Last" (e.g., "Murray Kyler Murray")
                def clean_redundant_name(name):
                    if not isinstance(name, str):
                        return ""
                    parts = name.split()
                    # If 3+ parts and first == last (case-insensitive), drop first
                    if len(parts) >= 3 and parts[0].lower() == parts[-1].lower():
                        return " ".join(parts[1:])
                    return name

                df["clean_player_name"] = df["player_name"].apply(clean_redundant_name)
                df["clean_name"] = (
                    df["clean_player_name"].str.lower().str.replace(".", "").str.strip()
                )

                # Ensure year col exists or enforce it
                df["season"] = year

                # Ensure we have the target columns
                # If scraping failed to find dead cap, we initialize it to 0
                cols_map = {
                    "guaranteed_money_millions": "guaranteed_m",
                    "dead_cap_millions": "dead_cap_current",
                    "years_remaining": "years_remaining_contract",
                    "age": "contract_age",  # Keep extracted Age
                }

                # Create missing columns as 0/nan
                for c in cols_map.keys():
                    if c not in df.columns:
                        if c == "age":
                            df[c] = np.nan
                        else:
                            df[c] = 0.0

                cols = ["clean_name", "season"] + list(cols_map.keys())
                available = [c for c in cols if c in df.columns]

                renamed = df[available].rename(columns=cols_map)
                dfs.append(renamed)
            except Exception as e:
                logger.error(f"Failed to load {latest}: {e}")

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

    def load_dead_money(self) -> pd.DataFrame:
        """Load dead money details for ALL years available."""
        files = sorted(
            self.raw_dir.glob("spotrac_player_salaries_*.csv"),
            key=lambda f: f.stat().st_mtime,
        )

        if not files:
            logger.warning("No dead money files found.")
            return pd.DataFrame()

        import re
        from collections import defaultdict

        year_files = defaultdict(list)
        for f in files:
            match = re.search(r"spotrac_player_salaries_(\d{4})_", f.name)
            if match:
                year_files[int(match.group(1))].append(f)

        dfs = []
        for year, year_file_list in year_files.items():
            latest = sorted(year_file_list, key=lambda f: f.stat().st_mtime)[-1]
            try:
                df = pd.read_csv(latest)
                # Standardize
                df["clean_name"] = (
                    df["player_name"].str.lower().str.replace(".", "").str.strip()
                )
                df["season"] = year

                if "dead_money_millions" in df.columns:
                    df["dead_cap_current"] = df["dead_money_millions"].fillna(0)
                else:
                    df["dead_cap_current"] = 0.0

                dfs.append(df[["clean_name", "season", "dead_cap_current"]])
            except Exception as e:
                logger.error(f"Failed to load dead money {latest}: {e}")

        if not dfs:
            return pd.DataFrame()

        return pd.concat(dfs, ignore_index=True)

    def build_timeline(self):
        logger.info("Building Canonical Timeline...")
        fin = self.load_financials()
        perf = self.load_performance()
        contracts = self.load_contract_details()
        dead_money = self.load_dead_money()

        if fin.empty:
            logger.error("No financial data found.")
            return

        logger.info(
            f"Merging {len(fin)} financial records with {len(perf)} performance records..."
        )
        timeline = pd.merge(fin, perf, on=["clean_name", "season"], how="left")

        # Merge Contract Details
        if not contracts.empty:
            logger.info(f"Merging {len(contracts)} contract detail records...")
            contracts = contracts.drop_duplicates(subset=["clean_name", "season"])
            timeline = pd.merge(
                timeline, contracts, on=["clean_name", "season"], how="left"
            )

        # Merge Dead Money
        if not dead_money.empty:
            logger.info(f"Merging {len(dead_money)} dead money records...")
            dead_money = dead_money.drop_duplicates(subset=["clean_name", "season"])
            # We want to prioritize dead money from this specific file if it exists,
            # or fill it if missing.
            # existing 'dead_cap_current' from contracts might be 0 because it was missing in contracts file.
            # So we suffix.
            timeline = pd.merge(
                timeline,
                dead_money,
                on=["clean_name", "season"],
                how="left",
                suffixes=("", "_dm"),
            )

            # Coalesce: Use dead money file value, fallback to contract file value
            if "dead_cap_current_dm" in timeline.columns:
                timeline["dead_cap_current"] = timeline["dead_cap_current_dm"].fillna(
                    timeline.get("dead_cap_current", 0)
                )
                timeline = timeline.drop(columns=["dead_cap_current_dm"])
        else:
            logger.warning("No dead money file to merge.")

        # Backfill Missing Data using Contract Details/Defaults
        # 1. Fill NaNs in monetary columns
        for col in ["guaranteed_m", "dead_cap_current", "years_remaining_contract"]:
            if col in timeline.columns:
                timeline[col] = timeline[col].fillna(0)

        # 2. Backfill Age if missing in timeline (from fin/perf) but present in contracts
        if "contract_age" in timeline.columns:
            if "age" in timeline.columns:
                timeline["age"] = timeline["age"].fillna(timeline["contract_age"])
            else:
                timeline["age"] = timeline["contract_age"]
            # Drop the temp column
            timeline = timeline.drop(columns=["contract_age"])

        # Fill missing performance with 0 (Did not play)
        timeline["AV_Proxy"] = timeline["AV_Proxy"].fillna(0)
        timeline["fantasy_points"] = timeline["fantasy_points"].fillna(0)

        # Mint IDs
        timeline["player_id"] = timeline["clean_name"].apply(self._mint_player_id)

        # Save One Big Table
        out_path = self.out_dir / "canonical_player_timeline.parquet"
        timeline.to_parquet(out_path, index=False)
        logger.info(f"Saved timeline with {len(timeline)} rows to {out_path}")


if __name__ == "__main__":
    builder = CanonicalPlayerTimeline()
    builder.build_timeline()

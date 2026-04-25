import pandas as pd
import numpy as np
import logging
import sys
from pathlib import Path
from typing import List, Optional
import os

# Ensure project root is in path
sys.path.append(str(Path(__file__).parent.parent))
from src.db_manager import DBManager
from src.config_loader import get_db_path, get_bronze_dir
from src.financial_ingestion import load_team_financials, load_player_merch
from src.spotrac_scraper_v2 import (
    scrape_and_save_player_contracts,
    scrape_and_save_player_rankings,
)
from src.overthecap_scraper import OverTheCapScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BRONZE_DIR = get_bronze_dir()


def clean_doubled_name(name):
    if not isinstance(name, str):
        return name
    parts = name.strip().split()
    if len(parts) >= 3 and parts[0] == parts[-1]:
        return " ".join(parts[1:])
    mid_idx = len(name) // 2
    if len(name) % 2 == 0:
        if name[:mid_idx] == name[mid_idx:]:
            return name[:mid_idx]
    if len(parts) >= 2:
        mid = len(parts) // 2
        if len(parts) % 2 == 0:
            if parts[:mid] == parts[mid:]:
                return " ".join(parts[:mid])
    return name


class BronzeLayer:
    """Bronze Layer: Raw Data Architecture (Direct to BigQuery)"""

    def __init__(self, db: DBManager):
        self.db = db

    def ingest_contracts(self, year: int):
        import datetime

        logger.info(
            f"BronzeLayer: Scraping OverTheCap contracts for {year} to bypass Spotrac 403 blocks..."
        )
        try:
            scraper = OverTheCapScraper()
            df = scraper.scrape_team_contracts(year)
            if df is None or df.empty:
                logger.error("Scraper returned empty DataFrame.")
                return

            # Inject Iceberg-like versioning timestamp
            df["_ingestion_timestamp"] = pd.Timestamp.utcnow()

            # Append directly to BigQuery Bronze Table
            self.db.append_dataframe_to_table(df, "bronze_overthecap_contracts")
            logger.info(
                "BronzeLayer: Successfully materialized contracts to bronze_overthecap_contracts."
            )
        except Exception as e:
            logger.error(f"BronzeLayer: Failed to ingest OTC contracts: {e}")

    @staticmethod
    def find_files(pattern: str, year: int) -> List[Path]:
        possible_globs = [
            BRONZE_DIR / "spotrac" / str(year) / f"{pattern}*.csv",
            Path("data/raw") / f"{pattern}_{year}*.csv",
            Path("data_raw_DEPRECATED") / f"{pattern}_{year}*.csv",
            # Handle penalties specific glob
            BRONZE_DIR / "penalties" / str(year) / f"{pattern}*.csv",
        ]

        for g in possible_globs:
            files = list(g.parent.glob(g.name))
            if files:
                # Sort by modification time (newest first) to get latest scrape
                files.sort(key=lambda x: x.stat().st_mtime)
                return [files[-1]]

        return []


class SilverLayer:
    """SilverLayer: Cleaning, Normalizing, and Loading into Structured Tables."""

    def __init__(self, db: DBManager):
        self.db = db

    def provision_schemas(self):
        logger.info("Provisioning Silver Layer schemas from contracts...")
        schema_path = Path(__file__).parent.parent.parent / "contracts" / "schema.sql"
        if not schema_path.exists():
            # Fallback for Docker if mounted differently or during build
            schema_path = Path("/app/contracts/schema.sql")

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema contract not found at {schema_path}")

        with open(schema_path, "r") as f:
            sql_content = f.read()

        # Split by semicolon to execute one by one, skipping empty lines
        statements = [s.strip() for s in sql_content.split(";") if s.strip()]

        for sql in statements:
            try:
                self.db.execute(sql)
            except Exception as e:
                logger.warning(
                    f"Failed to execute schema statement: {e}. Statement: {sql[:50]}..."
                )

    def ingest_contracts(self, year: int):
        logger.info(f"SilverLayer: Ingesting Contracts data from Bronze for {year}")
        try:
            # Emulate Iceberg logic: fetch the LATEST ingestion
            # We use MAX(_ingestion_timestamp) partitioned by year to get the newest snapshot.
            query = f"""
                WITH latest_scrape AS (
                    SELECT MAX(_ingestion_timestamp) as latest_ts 
                    FROM {self.db.project_id}.{self.db.dataset_id}.bronze_overthecap_contracts
                    WHERE year = {year}
                )
                SELECT *
                FROM {self.db.project_id}.{self.db.dataset_id}.bronze_overthecap_contracts
                WHERE year = {year}
                  AND _ingestion_timestamp = (SELECT latest_ts FROM latest_scrape)
            """
            df = self.db.fetch_df(query)
            if df.empty:
                logger.warning(f"No Bronze OverTheCap records found for {year}.")
                return
        except Exception as e:
            logger.error(f"Failed to query bronze_overthecap_contracts: {e}")
            return

        df["player_name"] = df["player_name"].apply(clean_doubled_name)

        # Map OverTheCap columns to the expected Silver schema (which previously relied on Spotrac)
        df["cap_hit_millions"] = df["year_cap_hit_millions"].fillna(0.0)
        df["dead_cap_millions"] = df["guaranteed_money_millions"].fillna(0.0)
        df["signing_bonus_millions"] = df["signing_bonus_millions"].fillna(0.0)
        df["total_contract_value_millions"] = df["total_value_millions"].fillna(0.0)

        # OverTheCap does not provide granular base_salary or age on the generic table layout
        required_cols = [
            "age",
            "base_salary_millions",
            "prorated_bonus_millions",
            "roster_bonus_millions",
            "guaranteed_salary_millions",
        ]
        for col in required_cols:
            df[col] = None

        logger.info(
            f"SilverLayer: Upserting {len(df)} contract records for {year} into silver_spotrac_contracts..."
        )
        self.db.execute(f"DELETE FROM silver_spotrac_contracts WHERE year = {year}")
        self.db.execute(
            """
            INSERT INTO silver_spotrac_contracts (player_name, team, year, position, cap_hit_millions, dead_cap_millions, signing_bonus_millions, guaranteed_money_millions, total_contract_value_millions, age, base_salary_millions, prorated_bonus_millions, roster_bonus_millions, guaranteed_salary_millions)
            SELECT player_name, team, year, position, cap_hit_millions, dead_cap_millions, signing_bonus_millions, guaranteed_money_millions, total_contract_value_millions, SAFE_CAST(age AS INT64), SAFE_CAST(base_salary_millions AS FLOAT64), SAFE_CAST(prorated_bonus_millions AS FLOAT64), SAFE_CAST(roster_bonus_millions AS FLOAT64), SAFE_CAST(guaranteed_salary_millions AS FLOAT64) FROM df
        """,
            {"df": df},
        )

        # Emulate Spotrac Salaries schema using OverTheCap guaranteed money so Gold Layer dependencies don't break
        df_sal = df.copy()
        df_sal["dead_cap"] = df_sal["dead_cap_millions"].astype(str)
        self.db.execute(f"DELETE FROM silver_spotrac_salaries WHERE year = {year}")
        self.db.execute(
            """
            INSERT INTO silver_spotrac_salaries (player_name, team, year, position, dead_cap)
            SELECT player_name, team, year, position, dead_cap FROM df_sal
        """,
            {"df_sal": df_sal},
        )

    def ingest_pfr(self, year: int):
        logger.info(f"SilverLayer: Ingesting PFR Data for {year}")
        # Direct path to the clean CSV generated by scrape_pfr.py
        file_path = None
        for p in [
            f"data/raw/pfr/{year}/game_logs_{year}.csv",
            f"data/raw/pfr/game_logs_{year}.csv",
            f"data/bronze/pfr/{year}/game_logs_{year}.csv",
            f"data/bronze/pfr/game_logs_{year}.csv",
            f"data_raw_DEPRECATED/pfr/{year}/game_logs_{year}.csv",
            f"data_raw_DEPRECATED/pfr/game_logs_{year}.csv",
        ]:
            try:
                if os.path.exists(p):
                    file_path = p
                    break
            except Exception:
                pass

        if not file_path:
            logger.warning(f"No PFR data found for {year} in any candidate paths")
            return

        df = pd.read_csv(file_path)

        # Handle raw MultiIndex CSV column names if present
        rename_map = {
            "Unnamed: 0_level_0_Player": "player_name",
            "Unnamed: 1_level_0_Tm": "team",
            "Def Interceptions_Int": "Interceptions",
            "Unnamed: 7_level_0_Sk": "Sacks",
        }
        df = df.rename(columns=rename_map)

        # Ensure defensive columns exist
        if "Sacks" not in df.columns:
            df["Sacks"] = 0
        if "Interceptions" not in df.columns:
            df["Interceptions"] = 0

        # Ensure correct types
        numeric_cols = [
            "Passing_Yds",
            "Rushing_Yds",
            "Receiving_Yds",
            "Passing_TD",
            "Rushing_TD",
            "Receiving_TD",
            "Sacks",
            "Interceptions",
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        self.db.execute(f"DELETE FROM silver_pfr_game_logs WHERE year = {year}")
        self.db.execute(
            """
            INSERT INTO silver_pfr_game_logs (player_name, team, year, week, game_url, Passing_Yds, Rushing_Yds, Receiving_Yds, Passing_TD, Rushing_TD, Receiving_TD, Sacks, Interceptions)
            SELECT 
                player_name, team, year, week, game_url, 
                Passing_Yds, Rushing_Yds, Receiving_Yds, 
                Passing_TD, Rushing_TD, Receiving_TD,
                Sacks, Interceptions
            FROM df
        """,
            {"df": df},
        )

    def ingest_penalties(self, year: int):
        logger.info(f"SilverLayer: Ingesting Penalties for {year}")
        files = BronzeLayer.find_files("improved_penalties", year)
        if not files:
            return

        df = pd.read_csv(files[-1])
        city_map = {
            "Houston": "HOU",
            "Dallas": "DAL",
            "Kansas City": "KC",
            "Buffalo": "BUF",
            "Pittsburgh": "PIT",
            "Denver": "DEN",
            "Baltimore": "BAL",
            "New Orleans": "NO",
            "New England": "NE",
            "Washington": "WAS",
            "Carolina": "CAR",
            "Atlanta": "ATL",
            "Indianapolis": "IND",
            "Minnesota": "MIN",
            "Las Vegas": "LV",
            "Detroit": "DET",
            "Green Bay": "GB",
            "Chicago": "CHI",
            "New York Jets": "NYJ",
            "New York Giants": "NYG",
            "San Francisco": "SF",
            "Tampa Bay": "TB",
            "Seattle": "SEA",
            "Miami": "MIA",
            "Jacksonville": "JAX",
            "Cleveland": "CLE",
            "Cincinnati": "CIN",
            "Arizona": "ARI",
            "Philadelphia": "PHI",
            "Tennessee": "TEN",
            "Los Angeles Rams": "LAR",
            "Los Angeles Chargers": "LAC",
        }
        df["team"] = df["team_city"].map(city_map)

        self.db.execute(f"DELETE FROM silver_penalties WHERE year = {year}")
        # Explicitly select schema columns to avoid binder errors on extra columns
        self.db.execute(
            """
            INSERT INTO silver_penalties (player_name_short, team, year, penalty_count, penalty_yards)
            SELECT player_name_short, team, year, penalty_count, penalty_yards FROM df
        """,
            {"df": df},
        )

    def ingest_team_cap(self):
        logger.info("SilverLayer: Ingesting Team Cap data")
        dead_money_dir = BRONZE_DIR / "dead_money"
        files = list(dead_money_dir.rglob("team_cap_*.csv"))
        if not files:
            return

        dfs = [pd.read_csv(f) for f in files]
        df = pd.concat(dfs)
        self.db.execute(
            "CREATE OR REPLACE TABLE silver_team_cap AS SELECT DISTINCT * FROM df",
            {"df": df},
        )

    def ingest_others(self):
        logger.info("SilverLayer: Ingesting other static datasets")
        fin_path = BRONZE_DIR / "other" / "finance" / "team_valuations_2024.csv"
        if fin_path.exists():
            load_team_financials(self.db.con, fin_path)

        merch_path = BRONZE_DIR / "other" / "merch" / "nflpa_player_sales_2024.csv"
        if merch_path.exists():
            load_player_merch(self.db.con, merch_path)

        draft_file = Path("data/raw/pfr/draft_history.csv")
        if draft_file.exists():
            df_draft = pd.read_csv(draft_file)
            self.db.execute(
                "CREATE OR REPLACE TABLE silver_pfr_draft_history AS SELECT * FROM df_draft",
                {"df_draft": df_draft},
            )

    def ingest_player_metadata(self):
        logger.info("SilverLayer: Ingesting player metadata")
        meta_file = Path("data/raw/player_metadata.csv")
        if meta_file.exists():
            df_meta = pd.read_csv(meta_file)
            # Normalize column names if needed, assume match for now
            self.db.execute(
                "CREATE OR REPLACE TABLE silver_player_metadata AS SELECT * FROM df_meta",
                {"df_meta": df_meta},
            )


class GoldLayer:
    """Gold Layer: Aggregating into Feature-Rich Analytics Tables."""

    def __init__(self, db: DBManager):
        self.db = db

    def build_fact_player_efficiency(self):
        logger.info("GoldLayer: Building fact_player_efficiency...")

        self.db.execute("""
        CREATE OR REPLACE TABLE fact_player_efficiency AS
        WITH pfr_agg AS (
            SELECT 
                player_name, team, year, week,
                COUNT(DISTINCT game_url) as games_played,
                SUM(SAFE_CAST(Passing_Yds AS FLOAT64)) as total_pass_yds,
                SUM(SAFE_CAST(Rushing_Yds AS FLOAT64)) as total_rush_yds,
                SUM(SAFE_CAST(Receiving_Yds AS FLOAT64)) as total_rec_yds,
                SUM(SAFE_CAST(Passing_TD AS INT64) + SAFE_CAST(Rushing_TD AS INT64) + SAFE_CAST(Receiving_TD AS INT64)) as total_tds,
                -- Defensive Aggregations
                SUM(SAFE_CAST(Sacks AS FLOAT64)) as total_sacks,
                SUM(SAFE_CAST(Interceptions AS FLOAT64)) as total_int
            FROM silver_pfr_game_logs
            GROUP BY 1, 2, 3, 4
        ),
        penalties_agg AS (
            SELECT 
                player_name_short, team, year,
                SUM(penalty_count) as total_penalty_count,
                SUM(penalty_yards) as total_penalty_yards
            FROM silver_penalties
            GROUP BY 1, 2, 3
        ),
        dedup_contracts AS (
            SELECT 
                CASE 
                    WHEN MOD(LENGTH(s.player_name), 2) = 0 AND SUBSTRING(s.player_name, 1, CAST(LENGTH(s.player_name)/2 AS INT64)) = SUBSTRING(s.player_name, CAST(LENGTH(s.player_name)/2 + 1 AS INT64))
                    THEN SUBSTRING(s.player_name, 1, CAST(LENGTH(s.player_name)/2 AS INT64))
                    ELSE s.player_name 
                END as player_name, 
                s.team, s.year, 
                MAX(s.position) as position,
                -- FIX: Do NOT fallback to rankings for cap hit, as rankings often contain Total Value
                SUM(s.cap_hit_millions) as cap_hit_millions,
                SUM(s.dead_cap_millions) as dead_cap_millions,
                MAX(s.signing_bonus_millions) as signing_bonus_millions,
                MAX(s.guaranteed_money_millions) as guaranteed_money_millions,
                MAX(s.base_salary_millions) as base_salary_millions,
                MAX(s.prorated_bonus_millions) as prorated_bonus_millions,
                MAX(s.roster_bonus_millions) as roster_bonus_millions,
                MAX(s.guaranteed_salary_millions) as guaranteed_salary_millions,
                MAX(s.total_contract_value_millions) as total_contract_value_millions,
                MAX(s.age) as age
            FROM silver_spotrac_contracts s
            LEFT JOIN (
                SELECT player_name, year, MAX(ranking_cap_hit_millions) as ranking_cap_hit_millions 
                FROM silver_spotrac_rankings 
                GROUP BY 1, 2
            ) r 
              ON LOWER(TRIM(CAST(s.player_name AS STRING))) = LOWER(TRIM(CAST(r.player_name AS STRING)))
              AND s.year = r.year
            GROUP BY 1, 2, 3
        ),
        salary_dead_cap AS (
            SELECT 
                player_name, team, year,
                MAX(SAFE_CAST(REPLACE(REPLACE(REPLACE(dead_cap, '$', ''), ',', ''), 'M', '') AS FLOAT64)) as salaries_dead_cap_millions
            FROM silver_spotrac_salaries
            GROUP BY 1, 2, 3
        ),
        player_meta AS (
            SELECT * FROM silver_player_metadata
        ),
        fact_long_fallback AS (
            SELECT 
                s.*,
                p.week as week,
                -- YTD Aggregation Window Functions
                COALESCE(SUM(p.games_played) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as games_played,
                SAFE_CAST(COALESCE(SUM(p.games_played) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) AS FLOAT64) / 17.0 as availability_rating,
                COALESCE(SUM(p.total_pass_yds) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_pass_yds,
                COALESCE(SUM(p.total_rush_yds) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_rush_yds,
                COALESCE(SUM(p.total_rec_yds) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_rec_yds,
                COALESCE(SUM(p.total_tds) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_tds,
                COALESCE(SUM(p.total_sacks) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_sacks,
                COALESCE(SUM(p.total_int) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_int,
                COALESCE(pen.total_penalty_count, 0) as total_penalty_count,
                COALESCE(pen.total_penalty_yards, 0) as total_penalty_yards,
                -- Elite Positional Flags for False Positive Suppression
                CASE WHEN s.position = 'QB' THEN 1 ELSE 0 END as is_qb,
                CASE WHEN s.cap_hit_millions >= 25.0 THEN 1 ELSE 0 END as is_elite_tier,
                m.college,
                m.draft_round,
                m.draft_pick,
                m.experience_years
            FROM dedup_contracts s
            LEFT JOIN pfr_agg p ON LOWER(TRIM(CAST(s.player_name AS STRING))) = LOWER(TRIM(CAST(p.player_name AS STRING))) 
                AND s.year = p.year AND s.team = p.team
            LEFT JOIN penalties_agg pen ON s.year = pen.year AND s.team = pen.team
                AND (LOWER(s.player_name) LIKE CONCAT(LOWER(LEFT(pen.player_name_short, 1)), '%') AND LOWER(s.player_name) LIKE CONCAT('%', LOWER(SUBSTRING(pen.player_name_short, 3))))
            LEFT JOIN player_meta m ON LOWER(TRIM(CAST(s.player_name AS STRING))) = LOWER(TRIM(CAST(m.full_name AS STRING)))
        )
        SELECT 
            f.*,
            -- Dynamic YTD Cap Hurdles based on Week Progression (1-17)
            (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week as potential_dead_cap_millions,
            (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week as edce_risk,
            
            -- Fair Market Value against YTD stats
            ( 
                (COALESCE(f.total_tds,0) * 2.0 + (COALESCE(f.total_pass_yds,0) + COALESCE(f.total_rush_yds,0) + COALESCE(f.total_rec_yds,0)) / 100.0) * 1.8 
                + (COALESCE(f.total_sacks,0) * 4.0) + (COALESCE(f.total_int,0) * 5.0) 
              - (COALESCE(f.total_penalty_yards,0) / 10.0) 
            ) / 5.0 as ytd_performance_value,
            
            -- Target A: True Bust Variance (Absolute Dollars)
            CASE 
                WHEN (
                    (COALESCE(f.total_tds,0) * 2.0 + (COALESCE(f.total_pass_yds,0) + COALESCE(f.total_rush_yds,0) + COALESCE(f.total_rec_yds,0)) / 100.0) * 1.8 
                    + (COALESCE(f.total_sacks,0) * 4.0) + (COALESCE(f.total_int,0) * 5.0) 
                  - (COALESCE(f.total_penalty_yards,0) / 10.0) 
                ) / 5.0 > (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week THEN 0.0
                ELSE 
                    ((GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week)
                    - 
                    (( 
                        (COALESCE(f.total_tds,0) * 2.0 + (COALESCE(f.total_pass_yds,0) + COALESCE(f.total_rush_yds,0) + COALESCE(f.total_rec_yds,0)) / 100.0) * 1.8 
                        + (COALESCE(f.total_sacks,0) * 4.0) + (COALESCE(f.total_int,0) * 5.0) 
                      - (COALESCE(f.total_penalty_yards,0) / 10.0) 
                    ) / 5.0) 
            END as true_bust_variance,
            
            -- Target B: Dimensionless Efficiency Ratio (YTD Performance / YTD Cap Hurdle)
            -- Apply LEAST() Winsorization to cap explosive fractions (like backup RBs on minimal deals) at 10.0x ROI
            CASE 
                WHEN (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week <= 0 THEN 1.0
                ELSE 
                    LEAST(
                        ( 
                            (COALESCE(f.total_tds,0) * 2.0 + (COALESCE(f.total_pass_yds,0) + COALESCE(f.total_rush_yds,0) + COALESCE(f.total_rec_yds,0)) / 100.0) * 1.8 
                            + (COALESCE(f.total_sacks,0) * 4.0) + (COALESCE(f.total_int,0) * 5.0) 
                          - (COALESCE(f.total_penalty_yards,0) / 10.0) 
                        ) / 5.0 
                        / 
                        ((GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week)
                    , 10.0)
            END as efficiency_ratio,
            
            -- Target C: Binary Classification (Bust = 1, Success = 0)
            -- If their efficiency_ratio is < 0.70, they are producing less than 70% of their contract's expected value
            CASE 
                WHEN (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week <= 0 THEN 0
                WHEN (
                        (COALESCE(f.total_tds,0) * 2.0 + (COALESCE(f.total_pass_yds,0) + COALESCE(f.total_rush_yds,0) + COALESCE(f.total_rec_yds,0)) / 100.0) * 1.8 
                        + (COALESCE(f.total_sacks,0) * 4.0) + (COALESCE(f.total_int,0) * 5.0) 
                      - (COALESCE(f.total_penalty_yards,0) / 10.0) 
                    ) / 5.0 
                    / 
                    ((GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week) < 0.70 
                THEN 1
                ELSE 0
            END as is_bust_binary
            
        FROM fact_long_fallback f
        LEFT JOIN salary_dead_cap sdc ON LOWER(TRIM(CAST(f.player_name AS STRING))) = LOWER(TRIM(CAST(sdc.player_name AS STRING))) AND f.year = sdc.year AND LOWER(TRIM(CAST(f.team AS STRING))) = LOWER(TRIM(CAST(sdc.team AS STRING)))
        """)
        logger.info("✓ Gold Layer populated: fact_player_efficiency")


def main():
    import argparse
    from datetime import datetime

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--year", type=int, required=False, help="Defaults to current active NFL season"
    )
    parser.add_argument("--skip-gold", action="store_true")
    parser.add_argument("--gold-only", action="store_true")
    args = parser.parse_args()

    # Calculate dynamic NFL year (Rollover in March)
    target_year = args.year
    if not target_year:
        now = datetime.now()
        target_year = now.year if now.month >= 3 else now.year - 1

    with DBManager() as db:
        silver = SilverLayer(db)
        gold = GoldLayer(db)

        if not args.gold_only:
            silver.provision_schemas()
            bronze = BronzeLayer(db)
            bronze.ingest_contracts(target_year)
            silver.ingest_contracts(target_year)
            silver.ingest_pfr(target_year)
            silver.ingest_penalties(target_year)
            silver.ingest_team_cap()
            silver.ingest_team_cap()
            silver.ingest_others()
            silver.ingest_player_metadata()

        if not args.skip_gold or args.gold_only:
            gold.build_fact_player_efficiency()
            # ML Enrichment is now decoupled and run via src/inference.py in the orchestration layer
            # This avoids circular dependencies with FeatureFactory


if __name__ == "__main__":
    main()

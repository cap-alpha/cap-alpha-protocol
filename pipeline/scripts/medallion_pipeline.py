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
from src.spotrac_scraper_v2 import scrape_and_save_player_contracts, scrape_and_save_player_rankings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BRONZE_DIR = get_bronze_dir()

def clean_doubled_name(name):
    if not isinstance(name, str): return name
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
    """Bronze Layer: Raw Data Discovery & Reading."""
    @staticmethod
    def find_files(pattern: str, year: int) -> List[Path]:
        possible_globs = [
            BRONZE_DIR / 'spotrac' / str(year) / f"{pattern}*.csv",
            Path('data/raw') / f"{pattern}_{year}*.csv",
            Path('data_raw_DEPRECATED') / f"{pattern}_{year}*.csv",
            # Handle penalties specific glob
            BRONZE_DIR / 'penalties' / str(year) / f"{pattern}*.csv"
        ]
        
        for g in possible_globs:
            files = list(g.parent.glob(g.name))
            if files:
                # Sort by modification time (newest first) to get latest scrape
                files.sort(key=lambda x: x.stat().st_mtime)
                return [files[-1]]
                
        return []
        # HARDCODED FALLBACK FOR 2025 CONTRACTS (Debug Fix)
        if pattern == "spotrac_player_contracts" and year == 2025:
             fallback = Path("data/raw/spotrac_player_contracts_2025_20260202_181248.csv")
             if fallback.exists():
                 print(f"DEBUG: Using Hardcoded Fallback for {pattern}: {fallback}")
                 return [fallback]
                 
        return []
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
                logger.warning(f"Failed to execute schema statement: {e}. Statement: {sql[:50]}...")

    def ingest_spotrac(self, year: int):
        logger.info(f"SilverLayer: Ingesting Spotrac data for {year}")
        # Try to find file with year in filename first
        files = BronzeLayer.find_files(f"spotrac_player_contracts_{year}", year)
        
        if not files:
             logger.info(f"Missing Spotrac Contracts for {year}. Initiating SCRAPE...")
             try:
                 output_dir = BRONZE_DIR / 'spotrac' / str(year)
                 scrape_and_save_player_contracts(year, output_dir=output_dir)
                 files = BronzeLayer.find_files(f"spotrac_player_contracts_{year}", year)
             except Exception as e:
                 logger.error(f"Scrape failed for contracts {year}: {e}")

        if not files:
             # Fallback to generic search if specific year file not found
             logger.info(f"Specific year file not found, trying generic search...")
             files = BronzeLayer.find_files("spotrac_player_contracts", year)
        
        if files:
            logger.info(f"Loading Spotrac Contracts from: {files[0]}")
            df = pd.read_csv(files[0])
        else:
            logger.info(f"Contracts file missing. Trying Rankings...")
            files = BronzeLayer.find_files("spotrac_player_rankings", year)
            
            if not files:
                logger.info(f"Missing Spotrac Rankings for {year}. Initiating SCRAPE...")
                try:
                    output_dir = BRONZE_DIR / 'spotrac' / str(year)
                    scrape_and_save_player_rankings(year, output_dir=output_dir)
                    files = BronzeLayer.find_files("spotrac_player_rankings", year)
                except Exception as e:
                     logger.error(f"Scrape failed for rankings {year}: {e}")

            if not files:
                logger.warning(f"No Spotrac files found for {year} even after scrape attempt.")
                return

            df = pd.read_csv(files[0])
        
        df['player_name'] = df['player_name'].apply(clean_doubled_name)
        
        # Ensure cap_hit_millions exists
        if 'cap_hit_millions' not in df.columns:
             logger.warning("cap_hit_millions missing. Setting to 0 to avoid massive outliers (do NOT fallback to total_contract_value).")
             df['cap_hit_millions'] = 0.0
        
        df = df.rename(columns={
            'guaranteed_money_millions': 'dead_cap_millions',
        })
        
        required_cols = [
            'cap_hit_millions', 'dead_cap_millions', 'age', 
            'signing_bonus_millions', 'guaranteed_money_millions', 'total_contract_value_millions',
            'base_salary_millions', 'prorated_bonus_millions', 'roster_bonus_millions', 'guaranteed_salary_millions'
        ]
        for col in required_cols:
            if col not in df.columns: df[col] = None

        self.db.execute(f"DELETE FROM silver_spotrac_contracts WHERE year = {year}")
        self.db.execute("""
            INSERT INTO silver_spotrac_contracts (player_name, team, year, position, cap_hit_millions, dead_cap_millions, signing_bonus_millions, guaranteed_money_millions, total_contract_value_millions, age, base_salary_millions, prorated_bonus_millions, roster_bonus_millions, guaranteed_salary_millions)
            SELECT player_name, team, year, position, cap_hit_millions, dead_cap_millions, signing_bonus_millions, guaranteed_money_millions, total_contract_value_millions, age, base_salary_millions, prorated_bonus_millions, roster_bonus_millions, guaranteed_salary_millions FROM df
        """, {"df": df})

        # Salaries
        sal_files = BronzeLayer.find_files("spotrac_player_salaries", year)
        if sal_files:
            df_sal = pd.read_csv(sal_files[0])
            if 'player_name' in df_sal.columns:
                df_sal['player_name'] = df_sal['player_name'].apply(clean_doubled_name)
            # Normalize columns to match schema
            col_map = {
                "dead_money_millions": "dead cap",
                "Dead Cap": "dead cap",
                "DeadCap": "dead cap",
                "dead_cap": "dead cap"
            }
            df_sal = df_sal.rename(columns=col_map)
            
            # Ensure "dead cap" column exists, fill with 0/None if missing
            if "dead cap" not in df_sal.columns:
                 logger.warning(f"Could not find 'dead cap' column in Spotrac Salaries {year}. Columns: {df_sal.columns.tolist()}")
                 df_sal["dead cap"] = "0"

            # Ensure columns exist
            if 'position' not in df_sal.columns:
                 # Try to infer or leave null
                 df_sal['position'] = None
                 
            self.db.execute(f"DELETE FROM silver_spotrac_salaries WHERE year = {year}")
            self.db.execute("""
                INSERT INTO silver_spotrac_salaries (player_name, team, year, position, "dead cap")
                SELECT player_name, team, year, position, "dead cap" FROM df_sal
            """, {"df_sal": df_sal})

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
            f"data_raw_DEPRECATED/pfr/game_logs_{year}.csv"
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
            "Unnamed: 7_level_0_Sk": "Sacks"
        }
        df = df.rename(columns=rename_map)

        # Ensure defensive columns exist
        if 'Sacks' not in df.columns: df['Sacks'] = 0
        if 'Interceptions' not in df.columns: df['Interceptions'] = 0
        
        # Ensure correct types
        numeric_cols = ['Passing_Yds', 'Rushing_Yds', 'Receiving_Yds', 'Passing_TD', 'Rushing_TD', 'Receiving_TD', 'Sacks', 'Interceptions']
        for col in numeric_cols:
             if col in df.columns:
                 df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        self.db.execute(f"DELETE FROM silver_pfr_game_logs WHERE year = {year}")
        self.db.execute("""
            INSERT INTO silver_pfr_game_logs (player_name, team, year, week, game_url, Passing_Yds, Rushing_Yds, Receiving_Yds, Passing_TD, Rushing_TD, Receiving_TD, Sacks, Interceptions)
            SELECT 
                player_name, team, year, week, game_url, 
                Passing_Yds, Rushing_Yds, Receiving_Yds, 
                Passing_TD, Rushing_TD, Receiving_TD,
                Sacks, Interceptions
            FROM df
        """, {"df": df})

    def ingest_penalties(self, year: int):
        logger.info(f"SilverLayer: Ingesting Penalties for {year}")
        files = BronzeLayer.find_files("improved_penalties", year)
        if not files: return
        
        df = pd.read_csv(files[-1])
        city_map = {
            "Houston": "HOU", "Dallas": "DAL", "Kansas City": "KC", "Buffalo": "BUF",
            "Pittsburgh": "PIT", "Denver": "DEN", "Baltimore": "BAL", "New Orleans": "NO",
            "New England": "NE", "Washington": "WAS", "Carolina": "CAR", "Atlanta": "ATL",
            "Indianapolis": "IND", "Minnesota": "MIN", "Las Vegas": "LV", "Detroit": "DET",
            "Green Bay": "GB", "Chicago": "CHI", "New York Jets": "NYJ", "New York Giants": "NYG",
            "San Francisco": "SF", "Tampa Bay": "TB", "Seattle": "SEA", "Miami": "MIA",
            "Jacksonville": "JAX", "Cleveland": "CLE", "Cincinnati": "CIN", "Arizona": "ARI",
            "Philadelphia": "PHI", "Tennessee": "TEN", "Los Angeles Rams": "LAR", "Los Angeles Chargers": "LAC"
        }
        df['team'] = df['team_city'].map(city_map)
        
        self.db.execute(f"DELETE FROM silver_penalties WHERE year = {year}")
        # Explicitly select schema columns to avoid binder errors on extra columns
        self.db.execute("""
            INSERT INTO silver_penalties (player_name_short, team, year, penalty_count, penalty_yards)
            SELECT player_name_short, team, year, penalty_count, penalty_yards FROM df
        """, {"df": df})

    def ingest_team_cap(self):
        logger.info("SilverLayer: Ingesting Team Cap data")
        dead_money_dir = BRONZE_DIR / "dead_money"
        files = list(dead_money_dir.rglob("team_cap_*.csv"))
        if not files: return
        
        dfs = [pd.read_csv(f) for f in files]
        df = pd.concat(dfs)
        self.db.execute("CREATE OR REPLACE TABLE silver_team_cap AS SELECT DISTINCT * FROM df", {"df": df})

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
             self.db.execute("CREATE OR REPLACE TABLE silver_pfr_draft_history AS SELECT * FROM df_draft", {"df_draft": df_draft})
             
    def ingest_player_metadata(self):
        logger.info("SilverLayer: Ingesting player metadata")
        meta_file = Path("data/raw/player_metadata.csv")
        if meta_file.exists():
            df_meta = pd.read_csv(meta_file)
            # Normalize column names if needed, assume match for now
            self.db.execute("CREATE OR REPLACE TABLE silver_player_metadata AS SELECT * FROM df_meta", {"df_meta": df_meta})

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
                SUM(TRY_CAST(Passing_Yds AS FLOAT)) as total_pass_yds,
                SUM(TRY_CAST(Rushing_Yds AS FLOAT)) as total_rush_yds,
                SUM(TRY_CAST(Receiving_Yds AS FLOAT)) as total_rec_yds,
                SUM(TRY_CAST(Passing_TD AS INT) + TRY_CAST(Rushing_TD AS INT) + TRY_CAST(Receiving_TD AS INT)) as total_tds,
                -- Defensive Aggregations
                SUM(TRY_CAST(Sacks AS FLOAT)) as total_sacks,
                SUM(TRY_CAST(Interceptions AS FLOAT)) as total_int
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
                    WHEN LENGTH(s.player_name) % 2 = 0 AND SUBSTRING(s.player_name, 1, CAST(LENGTH(s.player_name)/2 AS BIGINT)) = SUBSTRING(s.player_name, CAST(LENGTH(s.player_name)/2 + 1 AS BIGINT))
                    THEN SUBSTRING(s.player_name, 1, CAST(LENGTH(s.player_name)/2 AS BIGINT))
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
              ON LOWER(TRIM(CAST(s.player_name AS VARCHAR))) = LOWER(TRIM(CAST(r.player_name AS VARCHAR)))
              AND s.year = r.year
            GROUP BY 1, 2, 3
        ),
        salary_dead_cap AS (
            SELECT 
                player_name, team, year,
                MAX(TRY_CAST(REPLACE(REPLACE(REPLACE("dead cap", '$', ''), ',', ''), 'M', '') AS FLOAT)) as salaries_dead_cap_millions
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
                CAST(COALESCE(SUM(p.games_played) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) AS FLOAT) / 17.0 as availability_rating,
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
            LEFT JOIN pfr_agg p ON LOWER(TRIM(CAST(s.player_name AS VARCHAR))) = LOWER(TRIM(CAST(p.player_name AS VARCHAR))) 
                AND s.year = p.year AND s.team = p.team
            LEFT JOIN penalties_agg pen ON s.year = pen.year AND s.team = pen.team
                AND (LOWER(s.player_name) LIKE LOWER(LEFT(pen.player_name_short, 1)) || '%' AND LOWER(s.player_name) LIKE '%' || LOWER(SUBSTRING(pen.player_name_short, 3)))
            LEFT JOIN player_meta m ON LOWER(TRIM(CAST(s.player_name AS VARCHAR))) = LOWER(TRIM(CAST(m.full_name AS VARCHAR)))
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
        LEFT JOIN salary_dead_cap sdc ON LOWER(TRIM(CAST(f.player_name AS VARCHAR))) = LOWER(TRIM(CAST(sdc.player_name AS VARCHAR))) AND f.year = sdc.year AND LOWER(TRIM(CAST(f.team AS VARCHAR))) = LOWER(TRIM(CAST(sdc.team AS VARCHAR)))
        """)
        logger.info("✓ Gold Layer populated: fact_player_efficiency")

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--skip-gold", action="store_true")
    parser.add_argument("--gold-only", action="store_true")
    args = parser.parse_args()

    with DBManager() as db:
        silver = SilverLayer(db)
        gold = GoldLayer(db)

        if not args.gold_only:
            silver.provision_schemas()
            silver.ingest_spotrac(args.year)
            silver.ingest_pfr(args.year)
            silver.ingest_penalties(args.year)
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

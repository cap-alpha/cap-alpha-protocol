"""
Incremental Gold Layer Refresh — SP18.5-3

Replaces the full CREATE OR REPLACE TABLE rebuild of fact_player_efficiency
with a targeted re-computation of only the (player_name, year, team) rows
whose upstream Silver data changed since the last Gold build.

Design
------
- gold_build_watermark table stores the last build timestamp per mart.
- On each incremental run:
  1. Load last_built_at from gold_build_watermark for fact_player_efficiency.
  2. Query silver_spotrac_contracts for rows where effective_start_date > last_built_at.
  3. Collect the distinct (player_name, year, team) keys that changed.
  4. DELETE those keys from fact_player_efficiency.
  5. Re-INSERT only those keys using the full aggregation SQL (scoped to the key set).
  6. Upsert the watermark to NOW().
- --full-refresh bypasses the watermark and rebuilds everything (used after schema changes
  or initial deployment).

Limitations / known gaps (see SP18.5-1 audit for the full list)
----------------------------------------------------------------
- Only silver_spotrac_contracts has effective_start_date today. When other Silver tables
  (pfr_game_logs, penalties, player_metadata) gain SCD2 columns, expand
  _find_changed_keys() to union changes from all sources.
- Rebuild scope is (player_name, year, team): a position/team change triggers a full
  player-year re-computation, which is correct and safe.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import pandas as pd

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

_WATERMARK_TABLE = "gold_build_watermark"
_TARGET_MART = "fact_player_efficiency"


class IncrementalGoldRefresh:
    """
    Manages incremental delta refreshes for Gold/fact tables.

    Parameters
    ----------
    db : DBManager
        Open BigQuery connection.
    """

    def __init__(self, db: DBManager):
        self.db = db
        self._ensure_watermark_table()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self, full_refresh: bool = False) -> dict:
        """
        Entry point: run an incremental (or full) refresh of fact_player_efficiency.

        Parameters
        ----------
        full_refresh : bool
            If True, rebuild the entire mart from scratch (ignores watermark).

        Returns
        -------
        dict with keys: build_type, rows_affected, changed_keys (list of tuples)
        """
        if full_refresh:
            logger.info("IncrementalGoldRefresh: Running FULL refresh of fact_player_efficiency.")
            self._full_rebuild()
            count = self._count_mart()
            self._upsert_watermark("full", count)
            return {"build_type": "full", "rows_affected": count, "changed_keys": []}

        watermark = self._load_watermark()
        logger.info(
            f"IncrementalGoldRefresh: Last build at {watermark}. "
            "Finding changed Silver keys..."
        )

        changed_keys = self._find_changed_keys(since=watermark)

        if not changed_keys:
            logger.info("IncrementalGoldRefresh: No Silver changes detected. Skipping Gold rebuild.")
            return {"build_type": "incremental", "rows_affected": 0, "changed_keys": []}

        logger.info(
            f"IncrementalGoldRefresh: {len(changed_keys)} changed (player_name, year, team) "
            "combinations detected. Rebuilding affected Gold rows..."
        )

        rows_affected = self._rebuild_keys(changed_keys)
        self._upsert_watermark("incremental", rows_affected)

        logger.info(
            f"IncrementalGoldRefresh: Complete. {rows_affected} rows refreshed."
        )
        return {
            "build_type": "incremental",
            "rows_affected": rows_affected,
            "changed_keys": changed_keys,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_watermark(self) -> Optional[datetime]:
        """Returns the last successful build timestamp, or epoch if no row exists."""
        try:
            row = self.db.execute(
                f"SELECT last_built_at FROM `{self.db.project_id}.{self.db.dataset_id}.{_WATERMARK_TABLE}` "
                f"WHERE mart_name = '{_TARGET_MART}' LIMIT 1"
            ).fetchone()
            if row and row[0]:
                return pd.Timestamp(row[0]).to_pydatetime()
        except Exception as e:
            logger.warning(f"Could not load watermark: {e}")
        # Default: epoch — treat everything as new
        return datetime(1970, 1, 1, tzinfo=timezone.utc)

    def _find_changed_keys(
        self, since: Optional[datetime]
    ) -> List[Tuple[str, int, str]]:
        """
        Returns (player_name, year, team) tuples with Silver changes since `since`.

        Currently scoped to silver_spotrac_contracts only (the only SCD2 table).
        When silver_pfr_game_logs gains effective_start_date, add a UNION here.
        """
        since_ts = since.isoformat() if since else "1970-01-01T00:00:00+00:00"

        query = f"""
        SELECT DISTINCT player_name, year, team
        FROM `{self.db.project_id}.{self.db.dataset_id}.silver_spotrac_contracts`
        WHERE effective_start_date > TIMESTAMP('{since_ts}')
          AND is_current = TRUE
          AND player_name IS NOT NULL
          AND team IS NOT NULL
        ORDER BY year, player_name
        """
        try:
            df = self.db.fetch_df(query)
            if df.empty:
                return []
            return list(df.itertuples(index=False, name=None))
        except Exception as e:
            logger.warning(f"_find_changed_keys failed: {e}")
            return []

    def _rebuild_keys(
        self, changed_keys: List[Tuple[str, int, str]]
    ) -> int:
        """
        Deletes Gold rows for the changed keys and re-inserts from Silver.
        Uses a temporary staging table to avoid row-by-row round-trips.
        """
        keys_df = pd.DataFrame(
            changed_keys, columns=["player_name", "year", "team"]
        )

        # Write keys to a temp staging table for use in DELETE + INSERT
        stg_keys = "gold_refresh_keys_stg"
        self.db.append_dataframe_to_table(keys_df, stg_keys)
        full_stg = f"{self.db.project_id}.{self.db.dataset_id}.{stg_keys}"
        full_mart = f"{self.db.project_id}.{self.db.dataset_id}.{_TARGET_MART}"

        try:
            # Step 1: Delete stale Gold rows for the changed keys
            delete_sql = f"""
            DELETE FROM `{full_mart}` T
            WHERE EXISTS (
                SELECT 1 FROM `{full_stg}` S
                WHERE LOWER(TRIM(T.player_name)) = LOWER(TRIM(S.player_name))
                  AND T.year  = S.year
                  AND T.team  = S.team
            )
            """
            self.db.execute(delete_sql)

            # Step 2: Re-insert the affected rows from the standard Gold aggregation SQL,
            # filtered to only the changed keys.
            insert_sql = f"""
            INSERT INTO `{full_mart}`
            WITH pfr_agg AS (
                SELECT
                    player_name, team, year, week,
                    COUNT(DISTINCT game_url) as games_played,
                    SUM(SAFE_CAST(Passing_Yds AS FLOAT64))   as total_pass_yds,
                    SUM(SAFE_CAST(Rushing_Yds AS FLOAT64))   as total_rush_yds,
                    SUM(SAFE_CAST(Receiving_Yds AS FLOAT64)) as total_rec_yds,
                    SUM(
                        SAFE_CAST(Passing_TD AS INT64) +
                        SAFE_CAST(Rushing_TD AS INT64) +
                        SAFE_CAST(Receiving_TD AS INT64)
                    ) as total_tds,
                    SUM(SAFE_CAST(Sacks AS FLOAT64))         as total_sacks,
                    SUM(SAFE_CAST(Interceptions AS FLOAT64)) as total_int
                FROM `{self.db.project_id}.{self.db.dataset_id}.silver_pfr_game_logs`
                GROUP BY 1, 2, 3, 4
            ),
            penalties_agg AS (
                SELECT
                    player_name_short, team, year,
                    SUM(penalty_count) as total_penalty_count,
                    SUM(penalty_yards) as total_penalty_yards
                FROM `{self.db.project_id}.{self.db.dataset_id}.silver_penalties`
                GROUP BY 1, 2, 3
            ),
            changed_contracts AS (
                -- Scope to only the changed keys
                SELECT s.*
                FROM `{self.db.project_id}.{self.db.dataset_id}.silver_spotrac_contracts` s
                JOIN `{full_stg}` k
                  ON LOWER(TRIM(s.player_name)) = LOWER(TRIM(k.player_name))
                 AND s.year = k.year
                 AND s.team = k.team
                WHERE s.is_current = TRUE
            ),
            dedup_contracts AS (
                SELECT
                    player_name, team, year,
                    MAX(position)                      as position,
                    SUM(cap_hit_millions)              as cap_hit_millions,
                    SUM(dead_cap_millions)             as dead_cap_millions,
                    MAX(signing_bonus_millions)        as signing_bonus_millions,
                    MAX(guaranteed_money_millions)     as guaranteed_money_millions,
                    MAX(base_salary_millions)          as base_salary_millions,
                    MAX(prorated_bonus_millions)       as prorated_bonus_millions,
                    MAX(roster_bonus_millions)         as roster_bonus_millions,
                    MAX(guaranteed_salary_millions)    as guaranteed_salary_millions,
                    MAX(total_contract_value_millions) as total_contract_value_millions,
                    MAX(age)                           as age
                FROM changed_contracts
                GROUP BY 1, 2, 3
            ),
            salary_dead_cap AS (
                SELECT
                    player_name, team, year,
                    MAX(SAFE_CAST(
                        REPLACE(REPLACE(REPLACE(dead_cap, '$', ''), ',', ''), 'M', '')
                    AS FLOAT64)) as salaries_dead_cap_millions
                FROM `{self.db.project_id}.{self.db.dataset_id}.silver_spotrac_salaries`
                GROUP BY 1, 2, 3
            ),
            player_meta AS (
                SELECT * FROM `{self.db.project_id}.{self.db.dataset_id}.silver_player_metadata`
            ),
            fact_long AS (
                SELECT
                    s.*,
                    p.week,
                    COALESCE(SUM(p.games_played) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as games_played,
                    SAFE_CAST(COALESCE(SUM(p.games_played) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) AS FLOAT64) / 17.0 as availability_rating,
                    COALESCE(SUM(p.total_pass_yds) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_pass_yds,
                    COALESCE(SUM(p.total_rush_yds) OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_rush_yds,
                    COALESCE(SUM(p.total_rec_yds)  OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_rec_yds,
                    COALESCE(SUM(p.total_tds)      OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_tds,
                    COALESCE(SUM(p.total_sacks)    OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_sacks,
                    COALESCE(SUM(p.total_int)      OVER (PARTITION BY s.player_name, s.year ORDER BY p.week), 0) as total_int,
                    COALESCE(pen.total_penalty_count, 0)  as total_penalty_count,
                    COALESCE(pen.total_penalty_yards, 0)  as total_penalty_yards,
                    CASE WHEN s.position = 'QB' THEN 1 ELSE 0 END as is_qb,
                    CASE WHEN s.cap_hit_millions >= 25.0 THEN 1 ELSE 0 END as is_elite_tier,
                    m.college,
                    m.draft_round,
                    m.draft_pick,
                    m.experience_years
                FROM dedup_contracts s
                LEFT JOIN pfr_agg p
                  ON LOWER(TRIM(s.player_name)) = LOWER(TRIM(p.player_name))
                 AND s.year = p.year AND s.team = p.team
                LEFT JOIN penalties_agg pen
                  ON s.year = pen.year AND s.team = pen.team
                 AND LOWER(s.player_name) LIKE CONCAT(LOWER(LEFT(pen.player_name_short, 1)), '%')
                 AND LOWER(s.player_name) LIKE CONCAT('%', LOWER(SUBSTRING(pen.player_name_short, 3)))
                LEFT JOIN player_meta m
                  ON LOWER(TRIM(s.player_name)) = LOWER(TRIM(m.full_name))
            )
            SELECT
                f.*,
                (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week as potential_dead_cap_millions,
                (GREATEST(COALESCE(sdc.salaries_dead_cap_millions, 0), f.dead_cap_millions, COALESCE(f.signing_bonus_millions, 0) * 2.0) / 17.0) * f.week as edce_risk,
                (
                    (COALESCE(f.total_tds,0)*2.0 + (COALESCE(f.total_pass_yds,0)+COALESCE(f.total_rush_yds,0)+COALESCE(f.total_rec_yds,0))/100.0)*1.8
                    + COALESCE(f.total_sacks,0)*4.0 + COALESCE(f.total_int,0)*5.0
                    - COALESCE(f.total_penalty_yards,0)/10.0
                ) / 5.0 as ytd_performance_value,
                CASE
                    WHEN (
                        (COALESCE(f.total_tds,0)*2.0 + (COALESCE(f.total_pass_yds,0)+COALESCE(f.total_rush_yds,0)+COALESCE(f.total_rec_yds,0))/100.0)*1.8
                        + COALESCE(f.total_sacks,0)*4.0 + COALESCE(f.total_int,0)*5.0
                        - COALESCE(f.total_penalty_yards,0)/10.0
                    ) / 5.0 > (GREATEST(COALESCE(sdc.salaries_dead_cap_millions,0),f.dead_cap_millions,COALESCE(f.signing_bonus_millions,0)*2.0)/17.0)*f.week
                    THEN 0.0
                    ELSE (GREATEST(COALESCE(sdc.salaries_dead_cap_millions,0),f.dead_cap_millions,COALESCE(f.signing_bonus_millions,0)*2.0)/17.0)*f.week
                         - (
                             (COALESCE(f.total_tds,0)*2.0 + (COALESCE(f.total_pass_yds,0)+COALESCE(f.total_rush_yds,0)+COALESCE(f.total_rec_yds,0))/100.0)*1.8
                             + COALESCE(f.total_sacks,0)*4.0 + COALESCE(f.total_int,0)*5.0
                             - COALESCE(f.total_penalty_yards,0)/10.0
                           ) / 5.0
                END as true_bust_variance,
                CASE
                    WHEN (GREATEST(COALESCE(sdc.salaries_dead_cap_millions,0),f.dead_cap_millions,COALESCE(f.signing_bonus_millions,0)*2.0)/17.0)*f.week <= 0 THEN 1.0
                    ELSE LEAST(
                        (
                            (COALESCE(f.total_tds,0)*2.0 + (COALESCE(f.total_pass_yds,0)+COALESCE(f.total_rush_yds,0)+COALESCE(f.total_rec_yds,0))/100.0)*1.8
                            + COALESCE(f.total_sacks,0)*4.0 + COALESCE(f.total_int,0)*5.0
                            - COALESCE(f.total_penalty_yards,0)/10.0
                        ) / 5.0
                        / ((GREATEST(COALESCE(sdc.salaries_dead_cap_millions,0),f.dead_cap_millions,COALESCE(f.signing_bonus_millions,0)*2.0)/17.0)*f.week)
                    , 10.0)
                END as efficiency_ratio,
                CASE
                    WHEN (GREATEST(COALESCE(sdc.salaries_dead_cap_millions,0),f.dead_cap_millions,COALESCE(f.signing_bonus_millions,0)*2.0)/17.0)*f.week <= 0 THEN 0
                    WHEN (
                            (COALESCE(f.total_tds,0)*2.0 + (COALESCE(f.total_pass_yds,0)+COALESCE(f.total_rush_yds,0)+COALESCE(f.total_rec_yds,0))/100.0)*1.8
                            + COALESCE(f.total_sacks,0)*4.0 + COALESCE(f.total_int,0)*5.0
                            - COALESCE(f.total_penalty_yards,0)/10.0
                          ) / 5.0
                          / ((GREATEST(COALESCE(sdc.salaries_dead_cap_millions,0),f.dead_cap_millions,COALESCE(f.signing_bonus_millions,0)*2.0)/17.0)*f.week) < 0.70
                    THEN 1
                    ELSE 0
                END as is_bust_binary
            FROM fact_long f
            LEFT JOIN salary_dead_cap sdc
              ON LOWER(TRIM(f.player_name)) = LOWER(TRIM(sdc.player_name))
             AND f.year = sdc.year
             AND LOWER(TRIM(f.team)) = LOWER(TRIM(sdc.team))
            """
            self.db.execute(insert_sql)

            # Count rows inserted (approximation via changed keys × avg weeks)
            rows_check = self.db.execute(
                f"""
                SELECT COUNT(*) FROM `{full_mart}` T
                JOIN `{full_stg}` S
                  ON LOWER(TRIM(T.player_name)) = LOWER(TRIM(S.player_name))
                 AND T.year = S.year AND T.team = S.team
                """
            ).fetchone()
            rows_affected = int(rows_check[0]) if rows_check else len(changed_keys)

        finally:
            self.db.execute(f"DROP TABLE IF EXISTS `{full_stg}`;")

        return rows_affected

    def _full_rebuild(self) -> None:
        """Full CREATE OR REPLACE rebuild — delegates to the existing GoldLayer logic."""
        # Import inline to avoid circular dependency with medallion_pipeline
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
        try:
            from medallion_pipeline import GoldLayer
            gold = GoldLayer(self.db)
            gold.build_fact_player_efficiency()
        except Exception as e:
            logger.error(f"Full rebuild failed: {e}")
            raise

    def _count_mart(self) -> int:
        try:
            row = self.db.execute(
                f"SELECT COUNT(*) FROM `{self.db.project_id}.{self.db.dataset_id}.{_TARGET_MART}`"
            ).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _upsert_watermark(self, build_type: str, rows_affected: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        full_wm = f"{self.db.project_id}.{self.db.dataset_id}.{_WATERMARK_TABLE}"

        merge_sql = f"""
        MERGE `{full_wm}` T
        USING (SELECT '{_TARGET_MART}' as mart_name) S ON T.mart_name = S.mart_name
        WHEN MATCHED THEN UPDATE SET
            T.last_built_at    = TIMESTAMP('{now}'),
            T.build_type       = '{build_type}',
            T.rows_affected    = {rows_affected},
            T.system_ingest_ts = CURRENT_TIMESTAMP()
        WHEN NOT MATCHED THEN INSERT
            (mart_name, last_built_at, build_type, rows_affected, system_ingest_ts)
            VALUES ('{_TARGET_MART}', TIMESTAMP('{now}'), '{build_type}', {rows_affected}, CURRENT_TIMESTAMP());
        """
        try:
            self.db.execute(merge_sql)
        except Exception as e:
            logger.warning(f"Could not upsert watermark: {e}")

    def _ensure_watermark_table(self) -> None:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS `{self.db.project_id}.{self.db.dataset_id}.{_WATERMARK_TABLE}`
        (
          mart_name         STRING    NOT NULL,
          last_built_at     TIMESTAMP NOT NULL,
          build_type        STRING    NOT NULL,
          rows_affected     INT64,
          system_ingest_ts  TIMESTAMP NOT NULL
        )
        CLUSTER BY mart_name;
        """
        try:
            self.db.execute(ddl)
        except Exception as e:
            logger.debug(f"_ensure_watermark_table: {e}")

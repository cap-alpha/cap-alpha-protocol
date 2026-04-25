"""
Asset Pre-computation (SP24-3, GH-#88)

Shifts heavy statistical aggregations from the API/frontend layer into the
pipeline so they run once at ingestion time and are served as pre-built Gold
tables.

Pre-computed assets:
  gold_layer.team_cap_summary   — per-team cap totals, risk cap, player counts
  gold_layer.player_risk_tiers  — enriched player rows with risk_tier label

Both tables are fully replaced on each daily run (WRITE_TRUNCATE semantics via
CREATE OR REPLACE TABLE) so consumers always see a consistent snapshot.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

FACT_TABLE = "nfl_dead_money.fact_player_efficiency"
TEAM_CAP_TABLE = "gold_layer.team_cap_summary"
RISK_TIERS_TABLE = "gold_layer.player_risk_tiers"

# Thresholds mirror what the frontend currently hard-codes
RISK_SAFE_MAX = 0.2
RISK_HIGH_MIN = 0.8
RISK_CAP_THRESHOLD = 0.7


class AssetPrecomputer:
    """Pre-computes Gold-layer summary tables from fact_player_efficiency."""

    def __init__(self, db: Optional[DBManager] = None):
        self._close_db = db is None
        self.db = db if db is not None else DBManager()

    def close(self):
        if self._close_db:
            self.db.close()

    # ------------------------------------------------------------------
    # team_cap_summary
    # ------------------------------------------------------------------

    def compute_team_cap_summary(self) -> int:
        """
        Pre-aggregates per-team cap metrics from fact_player_efficiency.

        Replaces gold_layer.team_cap_summary with a fresh snapshot.
        Returns the number of team rows written.
        """
        project_id = os.environ.get("GCP_PROJECT_ID")
        now = datetime.now(timezone.utc).isoformat()

        sql = f"""
            CREATE OR REPLACE TABLE `{project_id}.{TEAM_CAP_TABLE}` AS
            SELECT
                team,
                COUNT(*)                                                  AS player_count,
                ROUND(SUM(cap_hit_millions), 2)                           AS total_cap,
                ROUND(SUM(CASE WHEN risk_score > {RISK_CAP_THRESHOLD}
                               THEN cap_hit_millions ELSE 0 END), 2)      AS risk_cap,
                ROUND(AVG(age), 1)                                        AS avg_age,
                ROUND(AVG(risk_score), 4)                                 AS avg_risk_score,
                ROUND(SUM(dead_cap_millions), 2)                          AS total_dead_cap,
                ROUND(SUM(fair_market_value), 2)                          AS total_surplus_value,
                TIMESTAMP('{now}')                                        AS computed_at
            FROM `{project_id}.{FACT_TABLE}`
            WHERE cap_hit_millions IS NOT NULL
              AND cap_hit_millions > 0
              AND team IS NOT NULL
            GROUP BY team
            ORDER BY total_cap DESC
        """
        self.db.execute(sql)

        count_df = self.db.fetch_df(
            f"SELECT COUNT(*) AS n FROM `{project_id}.{TEAM_CAP_TABLE}`"
        )
        n = int(count_df.iloc[0]["n"])
        logger.info(f"[asset_precompute] team_cap_summary: {n} teams written")
        return n

    # ------------------------------------------------------------------
    # player_risk_tiers
    # ------------------------------------------------------------------

    def compute_player_risk_tiers(self) -> int:
        """
        Enriches fact_player_efficiency with a pre-computed risk_tier label
        (SAFE / MODERATE / HIGH) so the frontend can filter without JavaScript.

        Only the most-recent contract row per player is kept (mirrors the
        ROW_NUMBER() de-dup currently done at query time by the web server action).
        Returns the number of player rows written.
        """
        project_id = os.environ.get("GCP_PROJECT_ID")
        now = datetime.now(timezone.utc).isoformat()

        sql = f"""
            CREATE OR REPLACE TABLE `{project_id}.{RISK_TIERS_TABLE}` AS
            WITH ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY player_name
                        ORDER BY year DESC
                    ) AS _rn
                FROM `{project_id}.{FACT_TABLE}`
                WHERE cap_hit_millions IS NOT NULL
                  AND cap_hit_millions > 0
            )
            SELECT
                player_name,
                team,
                position,
                year,
                age,
                games_played,
                cap_hit_millions,
                dead_cap_millions,
                risk_score,
                fair_market_value,
                edce_risk,
                CASE
                    WHEN risk_score < {RISK_SAFE_MAX}  THEN 'SAFE'
                    WHEN risk_score >= {RISK_HIGH_MIN} THEN 'HIGH'
                    ELSE 'MODERATE'
                END                                AS risk_tier,
                TIMESTAMP('{now}')                 AS computed_at
            FROM ranked
            WHERE _rn = 1
            ORDER BY cap_hit_millions DESC
        """
        self.db.execute(sql)

        count_df = self.db.fetch_df(
            f"SELECT COUNT(*) AS n FROM `{project_id}.{RISK_TIERS_TABLE}`"
        )
        n = int(count_df.iloc[0]["n"])
        logger.info(f"[asset_precompute] player_risk_tiers: {n} players written")
        return n

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """
        Runs all pre-computation steps in dependency order.
        Returns a summary dict with row counts for observability.
        """
        results = {}
        errors = {}

        for name, fn in [
            ("team_cap_summary", self.compute_team_cap_summary),
            ("player_risk_tiers", self.compute_player_risk_tiers),
        ]:
            try:
                results[name] = fn()
            except Exception as exc:
                logger.error(f"[asset_precompute] {name} failed: {exc}")
                errors[name] = str(exc)

        if errors:
            raise RuntimeError(
                f"Asset pre-computation failed for: {list(errors.keys())}. "
                f"Details: {errors}"
            )

        return results


def run_precompute(db: Optional[DBManager] = None) -> dict:
    """Module-level entry point used by run_daily.py."""
    precomputer = AssetPrecomputer(db=db)
    try:
        return precomputer.run_all()
    finally:
        precomputer.close()

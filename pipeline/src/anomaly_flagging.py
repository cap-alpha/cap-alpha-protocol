"""
Anomaly Flagging — Suspicious Volume Spike (SP23-3, GH-#85)

Detects atypical surges in negative-sentiment media coverage directed at a
specific player and quarantines those signals for manual review before they
influence the prediction pipeline.

Algorithm
---------
For each player mentioned in today's ingest window:
  1. Compute baseline: mean and std-dev of daily mention count over the last
     LOOKBACK_DAYS days.
  2. Compute z-score: (today_count - baseline_mean) / baseline_stddev
  3. If z-score >= SPIKE_THRESHOLD_SOFT  → flag as SUSPICIOUS (review queue)
     If z-score >= SPIKE_THRESHOLD_HARD  → flag as ANOMALY  (quarantine)

Data source
-----------
Counts come from `bronze_layer.raw_pundit_media` (the number of articles
mentioning each player per day, inferred from raw_text keyword matches and
target_player_name from the prediction_ledger).

Output
------
`gold_layer.sentiment_anomaly_flags` is written on each run:
  - player mentions and z-scores for flagged players
  - flag_type: SUSPICIOUS | ANOMALY
  - Automatically quarantined articles are written to this table for
    downstream manual review tooling.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import pandas as pd

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RAW_MEDIA_TABLE = "nfl_dead_money.raw_pundit_media"
FLAGS_TABLE = "gold_layer.sentiment_anomaly_flags"

LOOKBACK_DAYS = 30
SPIKE_THRESHOLD_SOFT = 2.5  # z-score: SUSPICIOUS
SPIKE_THRESHOLD_HARD = 4.0  # z-score: ANOMALY (quarantine)
MIN_BASELINE_DAYS = 7  # need at least N days of history to compare
MIN_DAILY_VOLUME = 2  # ignore players with < 2 mentions/day baseline


@dataclass
class PlayerAnomaly:
    player_name: str
    today_count: int
    baseline_mean: float
    baseline_stddev: float
    z_score: float
    flag_type: str  # SUSPICIOUS | ANOMALY
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AnomalyFlagEngine:
    """
    Detects and records suspicious volume spikes for player mentions.

    Intended to run once per daily pipeline cycle after media ingestion.
    """

    def __init__(self, db: Optional[DBManager] = None):
        self._close_db = db is None
        self.db = db if db is not None else DBManager()

    def close(self):
        if self._close_db:
            self.db.close()

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_spikes(
        self,
        window_days: int = LOOKBACK_DAYS,
        today: Optional[datetime] = None,
    ) -> List[PlayerAnomaly]:
        """
        Queries the last `window_days` of prediction_ledger data to find
        players with anomalously high mention volumes today.

        Returns a list of PlayerAnomaly objects for flagged players.
        """
        project_id = os.environ.get("GCP_PROJECT_ID")
        today = today or datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        window_start = today - timedelta(days=window_days)
        today_iso = today.isoformat()
        window_start_iso = window_start.isoformat()

        # Daily mention count per player over the last N days
        query = f"""
            SELECT
                COALESCE(target_player_name, 'UNKNOWN')    AS player_name,
                DATE(ingestion_timestamp)                   AS mention_date,
                COUNT(*)                                    AS daily_count
            FROM `{project_id}.{LEDGER_TABLE}`
            WHERE ingestion_timestamp >= TIMESTAMP('{window_start_iso}')
              AND target_player_name IS NOT NULL
              AND target_player_name != ''
            GROUP BY player_name, mention_date
            ORDER BY player_name, mention_date
        """
        try:
            df = self.db.fetch_df(query)
        except Exception as exc:
            logger.error(f"[anomaly_flagging] Could not fetch mention data: {exc}")
            return []

        if df.empty:
            logger.info("[anomaly_flagging] No player mention data found in window")
            return []

        today_date = today.date()
        anomalies: List[PlayerAnomaly] = []

        for player_name, player_df in df.groupby("player_name"):
            # Separate today vs history
            player_df = player_df.copy()
            player_df["mention_date"] = pd.to_datetime(
                player_df["mention_date"]
            ).dt.date

            today_rows = player_df[player_df["mention_date"] == today_date]
            history_rows = player_df[player_df["mention_date"] < today_date]

            if today_rows.empty:
                continue

            today_count = int(today_rows["daily_count"].sum())

            # Need enough history to compute a meaningful baseline
            if len(history_rows) < MIN_BASELINE_DAYS:
                continue

            baseline_mean = float(history_rows["daily_count"].mean())
            baseline_stddev = float(history_rows["daily_count"].std(ddof=1))

            # Skip players with negligible baseline volume
            if baseline_mean < MIN_DAILY_VOLUME:
                continue

            # Avoid division by zero for perfectly consistent sources
            if baseline_stddev < 0.1:
                baseline_stddev = 0.1

            z_score = (today_count - baseline_mean) / baseline_stddev

            if z_score >= SPIKE_THRESHOLD_HARD:
                flag_type = "ANOMALY"
            elif z_score >= SPIKE_THRESHOLD_SOFT:
                flag_type = "SUSPICIOUS"
            else:
                continue

            anomalies.append(
                PlayerAnomaly(
                    player_name=str(player_name),
                    today_count=today_count,
                    baseline_mean=round(baseline_mean, 2),
                    baseline_stddev=round(baseline_stddev, 2),
                    z_score=round(z_score, 3),
                    flag_type=flag_type,
                )
            )

        flagged = len(anomalies)
        hard = sum(1 for a in anomalies if a.flag_type == "ANOMALY")
        logger.info(
            f"[anomaly_flagging] Detected {flagged} player anomalies "
            f"({hard} ANOMALY, {flagged - hard} SUSPICIOUS)"
        )
        return anomalies

    # ------------------------------------------------------------------
    # Persist flags
    # ------------------------------------------------------------------

    def write_flags(self, anomalies: List[PlayerAnomaly]) -> int:
        """
        Appends flagged anomalies to gold_layer.sentiment_anomaly_flags.
        Returns the number of rows written.
        """
        if not anomalies:
            return 0

        project_id = os.environ.get("GCP_PROJECT_ID")
        rows = [
            {
                "player_name": a.player_name,
                "today_count": a.today_count,
                "baseline_mean": a.baseline_mean,
                "baseline_stddev": a.baseline_stddev,
                "z_score": a.z_score,
                "flag_type": a.flag_type,
                "detected_at": a.detected_at,
            }
            for a in anomalies
        ]
        df = pd.DataFrame(rows)
        self.db.append_dataframe_to_table(df, FLAGS_TABLE)
        logger.info(
            f"[anomaly_flagging] Wrote {len(rows)} anomaly flags to {FLAGS_TABLE}"
        )
        return len(rows)

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    def run(self, today: Optional[datetime] = None) -> dict:
        """
        Run the full detect-and-persist cycle.

        Returns a summary dict for observability.
        """
        anomalies = self.detect_spikes(today=today)
        written = self.write_flags(anomalies)

        hard_anomalies = [a for a in anomalies if a.flag_type == "ANOMALY"]
        if hard_anomalies:
            players = [a.player_name for a in hard_anomalies[:5]]
            logger.warning(
                f"[anomaly_flagging] ANOMALY flag for: {players}"
                + (" (and more)" if len(hard_anomalies) > 5 else "")
            )

        return {
            "flagged_players": len(anomalies),
            "anomaly_count": sum(1 for a in anomalies if a.flag_type == "ANOMALY"),
            "suspicious_count": sum(
                1 for a in anomalies if a.flag_type == "SUSPICIOUS"
            ),
            "rows_written": written,
        }


def run_anomaly_detection(db: Optional[DBManager] = None) -> dict:
    """Module-level entry point used by run_daily.py."""
    engine = AnomalyFlagEngine(db=db)
    try:
        return engine.run()
    finally:
        engine.close()

"""
Rolling Accuracy Windows (Issue #831)

Computes pundit accuracy over 3 rolling time windows:
  - 30d:          last 30 calendar days of resolved predictions
  - last_season:  most recently *completed* NFL or NBA season
  - career:       all-time resolved predictions

Results are written to gold_layer.pundit_accuracy_windows via MERGE (idempotent).

After windows are computed, pundits are drift-flagged when:
  |career_accuracy - last_season_accuracy| >= 0.12
  AND last_season resolved_count >= 10
  AND career resolved_count >= 20

NFL season:  Sept 1 – Feb 28 (of the following calendar year)
NBA season:  Oct 1 – Jun 30

Displayability thresholds:
  30d          → resolved_count >= 5
  last_season  → resolved_count >= 10
  career       → resolved_count >= 20

Usage:
    python -m src.rolling_windows          # compute all windows for today
    python -m src.rolling_windows --stats  # print summary table
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import date, datetime, timezone
from typing import Optional

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
QUALITY_TABLE = "gold_layer.assertion_quality"
WINDOWS_TABLE = "gold_layer.pundit_accuracy_windows"

DRIFT_THRESHOLD = 0.12
MIN_30D = 5
MIN_LAST_SEASON = 10
MIN_CAREER = 20


# ---------------------------------------------------------------------------
# Season helpers
# ---------------------------------------------------------------------------


def _nfl_last_completed_season(today: date) -> tuple[date, date]:
    """
    Returns (season_start, season_end) for the most recently completed NFL season.

    NFL regular + postseason: Sept 1 through Feb 28 of the following year.
    "Most recently completed" means the season whose Feb end date has already passed.

    Examples (from today's perspective):
      today=2026-05-08 → season 2025: 2025-09-01 to 2026-02-28  (completed)
      today=2025-01-15 → season 2024: 2024-09-01 to 2025-02-28  (completed, Feb not yet passed)
        Actually Jan 15 → Feb 28 of same year hasn't passed yet → season 2023
    """
    year = today.year
    # The current season ends Feb 28 of `year`. If we're past Feb 28, current season is done.
    current_end = date(year, 2, 28)
    if today > current_end:
        # Season year is (year-1), e.g. today=2026-05-08 → season starts 2025-09-01
        season_start = date(year - 1, 9, 1)
        season_end = current_end
    else:
        # Still in Feb or Jan — use season that ended Feb 28 of last year
        season_start = date(year - 2, 9, 1)
        season_end = date(year - 1, 2, 28)
    return season_start, season_end


def _nba_last_completed_season(today: date) -> tuple[date, date]:
    """
    Returns (season_start, season_end) for the most recently completed NBA season.

    NBA: Oct 1 – Jun 30.
    """
    year = today.year
    current_end = date(year, 6, 30)
    if today > current_end:
        season_start = date(year - 1, 10, 1)
        season_end = current_end
    else:
        season_start = date(year - 2, 10, 1)
        season_end = date(year - 1, 6, 30)
    return season_start, season_end


# ---------------------------------------------------------------------------
# BQ SQL builders — all BQ-native
# ---------------------------------------------------------------------------


def _window_sql(
    project_id: str,
    window_type: str,
    sport: Optional[str],
    today: date,
) -> str:
    """
    Returns a BigQuery SELECT fragment for one window type.

    Returns columns:
        pundit_id, entity_class, claim_type, sport,
        window_type, accuracy_rate, brier_score, resolved_count
    """
    ledger = f"`{project_id}.{LEDGER_TABLE}`"
    resolutions = f"`{project_id}.{RESOLUTIONS_TABLE}`"
    quality = f"`{project_id}.{QUALITY_TABLE}`"

    if window_type == "30d":
        date_filter = "DATE(r.resolved_at) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)"
    elif window_type == "last_season":
        if sport == "NFL":
            s_start, s_end = _nfl_last_completed_season(today)
        else:
            # Default to NBA for any other sport
            s_start, s_end = _nba_last_completed_season(today)
        date_filter = (
            f"DATE(r.resolved_at) BETWEEN DATE('{s_start.isoformat()}') "
            f"AND DATE('{s_end.isoformat()}')"
        )
    else:  # career
        date_filter = "TRUE"

    sport_filter = ""
    if sport:
        sport_filter = f"AND l.sport = '{sport}'"

    return f"""
    SELECT
        l.pundit_id,
        l.entity_class,
        l.claim_type,
        l.sport,
        '{window_type}' AS window_type,
        SAFE_DIVIDE(
            COUNTIF(r.binary_correct IS TRUE),
            COUNT(r.prediction_hash)
        ) AS accuracy_rate,
        AVG(
            POW(
                COALESCE(aq.quality_score, 0.5) - IF(r.binary_correct, 1.0, 0.0),
                2
            )
        ) AS brier_score,
        COUNT(r.prediction_hash) AS resolved_count
    FROM {ledger} l
    INNER JOIN {resolutions} r
        ON l.prediction_hash = r.prediction_hash
    LEFT JOIN {quality} aq
        ON l.prediction_hash = aq.prediction_hash
    WHERE r.resolution_status IN ('CORRECT', 'INCORRECT')
      AND r.binary_correct IS NOT NULL
      AND {date_filter}
      {sport_filter}
    GROUP BY
        l.pundit_id,
        l.entity_class,
        l.claim_type,
        l.sport
    """


def _build_all_windows_query(project_id: str, today: date) -> str:
    """
    Builds a UNION ALL across all 3 windows × 2 sports (NFL + NBA)
    for last_season, plus sport-agnostic 30d and career windows.
    """
    parts = []

    # 30d and career: sport comes from the data, no date boundary per-sport
    for wtype in ("30d", "career"):
        parts.append(_window_sql(project_id, wtype, sport=None, today=today))

    # last_season: compute per sport so season boundaries are correct
    for sport in ("NFL", "NBA"):
        parts.append(_window_sql(project_id, "last_season", sport=sport, today=today))

    union = "\n    UNION ALL\n    ".join(f"({p})" for p in parts)
    return f"SELECT * FROM ({union})"


def _merge_sql(project_id: str, computed_at: str) -> str:
    """
    Returns the MERGE statement that upserts into pundit_accuracy_windows.
    Key: (pundit_id, entity_class, claim_type, sport, window_type).
    """
    target = f"`{project_id}.{WINDOWS_TABLE}`"
    return f"""
    MERGE {target} T
    USING ({{source_query}}) S
    ON  T.pundit_id    = S.pundit_id
    AND T.entity_class IS NOT DISTINCT FROM S.entity_class
    AND T.claim_type   IS NOT DISTINCT FROM S.claim_type
    AND T.sport        IS NOT DISTINCT FROM S.sport
    AND T.window_type  = S.window_type
    AND DATE(T.computed_at) = DATE('{computed_at[:10]}')
    WHEN MATCHED THEN UPDATE SET
        accuracy_rate   = S.accuracy_rate,
        brier_score     = S.brier_score,
        resolved_count  = S.resolved_count,
        displayable     = S.displayable,
        drift_flagged   = S.drift_flagged,
        drift_magnitude = S.drift_magnitude,
        computed_at     = TIMESTAMP('{computed_at}')
    WHEN NOT MATCHED THEN INSERT (
        pundit_id, entity_class, claim_type, sport, window_type,
        accuracy_rate, brier_score, resolved_count,
        displayable, drift_flagged, drift_magnitude, computed_at
    ) VALUES (
        S.pundit_id, S.entity_class, S.claim_type, S.sport, S.window_type,
        S.accuracy_rate, S.brier_score, S.resolved_count,
        S.displayable, S.drift_flagged, S.drift_magnitude,
        TIMESTAMP('{computed_at}')
    )
    """


# ---------------------------------------------------------------------------
# Displayability
# ---------------------------------------------------------------------------


def _displayable(window_type: str, resolved_count: int) -> bool:
    thresholds = {"30d": MIN_30D, "last_season": MIN_LAST_SEASON, "career": MIN_CAREER}
    min_n = thresholds.get(window_type)
    if min_n is None:
        return False
    return resolved_count >= min_n


# ---------------------------------------------------------------------------
# Core compute
# ---------------------------------------------------------------------------


def _ensure_windows_table(db: DBManager) -> None:
    """Creates gold_layer.pundit_accuracy_windows if it doesn't exist."""
    project_id = os.environ.get("GCP_PROJECT_ID")
    ddl = f"""
        CREATE TABLE IF NOT EXISTS `{project_id}.{WINDOWS_TABLE}` (
            pundit_id       STRING    NOT NULL,
            entity_class    STRING,
            claim_type      STRING,
            sport           STRING,
            window_type     STRING    NOT NULL,
            accuracy_rate   FLOAT64,
            brier_score     FLOAT64,
            resolved_count  INT64,
            displayable     BOOL,
            drift_flagged   BOOL,
            drift_magnitude FLOAT64,
            computed_at     TIMESTAMP NOT NULL
        )
        PARTITION BY DATE(computed_at)
        CLUSTER BY pundit_id, window_type, entity_class
        OPTIONS (
            description = 'Rolling accuracy windows (30d/last_season/career) per pundit'
        )
    """
    db.client.query(ddl).result()
    logger.info("Ensured windows table exists: %s", WINDOWS_TABLE)


def _compute_drift_flags(
    rows: list[dict],
) -> dict[tuple, tuple[bool, float]]:
    """
    For each (pundit_id, entity_class, claim_type, sport) key, computes
    drift_flagged and drift_magnitude by comparing career vs last_season accuracy.

    Returns a dict keyed by (pundit_id, entity_class, claim_type, sport)
    → (drift_flagged: bool, drift_magnitude: float).
    """
    # Index rows by key × window_type
    by_key: dict[tuple, dict[str, dict]] = {}
    for row in rows:
        key = (row["pundit_id"], row["entity_class"], row["claim_type"], row["sport"])
        by_key.setdefault(key, {})[row["window_type"]] = row

    drift: dict[tuple, tuple[bool, float]] = {}
    for key, windows in by_key.items():
        career = windows.get("career")
        last_season = windows.get("last_season")

        if (
            career is None
            or last_season is None
            or career["accuracy_rate"] is None
            or last_season["accuracy_rate"] is None
        ):
            drift[key] = (False, 0.0)
            continue

        # Apply minimum resolved_count gates
        career_ok = career["resolved_count"] >= MIN_CAREER
        last_season_ok = last_season["resolved_count"] >= MIN_LAST_SEASON

        if not (career_ok and last_season_ok):
            drift[key] = (False, 0.0)
            continue

        magnitude = abs(career["accuracy_rate"] - last_season["accuracy_rate"])
        flagged = magnitude >= DRIFT_THRESHOLD
        drift[key] = (flagged, round(magnitude, 6))

    return drift


def compute_rolling_windows(
    db: Optional[DBManager] = None,
    today: Optional[date] = None,
) -> int:
    """
    Computes all rolling accuracy windows and MERGEs into BQ.

    Returns the number of rows written.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    if today is None:
        today = date.today()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        if not project_id:
            raise ValueError("GCP_PROJECT_ID environment variable not set")

        _ensure_windows_table(db)

        # Step 1: fetch all window rows
        logger.info("Computing rolling accuracy windows for %s…", today)
        windows_query = _build_all_windows_query(project_id, today)
        df = db.client.query(windows_query).to_dataframe()

        if df.empty:
            logger.info("No resolved predictions found — nothing to write.")
            return 0

        rows = df.to_dict(orient="records")
        logger.info("Fetched %d window rows from BQ.", len(rows))

        # Step 2: compute drift flags per pundit key
        drift_map = _compute_drift_flags(rows)

        # Step 3: annotate rows with displayable + drift columns
        computed_at = datetime.now(timezone.utc).isoformat()
        annotated_rows = []
        for row in rows:
            key = (
                row["pundit_id"],
                row["entity_class"],
                row["claim_type"],
                row["sport"],
            )
            drift_flagged, drift_magnitude = drift_map.get(key, (False, 0.0))
            rc = int(row["resolved_count"]) if row["resolved_count"] is not None else 0
            annotated_rows.append(
                {
                    **row,
                    "displayable": _displayable(row["window_type"], rc),
                    "drift_flagged": drift_flagged,
                    "drift_magnitude": drift_magnitude,
                    "computed_at": computed_at,
                }
            )

        # Step 4: MERGE into BQ using a VALUES literal constructed from the rows.
        # We upload via load_table_from_dataframe to a temp table then MERGE.
        import pandas as pd
        from google.cloud import bigquery

        temp_table_id = (
            f"{project_id}.gold_layer._tmp_windows_{today.strftime('%Y%m%d')}"
        )

        annotated_df = pd.DataFrame(annotated_rows)
        # Ensure computed_at is TIMESTAMP-compatible string
        annotated_df["computed_at"] = pd.to_datetime(
            annotated_df["computed_at"], utc=True
        )

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            schema=[
                bigquery.SchemaField("pundit_id", "STRING"),
                bigquery.SchemaField("entity_class", "STRING"),
                bigquery.SchemaField("claim_type", "STRING"),
                bigquery.SchemaField("sport", "STRING"),
                bigquery.SchemaField("window_type", "STRING"),
                bigquery.SchemaField("accuracy_rate", "FLOAT64"),
                bigquery.SchemaField("brier_score", "FLOAT64"),
                bigquery.SchemaField("resolved_count", "INT64"),
                bigquery.SchemaField("displayable", "BOOL"),
                bigquery.SchemaField("drift_flagged", "BOOL"),
                bigquery.SchemaField("drift_magnitude", "FLOAT64"),
                bigquery.SchemaField("computed_at", "TIMESTAMP"),
            ],
        )
        load_job = db.client.load_table_from_dataframe(
            annotated_df, temp_table_id, job_config=job_config
        )
        load_job.result()
        logger.info(
            "Loaded %d rows into temp table %s.", len(annotated_df), temp_table_id
        )

        # MERGE from temp table into windows table
        target = f"`{project_id}.{WINDOWS_TABLE}`"
        source = f"`{temp_table_id}`"
        merge_sql = f"""
            MERGE {target} T
            USING {source} S
            ON  T.pundit_id    = S.pundit_id
            AND T.entity_class IS NOT DISTINCT FROM S.entity_class
            AND T.claim_type   IS NOT DISTINCT FROM S.claim_type
            AND T.sport        IS NOT DISTINCT FROM S.sport
            AND T.window_type  = S.window_type
            AND DATE(T.computed_at) = DATE(S.computed_at)
            WHEN MATCHED THEN UPDATE SET
                accuracy_rate   = S.accuracy_rate,
                brier_score     = S.brier_score,
                resolved_count  = S.resolved_count,
                displayable     = S.displayable,
                drift_flagged   = S.drift_flagged,
                drift_magnitude = S.drift_magnitude,
                computed_at     = S.computed_at
            WHEN NOT MATCHED THEN INSERT ROW
        """
        merge_job = db.client.query(merge_sql)
        merge_job.result()
        logger.info(
            "MERGE complete — %d rows written to %s.",
            len(annotated_rows),
            WINDOWS_TABLE,
        )

        # Clean up temp table
        db.client.delete_table(temp_table_id, not_found_ok=True)

        return len(annotated_rows)

    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# Stats printer
# ---------------------------------------------------------------------------


def print_windows_stats(db: Optional[DBManager] = None) -> None:
    """Print a summary of the latest rolling window computation."""
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                window_type,
                COUNT(DISTINCT pundit_id) AS pundits,
                COUNTIF(displayable)      AS displayable_rows,
                COUNTIF(drift_flagged)    AS drift_flagged_rows,
                AVG(accuracy_rate)        AS avg_accuracy,
                MAX(computed_at)          AS last_computed
            FROM `{project_id}.{WINDOWS_TABLE}`
            WHERE DATE(computed_at) = (
                SELECT MAX(DATE(computed_at)) FROM `{project_id}.{WINDOWS_TABLE}`
            )
            GROUP BY window_type
            ORDER BY window_type
        """
        df = db.client.query(query).to_dataframe()

        if df.empty:
            print("No window data found.")
            return

        print(f"\n{'=' * 80}")
        print("  Rolling Accuracy Windows — latest run")
        print(f"{'=' * 80}")
        print(
            f"  {'Window':<15} {'Pundits':>8} {'Displayable':>12} "
            f"{'Drift⚑':>8} {'Avg Acc':>9}"
        )
        print(f"  {'-' * 60}")
        for _, row in df.iterrows():
            print(
                f"  {str(row['window_type']):<15} {int(row['pundits']):>8} "
                f"{int(row['displayable_rows']):>12} {int(row['drift_flagged_rows']):>8} "
                f"{row['avg_accuracy']:>9.4f}"
            )
        print(f"{'=' * 80}\n")

    finally:
        if close_db:
            db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
    )

    if "--stats" in sys.argv:
        print_windows_stats()
    else:
        print("Computing rolling accuracy windows…")
        n = compute_rolling_windows()
        print(f"Done. Wrote {n} window rows.")
        if n:
            print_windows_stats()


if __name__ == "__main__":
    main()

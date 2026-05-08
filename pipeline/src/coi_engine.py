"""
Conflict-of-Interest Detection Engine -- Phase 1 (Issue #810)

Surfaces statistical anomalies in pundit behavior across three signals:

  Signal 1 -- CONFIDENCE_SPIKE: rolling 180-day z-score >= 2.0, absolute confidence >= 0.80
  Signal 2 -- ENTITY_BIAS: global vs. per-entity accuracy gap >= 0.20 (or 0.30 if entity
              dominates pundit's claim portfolio), minimum 15 resolved per entity
  Signal 3 -- NARRATIVE_CLUSTER: >= 3 pundits from >= 2 outlets publish semantically
              similar claims about the same entity+category+stance within a 72h window

All output is framed as *patterns warranting scrutiny*, never as accusations of
misconduct. Every flag carries a mandatory disclaimer.

Signal 4 (MARKET_LEAD) is deferred to Phase 2 -- requires external betting-line data.

Usage:
    python -m src.coi_engine                   # run all signals
    python -m src.coi_engine --signal 1        # run only Signal 1
    python -m src.coi_engine --signal 2        # run only Signal 2
    python -m src.coi_engine --signal 3        # run only Signal 3
    python -m src.coi_engine --dry-run         # compute flags without writing to BQ
    python -m src.coi_engine --summary         # print flag summary table

Pipeline integration (run_daily.py):
    run_daily.py -> ... -> resolve_daily.py -> coi_engine.run_daily()

Write behaviour:
    Idempotent -- flag_id is SHA-256(pundit_id + signal_type + window_start + entity_key).
    Re-runs on the same calendar day produce the same flag_id; duplicates are
    deduplicated via MERGE INTO ... ON flag_id.
    Suppressed flags are stored (audit trail), never deleted.
"""

import argparse
import hashlib
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from google.cloud import bigquery

from src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table references
# ---------------------------------------------------------------------------

COI_FLAGS_TABLE = "gold_layer.coi_flags"
LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"

# ---------------------------------------------------------------------------
# Detection thresholds
# ---------------------------------------------------------------------------

# Signal 1 -- Confidence spike
SIGNAL1_Z_THRESHOLD = 2.0
SIGNAL1_ABS_THRESHOLD = 0.80
SIGNAL1_BASELINE_WINDOW_DAYS = 180
SIGNAL1_MIN_BASELINE_CLAIMS = 20

# Signal 2 -- Entity bias
SIGNAL2_MIN_RESOLVED = 15
SIGNAL2_DELTA_DEFAULT = 0.20
SIGNAL2_DELTA_DOMINANT = 0.30
SIGNAL2_ENTITY_DOMINANT_SHARE = 0.60
SIGNAL2_MIN_GLOBAL_RESOLVED = 50

# Signal 3 -- Narrative cluster
SIGNAL3_WINDOW_HOURS = 72
SIGNAL3_MIN_PUNDITS = 3
SIGNAL3_MIN_OUTLETS = 2
SIGNAL3_JACCARD_THRESHOLD = 0.30

# Severity thresholds
SEVERITY_HIGH_Z = 3.0
SEVERITY_HIGH_DELTA = 0.35
SEVERITY_HIGH_CLUSTER = 5
SEVERITY_MEDIUM_Z = 2.0
SEVERITY_MEDIUM_DELTA = 0.20
SEVERITY_MEDIUM_CLUSTER = 3

DETECTOR_VERSION = "1.0.0"

DISCLAIMER = (
    "Statistical anomaly only. No inference of intent. "
    "These patterns may reflect legitimate expertise, editorial decisions, or chance. "
    "CapAlpha does not determine intent."
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class COIFlag:
    flag_id: str
    pundit_id: str
    signal_type: str
    severity: str
    detected_at: datetime
    window_start: Optional[datetime]
    window_end: Optional[datetime]
    entity_key: Optional[str]
    claim_hashes: list
    signal_data: dict
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    pipeline_run_id: str = ""
    schema_version: str = "1.0"

    def to_bq_row(self) -> dict:
        return {
            "flag_id": self.flag_id,
            "pundit_id": self.pundit_id,
            "signal_type": self.signal_type,
            "severity": self.severity,
            "detected_at": self.detected_at.isoformat(),
            "window_start": self.window_start.isoformat()
            if self.window_start
            else None,
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "entity_key": self.entity_key,
            "claim_hashes": self.claim_hashes,
            "signal_data": json.dumps({**self.signal_data, "disclaimer": DISCLAIMER}),
            "suppressed": self.suppressed,
            "suppression_reason": self.suppression_reason,
            "pipeline_run_id": self.pipeline_run_id,
            "schema_version": self.schema_version,
        }


# ---------------------------------------------------------------------------
# Flag ID generation
# ---------------------------------------------------------------------------


def _make_flag_id(
    pundit_id: str,
    signal_type: str,
    window_start: Optional[datetime],
    entity_key: Optional[str],
) -> str:
    """SHA-256(pundit_id | signal_type | window_start_date | entity_key) for idempotency."""
    parts = "|".join(
        [
            pundit_id,
            signal_type,
            window_start.date().isoformat() if window_start else "",
            entity_key or "",
        ]
    )
    return hashlib.sha256(parts.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Severity helpers
# ---------------------------------------------------------------------------


def _confidence_spike_severity(z_score: float) -> str:
    if z_score >= SEVERITY_HIGH_Z:
        return "HIGH"
    if z_score >= SEVERITY_MEDIUM_Z:
        return "MEDIUM"
    return "LOW"


def _entity_bias_severity(delta: float) -> str:
    if delta >= SEVERITY_HIGH_DELTA:
        return "HIGH"
    if delta >= SEVERITY_MEDIUM_DELTA:
        return "MEDIUM"
    return "LOW"


def _cluster_severity(n_pundits: int) -> str:
    if n_pundits >= SEVERITY_HIGH_CLUSTER:
        return "HIGH"
    if n_pundits >= SEVERITY_MEDIUM_CLUSTER:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Signal 1 -- Confidence Spike
# ---------------------------------------------------------------------------


def _check_confidence_coverage(db: DBManager) -> float:
    """Return fraction of ledger rows with non-NULL confidence."""
    query = (
        "SELECT COUNTIF(confidence IS NOT NULL) / COUNT(*) AS overall_coverage"
        f" FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}`"
    )
    try:
        result = db.fetch_df(query)
        if result.empty:
            return 0.0
        return float(result["overall_coverage"].iloc[0] or 0.0)
    except Exception as e:
        logger.warning(f"[Signal1] Coverage check failed: {e}")
        return 0.0


def run_signal1_confidence_spike(
    db: DBManager,
    run_id: str,
    lookback_hours: int = 24,
    dry_run: bool = False,
) -> list:
    """
    Detect confidence spikes: rolling 180-day z-score >= 2.0 AND absolute confidence >= 0.80.
    Skipped if overall confidence coverage < 50% (returns [] with a warning).

    Returns list of COIFlag objects.
    """
    coverage = _check_confidence_coverage(db)
    logger.info(f"[Signal1] Overall confidence coverage: {coverage:.1%}")
    if coverage < 0.50:
        logger.warning(
            f"[Signal1] Coverage {coverage:.1%} < 50% -- Signal 1 skipped."
            " Re-enable when extraction populates confidence more broadly."
        )
        return []

    query = (
        f"WITH baseline AS ("
        f"  SELECT pundit_id,"
        f"    AVG(confidence) AS mu,"
        f"    STDDEV_SAMP(confidence) AS sigma,"
        f"    COUNT(*) AS n_claims"
        f"  FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}`"
        f"  WHERE confidence IS NOT NULL"
        f"    AND ingestion_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(),"
        f"        INTERVAL {SIGNAL1_BASELINE_WINDOW_DAYS} DAY)"
        f"  GROUP BY pundit_id"
        f"  HAVING n_claims >= {SIGNAL1_MIN_BASELINE_CLAIMS}"
        f"),"
        f"recent AS ("
        f"  SELECT l.prediction_hash, l.pundit_id, l.confidence, l.ingestion_timestamp"
        f"  FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}` l"
        f"  WHERE l.confidence IS NOT NULL"
        f"    AND l.confidence >= {SIGNAL1_ABS_THRESHOLD}"
        f"    AND l.ingestion_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(),"
        f"        INTERVAL {lookback_hours} HOUR)"
        f"),"
        f"scored AS ("
        f"  SELECT r.prediction_hash, r.pundit_id,"
        f"    r.confidence AS raw_confidence,"
        f"    r.ingestion_timestamp,"
        f"    b.mu, b.sigma, b.n_claims AS baseline_n,"
        f"    SAFE_DIVIDE(r.confidence - b.mu, NULLIF(b.sigma, 0)) AS z_score"
        f"  FROM recent r"
        f"  INNER JOIN baseline b ON b.pundit_id = r.pundit_id"
        f")"
        f"SELECT * FROM scored"
        f"  WHERE z_score >= {SIGNAL1_Z_THRESHOLD}"
        f"    AND z_score IS NOT NULL"
        f"  ORDER BY pundit_id, ingestion_timestamp"
    )

    try:
        df = db.fetch_df(query)
    except Exception as e:
        logger.error(f"[Signal1] Query failed: {e}")
        return []

    if df.empty:
        logger.info("[Signal1] No confidence spikes detected.")
        return []

    flags = []
    now = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        z = float(row["z_score"])
        severity = _confidence_spike_severity(z)
        window_start = pd.Timestamp(row["ingestion_timestamp"]).to_pydatetime()
        flag_id = _make_flag_id(
            row["pundit_id"], "CONFIDENCE_SPIKE", window_start, None
        )

        flags.append(
            COIFlag(
                flag_id=flag_id,
                pundit_id=row["pundit_id"],
                signal_type="CONFIDENCE_SPIKE",
                severity=severity,
                detected_at=now,
                window_start=window_start,
                window_end=window_start,
                entity_key=None,
                claim_hashes=[row["prediction_hash"]],
                signal_data={
                    "claim_confidence": float(row["raw_confidence"]),
                    "baseline_mean": float(row["mu"]),
                    "baseline_stddev": float(row["sigma"]),
                    "z_score": z,
                    "baseline_claim_count": int(row["baseline_n"]),
                },
                pipeline_run_id=run_id,
            )
        )

    logger.info(f"[Signal1] Detected {len(flags)} confidence spike flag(s).")
    return flags


# ---------------------------------------------------------------------------
# Signal 2 -- Entity Bias
# ---------------------------------------------------------------------------


def run_signal2_entity_bias(
    db: DBManager,
    run_id: str,
    dry_run: bool = False,
) -> list:
    """
    Detect systematic entity bias: global vs. per-entity accuracy gap.
    Threshold: 0.20 normally, 0.30 when entity_claim_share > 0.60.
    Minimum: 15 resolved per entity, 50 resolved globally.

    Returns list of COIFlag objects.
    """
    query = (
        f"WITH resolved AS ("
        f"  SELECT l.prediction_hash, l.pundit_id,"
        f"    COALESCE(l.target_player, l.target_team) AS entity_key,"
        f"    CASE r.resolution_status"
        f"      WHEN 'CORRECT'   THEN 1.0"
        f"      WHEN 'INCORRECT' THEN 0.0"
        f"      ELSE NULL"
        f"    END AS binary_correct"
        f"  FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}` l"
        f"  INNER JOIN `{db.project_id}.nfl_dead_money.{RESOLUTIONS_TABLE}` r"
        f"    ON r.prediction_hash = l.prediction_hash"
        f"  WHERE r.resolution_status IN ('CORRECT', 'INCORRECT')"
        f"    AND COALESCE(l.target_player, l.target_team) IS NOT NULL"
        f"),"
        f"global_stats AS ("
        f"  SELECT pundit_id, COUNT(*) AS n_global, AVG(binary_correct) AS p_global"
        f"  FROM resolved GROUP BY pundit_id"
        f"  HAVING COUNT(*) >= {SIGNAL2_MIN_GLOBAL_RESOLVED}"
        f"),"
        f"entity_stats AS ("
        f"  SELECT pundit_id, entity_key,"
        f"    COUNT(*) AS n_entity, AVG(binary_correct) AS p_entity"
        f"  FROM resolved GROUP BY pundit_id, entity_key"
        f"  HAVING COUNT(*) >= {SIGNAL2_MIN_RESOLVED}"
        f"),"
        f"pundit_total AS ("
        f"  SELECT pundit_id, COUNT(*) AS n_total"
        f"  FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}` GROUP BY pundit_id"
        f"),"
        f"entity_all_claims AS ("
        f"  SELECT l.pundit_id,"
        f"    COALESCE(l.target_player, l.target_team) AS entity_key,"
        f"    COUNT(*) AS n_entity_all"
        f"  FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}` l"
        f"  WHERE COALESCE(l.target_player, l.target_team) IS NOT NULL"
        f"  GROUP BY l.pundit_id, COALESCE(l.target_player, l.target_team)"
        f"),"
        f"gap_calc AS ("
        f"  SELECT es.pundit_id, es.entity_key,"
        f"    gs.p_global, es.p_entity, es.n_entity, gs.n_global,"
        f"    es.p_entity - gs.p_global AS delta_raw,"
        f"    SAFE_DIVIDE(ec.n_entity_all, NULLIF(pt.n_total, 0)) AS entity_claim_share"
        f"  FROM entity_stats es"
        f"  INNER JOIN global_stats gs ON gs.pundit_id = es.pundit_id"
        f"  LEFT  JOIN entity_all_claims ec"
        f"    ON ec.pundit_id = es.pundit_id AND ec.entity_key = es.entity_key"
        f"  LEFT  JOIN pundit_total pt ON pt.pundit_id = es.pundit_id"
        f")"
        f"SELECT gc.*,"
        f"  CASE WHEN gc.entity_claim_share > {SIGNAL2_ENTITY_DOMINANT_SHARE}"
        f"    THEN {SIGNAL2_DELTA_DOMINANT} ELSE {SIGNAL2_DELTA_DEFAULT}"
        f"  END AS delta_threshold,"
        f"  ARRAY("
        f"    SELECT l.prediction_hash"
        f"    FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}` l"
        f"    INNER JOIN `{db.project_id}.nfl_dead_money.{RESOLUTIONS_TABLE}` r"
        f"      ON r.prediction_hash = l.prediction_hash"
        f"    WHERE l.pundit_id = gc.pundit_id"
        f"      AND COALESCE(l.target_player, l.target_team) = gc.entity_key"
        f"      AND r.resolution_status IN ('CORRECT', 'INCORRECT')"
        f"    ORDER BY l.ingestion_timestamp DESC LIMIT 5"
        f"  ) AS claim_hashes"
        f" FROM gap_calc gc"
        f" WHERE ABS(gc.delta_raw) >= ("
        f"   CASE WHEN gc.entity_claim_share > {SIGNAL2_ENTITY_DOMINANT_SHARE}"
        f"     THEN {SIGNAL2_DELTA_DOMINANT} ELSE {SIGNAL2_DELTA_DEFAULT} END"
        f" )"
    )

    try:
        df = db.fetch_df(query)
    except Exception as e:
        logger.error(f"[Signal2] Query failed: {e}")
        return []

    if df.empty:
        logger.info("[Signal2] No entity bias patterns detected.")
        return []

    flags = []
    now = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        delta = float(row["delta_raw"])
        severity = _entity_bias_severity(abs(delta))
        entity_key = str(row["entity_key"])
        delta_threshold = float(row["delta_threshold"])
        entity_claim_share = float(row["entity_claim_share"] or 0.0)

        flag_id = _make_flag_id(row["pundit_id"], "ENTITY_BIAS", None, entity_key)
        claim_hashes = list(row["claim_hashes"]) if row["claim_hashes"] else []

        flags.append(
            COIFlag(
                flag_id=flag_id,
                pundit_id=row["pundit_id"],
                signal_type="ENTITY_BIAS",
                severity=severity,
                detected_at=now,
                window_start=None,
                window_end=None,
                entity_key=entity_key,
                claim_hashes=claim_hashes,
                signal_data={
                    "global_accuracy": float(row["p_global"]),
                    "entity_accuracy": float(row["p_entity"]),
                    "accuracy_delta": delta,
                    "entity_resolved_count": int(row["n_entity"]),
                    "entity_claim_share": entity_claim_share,
                    "delta_threshold_applied": delta_threshold,
                },
                pipeline_run_id=run_id,
            )
        )

    logger.info(f"[Signal2] Detected {len(flags)} entity bias flag(s).")
    return flags


# ---------------------------------------------------------------------------
# Signal 3 -- Narrative Cluster (lexical matching)
# ---------------------------------------------------------------------------


def _extract_tokens(claim_text: str) -> frozenset:
    """Lowercase, strip punctuation, return word-token frozenset."""
    if not claim_text:
        return frozenset()
    text = re.sub(r"[^a-z0-9\s]", " ", claim_text.lower())
    return frozenset(text.split())


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _extract_outlet(source_url: Optional[str]) -> str:
    """Return normalized domain from a URL, or 'unknown'."""
    if not source_url:
        return "unknown"
    url = re.sub(r"^https?://", "", str(source_url).lower())
    domain = url.split("/")[0]
    domain = re.sub(r"^www\.", "", domain)
    return domain or "unknown"


def run_signal3_narrative_cluster(
    db: DBManager,
    run_id: str,
    window_hours: int = SIGNAL3_WINDOW_HOURS,
    min_pundits: int = SIGNAL3_MIN_PUNDITS,
    min_outlets: int = SIGNAL3_MIN_OUTLETS,
    dry_run: bool = False,
) -> list:
    """
    Detect coordinated narrative clusters: >= 3 pundits from >= 2 outlets publish
    lexically similar claims about the same entity+category+stance within 72h.

    Suppression: if >= 50% of cluster pundits share the same outlet, the flag is
    stored as suppressed=True (shared-source mitigation).

    Returns list of COIFlag objects -- one per pundit in each qualifying cluster.
    """
    query = (
        f"SELECT l.prediction_hash, l.pundit_id, l.extracted_claim,"
        f"  l.claim_category, l.stance,"
        f"  COALESCE(l.target_player, l.target_team) AS entity_key,"
        f"  l.ingestion_timestamp, l.source_url"
        f" FROM `{db.project_id}.nfl_dead_money.{LEDGER_TABLE}` l"
        f" WHERE l.ingestion_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(),"
        f"     INTERVAL {window_hours + 24} HOUR)"
        f"   AND COALESCE(l.target_player, l.target_team) IS NOT NULL"
        f"   AND l.extracted_claim IS NOT NULL"
        f" ORDER BY l.ingestion_timestamp ASC"
    )

    try:
        df = db.fetch_df(query)
    except Exception as e:
        logger.error(f"[Signal3] Query failed: {e}")
        return []

    if df.empty:
        logger.info("[Signal3] No recent claims to cluster.")
        return []

    flags = []
    now = datetime.now(timezone.utc)
    seen_clusters: set = set()

    df["tokens"] = df["extracted_claim"].apply(_extract_tokens)
    df["outlet"] = df["source_url"].apply(_extract_outlet)
    df["group_key"] = (
        df["entity_key"].fillna("")
        + "|"
        + df["claim_category"].fillna("")
        + "|"
        + df["stance"].fillna("")
    )

    for group_key, group_df in df.groupby("group_key"):
        if len(group_df) < min_pundits:
            continue

        group_df = group_df.sort_values("ingestion_timestamp").reset_index(drop=True)
        rows = group_df.to_dict("records")

        for i, anchor in enumerate(rows):
            anchor_ts = pd.Timestamp(anchor["ingestion_timestamp"])
            window_end_ts = anchor_ts + pd.Timedelta(hours=window_hours)

            cluster = [anchor]
            for j in range(i + 1, len(rows)):
                cand = rows[j]
                if pd.Timestamp(cand["ingestion_timestamp"]) > window_end_ts:
                    break
                if (
                    _jaccard(anchor["tokens"], cand["tokens"])
                    >= SIGNAL3_JACCARD_THRESHOLD
                ):
                    cluster.append(cand)

            if len(cluster) < min_pundits:
                continue

            pundit_ids = list({r["pundit_id"] for r in cluster})
            outlets = list({r["outlet"] for r in cluster})

            if len(pundit_ids) < min_pundits or len(outlets) < min_outlets:
                continue

            cluster_key = frozenset(r["prediction_hash"] for r in cluster)
            if cluster_key in seen_clusters:
                continue
            seen_clusters.add(cluster_key)

            # Shared-source suppression
            outlet_counts: dict = defaultdict(int)
            for r in cluster:
                outlet_counts[r["outlet"]] += 1
            max_outlet_share = max(outlet_counts.values()) / len(cluster)
            suppressed = max_outlet_share >= 0.50
            suppression_reason = (
                "shared_source_fraction_ge_50pct" if suppressed else None
            )

            entity_key = anchor["entity_key"]
            window_start_dt = anchor_ts.to_pydatetime()
            cluster_end_ts = max(
                pd.Timestamp(r["ingestion_timestamp"]) for r in cluster
            )
            window_end_dt = cluster_end_ts.to_pydatetime()
            window_hrs_actual = int((cluster_end_ts - anchor_ts).total_seconds() / 3600)
            severity = _cluster_severity(len(pundit_ids))

            signal_data = {
                "pundit_count": len(pundit_ids),
                "window_hours": window_hrs_actual,
                "pairwise_similarity_method": "jaccard_lexical",
                "pundits_in_cluster": pundit_ids,
                "outlets_in_cluster": outlets,
                "shared_source_fraction": max_outlet_share,
                "entity_key": entity_key,
                "claim_category": anchor.get("claim_category"),
                "stance": anchor.get("stance"),
            }
            claim_hashes = [r["prediction_hash"] for r in cluster]

            for pundit_id in pundit_ids:
                flag_id = _make_flag_id(
                    pundit_id, "NARRATIVE_CLUSTER", window_start_dt, entity_key
                )
                flags.append(
                    COIFlag(
                        flag_id=flag_id,
                        pundit_id=pundit_id,
                        signal_type="NARRATIVE_CLUSTER",
                        severity=severity,
                        detected_at=now,
                        window_start=window_start_dt,
                        window_end=window_end_dt,
                        entity_key=entity_key,
                        claim_hashes=claim_hashes,
                        signal_data=signal_data,
                        suppressed=suppressed,
                        suppression_reason=suppression_reason,
                        pipeline_run_id=run_id,
                    )
                )

    logger.info(f"[Signal3] Detected {len(flags)} narrative cluster flag(s).")
    return flags


# ---------------------------------------------------------------------------
# BQ write -- idempotent MERGE via temp table
# ---------------------------------------------------------------------------


def _ensure_table(db: DBManager) -> None:
    """Create gold_layer.coi_flags if it does not already exist."""
    ddl = (
        f"CREATE TABLE IF NOT EXISTS"
        f" `{db.project_id}.nfl_dead_money.{COI_FLAGS_TABLE}`"
        f" ("
        f"   flag_id            STRING    NOT NULL,"
        f"   pundit_id          STRING    NOT NULL,"
        f"   signal_type        STRING    NOT NULL,"
        f"   severity           STRING    NOT NULL,"
        f"   detected_at        TIMESTAMP NOT NULL,"
        f"   window_start       TIMESTAMP,"
        f"   window_end         TIMESTAMP,"
        f"   entity_key         STRING,"
        f"   claim_hashes       ARRAY<STRING>,"
        f"   signal_data        JSON,"
        f"   suppressed         BOOL      NOT NULL DEFAULT FALSE,"
        f"   suppression_reason STRING,"
        f"   pipeline_run_id    STRING    NOT NULL,"
        f"   schema_version     STRING    NOT NULL DEFAULT '1.0'"
        f" )"
        f" PARTITION BY DATE(detected_at)"
        f" CLUSTER BY pundit_id, signal_type"
        f" OPTIONS(description='COI/anomaly detection flags. Issue #810.');"
    )
    try:
        db.execute(ddl)
        logger.info(f"[COIEngine] Ensured table {COI_FLAGS_TABLE} exists.")
    except Exception as e:
        logger.warning(f"[COIEngine] Table ensure (may already exist): {e}")


def write_flags(db: DBManager, flags: list, dry_run: bool = False) -> int:
    """
    Idempotent write: insert new flags, skip existing flag_ids (MERGE).
    Returns the number of rows submitted.
    """
    if not flags:
        return 0

    if dry_run:
        logger.info(f"[COIEngine] DRY RUN -- would write {len(flags)} flag(s).")
        for f in flags:
            logger.info(
                f"  {f.signal_type} | {f.pundit_id} | {f.severity} | {f.flag_id[:16]}..."
            )
        return 0

    rows = [f.to_bq_row() for f in flags]
    temp_table = f"tmp_coi_{uuid.uuid4().hex[:8]}"
    temp_ref = f"{db.project_id}.nfl_dead_money.{temp_table}"

    try:
        load_job = db.client.load_table_from_json(
            rows,
            temp_ref,
            job_config=bigquery.LoadJobConfig(
                write_disposition="WRITE_TRUNCATE",
                autodetect=True,
            ),
        )
        load_job.result()

        merge_sql = (
            f"MERGE `{db.project_id}.nfl_dead_money.{COI_FLAGS_TABLE}` AS T"
            f" USING `{temp_ref}` AS S ON T.flag_id = S.flag_id"
            f" WHEN NOT MATCHED THEN"
            f"   INSERT (flag_id, pundit_id, signal_type, severity, detected_at,"
            f"           window_start, window_end, entity_key, claim_hashes,"
            f"           signal_data, suppressed, suppression_reason,"
            f"           pipeline_run_id, schema_version)"
            f"   VALUES (S.flag_id, S.pundit_id, S.signal_type, S.severity, S.detected_at,"
            f"           S.window_start, S.window_end, S.entity_key, S.claim_hashes,"
            f"           S.signal_data, S.suppressed, S.suppression_reason,"
            f"           S.pipeline_run_id, S.schema_version)"
        )
        db.client.query(merge_sql).result()
        db.client.delete_table(temp_ref, not_found_ok=True)

        logger.info(f"[COIEngine] Wrote {len(rows)} flag(s) to {COI_FLAGS_TABLE}.")
        return len(rows)
    except Exception as e:
        logger.error(f"[COIEngine] Write failed: {e}")
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_daily(
    db: Optional[DBManager] = None,
    run_id: Optional[str] = None,
    signals: Optional[list] = None,
    dry_run: bool = False,
) -> dict:
    """
    Main entry point called by run_daily.py after resolve_daily completes.

    Args:
        db:       DBManager instance (created internally if None).
        run_id:   Pipeline run ID (UUID-8 generated if None).
        signals:  List of signal numbers [1, 2, 3] to run. None = all.
        dry_run:  Compute flags without writing to BigQuery.

    Returns:
        dict with signal1_count, signal2_count, signal3_count, total_written, run_id.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())[:8]

    own_db = db is None
    if own_db:
        db = DBManager()

    signals_to_run = set(signals) if signals else {1, 2, 3}
    logger.info(
        f"[COIEngine] Starting (run={run_id}, signals={sorted(signals_to_run)},"
        f" dry_run={dry_run})"
    )

    try:
        if not dry_run:
            _ensure_table(db)

        all_flags: list = []
        s1_flags: list = []
        s2_flags: list = []
        s3_flags: list = []

        if 1 in signals_to_run:
            s1_flags = run_signal1_confidence_spike(db, run_id, dry_run=dry_run)
            all_flags.extend(s1_flags)

        if 2 in signals_to_run:
            s2_flags = run_signal2_entity_bias(db, run_id, dry_run=dry_run)
            all_flags.extend(s2_flags)

        if 3 in signals_to_run:
            s3_flags = run_signal3_narrative_cluster(db, run_id, dry_run=dry_run)
            all_flags.extend(s3_flags)

        n_written = write_flags(db, all_flags, dry_run=dry_run)

        result = {
            "signal1_count": len(s1_flags),
            "signal2_count": len(s2_flags),
            "signal3_count": len(s3_flags),
            "total_written": n_written,
            "run_id": run_id,
        }
        logger.info(f"[COIEngine] Done: {result}")
        return result
    finally:
        if own_db:
            db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_summary(db: DBManager) -> None:
    query = (
        f"SELECT signal_type, severity, COUNT(*) AS n_flags,"
        f"  COUNTIF(suppressed) AS n_suppressed,"
        f"  MIN(detected_at) AS earliest, MAX(detected_at) AS latest"
        f" FROM `{db.project_id}.nfl_dead_money.{COI_FLAGS_TABLE}`"
        f" GROUP BY signal_type, severity ORDER BY signal_type, severity"
    )
    try:
        df = db.fetch_df(query)
        print(df.to_string(index=False) if not df.empty else "No COI flags in table.")
    except Exception as e:
        print(f"Summary query failed: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="COI Detection Engine (Issue #810)")
    parser.add_argument(
        "--signal",
        type=int,
        choices=[1, 2, 3],
        action="append",
        help="Run specified signal(s). Repeat for multiple. Default: all.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute flags but do not write to BigQuery.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print flag summary from BigQuery and exit.",
    )
    args = parser.parse_args()

    db = DBManager()
    try:
        if args.summary:
            _print_summary(db)
            return
        run_daily(db=db, signals=args.signal or None, dry_run=args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()

"""
Source Reputation Weighting (SP23-2, GH-#84)

Enforces a heuristic decay on publishers/domains whose historical prediction
accuracy drops below an acceptable baseline, preventing low-quality sources
from polluting the assertion pipeline.

Reputation model
----------------
Each source domain is scored on a [0.0, 1.0] scale:

  - Insufficient history (< MIN_RESOLVED_PREDICTIONS): weight = UNVERIFIED_WEIGHT (1.0)
    New/unverified sources are admitted at full weight — they earn their score.
  - accuracy_rate >= HIGH_ACCURACY_THRESHOLD (0.60): weight = 1.0
  - HIGH_ACCURACY_THRESHOLD > accuracy_rate >= LOW_ACCURACY_THRESHOLD (0.35):
    weight = linear interpolation 0.5 → 1.0
  - accuracy_rate < LOW_ACCURACY_THRESHOLD (0.35): weight = PENALTY_WEIGHT (0.25)
  - accuracy_rate < SUPPRESS_THRESHOLD (0.20): weight = 0.0 (fully suppressed)

Pre-computed Gold table
-----------------------
`gold_layer.source_reputation` is rebuilt by compute_reputation() on each
daily pipeline run. The assertion extractor reads from this table (or the
in-process cache) to gate incoming articles.

Integration
-----------
`filter_suppressed_source_ids(source_ids, db)` returns the subset that are
actively suppressed (weight == 0.0) so callers can skip LLM extraction
entirely for those sources.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.db_manager import DBManager

logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
REPUTATION_TABLE = "gold_layer.source_reputation"

# Reputation thresholds
MIN_RESOLVED_PREDICTIONS = 10       # below this → unverified, full weight
UNVERIFIED_WEIGHT = 1.0             # new/unverified sources start at full weight
HIGH_ACCURACY_THRESHOLD = 0.60     # >= this → no penalty
LOW_ACCURACY_THRESHOLD = 0.35      # < this → heavy penalty
SUPPRESS_THRESHOLD = 0.20          # < this → fully suppressed (weight = 0.0)
PENALTY_WEIGHT = 0.25              # weight for low-accuracy sources


def _compute_weight(accuracy_rate: Optional[float], resolved_count: int) -> float:
    """Map accuracy_rate + resolved_count to a [0.0, 1.0] reputation weight."""
    if resolved_count < MIN_RESOLVED_PREDICTIONS:
        return UNVERIFIED_WEIGHT
    if accuracy_rate is None:
        return UNVERIFIED_WEIGHT
    if accuracy_rate >= HIGH_ACCURACY_THRESHOLD:
        return 1.0
    if accuracy_rate < SUPPRESS_THRESHOLD:
        return 0.0
    if accuracy_rate < LOW_ACCURACY_THRESHOLD:
        return PENALTY_WEIGHT
    # Linear interpolation: LOW_ACCURACY_THRESHOLD → 0.5, HIGH_ACCURACY_THRESHOLD → 1.0
    ratio = (accuracy_rate - LOW_ACCURACY_THRESHOLD) / (
        HIGH_ACCURACY_THRESHOLD - LOW_ACCURACY_THRESHOLD
    )
    return round(0.5 + 0.5 * ratio, 4)


class SourceReputationEngine:
    """
    Builds and serves source reputation weights.

    Usage
    -----
    engine = SourceReputationEngine(db)
    engine.compute_reputation()          # rebuild Gold table
    weight = engine.get_weight("espn_nfl")  # look up weight
    suppressed = engine.suppressed_sources() # set of fully-suppressed source_ids
    """

    def __init__(self, db: Optional[DBManager] = None):
        self._close_db = db is None
        self.db = db if db is not None else DBManager()
        self._cache: Optional[Dict[str, float]] = None

    def close(self):
        if self._close_db:
            self.db.close()

    # ------------------------------------------------------------------
    # Compute and persist
    # ------------------------------------------------------------------

    def compute_reputation(self) -> int:
        """
        Queries resolved predictions per source, computes reputation weights,
        and writes the snapshot to gold_layer.source_reputation.

        Returns the number of source rows written.
        """
        project_id = os.environ.get("GCP_PROJECT_ID")
        now = datetime.now(timezone.utc).isoformat()

        # Per source_url domain: aggregate accuracy from resolved predictions
        # Uses NET_LOC extraction via REGEXP_EXTRACT; strips www. prefix
        sql = f"""
            CREATE OR REPLACE TABLE `{project_id}.{REPUTATION_TABLE}` AS
            WITH source_stats AS (
                SELECT
                    -- Normalise source domain: strip protocol + www.
                    REGEXP_REPLACE(
                        REGEXP_EXTRACT(l.source_url, r'https?://(?:www\\.)?([^/]+)'),
                        r'^www\\.', ''
                    )                                                          AS source_domain,
                    COUNT(*)                                                   AS total_predictions,
                    COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))   AS resolved_count,
                    COUNTIF(r.resolution_status = 'CORRECT')                   AS correct_count,
                    SAFE_DIVIDE(
                        COUNTIF(r.resolution_status = 'CORRECT'),
                        COUNTIF(r.resolution_status IN ('CORRECT', 'INCORRECT'))
                    )                                                          AS accuracy_rate,
                    AVG(r.brier_score)                                         AS avg_brier_score
                FROM `{project_id}.{LEDGER_TABLE}` l
                LEFT JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
                    ON l.prediction_hash = r.prediction_hash
                WHERE l.source_url IS NOT NULL
                GROUP BY source_domain
            )
            SELECT
                source_domain,
                total_predictions,
                resolved_count,
                correct_count,
                ROUND(accuracy_rate, 4)                                        AS accuracy_rate,
                ROUND(avg_brier_score, 4)                                      AS avg_brier_score,
                -- Python-computed weight is applied post-query; store raw inputs
                CASE
                    WHEN resolved_count < {MIN_RESOLVED_PREDICTIONS}
                        THEN {UNVERIFIED_WEIGHT}
                    WHEN accuracy_rate IS NULL
                        THEN {UNVERIFIED_WEIGHT}
                    WHEN accuracy_rate >= {HIGH_ACCURACY_THRESHOLD}
                        THEN 1.0
                    WHEN accuracy_rate < {SUPPRESS_THRESHOLD}
                        THEN 0.0
                    WHEN accuracy_rate < {LOW_ACCURACY_THRESHOLD}
                        THEN {PENALTY_WEIGHT}
                    ELSE ROUND(
                        0.5 + 0.5 * (accuracy_rate - {LOW_ACCURACY_THRESHOLD})
                              / ({HIGH_ACCURACY_THRESHOLD} - {LOW_ACCURACY_THRESHOLD}),
                        4
                    )
                END                                                             AS reputation_weight,
                CASE
                    WHEN resolved_count < {MIN_RESOLVED_PREDICTIONS} THEN 'UNVERIFIED'
                    WHEN accuracy_rate IS NULL                         THEN 'UNVERIFIED'
                    WHEN accuracy_rate < {SUPPRESS_THRESHOLD}          THEN 'SUPPRESSED'
                    WHEN accuracy_rate < {LOW_ACCURACY_THRESHOLD}      THEN 'LOW'
                    WHEN accuracy_rate < {HIGH_ACCURACY_THRESHOLD}     THEN 'MODERATE'
                    ELSE 'HIGH'
                END                                                             AS reputation_tier,
                TIMESTAMP('{now}')                                              AS computed_at
            FROM source_stats
            WHERE source_domain IS NOT NULL
            ORDER BY reputation_weight DESC, resolved_count DESC
        """
        self.db.execute(sql)
        self._cache = None  # invalidate cache after recompute

        count_df = self.db.fetch_df(
            f"SELECT COUNT(*) AS n FROM `{project_id}.{REPUTATION_TABLE}`"
        )
        n = int(count_df.iloc[0]["n"])
        logger.info(f"[source_reputation] Wrote {n} source reputation rows")
        return n

    # ------------------------------------------------------------------
    # Weight lookup (in-process cache populated from Gold table)
    # ------------------------------------------------------------------

    def _load_cache(self) -> Dict[str, float]:
        """Loads source_domain → reputation_weight from the Gold table."""
        project_id = os.environ.get("GCP_PROJECT_ID")
        try:
            df = self.db.fetch_df(
                f"SELECT source_domain, reputation_weight "
                f"FROM `{project_id}.{REPUTATION_TABLE}`"
            )
            return dict(zip(df["source_domain"], df["reputation_weight"]))
        except Exception as exc:
            logger.warning(
                f"[source_reputation] Could not load cache ({exc}); "
                "defaulting all sources to full weight"
            )
            return {}

    def get_weight(self, source_domain: str) -> float:
        """
        Returns the reputation weight for a given source domain.
        Unknown domains are treated as UNVERIFIED (weight = 1.0).
        """
        if self._cache is None:
            self._cache = self._load_cache()
        return self._cache.get(source_domain, UNVERIFIED_WEIGHT)

    def suppressed_sources(self) -> set:
        """Returns the set of source domains with weight == 0.0 (fully suppressed)."""
        if self._cache is None:
            self._cache = self._load_cache()
        return {domain for domain, w in self._cache.items() if w == 0.0}


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def extract_domain(url: str) -> str:
    """Extract normalised domain from a URL (strips protocol and www.)."""
    if not url:
        return ""
    # Remove protocol
    domain = url.split("//", 1)[-1] if "//" in url else url
    # Remove path
    domain = domain.split("/", 1)[0]
    # Strip www.
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.lower()


def compute_and_persist(db: Optional[DBManager] = None) -> int:
    """Module-level entry point used by run_daily.py."""
    engine = SourceReputationEngine(db=db)
    try:
        return engine.compute_reputation()
    finally:
        engine.close()

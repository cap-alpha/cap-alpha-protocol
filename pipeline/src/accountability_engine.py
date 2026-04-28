"""
Accountability Engine (Issue #162)

Tracks how pundits behave *after* being proven wrong. This is the 7th scoring
axis: Accountability.

Pipeline:
  gold_layer.prediction_resolutions (INCORRECT) →
    scan raw_pundit_media for subsequent content →
      LLM classification →
        gold_layer.accountability_ledger

Accountability classes:
  owns_it        — pundit references the miss and explains what they got wrong
  silent_burial  — no mention of the miss in subsequent content
  revisionism    — "What I actually said was..." reframing
  doubling_down  — "I'm still right, the outcome was fluky"
  deflection     — "Nobody could've predicted that"
  insufficient_data — not enough subsequent content to classify

Usage:
    python -m src.accountability_engine                  # scan all unclassified
    python -m src.accountability_engine --limit 20       # process N predictions
    python -m src.accountability_engine --dry-run        # preview without writing
    python -m src.accountability_engine --window-days 180  # extend scan window
    python -m src.accountability_engine --summary        # print BQ summary table
"""

import argparse
import logging
import os
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from src.db_manager import DBManager
from src.llm_provider import get_provider

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
ACCOUNTABILITY_TABLE = "gold_layer.accountability_ledger"
RAW_MEDIA_TABLE = "raw_pundit_media"

# How many days of content to scan after a prediction resolves
DEFAULT_WINDOW_DAYS = 90

# Minimum characters of subsequent content needed before LLM classification
# (below this threshold → insufficient_data without calling the LLM)
MIN_CONTENT_CHARS = 200

ACCOUNTABILITY_CLASSES = {
    "owns_it": "Pundit explicitly references the missed prediction and acknowledges the error",
    "silent_burial": "Pundit continues publishing on the same topic but never mentions the miss",
    "revisionism": "Pundit reframes what they originally said (e.g. 'What I actually meant was...')",
    "doubling_down": "Pundit still defends the prediction ('I'm still right, the outcome was fluky')",
    "deflection": "Pundit blames external factors ('Nobody could have predicted that')",
    "insufficient_data": "Not enough subsequent content from this pundit to classify their behavior",
}

ACCOUNTABILITY_PROMPT = """You are analyzing how a sports pundit behaved after one of their predictions turned out to be WRONG.

ORIGINAL PREDICTION (resolved as INCORRECT):
  Pundit: {pundit_name}
  Claim: {original_claim}
  Category: {claim_category}
  Published: {prediction_date}
  Resolved incorrect on: {resolved_at}

SUBSEQUENT CONTENT from the same pundit (published after the resolution date):
---
{subsequent_content}
---

Based solely on this subsequent content, classify the pundit's accountability behavior using ONE of these labels:

- owns_it: The pundit explicitly references the missed prediction and acknowledges they were wrong.
- silent_burial: The pundit continues covering the same topic but never mentions the miss.
- revisionism: The pundit reframes or misremembers what they originally predicted.
- doubling_down: The pundit still defends the original prediction despite it being wrong.
- deflection: The pundit blames bad luck or external factors rather than acknowledging the error.
- insufficient_data: There is not enough subsequent content to determine their behavior.

Rules:
- If the subsequent content does not mention the topic of the original prediction at all, classify as "insufficient_data".
- If the topic is mentioned but the miss is never referenced, classify as "silent_burial".
- Return ONLY the label (one word or two words joined by underscore). Nothing else.

Label:"""


@dataclass
class AccountabilityResult:
    prediction_hash: str
    pundit_id: str
    pundit_name: str
    original_claim: str
    resolution_status: str
    resolved_at: Optional[str]
    accountability_class: str
    evidence_url: Optional[str]
    evidence_snippet: Optional[str]
    window_days: int
    articles_scanned: int
    llm_model: str
    classified_at: str = ""

    def __post_init__(self):
        if not self.classified_at:
            self.classified_at = datetime.now(timezone.utc).isoformat()


def get_unclassified_incorrect_predictions(
    limit: Optional[int] = None,
    db: Optional[DBManager] = None,
) -> pd.DataFrame:
    """
    Returns INCORRECT predictions that don't yet have an accountability record.
    Sorted oldest-resolved-first so early misses get classified before recent ones.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        limit_clause = f"LIMIT {limit}" if limit else ""
        query = f"""
            SELECT
                l.prediction_hash,
                l.pundit_id,
                l.pundit_name,
                l.extracted_claim,
                l.claim_category,
                l.target_player_name,
                l.target_team,
                l.ingestion_timestamp AS prediction_ts,
                r.resolved_at
            FROM `{project_id}.{LEDGER_TABLE}` l
            JOIN `{project_id}.{RESOLUTIONS_TABLE}` r
                ON l.prediction_hash = r.prediction_hash
            LEFT JOIN `{project_id}.{ACCOUNTABILITY_TABLE}` a
                ON l.prediction_hash = a.prediction_hash
            WHERE r.resolution_status = 'INCORRECT'
              AND a.prediction_hash IS NULL
            ORDER BY r.resolved_at ASC
            {limit_clause}
        """
        return db.fetch_df(query)
    finally:
        if close_db:
            db.close()


def get_subsequent_content(
    pundit_id: str,
    after_ts: str,
    claim_subject: Optional[str],
    window_days: int,
    db: Optional[DBManager] = None,
) -> pd.DataFrame:
    """
    Fetches raw_pundit_media content from the same pundit published after
    after_ts within window_days, optionally filtered by claim_subject keyword.

    Returns DataFrame with columns: url, title, content_text, published_date
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")

        subject_filter = ""
        if claim_subject:
            safe_subject = claim_subject.replace("'", "\\'")
            subject_filter = (
                f"AND LOWER(COALESCE(content_text, '') || ' ' || COALESCE(title, ''))"
                f" LIKE LOWER('%{safe_subject}%')"
            )

        query = f"""
            SELECT
                url,
                title,
                content_text,
                published_date
            FROM `{project_id}.{RAW_MEDIA_TABLE}`
            WHERE pundit_id = '{pundit_id}'
              AND published_date > TIMESTAMP('{after_ts}')
              AND published_date <= TIMESTAMP_ADD(
                    TIMESTAMP('{after_ts}'), INTERVAL {window_days} DAY)
              {subject_filter}
            ORDER BY published_date ASC
            LIMIT 10
        """
        return db.fetch_df(query)
    finally:
        if close_db:
            db.close()


def _build_content_blob(
    rows: pd.DataFrame,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Merges multiple articles into a single text blob for the LLM.

    Returns: (content_blob, first_evidence_url, evidence_snippet)
    """
    if rows.empty:
        return "", None, None

    parts = []
    for _, row in rows.iterrows():
        title = row.get("title") or ""
        text = row.get("content_text") or ""
        date = str(row.get("published_date", ""))
        parts.append(f"[{date}] {title}\n{text[:1000]}")

    content_blob = "\n\n---\n\n".join(parts)

    evidence_url = None
    evidence_snippet = None
    for _, row in rows.iterrows():
        url = row.get("url")
        text = row.get("content_text") or ""
        if url and text:
            evidence_url = url
            evidence_snippet = text[:500]
            break

    return content_blob, evidence_url, evidence_snippet


def _normalize_class(raw: str) -> str:
    """
    Map raw LLM response to a valid accountability class.
    Falls back to insufficient_data on unrecognized output.
    """
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_").rstrip(".:,;")
    if not normalized:
        return "insufficient_data"
    valid = set(ACCOUNTABILITY_CLASSES.keys())
    if normalized in valid:
        return normalized
    # Partial match: normalized must be a non-trivial substring (len >= 4)
    if len(normalized) >= 4:
        for cls in valid:
            if cls in normalized or normalized in cls:
                return cls
    logger.warning(f"Unrecognized class: {raw!r} — defaulting to insufficient_data")
    return "insufficient_data"


def classify_accountability(
    prediction_row: pd.Series,
    window_days: int = DEFAULT_WINDOW_DAYS,
    provider=None,
    db: Optional[DBManager] = None,
) -> AccountabilityResult:
    """
    Classify how a pundit behaved after a specific INCORRECT prediction.

    1. Fetch subsequent content from the same pundit on the same topic.
    2. If insufficient content, return insufficient_data without calling LLM.
    3. Otherwise, use the LLM to classify the post-miss behavior.
    """
    if provider is None:
        provider = get_provider()

    prediction_hash = prediction_row["prediction_hash"]
    pundit_id = prediction_row["pundit_id"]
    pundit_name = prediction_row.get("pundit_name", pundit_id)
    original_claim = prediction_row.get("extracted_claim", "")
    claim_category = prediction_row.get("claim_category", "")
    resolved_at = str(prediction_row.get("resolved_at", ""))
    prediction_ts = str(prediction_row.get("prediction_ts", ""))

    claim_subject = prediction_row.get("target_player_name") or prediction_row.get(
        "target_team"
    )

    subsequent_df = get_subsequent_content(
        pundit_id=pundit_id,
        after_ts=resolved_at,
        claim_subject=claim_subject,
        window_days=window_days,
        db=db,
    )

    articles_scanned = len(subsequent_df)
    content_blob, evidence_url, evidence_snippet = _build_content_blob(subsequent_df)

    if len(content_blob) < MIN_CONTENT_CHARS:
        return AccountabilityResult(
            prediction_hash=prediction_hash,
            pundit_id=pundit_id,
            pundit_name=pundit_name,
            original_claim=original_claim,
            resolution_status="INCORRECT",
            resolved_at=resolved_at,
            accountability_class="insufficient_data",
            evidence_url=None,
            evidence_snippet=None,
            window_days=window_days,
            articles_scanned=articles_scanned,
            llm_model=provider.model,
        )

    prompt = ACCOUNTABILITY_PROMPT.format(
        pundit_name=pundit_name,
        original_claim=original_claim,
        claim_category=claim_category,
        prediction_date=prediction_ts[:10],
        resolved_at=resolved_at[:10],
        subsequent_content=content_blob[:4000],
    )

    raw_response = provider.classify(prompt)
    accountability_class = _normalize_class(raw_response)

    logger.info(
        f"Classified {prediction_hash[:16]}… ({pundit_name}): {accountability_class} "
        f"[{articles_scanned} articles scanned]"
    )

    return AccountabilityResult(
        prediction_hash=prediction_hash,
        pundit_id=pundit_id,
        pundit_name=pundit_name,
        original_claim=original_claim,
        resolution_status="INCORRECT",
        resolved_at=resolved_at,
        accountability_class=accountability_class,
        evidence_url=evidence_url,
        evidence_snippet=evidence_snippet,
        window_days=window_days,
        articles_scanned=articles_scanned,
        llm_model=provider.model,
    )


def record_accountability(
    result: AccountabilityResult, db: Optional[DBManager] = None
) -> None:
    """
    Upserts an accountability result into gold_layer.accountability_ledger.
    Uses MERGE so re-running the scanner updates stale records.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        now = datetime.now(timezone.utc).isoformat()

        def _q(s: Optional[str]) -> str:
            if s is None:
                return "NULL"
            return "'" + str(s).replace("'", "\\'")[:1000] + "'"

        merge_sql = f"""
            MERGE `{project_id}.{ACCOUNTABILITY_TABLE}` T
            USING (SELECT '{result.prediction_hash}' AS prediction_hash) S
            ON T.prediction_hash = S.prediction_hash
            WHEN MATCHED THEN UPDATE SET
                accountability_class = '{result.accountability_class}',
                evidence_url         = {_q(result.evidence_url)},
                evidence_snippet     = {_q(result.evidence_snippet)},
                window_days          = {result.window_days},
                articles_scanned     = {result.articles_scanned},
                llm_model            = '{result.llm_model}',
                classified_at        = '{now}',
                updated_at           = '{now}'
            WHEN NOT MATCHED THEN INSERT (
                prediction_hash, pundit_id, pundit_name, original_claim,
                resolution_status, resolved_at, accountability_class,
                evidence_url, evidence_snippet, window_days, articles_scanned,
                llm_model, classified_at, created_at, updated_at
            ) VALUES (
                '{result.prediction_hash}',
                '{result.pundit_id}',
                {_q(result.pundit_name)},
                {_q(result.original_claim)},
                'INCORRECT',
                {_q(result.resolved_at)},
                '{result.accountability_class}',
                {_q(result.evidence_url)},
                {_q(result.evidence_snippet)},
                {result.window_days},
                {result.articles_scanned},
                '{result.llm_model}',
                '{now}',
                '{now}',
                '{now}'
            )
        """
        db.execute(merge_sql)
    finally:
        if close_db:
            db.close()


def get_accountability_summary(db: Optional[DBManager] = None) -> pd.DataFrame:
    """
    Returns per-pundit accountability class distribution.
    Useful for the scoring layer and dashboard queries.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        query = f"""
            SELECT
                pundit_id,
                pundit_name,
                accountability_class,
                COUNT(*) AS count,
                ROUND(
                    COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY pundit_id),
                    1
                ) AS pct
            FROM `{project_id}.{ACCOUNTABILITY_TABLE}`
            WHERE accountability_class != 'insufficient_data'
            GROUP BY pundit_id, pundit_name, accountability_class
            ORDER BY pundit_id, count DESC
        """
        return db.fetch_df(query)
    finally:
        if close_db:
            db.close()


def run_accountability_scan(
    limit: Optional[int] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    dry_run: bool = False,
    db: Optional[DBManager] = None,
) -> list[AccountabilityResult]:
    """
    Main entry point: scan all unclassified INCORRECT predictions and classify them.

    Returns list of AccountabilityResults (written to BQ unless dry_run=True).
    """
    provider = get_provider()
    logger.info(
        f"Accountability scan — provider={provider.model}, "
        f"window={window_days}d, dry_run={dry_run}"
    )

    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        pending = get_unclassified_incorrect_predictions(limit=limit, db=db)
        logger.info(f"Found {len(pending)} unclassified INCORRECT predictions")

        results = []
        for _, row in pending.iterrows():
            try:
                result = classify_accountability(
                    prediction_row=row,
                    window_days=window_days,
                    provider=provider,
                    db=db,
                )
                results.append(result)

                if not dry_run:
                    record_accountability(result, db=db)
            except Exception as e:
                logger.error(
                    f"Failed to classify {row.get('prediction_hash', '?')[:16]}…: {e}"
                )
                continue

        if results:
            counts = Counter(r.accountability_class for r in results)
            logger.info(f"Classification summary: {dict(counts)}")

        return results
    finally:
        if close_db:
            db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Accountability Engine — classify pundit post-miss behavior"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Max predictions to process"
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help="Days of subsequent content to scan (default: 90)",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Classify but do not write to BigQuery"
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print accountability summary from BQ and exit",
    )
    args = parser.parse_args()

    if args.summary:
        df = get_accountability_summary()
        if df.empty:
            print("No accountability records found.")
        else:
            print(df.to_string(index=False))
    else:
        results = run_accountability_scan(
            limit=args.limit,
            window_days=args.window_days,
            dry_run=args.dry_run,
        )
        print(f"Processed {len(results)} predictions.")
        if args.dry_run:
            for r in results:
                print(
                    f"  {r.pundit_name}: {r.accountability_class} "
                    f"— {(r.original_claim or '')[:60]}"
                )

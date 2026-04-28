"""
Assertion Quality Scorer (Issue: quality eval system)

Evaluates the quality of extracted predictions in gold_layer.prediction_ledger
and writes scores to gold_layer.assertion_quality.

Quality signals (heuristic, fast, free):
  - has_player_name    (+0.2)  target_player_name is populated
  - has_specific_number (+0.2) claim contains a pick #, stat, dollar amt, win total
  - has_team           (+0.1)  target_team is populated
  - has_season_year    (+0.1)  season_year is populated
  - claim_length       (+0.1 / -0.1) 20-150 chars good; <10 or >300 penalty
  - falsifiable_verb   (+0.1)  contains will/won't/is going to/predicts/comparisons
  - is_tautology       (-0.2)  contains could/might/may/possible/etc.
  - category_match     (-0.1)  draft_pick category with no pick number in claim

Optional: llama3.1:8b (if available) for 1-sentence verdict HIGH/MEDIUM/LOW.

Usage:
    python -m src.assertion_quality --all          # score all unscored predictions
    python -m src.assertion_quality --limit 100    # score up to N
    python -m src.assertion_quality --force        # re-score already-scored
    python -m src.assertion_quality --dry-run      # preview, no writes
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

LEDGER_TABLE = "gold_layer.prediction_ledger"
QUALITY_TABLE = "gold_layer.assertion_quality"

# Heuristic weights
W_PLAYER = 0.2
W_NUMBER = 0.2
W_TEAM = 0.1
W_YEAR = 0.1
W_LENGTH_GOOD = 0.1
W_LENGTH_BAD = -0.1
W_FALSIFIABLE = 0.1
W_TAUTOLOGY = -0.2
W_CATEGORY_MISMATCH = -0.1

# Patterns
_NUMBER_RE = re.compile(
    r"\b(\d+(?:st|nd|rd|th)?\s*(?:overall|pick|round|wins?|losses?|touchdowns?|yards?|million|thousand|sacks?|targets?|catches?|starts?|goals?|points?|assists?)|\$[\d,.]+|\d+%|\d{1,3}(?:\.\d+)?(?:\s*(?:mvp|pro\s*bowl|first\s*team|second\s*team))?)",
    re.IGNORECASE,
)
_PICK_NUMBER_RE = re.compile(
    r"\b(?:number\s*)?#?\s*\d+\s*(?:overall|pick)|pick\s*(?:number\s*)?#?\s*\d+|\b\d+(?:st|nd|rd|th)\s+(?:overall|pick)",
    re.IGNORECASE,
)
_FALSIFIABLE_RE = re.compile(
    r"\b(will\b|won'?t\b|is\s+going\s+to\b|predicts?\b|project(?:s|ed)?\b|expect(?:s|ed)?\b|shall\b|should\b|select(?:s|ed)?\b|draft(?:s|ed)?\b|sign(?:s|ed)?\b|cut(?:s)?\b|retire(?:s|d)?\b|over\s+\d|under\s+\d|more\s+than\s+\d|less\s+than\s+\d|at\s+least\s+\d|no\s+more\s+than\s+\d|exceed(?:s|ed)?\b|miss(?:es|ed)?\s+(?:the\s+)?playoffs?\b|make(?:s)?\s+(?:the\s+)?playoffs?\b)",
    re.IGNORECASE,
)
_TAUTOLOGY_RE = re.compile(
    r"\b(could\b|might\b|may\b|possible\b|possibly\b|perhaps\b|maybe\b|potentially\b|seems?\s+like\b|appears?\s+to\b|tend(?:s)?\s+to\b|often\b|usually\b|sometimes\b)",
    re.IGNORECASE,
)


def _heuristic_signals(row: dict) -> dict:
    """Compute individual heuristic boolean flags for a prediction row."""
    claim = str(row.get("extracted_claim") or row.get("raw_assertion_text") or "")
    player = row.get("target_player_name")
    team = row.get("target_team")
    year = row.get("season_year")
    category = str(row.get("claim_category") or "").lower()

    length = len(claim)

    signals = {
        "has_player_name": bool(
            player and str(player).strip() not in ("", "None", "null")
        ),
        "has_specific_number": bool(_NUMBER_RE.search(claim)),
        "has_team": bool(team and str(team).strip() not in ("", "None", "null")),
        "has_season_year": bool(
            year and str(year).strip() not in ("", "None", "null", "0")
        ),
        "claim_length_good": 20 <= length <= 150,
        "claim_length_bad": length < 10 or length > 300,
        "falsifiable_verb": bool(_FALSIFIABLE_RE.search(claim)),
        "is_tautology": bool(_TAUTOLOGY_RE.search(claim)),
        "category_mismatch": (
            category == "draft_pick" and not _PICK_NUMBER_RE.search(claim)
        ),
    }
    return signals


def score_prediction(row: dict) -> tuple[float, str, dict]:
    """
    Returns (score 0.0–1.0, tier string, signals dict).
    """
    signals = _heuristic_signals(row)

    score = 0.0
    if signals["has_player_name"]:
        score += W_PLAYER
    if signals["has_specific_number"]:
        score += W_NUMBER
    if signals["has_team"]:
        score += W_TEAM
    if signals["has_season_year"]:
        score += W_YEAR
    if signals["claim_length_good"]:
        score += W_LENGTH_GOOD
    if signals["claim_length_bad"]:
        score += W_LENGTH_BAD
    if signals["falsifiable_verb"]:
        score += W_FALSIFIABLE
    if signals["is_tautology"]:
        score += W_TAUTOLOGY
    if signals["category_mismatch"]:
        score += W_CATEGORY_MISMATCH

    # Clamp to [0.0, 1.0]
    score = round(max(0.0, min(1.0, score)), 4)

    tier = "HIGH" if score >= 0.7 else ("MEDIUM" if score >= 0.4 else "LOW")
    return score, tier, signals


# ---------------------------------------------------------------------------
# Optional: small LLM verdict via Ollama
# ---------------------------------------------------------------------------

_SMALL_MODEL: Optional[str] = None
_SMALL_MODEL_CHECKED = False

PREFERRED_SMALL_MODELS = ["llama3.1:8b", "llama3:latest", "phi3:mini", "llama3.2:3b"]


def _detect_small_model() -> Optional[str]:
    """Return the best available small Ollama model, or None."""
    global _SMALL_MODEL, _SMALL_MODEL_CHECKED
    if _SMALL_MODEL_CHECKED:
        return _SMALL_MODEL
    _SMALL_MODEL_CHECKED = True
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().splitlines()
        available = [line.split()[0] for line in lines[1:] if line.strip()]
        for preferred in PREFERRED_SMALL_MODELS:
            for model in available:
                if preferred in model or model.startswith(preferred.split(":")[0]):
                    _SMALL_MODEL = model
                    logger.info(f"Small LLM available: {_SMALL_MODEL}")
                    return _SMALL_MODEL
    except Exception as e:
        logger.warning(f"Could not detect small Ollama model: {e}")
    logger.info("No small LLM found — heuristics-only mode")
    return None


def _llm_verdict(claim: str, model: str) -> Optional[str]:
    """Ask the small model for HIGH/MEDIUM/LOW quality verdict. Returns None on failure."""
    prompt = (
        "Is this NFL prediction assertion falsifiable and specific? "
        "Answer only with one word: HIGH, MEDIUM, or LOW.\n\n"
        f'Assertion: "{claim}"'
    )
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=30,
        )
        verdict = result.stdout.strip().upper()
        # Accept only clean single-word responses
        for word in ["HIGH", "MEDIUM", "LOW"]:
            if word in verdict:
                return word
    except Exception as e:
        logger.debug(f"LLM verdict failed for model {model}: {e}")
    return None


# ---------------------------------------------------------------------------
# BigQuery table creation
# ---------------------------------------------------------------------------

QUALITY_TABLE_SCHEMA = [
    {"name": "prediction_hash", "type": "STRING", "mode": "REQUIRED"},
    {"name": "quality_score", "type": "FLOAT64", "mode": "NULLABLE"},
    {"name": "quality_tier", "type": "STRING", "mode": "NULLABLE"},
    {"name": "heuristic_signals", "type": "STRING", "mode": "NULLABLE"},
    {"name": "llm_verdict", "type": "STRING", "mode": "NULLABLE"},
    {"name": "evaluator_model", "type": "STRING", "mode": "NULLABLE"},
    {"name": "evaluated_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
]


def ensure_quality_table(db) -> None:
    """Create gold_layer.assertion_quality if it doesn't exist."""
    from google.cloud import bigquery

    project_id = os.environ.get("GCP_PROJECT_ID")
    dataset_id = "gold_layer"
    table_id = "assertion_quality"
    full_ref = f"{project_id}.{dataset_id}.{table_id}"

    try:
        db.client.get_table(full_ref)
        logger.info(f"Table {full_ref} already exists.")
        return
    except Exception:
        pass  # table doesn't exist, create it

    schema = [
        bigquery.SchemaField(col["name"], col["type"], mode=col["mode"])
        for col in QUALITY_TABLE_SCHEMA
    ]
    table = bigquery.Table(full_ref, schema=schema)
    db.client.create_table(table)
    logger.info(f"Created table {full_ref}")


# ---------------------------------------------------------------------------
# Main scoring run
# ---------------------------------------------------------------------------


def run_scoring(
    db,
    limit: Optional[int] = None,
    force: bool = False,
    dry_run: bool = False,
    use_llm: bool = True,
) -> dict:
    """
    Score predictions from prediction_ledger and write to assertion_quality.
    Returns distribution stats.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    ledger_full = f"`{project_id}.{LEDGER_TABLE}`"
    quality_full = f"`{project_id}.{QUALITY_TABLE}`"

    if not dry_run:
        ensure_quality_table(db)

    # Build fetch query
    if force:
        fetch_sql = f"""
            SELECT
                prediction_hash,
                extracted_claim,
                raw_assertion_text,
                claim_category,
                target_player_name,
                target_team,
                season_year
            FROM {ledger_full}
            ORDER BY ingestion_timestamp DESC
        """
    else:
        fetch_sql = f"""
            SELECT
                l.prediction_hash,
                l.extracted_claim,
                l.raw_assertion_text,
                l.claim_category,
                l.target_player_name,
                l.target_team,
                l.season_year
            FROM {ledger_full} l
            LEFT JOIN {quality_full} q
                ON l.prediction_hash = q.prediction_hash
            WHERE q.prediction_hash IS NULL
            ORDER BY l.ingestion_timestamp DESC
        """

    if limit:
        fetch_sql = fetch_sql.rstrip() + f"\nLIMIT {limit}"

    logger.info("Fetching predictions to score...")
    df = db.fetch_df(fetch_sql)
    logger.info(f"Found {len(df)} predictions to score")

    if df.empty:
        logger.info("Nothing to score.")
        return {"high": 0, "medium": 0, "low": 0, "total": 0}

    # Detect small LLM
    small_model = _detect_small_model() if use_llm else None
    evaluator_model = small_model if small_model else "heuristic_v1"

    results = []
    now = datetime.now(timezone.utc)

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        score, tier, signals = score_prediction(row_dict)

        # Optional LLM verdict
        llm_verdict = None
        if small_model:
            claim = str(
                row_dict.get("extracted_claim")
                or row_dict.get("raw_assertion_text")
                or ""
            )
            if claim.strip():
                llm_verdict = _llm_verdict(claim, small_model)

        results.append(
            {
                "prediction_hash": row_dict["prediction_hash"],
                "quality_score": score,
                "quality_tier": tier,
                "heuristic_signals": json.dumps(signals),
                "llm_verdict": llm_verdict,
                "evaluator_model": evaluator_model,
                "evaluated_at": now,
            }
        )

    results_df = pd.DataFrame(results)

    # Distribution stats
    tier_counts = results_df["quality_tier"].value_counts().to_dict()
    stats = {
        "total": len(results_df),
        "high": tier_counts.get("HIGH", 0),
        "medium": tier_counts.get("MEDIUM", 0),
        "low": tier_counts.get("LOW", 0),
    }

    if dry_run:
        logger.info("[DRY RUN] Would write %d quality scores", len(results_df))
        _print_distribution(stats, results_df, df)
        return stats

    # Write to BQ via append — use direct BQ client to target gold_layer dataset
    from google.cloud import bigquery

    project_id = os.environ.get("GCP_PROJECT_ID")
    table_ref = f"{project_id}.gold_layer.assertion_quality"

    # Ensure evaluated_at is a proper pandas datetime column (not object dtype)
    results_df["evaluated_at"] = pd.to_datetime(results_df["evaluated_at"], utc=True)

    if force:
        # In force mode, delete existing rows first by re-creating via merge pattern:
        # Since this is a fresh quality table, WRITE_TRUNCATE for force re-score
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_TRUNCATE",
            schema=[
                bigquery.SchemaField("prediction_hash", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("quality_score", "FLOAT64"),
                bigquery.SchemaField("quality_tier", "STRING"),
                bigquery.SchemaField("heuristic_signals", "STRING"),
                bigquery.SchemaField("llm_verdict", "STRING"),
                bigquery.SchemaField("evaluator_model", "STRING"),
                bigquery.SchemaField("evaluated_at", "TIMESTAMP"),
            ],
        )
    else:
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            schema=[
                bigquery.SchemaField("prediction_hash", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("quality_score", "FLOAT64"),
                bigquery.SchemaField("quality_tier", "STRING"),
                bigquery.SchemaField("heuristic_signals", "STRING"),
                bigquery.SchemaField("llm_verdict", "STRING"),
                bigquery.SchemaField("evaluator_model", "STRING"),
                bigquery.SchemaField("evaluated_at", "TIMESTAMP"),
            ],
        )

    job = db.client.load_table_from_dataframe(
        results_df, table_ref, job_config=job_config
    )
    job.result()
    logger.info(f"Wrote {len(results_df)} quality scores to {table_ref}")

    _print_distribution(stats, results_df, df)
    return stats


def _print_distribution(
    stats: dict, results_df: pd.DataFrame, source_df: pd.DataFrame
) -> None:
    """Print quality distribution and samples."""
    print("\n" + "=" * 60)
    print("ASSERTION QUALITY DISTRIBUTION")
    print("=" * 60)
    print(
        f"  HIGH  (>=0.7):  {stats['high']:4d}  ({100 * stats['high'] / max(stats['total'], 1):.1f}%)"
    )
    print(
        f"  MEDIUM (0.4-0.7): {stats['medium']:4d}  ({100 * stats['medium'] / max(stats['total'], 1):.1f}%)"
    )
    print(
        f"  LOW   (<0.4):   {stats['low']:4d}  ({100 * stats['low'] / max(stats['total'], 1):.1f}%)"
    )
    print(f"  TOTAL:          {stats['total']:4d}")
    print("=" * 60)

    # Samples: merge scores back with claims
    merged = results_df.merge(
        source_df[["prediction_hash", "extracted_claim", "raw_assertion_text"]],
        on="prediction_hash",
        how="left",
    )
    merged["display_claim"] = merged["extracted_claim"].fillna(
        merged["raw_assertion_text"]
    )

    high_samples = merged[merged["quality_tier"] == "HIGH"].nlargest(5, "quality_score")
    low_samples = merged[merged["quality_tier"] == "LOW"].nsmallest(5, "quality_score")

    print("\nSAMPLE HIGH QUALITY predictions:")
    for _, r in high_samples.iterrows():
        print(f"  [{r['quality_score']:.2f}] {str(r['display_claim'])[:120]}")

    print("\nSAMPLE LOW QUALITY predictions:")
    for _, r in low_samples.iterrows():
        print(f"  [{r['quality_score']:.2f}] {str(r['display_claim'])[:120]}")
    print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Score assertion quality")
    parser.add_argument(
        "--all", action="store_true", help="Score all unscored predictions"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Maximum predictions to score"
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-score already-scored predictions"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without writing to BQ"
    )
    parser.add_argument(
        "--no-llm", action="store_true", help="Skip optional small LLM pass"
    )
    args = parser.parse_args()

    # Import here so module is importable without credentials for unit tests
    from src.db_manager import DBManager

    with DBManager() as db:
        stats = run_scoring(
            db=db,
            limit=args.limit,
            force=args.force,
            dry_run=args.dry_run,
            use_llm=not args.no_llm,
        )

    return stats


if __name__ == "__main__":
    main()

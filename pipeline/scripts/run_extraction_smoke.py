"""
Extraction smoke test for the CI pre-merge gate (Issue #596).

Executes a real Gemini API call on a fixed 2-paragraph transcript fixture,
writes results to a CI-only BigQuery dataset (silver_v2_claims_ci_smoke),
and asserts the required invariants:
  - at least 1 utterance extracted
  - all rows have non-NULL speech_act_type, testability_score, domain

Exit codes:
  0 — smoke test passed
  1 — smoke test failed (reason printed to stderr)
"""

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd
from google.cloud import bigquery

from src.assertion_extractor import (
    VALID_SPEECH_ACT_TYPES,
    compute_testability_score,
    extract_assertions,
)
from src.llm_provider import get_provider

CI_TABLE = "raw_utterance"
DOMAIN = "sports.nfl"

_SCHEMA = [
    bigquery.SchemaField("utterance_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source_doc_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("speaker_entity_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("uttered_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("text", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("speech_act_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("testability_score", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("resolution_horizon", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("domain", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("extraction_confidence", "FLOAT64", mode="REQUIRED"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]


def _ensure_ci_table(client: bigquery.Client, project_id: str, dataset_id: str) -> None:
    dataset_ref = bigquery.Dataset(f"{project_id}.{dataset_id}")
    dataset_ref.description = "CI-only smoke test dataset — rows expire after 1 day."
    client.create_dataset(dataset_ref, exists_ok=True)

    table_ref = f"{project_id}.{dataset_id}.{CI_TABLE}"
    table = bigquery.Table(table_ref, schema=_SCHEMA)
    # 1-day partition expiration keeps CI storage costs near zero
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="uttered_at",
        expiration_ms=24 * 60 * 60 * 1000,
    )
    client.create_table(table, exists_ok=True)


def _build_rows(utterances: list[dict], now: datetime) -> list[dict]:
    rows = []
    for u in utterances:
        subscores = u.get("testability_subscores") or {}
        score = (
            compute_testability_score(subscores)
            if subscores
            else max(0.0, min(1.0, float(u.get("testability_score", 0.0) or 0.0)))
        )
        sat = u.get("speech_act_type", "commentary")
        if sat not in VALID_SPEECH_ACT_TYPES:
            sat = "commentary"
        rows.append(
            {
                "utterance_id": str(uuid.uuid4()),
                "source_doc_id": "smoke_test_fixture",
                "speaker_entity_id": "smoke_test_speaker",
                "uttered_at": now,
                "text": str(u.get("text", ""))[:4000],
                "speech_act_type": sat,
                "testability_score": score,
                "resolution_horizon": None,
                "domain": DOMAIN,
                "extraction_confidence": max(
                    0.0, min(1.0, float(u.get("extraction_confidence", score) or score))
                ),
                "created_at": now,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction smoke test (Issue #596)")
    parser.add_argument("--fixture", required=True, help="Path to transcript fixture")
    parser.add_argument(
        "--dataset", default="silver_v2_claims_ci_smoke", help="CI BQ dataset name"
    )
    args = parser.parse_args()

    fixture_path = Path(args.fixture)
    if not fixture_path.exists():
        print(f"FATAL: fixture not found: {fixture_path}", file=sys.stderr)
        return 1

    transcript = fixture_path.read_text().strip()
    if not transcript:
        print("FATAL: fixture file is empty", file=sys.stderr)
        return 1

    project_id = os.environ.get("GCP_PROJECT_ID", "")
    if not project_id:
        print("FATAL: GCP_PROJECT_ID env var is required", file=sys.stderr)
        return 1

    provider_name = os.environ.get("LLM_EXTRACTION_PROVIDER", "default")
    model_name = os.environ.get("LLM_EXTRACTION_MODEL", "default")
    print(f"Provider: {provider_name} / {model_name}")

    try:
        provider = get_provider("extraction")
    except Exception as exc:
        print(f"FATAL: could not initialize LLM provider: {exc}", file=sys.stderr)
        return 1

    print("Extracting from fixture…")
    result = extract_assertions(
        content_hash="smoke_test_fixture",
        text=transcript,
        provider=provider,
        allow_historical=True,
    )

    utterances = result.utterances or []
    print(f"Extracted {len(utterances)} utterance(s).")

    if not utterances:
        print(
            "FATAL: 0 utterances extracted — LLM call may have failed or returned empty output",
            file=sys.stderr,
        )
        return 1

    mem_failures = []
    for i, u in enumerate(utterances):
        if not u.get("speech_act_type"):
            mem_failures.append(f"utterance[{i}]: speech_act_type is NULL/empty")
        if u.get("testability_score") is None:
            mem_failures.append(f"utterance[{i}]: testability_score is NULL")

    if mem_failures:
        print("FATAL: in-memory field assertion failures:", file=sys.stderr)
        for msg in mem_failures:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print("In-memory assertions passed.")

    client = bigquery.Client(project=project_id)
    _ensure_ci_table(client, project_id, args.dataset)

    now = datetime.now(timezone.utc)
    rows = _build_rows(utterances, now)
    df = pd.DataFrame(rows)
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str)
    df["resolution_horizon"] = None  # restore nullable after astype

    table_ref = f"{project_id}.{args.dataset}.{CI_TABLE}"
    job = client.load_table_from_dataframe(
        df, table_ref, job_config=bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
    )
    job.result()
    print(f"Wrote {len(rows)} row(s) to {table_ref}.")

    verify_query = f"""
        SELECT
            COUNT(*)                                                   AS total,
            COUNTIF(speech_act_type IS NULL OR speech_act_type = '')   AS null_sat,
            COUNTIF(testability_score IS NULL)                         AS null_score,
            COUNTIF(domain IS NULL OR domain = '')                     AS null_domain
        FROM `{table_ref}`
        WHERE created_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE)
    """
    bq_row = next(iter(client.query(verify_query).result()))
    total, null_sat, null_score, null_domain = (
        bq_row["total"],
        bq_row["null_sat"],
        bq_row["null_score"],
        bq_row["null_domain"],
    )

    if total == 0:
        print("FATAL: BQ verification found 0 rows in the last 5 minutes", file=sys.stderr)
        return 1

    bq_failures = []
    if null_sat:
        bq_failures.append(f"{null_sat}/{total} rows have NULL speech_act_type")
    if null_score:
        bq_failures.append(f"{null_score}/{total} rows have NULL testability_score")
    if null_domain:
        bq_failures.append(f"{null_domain}/{total} rows have NULL domain")

    if bq_failures:
        print("FATAL: BQ invariant violations:", file=sys.stderr)
        for msg in bq_failures:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print(f"OK: {total} row(s) verified in BQ — all required fields non-NULL.")
    print("Extraction smoke test PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

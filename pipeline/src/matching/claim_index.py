"""
Stage-1 retrieval funnel: claim embedding index + candidate retrieval --
Issue #1133 (#1129 spec §1 "Architecture — two-stage retrieval funnel",
Decision 8).

Builds and queries `silver_v2_claims.claim_embedding` (migration 031): one
row per (claim_id, model_id), embedding `raw_utterance.text` for the same
claim <-> raw_utterance join `src.resolvers.silver_v2_resolver
.select_due_claims()` uses.

"Active" claims (this module's embedding corpus) = claims with no row yet
in `silver_v2_claims.resolution`. Once a claim is resolved there is nothing
left for Stage-1 retrieval to match it against future news for -- excluding
resolved claims from the embedding corpus is deliberate scope, not an
oversight, and keeps the corpus (and therefore every `retrieve_candidates`
cosine sweep) bounded to claims that can actually still use a match.

Two entry points:
  - build_claim_embeddings(db)              -- idempotent batch embed + write.
  - retrieve_candidates(db, event_text, k)  -- Stage-1 candidate generation:
    embed one news event, brute-force cosine against every stored claim
    embedding, return the top-K (claim_id, score) pairs.

Brute-force numpy cosine is a DELIBERATE choice for this slice, not an
oversight: at the ~1-10k claim scale (741 NFL claims per #1129 Decision 9's
first slice; low thousands corpus-wide post-bridge-migration), a full
cosine sweep over stored vectors is low-single-digit milliseconds and adds
zero infra to run or operate. A real vector index (BigQuery VECTOR INDEX /
ScaNN / FAISS) is a later optimization once corpus size or query volume
actually warrants it -- tracked as a follow-up in the #1129 spec's §9
("Vector-index infra for Stage-1 retrieval"), not built speculatively here.

Explicitly OUT OF SCOPE for this module (Stage-1 / Stage-2 boundary, #1133):
  - Any LLM call, adjudication, or writing to silver_v2_claims.resolution.
    retrieve_candidates() only ranks candidates; nothing here decides
    resolve/contradict/no-match. That is `llm_judge_silver.py`'s job (being
    enhanced in parallel elsewhere -- not touched by this module).
  - Wiring into resolve_daily.py, the scheduling engine, or any scheduled
    workflow. Nothing here is called from run_daily.py yet.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from google.cloud import bigquery

from src.matching.embed import DEFAULT_MODEL_ID, embed_texts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Table references (bare dataset.table, no project/backtick qualification --
# matches silver_v2_resolver.py's convention so the same query text runs
# unchanged against BigQuery and against a DuckDB test double).
# ---------------------------------------------------------------------------

CLAIM_TABLE = "silver_v2_claims.claim"
RAW_UTTERANCE_TABLE = "silver_v2_claims.raw_utterance"
RESOLUTION_TABLE = "silver_v2_claims.resolution"
CLAIM_EMBEDDING_TABLE = "silver_v2_claims.claim_embedding"


# ---------------------------------------------------------------------------
# build_claim_embeddings
# ---------------------------------------------------------------------------


def _unembedded_active_claims(db: Any, model_id: str) -> pd.DataFrame:
    """
    "Active, not-yet-embedded-at-model_id" claims: claim_id + claim_text
    (via the claim -> raw_utterance join), excluding claims that already
    have a resolution and excluding claims that already have a
    claim_embedding row for `model_id`.

    This single anti-join is what makes build_claim_embeddings() idempotent
    (see module docstring): a claim row in silver_v2_claims.claim is
    immutable once `ledger_locked_at` passes (migration 016), so there is
    no in-place text mutation to detect -- "changed" reduces to "not yet
    embedded under this model_id". Re-running with the same model_id after
    a prior successful run returns 0 rows here (true no-op); pointing
    DEFAULT_MODEL_ID at a new model re-embeds every active claim under the
    new model_id without touching or duplicating old rows for the old one.
    """
    query = f"""
        SELECT
            c.claim_id      AS claim_id,
            ANY_VALUE(u.text) AS claim_text
        FROM {CLAIM_TABLE} c
        LEFT JOIN {RAW_UTTERANCE_TABLE} u
            ON u.utterance_id = c.utterance_id
        WHERE NOT EXISTS (
            SELECT 1 FROM {RESOLUTION_TABLE} res WHERE res.claim_id = c.claim_id
        )
        AND NOT EXISTS (
            SELECT 1 FROM {CLAIM_EMBEDDING_TABLE} ce
            WHERE ce.claim_id = c.claim_id AND ce.model_id = @model_id
        )
        GROUP BY c.claim_id
    """
    return db.fetch_df(
        query,
        query_parameters=[
            bigquery.ScalarQueryParameter("model_id", "STRING", model_id)
        ],
    )


def build_claim_embeddings(
    db: Any,
    model_id: str = DEFAULT_MODEL_ID,
    now: Optional[datetime] = None,
) -> dict:
    """
    Idempotent batch embed: find active claims not yet embedded under
    `model_id`, embed their raw_utterance text via
    `src.matching.embed.embed_texts`, append one row per successfully
    embedded claim to silver_v2_claims.claim_embedding.

    Always returns a dict with checked/embedded/skipped keys (0 when
    nothing happened) -- mirrors silver_v2_resolver.run_resolution_pass()'s
    summary contract (see that module's regression-guard test for why a
    summary must never be missing a key an upstream aggregator expects).

    `checked` = claims found by the anti-join (candidates for this run).
    `skipped` = candidates with NULL/empty claim_text -- defensive; should
    not happen since raw_utterance.text is NOT NULL, but a claim whose
    utterance_id FK is somehow dangling must never crash the whole batch.
    """
    embedded_at = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)

    candidates = _unembedded_active_claims(db, model_id)
    checked = len(candidates)
    if checked == 0:
        return {"checked": 0, "embedded": 0, "skipped": 0}

    valid_mask = candidates["claim_text"].apply(
        lambda t: isinstance(t, str) and t.strip() != ""
    )
    skipped = int((~valid_mask).sum())
    if skipped:
        logger.warning(
            "build_claim_embeddings: skipping %d claim(s) with missing/empty "
            "claim_text",
            skipped,
        )

    valid = candidates[valid_mask]
    if valid.empty:
        return {"checked": checked, "embedded": 0, "skipped": skipped}

    claim_ids = valid["claim_id"].tolist()
    vectors = embed_texts(valid["claim_text"].tolist(), model_id=model_id)

    rows = [
        {
            "claim_id": claim_id,
            "embedding": vector,
            "model_id": model_id,
            "embedded_at": embedded_at,
        }
        for claim_id, vector in zip(claim_ids, vectors)
    ]
    out_df = pd.DataFrame(rows)
    out_df["embedded_at"] = pd.to_datetime(out_df["embedded_at"], utc=True)
    db.append_dataframe_to_table(out_df, CLAIM_EMBEDDING_TABLE)

    logger.info(
        "build_claim_embeddings: embedded=%d skipped=%d model_id=%s",
        len(rows),
        skipped,
        model_id,
    )
    return {"checked": checked, "embedded": len(rows), "skipped": skipped}


# ---------------------------------------------------------------------------
# retrieve_candidates
# ---------------------------------------------------------------------------


def retrieve_candidates(
    db: Any,
    event_text: str,
    k: int = 10,
    model_id: str = DEFAULT_MODEL_ID,
) -> list[tuple[str, float]]:
    """
    Stage-1 retrieval: embed `event_text`, brute-force cosine similarity
    against every stored silver_v2_claims.claim_embedding row for
    `model_id`, return the top-K (claim_id, score) pairs sorted by score
    descending (ties broken by claim_id ascending, for deterministic
    output and deterministic tests).

    Brute-force numpy, not a vector index -- see module docstring.

    Returns `[]` if there are no stored embeddings for `model_id`, if
    `k <= 0`, or if `event_text` embeds to an all-zero vector (defensive;
    fastembed's models don't produce these in practice, but
    division-by-zero on the cosine norm must never raise here).
    """
    if k <= 0:
        return []

    stored = db.fetch_df(
        f"""
        SELECT claim_id, embedding
        FROM {CLAIM_EMBEDDING_TABLE}
        WHERE model_id = @model_id
        """,
        query_parameters=[
            bigquery.ScalarQueryParameter("model_id", "STRING", model_id)
        ],
    )
    if stored.empty:
        return []

    [event_vector] = embed_texts([event_text], model_id=model_id)
    event_arr = np.asarray(event_vector, dtype=np.float64)
    event_norm = np.linalg.norm(event_arr)
    if event_norm == 0.0:
        return []

    claim_ids = stored["claim_id"].tolist()
    matrix = np.asarray(stored["embedding"].tolist(), dtype=np.float64)
    matrix_norms = np.linalg.norm(matrix, axis=1)

    with np.errstate(invalid="ignore", divide="ignore"):
        scores = (matrix @ event_arr) / (matrix_norms * event_norm)
    scores = np.nan_to_num(scores, nan=0.0, posinf=0.0, neginf=0.0)

    order = sorted(
        range(len(claim_ids)),
        key=lambda i: (-scores[i], claim_ids[i]),
    )[:k]
    return [(claim_ids[i], float(scores[i])) for i in order]

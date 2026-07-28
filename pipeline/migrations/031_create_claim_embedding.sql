-- Migration 031: silver_v2_claims.claim_embedding — Stage-1 retrieval funnel vector store
-- Issue: #1133 (#1129 spec §1 "Architecture — two-stage retrieval funnel", Decision 8)
-- backfill: none — new table, first write is pipeline/src/matching/claim_index.py
--   :build_claim_embeddings() run manually/on-schedule; no existing data to backfill.
--
-- Stage 1 of the news->claim retrieval funnel embeds every active claim once,
-- embeds each incoming news event, and does brute-force cosine top-K to find
-- candidate (claim, event) pairs for Stage-2 LLM adjudication (out of scope
-- here -- see pipeline/src/matching/claim_index.py).
--
-- One row per (claim_id, model_id): re-embedding a claim under a NEW
-- model_id inserts an additional row rather than overwriting the old one,
-- so switching embedding models never destroys the ability to compare
-- against the prior model's vectors. Written by
-- pipeline/src/matching/claim_index.py:build_claim_embeddings(); read by
-- retrieve_candidates(). Additive only -- no existing tables touched.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/031_create_claim_embedding.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.claim_embedding`
(
  claim_id     STRING         NOT NULL  OPTIONS(description="FK to silver_v2_claims.claim.claim_id being embedded."),
  embedding    ARRAY<FLOAT64> NOT NULL  OPTIONS(description="Dense embedding vector of the claim's raw_utterance.text, produced by model_id. 384-dim for the default model_id BAAI/bge-small-en-v1.5 -- see pipeline/src/matching/embed.py."),
  model_id     STRING         NOT NULL  OPTIONS(description="Embedding model identifier, e.g. BAAI/bge-small-en-v1.5. Part of this table's effective key: one row per (claim_id, model_id); re-embedding under a new model_id inserts a NEW row rather than overwriting the old one, so old vectors are never silently lost on a model upgrade."),
  embedded_at  TIMESTAMP      NOT NULL  OPTIONS(description="UTC wall-clock time this embedding was computed.")
)
CLUSTER BY claim_id, model_id
OPTIONS (
  description = "Stage-1 retrieval funnel vector store (#1129 spec §1 / #1133). Brute-force cosine over these vectors is Stage-1 candidate generation for the news->claim matching funnel -- a proper vector index (BigQuery VECTOR INDEX / ScaNN) is a later optimization once corpus size warrants it, not built here. Not partitioned: expected corpus size is low thousands of active (unresolved) claims, and the dominant read pattern (retrieve_candidates()) scans the whole table per query, so date-partitioning would not help pruning. Written by pipeline/src/matching/claim_index.py:build_claim_embeddings(), read by retrieve_candidates()."
);

-- ── Verification queries (copy-paste into BigQuery console to confirm) ─────────
--
-- Confirm the table exists with the right columns/types:
--   SELECT column_name, data_type, is_nullable
--   FROM `{project_id}.silver_v2_claims.INFORMATION_SCHEMA.COLUMNS`
--   WHERE table_name = 'claim_embedding'
--   ORDER BY column_name;
--
-- Confirm additive-only (table starts empty; no other table's row count changes):
--   SELECT COUNT(*) AS total_rows FROM `{project_id}.silver_v2_claims.claim_embedding`;
--   -- expect 0 immediately after this migration runs, before the first
--   -- build_claim_embeddings() call.
--
-- After running build_claim_embeddings() once, sanity-check coverage vs. the
-- active (unresolved) claim corpus it should have embedded:
--   SELECT
--     (SELECT COUNT(DISTINCT claim_id) FROM `{project_id}.silver_v2_claims.claim_embedding`)
--       AS embedded_claims,
--     (SELECT COUNT(*) FROM `{project_id}.silver_v2_claims.claim` c
--       WHERE NOT EXISTS (
--         SELECT 1 FROM `{project_id}.silver_v2_claims.resolution` r
--         WHERE r.claim_id = c.claim_id
--       )) AS active_claims;
--   -- embedded_claims should equal active_claims (modulo any claims with
--   -- NULL/empty raw_utterance.text, which build_claim_embeddings() skips
--   -- and logs a warning for -- see its docstring).
--
-- Confirm no (claim_id, model_id) duplicates (idempotency guarantee):
--   SELECT claim_id, model_id, COUNT(*) AS n
--   FROM `{project_id}.silver_v2_claims.claim_embedding`
--   GROUP BY claim_id, model_id
--   HAVING COUNT(*) > 1;
--   -- expect 0 rows.

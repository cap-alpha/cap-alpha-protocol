-- Migration: 030_add_claim_scheduling_columns
-- Issue: #1129 Phase 1 — Scheduling engine (IMPLEMENTATION SPEC v1, §2 "Scheduling math")
-- Description: Adds the 3 columns the scheduling priority engine
--   (pipeline/src/scheduling/priority.py) needs to persist its output per claim:
--     - priority_score: last-computed P = max(window_proximity, visibility, 0.7*prominence)
--     - next_check_at:  when resolve_daily should next re-check this claim
--     - attempt:        consecutive no-change count, drives backoff (base[attempt] * V)
--
-- Additive only — no backfill logic here. Per spec §5, the initial schedule for
-- the silver_v2 corpus cutover (all migrated rows get next_check_at = now,
-- backoff starting from run 2) is a separate P0 concern, not part of this
-- column-add migration. Columns are nullable; NULL next_check_at simply means
-- "not yet scheduled."
--
-- Target table: silver_v2_claims.claim is the scheduling engine's source of
-- truth per spec §5 ("silver_v2_claims.claim is the single source of truth,
-- keyed on stable claim_id. Resolvers rewritten to read it.").

ALTER TABLE `{project_id}.silver_v2_claims.claim`
  ADD COLUMN IF NOT EXISTS priority_score FLOAT64
    OPTIONS(description="Last-computed scheduling priority P = max(window_proximity, visibility, 0.7*prominence), in [0,1]. See pipeline/src/scheduling/priority.py (#1129 spec §2). NULL until the scheduling engine is wired into resolve_daily."),
  ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMP
    OPTIONS(description="Next scheduled resolver check time for this claim, computed as now + max(base[attempt]*V, 6h). See pipeline/src/scheduling/priority.py (#1129 spec §2). NULL until the scheduling engine is wired into resolve_daily."),
  ADD COLUMN IF NOT EXISTS attempt INT64
    OPTIONS(description="Consecutive no-change check count for this claim, drives backoff base=[1d,3d,7d,30d] (clamped at last index). Increments on no-change, resets to 0 on revival. See pipeline/src/scheduling/priority.py (#1129 spec §2). NULL until the scheduling engine is wired into resolve_daily.");

-- ── Verification queries (copy-paste into BigQuery console to confirm) ─────────
--
-- Confirm the 3 columns exist with the right types:
--   SELECT column_name, data_type, is_nullable
--   FROM `{project_id}.silver_v2_claims.INFORMATION_SCHEMA.COLUMNS`
--   WHERE table_name = 'claim'
--     AND column_name IN ('priority_score', 'next_check_at', 'attempt')
--   ORDER BY column_name;
--
-- Confirm additive-only (existing row count unchanged, new columns all NULL
-- pre-backfill):
--   SELECT COUNT(*) AS total_rows,
--          COUNTIF(priority_score IS NULL) AS null_priority_score,
--          COUNTIF(next_check_at  IS NULL) AS null_next_check_at,
--          COUNTIF(attempt        IS NULL) AS null_attempt
--   FROM `{project_id}.silver_v2_claims.claim`;

-- conflicts.sql
-- Detects same-pundit self-contradictions in silver_v2_claims (Issue #920, Phase 4).
--
-- Conflict definition:
--   Two claims by the SAME pundit (speaker_entity_id), about the SAME subject entity
--   and metric, whose resolution windows overlap, and whose predicate_args differ
--   (i.e. the pundit predicted contradictory outcomes for the same entity+metric
--   within the same time window).
--
-- Cross-pundit disagreement (two different pundits contradicting each other) is
-- intentionally excluded from this query: it is stored in the data but not flagged.
-- Only same-pundit self-contradiction is the primary signal.
--
-- Deduplication: c1.claim_id < c2.claim_id eliminates (A,B) / (B,A) duplicate pairs.
--
-- Usage:
--   bq query --use_legacy_sql=false < pipeline/sql/conflicts.sql
--   Replace @project_id with the actual GCP_PROJECT_ID.
--
-- Expected output columns:
--   claim_a, claim_b        — the two conflicting claim_ids
--   pundit_id               — speaker_entity_id (the self-contradicting pundit)
--   subject_entity_id       — the entity both claims are about
--   subject_metric          — the attribute/metric being predicted
--   window_a_start/end      — resolution window for claim_a
--   window_b_start/end      — resolution window for claim_b

SELECT
  c1.claim_id           AS claim_a,
  c2.claim_id           AS claim_b,
  c1.speaker_entity_id  AS pundit_id,
  l1.entity_id          AS subject_entity_id,
  c1.subject_metric,
  c1.resolution_window_start  AS window_a_start,
  c1.resolution_window_end    AS window_a_end,
  c2.resolution_window_start  AS window_b_start,
  c2.resolution_window_end    AS window_b_end
FROM silver_v2_claims.claim c1
JOIN silver_v2_claims.claim_entity_link l1
    ON l1.claim_id = c1.claim_id
    AND l1.entity_role = 'subject'
JOIN silver_v2_claims.claim c2
    ON c2.speaker_entity_id = c1.speaker_entity_id
    AND c2.claim_id != c1.claim_id
JOIN silver_v2_claims.claim_entity_link l2
    ON l2.claim_id = c2.claim_id
    AND l2.entity_role = 'subject'
    AND l2.entity_id = l1.entity_id
WHERE c1.subject_metric = c2.subject_metric
  -- Overlapping resolution windows: A starts before B ends AND A ends after B starts
  AND c1.resolution_window_start < c2.resolution_window_end
  AND c1.resolution_window_end   > c2.resolution_window_start
  -- Contradictory: different predicate_args for the same entity+metric
  AND TO_JSON_STRING(c1.predicate_args) != TO_JSON_STRING(c2.predicate_args)
  -- Deduplicate pairs: only emit (A, B) not also (B, A)
  AND c1.claim_id < c2.claim_id
ORDER BY
  c1.speaker_entity_id,
  l1.entity_id,
  c1.subject_metric,
  c1.resolution_window_start

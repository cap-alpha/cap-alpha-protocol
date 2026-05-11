-- Migration 025: Backfill prediction_ledger.resolution_status from prediction_resolutions
--
-- root cause: record_resolution() wrote outcomes to prediction_resolutions but never
-- synced them back to prediction_ledger.resolution_status.  As a result, the ledger
-- showed 2898 PENDING even though 437 claims had already been resolved.
--
-- This migration is a one-time backfill.  Going forward, record_resolution() in
-- resolution_engine.py will UPDATE prediction_ledger on every resolution write.
--
-- Safe to re-run (UPDATE ... WHERE resolution_status = 'PENDING' is idempotent).

UPDATE `{project_id}.gold_layer.prediction_ledger` l
SET
    resolution_status = r.resolution_status,
    resolved_at       = r.resolved_at,
    resolution_notes  = r.outcome_notes
FROM `{project_id}.gold_layer.prediction_resolutions` r
WHERE l.prediction_hash = r.prediction_hash
  AND l.resolution_status = 'PENDING'
  AND r.resolution_status IN ('CORRECT', 'INCORRECT', 'VOID');

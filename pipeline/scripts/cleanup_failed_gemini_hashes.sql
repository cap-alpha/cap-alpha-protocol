-- One-time cleanup: remove processed_media_hashes entries from the failed
-- Gemini 2.0 run that marked 130 rows as "processed" with 0 extractions.
--
-- These rows were marked done but produced no predictions, likely due to
-- the Gemini 2.0 model issues. Clearing them allows re-processing after
-- source fixes (The Athletic keyword filter, First Take disabled, pundit
-- quality filter).
--
-- Run this AFTER deploying the source config + extractor fixes from #128.
--
-- Usage (inside Docker):
--   bq query --use_legacy_sql=false < pipeline/scripts/cleanup_failed_gemini_hashes.sql
--
-- Safety: only deletes hashes that have zero corresponding predictions
-- in the ledger, so successfully-extracted content is preserved.

DELETE FROM `{project_id}.nfl_dead_money.processed_media_hashes` p
WHERE NOT EXISTS (
    SELECT 1
    FROM `{project_id}.nfl_dead_money.prediction_ledger` l
    WHERE l.source_url IN (
        SELECT r.source_url
        FROM `{project_id}.nfl_dead_money.raw_pundit_media` r
        WHERE r.content_hash = p.content_hash
    )
);

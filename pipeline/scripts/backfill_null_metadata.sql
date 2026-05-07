-- backfill_null_metadata.sql — Issue #595
--
-- One-shot cleanup of raw_utterance rows written before Phase C landed.
-- Phase C (PR #583) added speech_act_type, testability_score, domain, and
-- extraction_confidence to every row. Rows written before that merge have
-- NULL in one or more of these columns.
--
-- Step 1: count affected rows (run first, decide re-extract vs delete)
SELECT
    COUNT(*) AS null_metadata_row_count,
    COUNTIF(speech_act_type IS NULL) AS null_speech_act_type,
    COUNTIF(testability_score IS NULL) AS null_testability_score,
    COUNTIF(domain IS NULL) AS null_domain,
    COUNTIF(extraction_confidence IS NULL) AS null_extraction_confidence,
    MIN(created_at) AS oldest_null_row,
    MAX(created_at) AS newest_null_row
FROM `${GCP_PROJECT_ID}.silver_v2_claims.raw_utterance`
WHERE
    speech_act_type IS NULL
    OR testability_score IS NULL
    OR domain IS NULL
    OR extraction_confidence IS NULL;

-- Step 2a: If count < 10k — mark source docs for re-extraction
-- (copy source_doc_ids to a temp table, then re-run assertion_extractor.py
--  with --source-doc-ids flag pointing at this list)
--
-- SELECT DISTINCT source_doc_id
-- FROM `${GCP_PROJECT_ID}.silver_v2_claims.raw_utterance`
-- WHERE speech_act_type IS NULL OR testability_score IS NULL
--   OR domain IS NULL OR extraction_confidence IS NULL;

-- Step 2b: If count >= 10k — hard-delete and document row count in PR
-- Record count before deleting:
--   SELECT COUNT(*) FROM ... (same WHERE clause as above)
-- Then delete:
DELETE FROM `${GCP_PROJECT_ID}.silver_v2_claims.raw_utterance`
WHERE
    speech_act_type IS NULL
    OR testability_score IS NULL
    OR domain IS NULL
    OR extraction_confidence IS NULL;

-- Step 3: verify zero NULL rows remain
SELECT COUNT(*) AS remaining_null_rows
FROM `${GCP_PROJECT_ID}.silver_v2_claims.raw_utterance`
WHERE
    speech_act_type IS NULL
    OR testability_score IS NULL
    OR domain IS NULL
    OR extraction_confidence IS NULL;

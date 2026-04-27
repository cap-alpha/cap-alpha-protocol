-- Reset processed_media_hashes rows that produced zero ledger entries,
-- so those source items get re-processed on the next extraction run.
--
-- Background: mark_as_processed() was called even when the LLM returned
-- no predictions. This permanently blocked 132 rows from re-extraction.
-- The bug is fixed in assertion_extractor.py (zero-prediction items are
-- no longer marked as processed). This SQL clears the backlog.
--
-- Safety guarantees:
--   1. Only touches hashes that exist in raw_pundit_media (no orphan deletes).
--   2. Preserves hashes that have at least one row in prediction_ledger.
--   3. Does NOT delete hashes for items filtered_out by the pre-filter
--      (they intentionally have no predictions and should stay marked).
--
-- Run order:
--   Step 1 (DIAGNOSTIC — run first, review output):
--       SELECT + COUNT to see which rows will be affected.
--   Step 2 (EXECUTE — run after reviewing Step 1):
--       DELETE to unblock re-extraction.
--
-- Usage:
--   bq query --use_legacy_sql=false --project_id=cap-alpha-protocol \
--       "$(sed -n '/^-- STEP 2/,/^;/p' pipeline/scripts/reset_zero_prediction_hashes.sql)"
--
-- Or interactively via BQ console.

-- STEP 1: DIAGNOSTIC — how many stuck hashes will be cleared
SELECT
    COUNT(*) AS stuck_hashes_to_reset,
    MIN(p.processed_at) AS earliest_stuck,
    MAX(p.processed_at) AS latest_stuck
FROM `cap-alpha-protocol.nfl_dead_money.processed_media_hashes` p
JOIN `cap-alpha-protocol.nfl_dead_money.raw_pundit_media` r
    ON r.content_hash = p.content_hash
WHERE NOT EXISTS (
    SELECT 1
    FROM `cap-alpha-protocol.nfl_dead_money.prediction_ledger` l
    WHERE l.source_url = r.source_url
);

-- STEP 2: EXECUTE — clear stuck hashes so they re-queue for extraction
-- Uncomment and run after reviewing Step 1 output.
/*
DELETE FROM `cap-alpha-protocol.nfl_dead_money.processed_media_hashes` p
WHERE p.content_hash IN (
    SELECT p2.content_hash
    FROM `cap-alpha-protocol.nfl_dead_money.processed_media_hashes` p2
    JOIN `cap-alpha-protocol.nfl_dead_money.raw_pundit_media` r
        ON r.content_hash = p2.content_hash
    WHERE NOT EXISTS (
        SELECT 1
        FROM `cap-alpha-protocol.nfl_dead_money.prediction_ledger` l
        WHERE l.source_url = r.source_url
    )
);
*/

-- STEP 3 (OPTIONAL): Remove orphan hashes not in raw_pundit_media at all
-- (cleanup only — does not affect re-extraction since these have no source rows)
/*
DELETE FROM `cap-alpha-protocol.nfl_dead_money.processed_media_hashes`
WHERE content_hash NOT IN (
    SELECT content_hash
    FROM `cap-alpha-protocol.nfl_dead_money.raw_pundit_media`
);
*/

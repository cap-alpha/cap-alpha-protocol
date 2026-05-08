-- Migration 015: Add published flag to pundit_registry (Issue #830)
--
-- Adds a BOOL column `published` (DEFAULT FALSE) to pundit_registry.
-- Published pundits are surfaced via the public API and UI; scores are
-- computed for all tracked pundits regardless of this flag.
--
-- After running this DDL, mark tier-1 pundits published by running:
--   python -m src.publish_tier1_pundits
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/015_add_published_to_pundit_registry.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

ALTER TABLE `{project_id}.nfl_dead_money.pundit_registry`
  ADD COLUMN IF NOT EXISTS published BOOL
    OPTIONS(description="If TRUE, this pundit is surfaced via the public API and UI. Default FALSE. Scores computed regardless.");

-- Back-fill existing rows: set to FALSE (BigQuery ALTER ADD COLUMN sets new rows to NULL
-- but existing rows stay NULL; explicitly set to FALSE for safety).
UPDATE `{project_id}.nfl_dead_money.pundit_registry`
SET published = FALSE
WHERE published IS NULL;

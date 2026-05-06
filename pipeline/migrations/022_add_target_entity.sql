-- Migration 022: add target_entity JSON column to prediction_ledger (Issue #688)
-- Design: Option D (hybrid) — add target_entity JSON alongside existing
-- target_player_id, target_player_name, target_team columns.
--
-- Rationale:
--   - BigQuery is append-only; removing target_player_* / target_team is
--     impossible without a full table rewrite, and migration risk is not
--     justified pre-launch.
--   - Existing NFL queries that filter on target_player_name / target_team
--     keep working without changes — no query rewrites needed at launch.
--   - target_entity JSON handles all non-NFL domains (politics, finance,
--     entertainment) without column sprawl: each new domain adds attributes
--     inside the JSON envelope rather than a new DDL column.
--   - Query pattern for "all predictions about politician X":
--       WHERE JSON_VALUE(target_entity, '$.name') = 'X'
--         AND JSON_VALUE(target_entity, '$.type') = 'politician'
--     BigQuery JSON functions are inlined and don't require joins.
--   - For NFL, the extractor maps target_player_name → target_entity with
--     type "player" and target_team → type "team", so both access patterns
--     work: legacy target_player_name column AND new target_entity JSON.
--
-- target_entity JSON schema (per type):
--   player:      { "type": "player", "name": "Patrick Mahomes", "team": "KC", "sport": "NFL" }
--   team:        { "type": "team",   "name": "Kansas City Chiefs", "abbrev": "KC", "sport": "NFL" }
--   politician:  { "type": "politician", "name": "Jane Smith", "party": "D", "office": "Senate", "state": "CA" }
--   party:       { "type": "party", "name": "Republican Party", "country": "US" }
--   bill:        { "type": "bill", "name": "H.R. 1234", "session": "119th", "country": "US" }
--   company:     { "type": "company", "name": "Apple Inc.", "ticker": "AAPL", "sector": "Technology" }
--   metric:      { "type": "metric", "name": "US CPI YoY", "source": "fred", "series_id": "CPIAUCSL" }
--
-- Clustering note: BigQuery does not support clustering on JSON columns
-- directly. The existing cluster on (pundit_id, claim_category) is
-- sufficient for the primary access patterns. Queries that filter by
-- entity type/name should be paired with a domain partition filter to
-- limit scan cost.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/022_add_target_entity.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

-- Part A: add target_entity to gold_layer.prediction_ledger
ALTER TABLE `{project_id}.gold_layer.prediction_ledger`
  ADD COLUMN IF NOT EXISTS target_entity JSON
    OPTIONS(description="Polymorphic entity envelope. Replaces target_player_name + target_team for non-NFL domains. For NFL: {\"type\":\"player\"|\"team\",\"name\":\"...\"}. For politics: {\"type\":\"politician\",\"name\":\"...\",\"party\":\"...\"}. NULL for claims not targeting a specific entity.");

-- Part B: add target_entity to silver_v2_claims.raw_utterance
-- (mirrors the ledger column so the full audit trail carries entity context)
ALTER TABLE `{project_id}.silver_v2_claims.raw_utterance`
  ADD COLUMN IF NOT EXISTS target_entity JSON
    OPTIONS(description="Polymorphic entity envelope. For NFL utterances, populated from target_player / target_team LLM output. For non-NFL domains, carries domain-specific entity attributes. NULL for utterances that don't target a specific entity.");

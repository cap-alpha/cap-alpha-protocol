-- Migration 010: Create player_timeline_events view (Issue #49)
--
-- Unifies heterogeneous player events (Contract Cap Hits, Pundit Predictions,
-- Resolved Predictions) into a single gold-layer view keyed by player_name.
-- Powers the player detail page timeline on the web front-end.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/010_create_player_timeline_events_view.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE OR REPLACE VIEW `${PROJECT_ID}.gold_layer.player_timeline_events`
OPTIONS (
  description = "Unified chronological player event feed. Sources: silver_spotrac_contracts, gold_layer.prediction_ledger, gold_layer.prediction_resolutions."
)
AS

-- ============================================================
-- 1. Contract / Cap Hit events
-- ============================================================
SELECT
  c.player_name,
  DATE(CAST(c.year AS STRING) || '-03-15')                                        AS event_date,
  c.year                                                                           AS event_year,
  'CONTRACT'                                                                       AS event_type,
  CONCAT(
    'Cap Hit: $', CAST(ROUND(COALESCE(c.cap_hit_millions, 0.0), 1) AS STRING), 'M'
  )                                                                                AS title,
  CONCAT(
    'Total contract: $',
    CAST(ROUND(COALESCE(c.total_contract_value_millions, 0.0), 1) AS STRING), 'M',
    IF(c.team IS NOT NULL, CONCAT('  |  Team: ', c.team), '')
  )                                                                                AS description,
  NULL                                                                             AS source_url,
  c.team

FROM `${PROJECT_ID}.nfl_dead_money.silver_spotrac_contracts` c
WHERE c.player_name IS NOT NULL

UNION ALL

-- ============================================================
-- 2. Pundit Prediction events (unresolved / all)
-- ============================================================
SELECT
  COALESCE(pl.target_player_name, pl.target_player_id)                            AS player_name,
  DATE(pl.ingestion_timestamp)                                                     AS event_date,
  EXTRACT(YEAR FROM pl.ingestion_timestamp)                                        AS event_year,
  'PREDICTION'                                                                     AS event_type,
  CONCAT(
    pl.pundit_name,
    ': ',
    UPPER(COALESCE(pl.claim_category, 'prediction'))
  )                                                                                AS title,
  CONCAT(
    pl.raw_assertion_text,
    IF(pl.resolution_status IS NOT NULL AND pl.resolution_status != 'PENDING',
      CONCAT('  [', pl.resolution_status, ']'), '')
  )                                                                                AS description,
  pl.source_url,
  pl.target_team                                                                   AS team

FROM `${PROJECT_ID}.gold_layer.prediction_ledger` pl
WHERE COALESCE(pl.target_player_name, pl.target_player_id) IS NOT NULL

UNION ALL

-- ============================================================
-- 3. Resolution events (CORRECT / INCORRECT verdicts)
-- ============================================================
SELECT
  COALESCE(pl.target_player_name, pl.target_player_id)                            AS player_name,
  DATE(pr.updated_at)                                                              AS event_date,
  EXTRACT(YEAR FROM pr.updated_at)                                                 AS event_year,
  'RESOLUTION'                                                                     AS event_type,
  CONCAT(
    'Prediction ',
    pr.resolution_status,
    IF(pl.pundit_name IS NOT NULL, CONCAT(' — ', pl.pundit_name), '')
  )                                                                                AS title,
  COALESCE(pr.resolution_notes, pl.extracted_claim, pl.raw_assertion_text)        AS description,
  pl.source_url,
  pl.target_team                                                                   AS team

FROM `${PROJECT_ID}.gold_layer.prediction_resolutions` pr
JOIN  `${PROJECT_ID}.gold_layer.prediction_ledger`     pl
  ON  pr.prediction_hash = pl.prediction_hash
WHERE COALESCE(pl.target_player_name, pl.target_player_id) IS NOT NULL
  AND pr.resolution_status IN ('CORRECT', 'INCORRECT')
;


-- ============================================================
-- POST-APPLY: smoke test
-- ============================================================
-- SELECT event_type, COUNT(*) AS cnt
-- FROM `${PROJECT_ID}.gold_layer.player_timeline_events`
-- GROUP BY 1
-- ORDER BY 2 DESC;

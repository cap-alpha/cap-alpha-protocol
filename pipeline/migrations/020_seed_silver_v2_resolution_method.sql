-- Migration 020: seed silver_v2_claims.resolution_method registry
-- Issue: #615 — [Gate 1] seed resolution_method + dual-write resolutions
--
-- Populates the resolution_method lookup table with the 5 NFL adapters that
-- back the existing resolve_daily.py categories. This enables dual-write:
-- every resolution written to gold_layer.prediction_resolutions also writes
-- a cryptographically-chained row to silver_v2_claims.resolution.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/020_seed_silver_v2_resolution_method.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

INSERT INTO `{project_id}.silver_v2_claims.resolution_method`
  (resolution_method_id, domain, name, adapter_path, data_source, config)
VALUES
  (
    'nfl_draft_pick_sportsdataio',
    'sports.nfl',
    'NFL Draft Pick via SportsData.io',
    'pipeline.src.resolve_daily:resolve_draft_picks',
    'sportsdataio.nfl',
    JSON '{"category":"draft_pick","source_table":"bronze_sportsdataio_players"}'
  ),
  (
    'nfl_game_outcome_scores',
    'sports.nfl',
    'NFL Game Outcome via SportsData.io Scores',
    'pipeline.src.resolve_daily:resolve_game_outcomes',
    'sportsdataio.nfl',
    JSON '{"category":"game_outcome","source_table":"bronze_sportsdataio_scores"}'
  ),
  (
    'nfl_player_perf_nflverse',
    'sports.nfl',
    'NFL Player Performance via nflverse',
    'pipeline.src.resolve_daily:resolve_player_performance',
    'nflverse.player_stats',
    JSON '{"category":"player_performance","source_table":"bronze_nflverse_player_stats"}'
  ),
  (
    'nfl_award_config',
    'sports.nfl',
    'NFL Award Winners via Config File',
    'pipeline.src.resolve_daily:resolve_award_predictions',
    'nfl_awards_config',
    JSON '{"category":"award_prediction","source":"pipeline/config/nfl_awards_{season}.yaml"}'
  ),
  (
    'nfl_fa_signing_rosters',
    'sports.nfl',
    'NFL Free Agent Signing via SportsData.io Rosters',
    'pipeline.src.resolve_daily:resolve_fa_signings',
    'sportsdataio.nfl',
    JSON '{"category":"fa_signing","source_table":"bronze_sportsdataio_players"}'
  );

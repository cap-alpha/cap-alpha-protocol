-- Migration 019: extraction_run — per-run extraction metrics
-- Issue: #598 — feat(observability): per-run extraction metrics table
--
-- Powers the quality dashboard per-run drill-down and the hourly health-alert job.
-- One row written per pipeline invocation of run_extraction(), in a try/finally
-- so partial failures are still recorded.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/019_create_extraction_run.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_claims.extraction_run`
(
  run_id                    STRING    NOT NULL  OPTIONS(description="UUIDv4 for this extraction run"),
  started_at                TIMESTAMP NOT NULL  OPTIONS(description="When the run started (UTC)"),
  finished_at               TIMESTAMP           OPTIONS(description="When the run finished; NULL if still in progress or aborted before recording"),
  provider                  STRING    NOT NULL  OPTIONS(description="LLM provider type (gemini|ollama|claude|dry-run)"),
  model                     STRING    NOT NULL  OPTIONS(description="LLM model name used for extraction"),
  prompt_version            STRING              OPTIONS(description="SHA-256 prefix of the extraction prompt, for tracking prompt regressions"),
  articles_processed        INT64               OPTIONS(description="Number of articles processed this run (includes errors, skips, and low-yield)"),
  utterances_written        INT64               OPTIONS(description="Number of utterances written to raw_utterance"),
  claims_promoted           INT64               OPTIONS(description="Number of claims promoted to the cryptographic ledger"),
  suppressed                INT64               OPTIONS(description="Number of utterances suppressed (non-testable or non-promotable speech acts)"),
  errors                    INT64               OPTIONS(description="Number of extraction errors (LLM failures, BQ write failures)"),
  mean_testability_score    FLOAT64             OPTIONS(description="Mean testability score across all utterances written this run; NULL if zero utterances"),
  metadata_completeness_pct FLOAT64             OPTIONS(description="Percentage (0–100) of utterances where the LLM returned explicit non-null speech_act_type, testability_score, and extraction_confidence; NULL if zero utterances"),
  git_sha                   STRING              OPTIONS(description="Git SHA of the code that ran this extraction (GITHUB_SHA env var)"),
  workflow_run_url          STRING              OPTIONS(description="URL to the GitHub Actions workflow run that produced this row")
)
PARTITION BY DATE(started_at)
OPTIONS(
  description="One row per extraction run. Powers quality dashboard per-run drill-down and alerting.",
  partition_expiration_days=365
);

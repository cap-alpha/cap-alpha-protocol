-- Migration 017: silver_v2_sports — Sports-domain extensions (Phase B-0)
-- Issue: #555 — Pivot to general-purpose truth ledger data model
-- Description: Sports-specific tables that build on top of silver_v2_core.
--              Franchise lineage tracks continuity, splits, merges, and rebrands
--              across the full history of professional sports franchises.
--
-- Design decisions:
--   - Both parent_entity_id and child_entity_id are UUIDv7 FKs to silver_v2_core.entity
--   - lineage_type covers the full spectrum: continuation, split, merge, expansion, dormant_resume, rebrand
--   - records_inherited + rosters_transferred are first-class booleans (used in timeline continuity scoring)
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/017_create_silver_v2_sports.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

CREATE SCHEMA IF NOT EXISTS `{project_id}.silver_v2_sports`;

-- ============================================================
-- 1. franchise_lineage — continuity graph for sports franchises
-- ============================================================
CREATE TABLE IF NOT EXISTS `{project_id}.silver_v2_sports.franchise_lineage`
(
  parent_entity_id      STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id of the predecessor franchise or organization"),
  child_entity_id       STRING    NOT NULL  OPTIONS(description="FK to silver_v2_core.entity.entity_id of the successor franchise or organization"),
  lineage_type          STRING    NOT NULL  OPTIONS(description="continuation — same franchise, new season; split — one franchise splits into two; merge — two franchises combine; expansion — new franchise created from existing org; dormant_resume — franchise reactivated after hiatus; rebrand — identity change only, full continuity"),
  effective_at          TIMESTAMP NOT NULL  OPTIONS(description="When this lineage relationship became effective (start of new season, trade deadline, etc.)"),
  records_inherited     BOOL      NOT NULL  OPTIONS(description="TRUE if the child entity inherits the parent's historical win-loss records for official purposes"),
  rosters_transferred   BOOL      NOT NULL  OPTIONS(description="TRUE if player contracts/rosters transferred from parent to child"),
  source_doc_id         STRING              OPTIONS(description="FK to raw source document evidencing this lineage relationship"),
  notes                 STRING              OPTIONS(description="Free-text notes for unusual cases (e.g. relocation details, league ruling citations)")
)
OPTIONS (
  description = "Directed lineage graph for sports franchises. Encodes continuity, splits, merges, expansions, dormancy, and rebrands. Both parent and child are UUIDv7 FKs to silver_v2_core.entity. Not partitioned — expected to be small (<10k rows for all major sports history)."
);

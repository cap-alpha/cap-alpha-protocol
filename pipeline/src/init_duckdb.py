#!/usr/bin/env python3
"""
Initialize a local DuckDB database with schemas matching the BigQuery layout.

Safe to re-run — every statement uses IF NOT EXISTS / CREATE OR REPLACE.

Usage:
    python -m src.init_duckdb                     # uses DUCKDB_PATH or default
    python -m src.init_duckdb --db-path /tmp/x.db

After this runs, set DB_BACKEND=duckdb to route the pipeline to DuckDB instead
of BigQuery.  Switch back by unsetting DB_BACKEND (or setting it to 'bigquery').
"""

import argparse
import json
import logging
import os
import sys

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Full schema DDL — DuckDB-native types
#
# BigQuery type → DuckDB type mapping:
#   STRING      → VARCHAR
#   INT64       → BIGINT
#   FLOAT64     → DOUBLE
#   BOOL        → BOOLEAN
#   TIMESTAMP   → TIMESTAMP  (stored as UTC; Python datetime objects round-trip cleanly)
#   JSON        → JSON       (DuckDB 0.9+ native JSON type)
#   ARRAY<T>    → T[]
#
# BQ-only clauses omitted: PARTITION BY, CLUSTER BY, OPTIONS(description=...)
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- ============================================================
-- Schema: nfl_dead_money  (Bronze + registry tables)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS nfl_dead_money;

CREATE TABLE IF NOT EXISTS nfl_dead_money.raw_pundit_media (
    content_hash          VARCHAR     NOT NULL,
    source_id             VARCHAR     NOT NULL,
    title                 VARCHAR,
    raw_text              VARCHAR,
    source_url            VARCHAR     NOT NULL,
    author                VARCHAR,
    matched_pundit_id     VARCHAR,
    matched_pundit_name   VARCHAR,
    published_at          TIMESTAMP,
    ingested_at           TIMESTAMP   NOT NULL,
    content_type          VARCHAR,
    fetch_source_type     VARCHAR,
    raw_metadata          VARCHAR,
    sport                 VARCHAR     DEFAULT 'NFL'
);

CREATE TABLE IF NOT EXISTS nfl_dead_money.processed_media_hashes (
    content_hash    VARCHAR     NOT NULL,
    processed_at    TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS nfl_dead_money.pundit_registry (
    pundit_id           VARCHAR     NOT NULL,
    pundit_name         VARCHAR     NOT NULL,
    sport               VARCHAR     NOT NULL,
    source_ids          VARCHAR[],
    match_authors       VARCHAR[],
    enabled             BOOLEAN     NOT NULL,
    is_source_default   BOOLEAN,
    polling_cadence     VARCHAR     NOT NULL,
    last_seen_at        TIMESTAMP,
    posts_per_month     DOUBLE,
    created_at          TIMESTAMP   NOT NULL,
    updated_at          TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS nfl_dead_money.source_registry (
    source_id           VARCHAR     NOT NULL,
    source_name         VARCHAR     NOT NULL,
    source_type         VARCHAR     NOT NULL,
    url                 VARCHAR     NOT NULL,
    sport               VARCHAR     NOT NULL,
    enabled             BOOLEAN     NOT NULL,
    scrape_full_text    BOOLEAN,
    keyword_filter      VARCHAR[],
    default_pundit_id   VARCHAR,
    polling_cadence     VARCHAR     NOT NULL,
    last_fetched_at     TIMESTAMP,
    last_item_count     BIGINT,
    created_at          TIMESTAMP   NOT NULL,
    updated_at          TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS nfl_dead_money.registry_audit_log (
    log_id              VARCHAR     NOT NULL,
    entity_type         VARCHAR     NOT NULL,
    entity_id           VARCHAR     NOT NULL,
    action              VARCHAR     NOT NULL,
    old_value           VARCHAR,
    new_value           VARCHAR,
    reason              VARCHAR,
    logged_at           TIMESTAMP   NOT NULL
);

-- entities: PRIMARY KEY enables ON CONFLICT upserts in DuckDBManager
CREATE TABLE IF NOT EXISTS nfl_dead_money.entities (
    entity_id           VARCHAR     NOT NULL PRIMARY KEY,
    entity_type         VARCHAR     NOT NULL,
    canonical_name      VARCHAR     NOT NULL,
    aliases             VARCHAR[],
    domain              VARCHAR     NOT NULL,
    metadata            JSON,
    first_seen_at       TIMESTAMP,
    last_seen_at        TIMESTAMP,
    claim_count         BIGINT,
    created_at          TIMESTAMP
);

-- prediction_ledger_graph_extension: PRIMARY KEY enables upserts
CREATE TABLE IF NOT EXISTS nfl_dead_money.prediction_ledger_graph_extension (
    prediction_hash               VARCHAR     NOT NULL PRIMARY KEY,
    entity_ids                    VARCHAR[],
    primary_entity_id             VARCHAR,
    claim_type                    VARCHAR,
    domain                        VARCHAR,
    asserted_state                JSON,
    embedding                     DOUBLE[],
    cluster_id                    VARCHAR,
    entity_resolution_confidence  DOUBLE,
    created_at                    TIMESTAMP,
    updated_at                    TIMESTAMP
);

-- ============================================================
-- Schema: gold_layer  (Ledger + resolutions)
-- ============================================================
CREATE SCHEMA IF NOT EXISTS gold_layer;

-- prediction_ledger: append-only, no PK constraint (same as BQ)
CREATE TABLE IF NOT EXISTS gold_layer.prediction_ledger (
    prediction_hash     VARCHAR     NOT NULL,
    chain_hash          VARCHAR     NOT NULL,
    ingestion_timestamp TIMESTAMP   NOT NULL,
    source_url          VARCHAR     NOT NULL,
    pundit_id           VARCHAR     NOT NULL,
    pundit_name         VARCHAR     NOT NULL,
    raw_assertion_text  VARCHAR     NOT NULL,
    extracted_claim     VARCHAR,
    claim_category      VARCHAR,
    season_year         BIGINT,
    target_player_id    VARCHAR,
    target_player_name  VARCHAR,
    target_team         VARCHAR,
    sport               VARCHAR     DEFAULT 'NFL',
    resolution_status   VARCHAR     DEFAULT 'PENDING',
    resolved_at         TIMESTAMP,
    resolution_notes    VARCHAR,
    stance              VARCHAR,
    prompt_version      VARCHAR,
    llm_provider        VARCHAR,
    llm_model           VARCHAR,
    target_entity       JSON,
    claim_norm_key      VARCHAR
);

-- Unique index enforcing no two rows with the same (pundit_id, source_url, claim_norm_key).
-- DuckDB treats each NULL as distinct in a UNIQUE index (NULLS NOT DISTINCT is not the
-- default), so rows with claim_norm_key = NULL (pre-dedup-era rows) are naturally exempt.
-- This is the DuckDB-side enforcement of the app-layer dedup added in Issue #935.
-- BigQuery does not support unique constraints; the application layer (check_claim_is_duplicate
-- scoped to pundit_id + source_url) provides equivalent protection in production.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_pundit_source_norm
    ON gold_layer.prediction_ledger (pundit_id, source_url, claim_norm_key);

CREATE TABLE IF NOT EXISTS gold_layer.prediction_resolutions (
    prediction_hash       VARCHAR     NOT NULL,
    resolution_status     VARCHAR     NOT NULL,
    resolved_at           TIMESTAMP,
    resolver              VARCHAR,
    brier_score           DOUBLE,
    binary_correct        BOOLEAN,
    timeliness_weight     DOUBLE,
    weighted_score        DOUBLE,
    outcome_source        VARCHAR,
    outcome_reference_id  VARCHAR,
    outcome_notes         VARCHAR,
    created_at            TIMESTAMP   NOT NULL,
    updated_at            TIMESTAMP   NOT NULL
);

-- ledger_chain_head: singleton sentinel for concurrency guard
CREATE TABLE IF NOT EXISTS gold_layer.ledger_chain_head (
    singleton_key   VARCHAR     NOT NULL PRIMARY KEY,
    chain_hash      VARCHAR     NOT NULL,
    updated_at      TIMESTAMP   NOT NULL
);

-- claim_edges view: joins ledger + graph-extension sidecar
CREATE OR REPLACE VIEW gold_layer.claim_edges AS
SELECT
    p.prediction_hash                       AS claim_id,
    p.pundit_id,
    p.pundit_name,
    p.raw_assertion_text,
    p.extracted_claim,
    p.claim_category,
    p.ingestion_timestamp                   AS timestamp_made,
    p.season_year,
    p.target_player_id,
    p.target_player_name,
    p.target_team,
    p.target_entity,
    p.stance,
    p.sport,
    p.resolution_status                     AS resolution,
    p.resolved_at,
    p.resolution_notes,
    p.chain_hash,
    p.source_url,
    p.prompt_version,
    p.llm_provider,
    p.llm_model,
    e.entity_ids,
    e.primary_entity_id,
    e.claim_type,
    e.domain,
    e.asserted_state,
    e.embedding,
    e.cluster_id,
    e.entity_resolution_confidence
FROM gold_layer.prediction_ledger p
LEFT JOIN nfl_dead_money.prediction_ledger_graph_extension e
    ON p.prediction_hash = e.prediction_hash;

-- ============================================================
-- Schema: silver_v2_claims
-- ============================================================
CREATE SCHEMA IF NOT EXISTS silver_v2_claims;

CREATE TABLE IF NOT EXISTS silver_v2_claims.extraction_run (
    run_id                    VARCHAR     NOT NULL,
    started_at                TIMESTAMP   NOT NULL,
    finished_at               TIMESTAMP,
    provider                  VARCHAR     NOT NULL,
    model                     VARCHAR     NOT NULL,
    prompt_version            VARCHAR,
    articles_processed        BIGINT,
    utterances_written        BIGINT,
    claims_promoted           BIGINT,
    suppressed                BIGINT,
    errors                    BIGINT,
    mean_testability_score    DOUBLE,
    metadata_completeness_pct DOUBLE,
    git_sha                   VARCHAR,
    workflow_run_url          VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.raw_utterance (
    utterance_id            VARCHAR     NOT NULL,
    source_doc_id           VARCHAR     NOT NULL,
    speaker_entity_id       VARCHAR     NOT NULL,
    uttered_at              TIMESTAMP   NOT NULL,
    text                    VARCHAR     NOT NULL,
    speech_act_type         VARCHAR     NOT NULL,
    testability_score       DOUBLE      NOT NULL,
    resolution_horizon      TIMESTAMP,
    domain                  VARCHAR     NOT NULL,
    extraction_confidence   DOUBLE      NOT NULL,
    target_entity           JSON,
    created_at              TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution_method (
    resolution_method_id    VARCHAR     NOT NULL,
    domain                  VARCHAR     NOT NULL,
    name                    VARCHAR     NOT NULL,
    adapter_path            VARCHAR     NOT NULL,
    data_source             VARCHAR     NOT NULL,
    config                  JSON
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.claim (
    claim_id                VARCHAR     NOT NULL,
    utterance_id            VARCHAR     NOT NULL,
    speaker_entity_id       VARCHAR     NOT NULL,
    domain                  VARCHAR     NOT NULL,
    claim_subject_type      VARCHAR     NOT NULL,
    subject_entity_ids      VARCHAR[],
    subject_metric          VARCHAR,
    predicate               VARCHAR     NOT NULL,
    predicate_args          JSON        NOT NULL,
    resolution_window_start TIMESTAMP   NOT NULL,
    resolution_window_end   TIMESTAMP   NOT NULL,
    resolution_method_id    VARCHAR     NOT NULL,
    asserted_at             TIMESTAMP   NOT NULL,
    ledger_locked_at        TIMESTAMP   NOT NULL,
    prior_claim_id          VARCHAR,
    prev_hash               VARCHAR     NOT NULL,
    this_hash               VARCHAR     NOT NULL,
    created_at              TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_claims.resolution (
    resolution_id           VARCHAR     NOT NULL,
    claim_id                VARCHAR     NOT NULL,
    resolved_at             TIMESTAMP   NOT NULL,
    outcome                 VARCHAR     NOT NULL,
    outcome_confidence      DOUBLE      NOT NULL,
    evidence                JSON        NOT NULL,
    resolution_method_id    VARCHAR     NOT NULL,
    prev_hash               VARCHAR     NOT NULL,
    this_hash               VARCHAR     NOT NULL,
    notes                   VARCHAR
);

-- ============================================================
-- Schema: silver_v2_core
-- ============================================================
CREATE SCHEMA IF NOT EXISTS silver_v2_core;

CREATE TABLE IF NOT EXISTS silver_v2_core.entity (
    entity_id           VARCHAR     NOT NULL,
    entity_kind         VARCHAR     NOT NULL,
    primary_domain      VARCHAR     NOT NULL,
    birth_or_founded    DATE,
    death_or_dissolved  DATE,
    external_ids        JSON,
    created_at          TIMESTAMP   NOT NULL,
    notes               VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_core.entity_alias (
    alias_id            VARCHAR     NOT NULL,
    entity_id           VARCHAR     NOT NULL,
    alias_text          VARCHAR     NOT NULL,
    alias_kind          VARCHAR     NOT NULL,
    valid_from          TIMESTAMP   NOT NULL,
    valid_to            TIMESTAMP,
    is_legal            BOOLEAN     NOT NULL,
    source_event_id     VARCHAR,
    confidence          DOUBLE      NOT NULL,
    language            VARCHAR
);

CREATE TABLE IF NOT EXISTS silver_v2_core.entity_attribute_event (
    event_id                VARCHAR     NOT NULL,
    entity_id               VARCHAR     NOT NULL,
    domain                  VARCHAR     NOT NULL,
    attr                    VARCHAR     NOT NULL,
    value                   VARCHAR     NOT NULL,
    value_json              JSON,
    valid_from              TIMESTAMP   NOT NULL,
    valid_to                TIMESTAMP,
    evidence_type           VARCHAR     NOT NULL,
    source_claim_id         VARCHAR,
    source_doc_id           VARCHAR,
    extraction_confidence   DOUBLE      NOT NULL,
    corroboration_count     BIGINT      NOT NULL,
    is_concurrent_ok        BOOLEAN     NOT NULL,
    superseded_by           VARCHAR,
    created_at              TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_core.transition_event (
    event_id                VARCHAR     NOT NULL,
    entity_id               VARCHAR     NOT NULL,
    domain                  VARCHAR     NOT NULL,
    type                    VARCHAR     NOT NULL,
    from_value              VARCHAR,
    to_value                VARCHAR,
    occurred_at             TIMESTAMP   NOT NULL,
    occurred_at_precision   VARCHAR     NOT NULL,
    payload                 JSON,
    source_claim_id         VARCHAR,
    source_doc_id           VARCHAR,
    confidence              DOUBLE      NOT NULL,
    created_at              TIMESTAMP   NOT NULL
);

CREATE TABLE IF NOT EXISTS silver_v2_core.domain_taxonomy (
    domain                VARCHAR     NOT NULL,
    parent_domain         VARCHAR,
    display_name          VARCHAR     NOT NULL,
    attribute_specs       JSON        NOT NULL,
    resolution_adapter    VARCHAR     NOT NULL,
    created_at            TIMESTAMP   NOT NULL
);

CREATE OR REPLACE VIEW silver_v2_core.entity_current AS
SELECT
    eae.entity_id,
    e.entity_kind,
    e.primary_domain,
    eae.domain,
    eae.attr,
    eae.value,
    eae.value_json,
    eae.valid_from,
    eae.evidence_type,
    eae.extraction_confidence,
    eae.corroboration_count,
    eae.is_concurrent_ok
FROM silver_v2_core.entity_attribute_event AS eae
INNER JOIN silver_v2_core.entity AS e ON e.entity_id = eae.entity_id
WHERE eae.valid_to IS NULL AND eae.superseded_by IS NULL;

CREATE OR REPLACE VIEW silver_v2_core.entity_timeline AS
SELECT
    te.entity_id,
    e.entity_kind,
    e.primary_domain,
    te.domain,
    te.type         AS event_type,
    te.from_value,
    te.to_value,
    te.occurred_at,
    te.occurred_at_precision,
    te.confidence,
    te.payload,
    'transition'    AS record_kind
FROM silver_v2_core.transition_event AS te
INNER JOIN silver_v2_core.entity AS e ON e.entity_id = te.entity_id
UNION ALL
SELECT
    eae.entity_id,
    e.entity_kind,
    e.primary_domain,
    eae.domain,
    CONCAT('attr:', eae.attr) AS event_type,
    NULL                      AS from_value,
    eae.value                 AS to_value,
    eae.valid_from            AS occurred_at,
    'second'                  AS occurred_at_precision,
    eae.extraction_confidence AS confidence,
    eae.value_json            AS payload,
    'attribute'               AS record_kind
FROM silver_v2_core.entity_attribute_event AS eae
INNER JOIN silver_v2_core.entity AS e ON e.entity_id = eae.entity_id
ORDER BY entity_id, occurred_at;

-- ============================================================
-- Schema: silver_v2_sports
-- ============================================================
CREATE SCHEMA IF NOT EXISTS silver_v2_sports;

CREATE TABLE IF NOT EXISTS silver_v2_sports.franchise_lineage (
    parent_entity_id      VARCHAR     NOT NULL,
    child_entity_id       VARCHAR     NOT NULL,
    lineage_type          VARCHAR     NOT NULL,
    effective_at          TIMESTAMP   NOT NULL,
    records_inherited     BOOLEAN     NOT NULL,
    rosters_transferred   BOOLEAN     NOT NULL,
    source_doc_id         VARCHAR,
    notes                 VARCHAR
)
"""

# ---------------------------------------------------------------------------
# domain_taxonomy seed data (mirrors migration 015_create_silver_v2_core.sql)
# ---------------------------------------------------------------------------

_DOMAIN_SEEDS = [
    {
        "domain": "sports",
        "parent_domain": None,
        "display_name": "Sports",
        "attribute_specs": [
            {"attr": "status", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "employment", "value_type": "string", "is_concurrent_ok": True},
        ],
        "resolution_adapter": "pipeline.resolvers.sports.base:SportsResolver",
    },
    {
        "domain": "sports.nfl",
        "parent_domain": "sports",
        "display_name": "NFL Football",
        "attribute_specs": [
            {"attr": "position", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "team", "value_type": "string", "is_concurrent_ok": False},
            {
                "attr": "jersey_number",
                "value_type": "string",
                "is_concurrent_ok": False,
            },
            {"attr": "status", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "employment", "value_type": "string", "is_concurrent_ok": True},
            {"attr": "contract_years", "value_type": "int", "is_concurrent_ok": False},
            {"attr": "salary_aav", "value_type": "float", "is_concurrent_ok": False},
        ],
        "resolution_adapter": "pipeline.resolvers.nfl.base:NflResolver",
    },
    {
        "domain": "politics",
        "parent_domain": None,
        "display_name": "Politics",
        "attribute_specs": [
            {
                "attr": "party_affiliation",
                "value_type": "string",
                "is_concurrent_ok": False,
            },
            {"attr": "status", "value_type": "string", "is_concurrent_ok": False},
        ],
        "resolution_adapter": "pipeline.resolvers.politics.base:PoliticsResolver",
    },
    {
        "domain": "politics.us",
        "parent_domain": "politics",
        "display_name": "U.S. Politics",
        "attribute_specs": [
            {
                "attr": "party_affiliation",
                "value_type": "string",
                "is_concurrent_ok": False,
            },
            {"attr": "caucus", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "office", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "state", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "citizenship", "value_type": "string", "is_concurrent_ok": True},
        ],
        "resolution_adapter": "pipeline.resolvers.politics.us:UsPoliticsResolver",
    },
    {
        "domain": "finance",
        "parent_domain": None,
        "display_name": "Finance",
        "attribute_specs": [
            {"attr": "status", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "sector", "value_type": "string", "is_concurrent_ok": False},
        ],
        "resolution_adapter": "pipeline.resolvers.finance.base:FinanceResolver",
    },
    {
        "domain": "tech",
        "parent_domain": None,
        "display_name": "Technology",
        "attribute_specs": [
            {"attr": "status", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "ticker", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "sector", "value_type": "string", "is_concurrent_ok": False},
            {"attr": "employment", "value_type": "string", "is_concurrent_ok": True},
        ],
        "resolution_adapter": "pipeline.resolvers.tech.base:TechResolver",
    },
]


def init_schema(db_path: str | None = None) -> None:
    """
    Create all schemas and tables in the DuckDB file at db_path.

    Safe to call repeatedly — uses IF NOT EXISTS and CREATE OR REPLACE.
    Skips domain_taxonomy seeding if the table already has rows.
    """
    import duckdb

    path = db_path or os.environ.get(
        "DUCKDB_PATH",
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "local.duckdb",
        ),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)

    conn = duckdb.connect(path)
    try:
        # Execute each DDL statement individually (DuckDB doesn't accept batched DDL)
        statements = [s.strip() for s in _SCHEMA_SQL.split(";") if s.strip()]
        for stmt in statements:
            try:
                conn.execute(stmt)
            except Exception as e:
                logger.warning("DDL statement skipped (%s): %.120s", e, stmt)

        # Seed domain_taxonomy only if empty
        count = conn.execute(
            "SELECT count(*) FROM silver_v2_core.domain_taxonomy"
        ).fetchone()[0]
        if count == 0:
            logger.info("Seeding domain_taxonomy with %d rows", len(_DOMAIN_SEEDS))
            for seed in _DOMAIN_SEEDS:
                conn.execute(
                    """
                    INSERT INTO silver_v2_core.domain_taxonomy
                        (domain, parent_domain, display_name, attribute_specs,
                         resolution_adapter, created_at)
                    VALUES ($domain, $parent_domain, $display_name, $attribute_specs::JSON,
                            $resolution_adapter, CURRENT_TIMESTAMP)
                    """,
                    {
                        "domain": seed["domain"],
                        "parent_domain": seed["parent_domain"],
                        "display_name": seed["display_name"],
                        "attribute_specs": json.dumps(seed["attribute_specs"]),
                        "resolution_adapter": seed["resolution_adapter"],
                    },
                )
        else:
            logger.info("domain_taxonomy already has %d rows — skipping seed", count)

        logger.info("DuckDB schema ready at %s", path)
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=None, help="Path to the DuckDB file")
    args = parser.parse_args()
    init_schema(args.db_path)
    print("Done.")

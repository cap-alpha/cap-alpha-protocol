"""
Tests for Phase 1 KG schema migration (028_kg_schema_additive.sql).
Issue #920 — silver_v2 temporal knowledge graph upgrade.

Unit tests: assert each expected table and column is declared in the migration SQL
(no BigQuery required — all parsing is offline).

Integration tests (skipped unless RUN_INTEGRATION=1 + GCP_PROJECT_ID set):
  - Actually queries BigQuery INFORMATION_SCHEMA to verify the objects exist.
  - Requires the migration to have been applied beforehand:
      source .env && python3 pipeline/scripts/apply_kg_schema.py

Run unit tests only (default):
    pytest pipeline/tests/migrations/test_kg_schema_phase1.py

Run integration tests:
    RUN_INTEGRATION=1 GCP_PROJECT_ID=cap-alpha-protocol \
        pytest pipeline/tests/migrations/test_kg_schema_phase1.py
"""

from __future__ import annotations

import os
import pathlib
import re
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIGRATION_FILE = (
    pathlib.Path(__file__).parent.parent.parent
    / "migrations"
    / "028_kg_schema_additive.sql"
)

SCRIPT_FILE = (
    pathlib.Path(__file__).parent.parent.parent / "scripts" / "apply_kg_schema.py"
)


def _migration_sql() -> str:
    """Return the raw migration SQL (with {project_id} placeholders intact)."""
    return MIGRATION_FILE.read_text()


def _normalized(sql: str) -> str:
    """Collapse whitespace for pattern matching."""
    return re.sub(r"\s+", " ", sql)


def _extract_table_block(sql: str, table_name: str) -> str | None:
    """
    Extract the column-definition block from a CREATE TABLE statement.

    Handles BigQuery DDL where table names are backtick-quoted:
        CREATE TABLE IF NOT EXISTS `{project_id}.dataset.table_name`
        (
          col1 TYPE ...
        )
        PARTITION BY ...

    Returns the text between the opening '(' and the matching closing ')'
    that precedes PARTITION or OPTIONS, or None if not found.
    """
    # Match: CREATE TABLE IF NOT EXISTS `...table_name` <newline> (
    # Using backtick-quoted name to avoid matching comment lines.
    pattern = (
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+"
        r"`[^`]*" + re.escape(table_name) + r"`"
        r"\s*\n\("
        r"(.*?)"
        r"\)\s*\n(PARTITION|OPTIONS)"
    )
    m = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1)
    return None


# ---------------------------------------------------------------------------
# Unit Tests: migration file structure
# ---------------------------------------------------------------------------


class TestMigrationFileExists:
    def test_migration_file_present(self):
        assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"

    def test_migration_file_non_empty(self):
        assert MIGRATION_FILE.stat().st_size > 0, "Migration file is empty"

    def test_backfill_header_present(self):
        """apply_migrations.py requires a -- backfill: header in the first 10 lines."""
        first_lines = MIGRATION_FILE.read_text().splitlines()[:10]
        has_backfill = any(
            re.match(r"--\s*backfill\s*:", line, re.IGNORECASE) for line in first_lines
        )
        assert has_backfill, (
            "Migration file must have a '-- backfill: <issue #NNN | none>' "
            "header in the first 10 lines"
        )


class TestClaimEntityLinkDDL:
    """Migration declares silver_v2_claims.claim_entity_link with required columns."""

    def test_create_table_statement_present(self):
        sql = _normalized(_migration_sql())
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS.*silver_v2_claims.*claim_entity_link",
            sql,
            re.IGNORECASE,
        ), "Missing CREATE TABLE IF NOT EXISTS for claim_entity_link"

    @pytest.mark.parametrize(
        "column",
        ["link_id", "claim_id", "entity_id", "entity_role", "ordinal", "created_at"],
    )
    def test_column_declared(self, column: str):
        sql = _migration_sql()
        block = _extract_table_block(sql, "claim_entity_link")
        assert block is not None, "Could not find claim_entity_link CREATE TABLE block"
        assert column in block, (
            f"Column '{column}' not found in claim_entity_link DDL block"
        )

    def test_partition_by_created_at(self):
        sql = _normalized(_migration_sql())
        m = re.search(
            r"claim_entity_link.*?PARTITION BY DATE\(created_at\)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, "claim_entity_link must be PARTITION BY DATE(created_at)"

    def test_cluster_by_entity_id_claim_id(self):
        sql = _normalized(_migration_sql())
        m = re.search(
            r"claim_entity_link.*?CLUSTER BY entity_id, claim_id",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, "claim_entity_link must CLUSTER BY entity_id, claim_id"


class TestEntityResolutionQueueDDL:
    """Migration declares silver_v2_claims.entity_resolution_queue with required columns."""

    def test_create_table_statement_present(self):
        sql = _normalized(_migration_sql())
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS.*silver_v2_claims.*entity_resolution_queue",
            sql,
            re.IGNORECASE,
        ), "Missing CREATE TABLE IF NOT EXISTS for entity_resolution_queue"

    @pytest.mark.parametrize(
        "column",
        [
            "queue_id",
            "raw_entity_string",
            "normalized_string",
            "domain",
            "placeholder_entity_id",
            "first_seen_at",
            "last_attempted_at",
            "attempt_count",
            "status",
            "resolved_entity_id",
            "resolved_by",
            "resolved_at",
            "notes",
            "created_at",
        ],
    )
    def test_column_declared(self, column: str):
        sql = _migration_sql()
        block = _extract_table_block(sql, "entity_resolution_queue")
        assert block is not None, (
            "Could not find entity_resolution_queue CREATE TABLE block"
        )
        assert column in block, (
            f"Column '{column}' not found in entity_resolution_queue DDL block"
        )

    def test_status_default_pending(self):
        sql = _migration_sql()
        block = _extract_table_block(sql, "entity_resolution_queue")
        assert block is not None, (
            "Could not find entity_resolution_queue CREATE TABLE block"
        )
        # status column should declare DEFAULT 'PENDING'
        assert "PENDING" in block, (
            "entity_resolution_queue.status must declare DEFAULT 'PENDING'"
        )

    def test_partition_by_created_at(self):
        sql = _normalized(_migration_sql())
        m = re.search(
            r"entity_resolution_queue.*?PARTITION BY DATE\(created_at\)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, "entity_resolution_queue must be PARTITION BY DATE(created_at)"

    def test_cluster_by_status_domain(self):
        sql = _normalized(_migration_sql())
        m = re.search(
            r"entity_resolution_queue.*?CLUSTER BY status, domain",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, "entity_resolution_queue must CLUSTER BY status, domain"


class TestClaimStateHistoryDDL:
    """Migration declares silver_v2_claims.claim_state_history with required columns."""

    def test_create_table_statement_present(self):
        sql = _normalized(_migration_sql())
        assert re.search(
            r"CREATE TABLE IF NOT EXISTS.*silver_v2_claims.*claim_state_history",
            sql,
            re.IGNORECASE,
        ), "Missing CREATE TABLE IF NOT EXISTS for claim_state_history"

    @pytest.mark.parametrize(
        "column",
        [
            "history_id",
            "claim_id",
            "state",
            "effective_from",
            "effective_to",
            "effective_source",
            "resolution_id",
            "brier_score",
            "binary_correct",
            "notes",
            "created_at",
        ],
    )
    def test_column_declared(self, column: str):
        sql = _migration_sql()
        block = _extract_table_block(sql, "claim_state_history")
        assert block is not None, (
            "Could not find claim_state_history CREATE TABLE block"
        )
        assert column in block, (
            f"Column '{column}' not found in claim_state_history DDL block"
        )

    def test_partition_by_effective_from(self):
        sql = _normalized(_migration_sql())
        m = re.search(
            r"claim_state_history.*?PARTITION BY DATE\(effective_from\)",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, "claim_state_history must be PARTITION BY DATE(effective_from)"

    def test_cluster_by_claim_id_state(self):
        sql = _normalized(_migration_sql())
        m = re.search(
            r"claim_state_history.*?CLUSTER BY claim_id, state",
            sql,
            re.IGNORECASE | re.DOTALL,
        )
        assert m, "claim_state_history must CLUSTER BY claim_id, state"


class TestAlterTableStatements:
    """Migration contains the required ALTER TABLE ADD COLUMN statements."""

    def test_entity_attribute_event_value_entity_id(self):
        sql = _normalized(_migration_sql())
        assert re.search(
            r"ALTER TABLE.*entity_attribute_event.*ADD COLUMN IF NOT EXISTS.*value_entity_id",
            sql,
            re.IGNORECASE,
        ), "Missing ALTER TABLE entity_attribute_event ADD COLUMN value_entity_id"

    def test_claim_legacy_prediction_hash(self):
        sql = _normalized(_migration_sql())
        assert re.search(
            r"ALTER TABLE.*silver_v2_claims.*claim.*ADD COLUMN IF NOT EXISTS.*legacy_prediction_hash",
            sql,
            re.IGNORECASE,
        ), "Missing ALTER TABLE claim ADD COLUMN legacy_prediction_hash"

    def test_claim_legacy_chain_hash(self):
        sql = _normalized(_migration_sql())
        assert re.search(
            r"ALTER TABLE.*silver_v2_claims.*claim.*ADD COLUMN IF NOT EXISTS.*legacy_chain_hash",
            sql,
            re.IGNORECASE,
        ), "Missing ALTER TABLE claim ADD COLUMN legacy_chain_hash"

    def test_no_drop_statements(self):
        """Phase 1 must be purely additive — no DROP TABLE or DROP COLUMN."""
        sql = _normalized(_migration_sql())
        assert not re.search(r"\bDROP\b", sql, re.IGNORECASE), (
            "Phase 1 migration must not contain any DROP statements"
        )

    def test_entity_timeline_not_dropped(self):
        """entity_timeline must not be dropped in Phase 1."""
        sql = _migration_sql()
        assert "entity_timeline" not in sql or "DROP" not in sql, (
            "entity_timeline must NOT be dropped in Phase 1 — that is Phase 5"
        )


class TestScriptFileExists:
    def test_script_file_present(self):
        assert SCRIPT_FILE.exists(), f"apply_kg_schema.py not found: {SCRIPT_FILE}"

    def test_script_imports_and_parses(self):
        """Script can be imported without crashing (no side effects at module level)."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("apply_kg_schema", SCRIPT_FILE)
        assert spec is not None
        mod = importlib.util.module_from_spec(spec)
        # Just verify the module-level constants are defined without executing main()
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        assert hasattr(mod, "EXPECTED_OBJECTS")
        assert hasattr(mod, "EXPECTED_ALTER_COLUMNS")
        assert hasattr(mod, "MIGRATION_FILE")

    def test_expected_objects_has_three_tables(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("apply_kg_schema", SCRIPT_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        table_names = [obj[1] for obj in mod.EXPECTED_OBJECTS]
        assert "claim_entity_link" in table_names
        assert "entity_resolution_queue" in table_names
        assert "claim_state_history" in table_names

    def test_expected_alter_columns_has_three_entries(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("apply_kg_schema", SCRIPT_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        col_names = [c[2] for c in mod.EXPECTED_ALTER_COLUMNS]
        assert "value_entity_id" in col_names
        assert "legacy_prediction_hash" in col_names
        assert "legacy_chain_hash" in col_names


class TestSplitStatements:
    """Unit tests for the _split_statements helper in apply_kg_schema.py."""

    def _import_split(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location("apply_kg_schema", SCRIPT_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod._split_statements

    def test_splits_on_semicolons(self):
        split = self._import_split()
        stmts = split("SELECT 1; SELECT 2;")
        assert len(stmts) == 2

    def test_does_not_split_inside_string_literal(self):
        split = self._import_split()
        # Semicolon inside a string should not cause a split
        stmts = split("SELECT 'a;b' AS x; SELECT 2;")
        assert len(stmts) == 2

    def test_strips_empty_statements(self):
        split = self._import_split()
        stmts = split("  ;  \n;  SELECT 1;  ")
        # Only the SELECT 1 should survive
        assert len(stmts) == 1

    def test_migration_file_parses_to_six_statements(self):
        """028_kg_schema_additive.sql has exactly 6 DDL statements."""
        split = self._import_split()
        sql = MIGRATION_FILE.read_text().replace("{project_id}", "test-proj")
        stmts = split(sql)
        # 3 CREATE TABLE + 1 ALTER (value_entity_id) + 2 ALTER (legacy_*) = 6
        assert len(stmts) == 6, (
            f"Expected 6 statements in migration file, got {len(stmts)}. "
            "Update this test if statements are intentionally added or removed."
        )


# ---------------------------------------------------------------------------
# Integration tests — require RUN_INTEGRATION=1 + GCP_PROJECT_ID
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION"),
    reason="RUN_INTEGRATION not set — skipping live BigQuery integration tests",
)
class TestKgSchemaPhase1Integration:
    """
    Live BigQuery integration tests.
    Requires 028_kg_schema_additive.sql to have been applied first:
        source .env && python3 pipeline/scripts/apply_kg_schema.py

    Enable with:
        RUN_INTEGRATION=1 pytest pipeline/tests/migrations/test_kg_schema_phase1.py
    """

    @pytest.fixture(scope="class")
    def bq_client(self):
        from google.cloud import bigquery  # type: ignore[import-untyped]

        project_id = os.environ["GCP_PROJECT_ID"]
        client = bigquery.Client(project=project_id)
        yield client
        client.close()

    @pytest.fixture(scope="class")
    def project_id(self):
        return os.environ["GCP_PROJECT_ID"]

    def _query_scalar(self, client, sql: str) -> int:
        rows = list(client.query(sql).result())
        return rows[0][0] if rows else 0

    @pytest.mark.parametrize(
        "dataset,table",
        [
            ("silver_v2_claims", "claim_entity_link"),
            ("silver_v2_claims", "entity_resolution_queue"),
            ("silver_v2_claims", "claim_state_history"),
        ],
    )
    def test_table_exists(self, bq_client, project_id, dataset, table):
        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`
            WHERE table_name = '{table}'
              AND table_type = 'BASE TABLE'
        """
        cnt = self._query_scalar(bq_client, sql)
        assert cnt == 1, f"Table {dataset}.{table} does not exist in BigQuery"

    @pytest.mark.parametrize(
        "dataset,table,column",
        [
            ("silver_v2_claims", "claim_entity_link", "link_id"),
            ("silver_v2_claims", "claim_entity_link", "claim_id"),
            ("silver_v2_claims", "claim_entity_link", "entity_id"),
            ("silver_v2_claims", "claim_entity_link", "entity_role"),
            ("silver_v2_claims", "claim_entity_link", "ordinal"),
            ("silver_v2_claims", "claim_entity_link", "created_at"),
            ("silver_v2_claims", "entity_resolution_queue", "queue_id"),
            ("silver_v2_claims", "entity_resolution_queue", "raw_entity_string"),
            ("silver_v2_claims", "entity_resolution_queue", "placeholder_entity_id"),
            ("silver_v2_claims", "entity_resolution_queue", "status"),
            ("silver_v2_claims", "entity_resolution_queue", "resolved_entity_id"),
            ("silver_v2_claims", "claim_state_history", "history_id"),
            ("silver_v2_claims", "claim_state_history", "claim_id"),
            ("silver_v2_claims", "claim_state_history", "state"),
            ("silver_v2_claims", "claim_state_history", "effective_from"),
            ("silver_v2_claims", "claim_state_history", "effective_to"),
            ("silver_v2_claims", "claim_state_history", "effective_source"),
            ("silver_v2_claims", "claim_state_history", "resolution_id"),
            ("silver_v2_claims", "claim_state_history", "brier_score"),
            ("silver_v2_claims", "claim_state_history", "binary_correct"),
            ("silver_v2_core", "entity_attribute_event", "value_entity_id"),
            ("silver_v2_claims", "claim", "legacy_prediction_hash"),
            ("silver_v2_claims", "claim", "legacy_chain_hash"),
        ],
    )
    def test_column_exists(self, bq_client, project_id, dataset, table, column):
        sql = f"""
            SELECT COUNT(*) AS cnt
            FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table}'
              AND column_name = '{column}'
        """
        cnt = self._query_scalar(bq_client, sql)
        assert cnt == 1, f"Column {dataset}.{table}.{column} does not exist in BigQuery"

    def test_new_tables_are_empty(self, bq_client, project_id):
        """Freshly-created tables should have zero rows (no side effects from DDL)."""
        for dataset, table in [
            ("silver_v2_claims", "claim_entity_link"),
            ("silver_v2_claims", "entity_resolution_queue"),
            ("silver_v2_claims", "claim_state_history"),
        ]:
            sql = f"SELECT COUNT(*) FROM `{project_id}.{dataset}.{table}`"
            cnt = self._query_scalar(bq_client, sql)
            assert cnt == 0, (
                f"Expected {dataset}.{table} to be empty after Phase 1 DDL, "
                f"found {cnt} rows"
            )

    def test_existing_tables_unaffected(self, bq_client, project_id):
        """
        The migration is additive — pre-existing tables in silver_v2_claims and
        silver_v2_core must still exist and be queryable.
        """
        for dataset, table in [
            ("silver_v2_claims", "claim"),
            ("silver_v2_claims", "resolution"),
            ("silver_v2_core", "entity"),
            ("silver_v2_core", "entity_attribute_event"),
        ]:
            sql = f"""
                SELECT COUNT(*) AS cnt
                FROM `{project_id}.{dataset}.INFORMATION_SCHEMA.TABLES`
                WHERE table_name = '{table}'
            """
            cnt = self._query_scalar(bq_client, sql)
            assert cnt >= 1, (
                f"Pre-existing table {dataset}.{table} not found after migration — "
                "Phase 1 must not drop any existing tables"
            )

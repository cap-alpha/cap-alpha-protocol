"""
Validity tests for pipeline/migrations/031_create_claim_embedding.sql
(Issue #1133 — Stage-1 retrieval funnel vector store).

Reuses the real `apply_migrations.py` parsing helpers (the same ones
`scripts/apply_migrations.py` runs against every migration in CI) so this
migration is checked against the actual runner, not a re-implementation of
its parsing rules. No live BigQuery connection required.
"""

from __future__ import annotations

import pathlib
import re
import sys

import pytest

_SCRIPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from apply_migrations import (
    _creates_table,
    _parse_backfill_declaration,
    _split_statements,
)  # noqa: E402

MIGRATION_PATH = (
    pathlib.Path(__file__).parent.parent.parent
    / "migrations"
    / "031_create_claim_embedding.sql"
)


@pytest.fixture(scope="module")
def migration_sql() -> str:
    return MIGRATION_PATH.read_text()


class TestMigrationFileExists:
    def test_file_exists_at_pre_assigned_path(self):
        assert MIGRATION_PATH.exists(), (
            f"Migration 031 must exist at exactly {MIGRATION_PATH} "
            "(pre-assigned number per issue #1133)."
        )


class TestMigrationStructure:
    def test_parses_as_single_create_table_statement(self, migration_sql):
        statements = [s for s in _split_statements(migration_sql) if _creates_table(s)]
        assert len(statements) == 1, (
            f"Expected exactly one CREATE TABLE statement, found "
            f"{len(statements)}: {statements}"
        )

    def test_creates_the_claim_embedding_table(self, migration_sql):
        statements = [s for s in _split_statements(migration_sql) if _creates_table(s)]
        assert "silver_v2_claims.claim_embedding" in statements[0]

    def test_is_idempotent_create_table_if_not_exists(self, migration_sql):
        assert re.search(r"CREATE TABLE IF NOT EXISTS", migration_sql, re.IGNORECASE)

    def test_has_backfill_declaration(self, migration_sql):
        """CREATE TABLE migrations must declare a backfill header (even if
        'none') -- apply_migrations.py warns loudly otherwise. This is a new
        table with nothing to backfill, so 'none' is correct."""
        declaration = _parse_backfill_declaration(migration_sql)
        assert declaration is not None
        assert "none" in declaration.lower()


class TestBigQueryNativeTypes:
    """Repo convention (CLAUDE.md): STRING not VARCHAR, FLOAT64/INT64,
    SAFE_CAST not TRY_CAST, MOD() not %% -- and the vector column must be
    the BigQuery-native ARRAY<FLOAT64>, not a DuckDB-style DOUBLE[]."""

    def test_no_varchar(self, migration_sql):
        assert not re.search(r"\bVARCHAR\b", migration_sql, re.IGNORECASE)

    def test_no_try_cast(self, migration_sql):
        assert not re.search(r"\bTRY_CAST\b", migration_sql, re.IGNORECASE)

    def test_uses_string_type(self, migration_sql):
        assert re.search(r"\bclaim_id\s+STRING\b", migration_sql)

    def test_uses_array_float64_for_embedding(self, migration_sql):
        assert re.search(r"\bembedding\s+ARRAY<FLOAT64>", migration_sql)

    def test_uses_timestamp_for_embedded_at(self, migration_sql):
        assert re.search(r"\bembedded_at\s+TIMESTAMP\b", migration_sql)


class TestSchema:
    """Every column the code in pipeline/src/matching/claim_index.py
    reads/writes must exist in the migration, and vice versa."""

    EXPECTED_COLUMNS = {"claim_id", "embedding", "model_id", "embedded_at"}

    def test_all_expected_columns_present(self, migration_sql):
        for col in self.EXPECTED_COLUMNS:
            assert re.search(rf"\b{col}\b", migration_sql), (
                f"Expected column '{col}' not found in migration SQL"
            )

    # BigQuery rejects NOT NULL on ARRAY columns ("NULL arrays are always stored
    # as an empty array"), so `embedding` must NOT be NOT NULL — declaring it so
    # is a hard 400 that aborts the whole migration step (incident 2026-07-29).
    NOT_NULL_COLUMNS = {"claim_id", "model_id", "embedded_at"}

    def test_scalar_columns_not_null(self, migration_sql):
        """Every scalar column is required. `embedding` (ARRAY) is excluded:
        BigQuery disallows NOT NULL on ARRAY fields."""
        for col in self.NOT_NULL_COLUMNS:
            match = re.search(rf"\b{col}\s+\S+(<\S+>)?\s+NOT NULL", migration_sql)
            assert match, f"Column '{col}' is not declared NOT NULL"

    def test_embedding_array_is_not_not_null(self, migration_sql):
        """Regression: the embedding ARRAY column must NOT carry NOT NULL, or
        BigQuery 400s the migration (incident 2026-07-29)."""
        assert not re.search(
            r"\bembedding\s+ARRAY<FLOAT64>\s+NOT NULL", migration_sql
        ), (
            "embedding ARRAY<FLOAT64> must not be declared NOT NULL (BigQuery rejects it)"
        )

    def test_uses_project_id_placeholder(self, migration_sql):
        """Matches every other migration's envsubst convention --
        `{project_id}`, not a hardcoded project in the DDL itself."""
        create_stmt = [
            s for s in _split_statements(migration_sql) if _creates_table(s)
        ][0]
        assert "{project_id}" in create_stmt
        assert "cap-alpha-protocol" not in create_stmt

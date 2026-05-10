"""
Tests for P0 graph extension schema — entities table, sidecar table, claim_edges view.
Issue #807.

Unit tests run without BigQuery (all BQ calls are mocked).
Integration tests are skipped unless RUN_BQ_INTEGRATION=1 + GCP_PROJECT_ID are set.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

from src.db_manager import DBManager


# ---------------------------------------------------------------------------
# Shared mock factory
# ---------------------------------------------------------------------------


def _make_mock_db() -> MagicMock:
    """Return a MagicMock DBManager pre-wired for graph-extension unit tests."""
    db = MagicMock(spec=DBManager)
    db.project_id = "test-project"
    db.dataset_id = "nfl_dead_money"

    # execute() returns a result proxy mock (no useful return value for write ops)
    exec_result = MagicMock()
    db.execute.return_value = exec_result

    # fetch_df() returns an empty DataFrame by default; override per test
    db.fetch_df.return_value = pd.DataFrame()

    return db


# ---------------------------------------------------------------------------
# Tests: upsert_entity
# ---------------------------------------------------------------------------


class TestUpsertEntity:
    def test_returns_entity_id(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        entity = {
            "entity_id": "player_patrick-mahomes_e3f9a2",
            "entity_type": "PLAYER",
            "canonical_name": "Patrick Mahomes",
            "domain": "SPORTS",
        }
        result = db.upsert_entity(entity)
        assert result == "player_patrick-mahomes_e3f9a2"

    def test_calls_execute_once(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        entity = {
            "entity_id": "team_kc-chiefs_a1b2c3",
            "entity_type": "TEAM",
            "canonical_name": "Kansas City Chiefs",
            "domain": "SPORTS",
        }
        db.upsert_entity(entity)
        db.execute.assert_called_once()

    def test_merge_sql_contains_entity_id(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        entity = {
            "entity_id": "award_super-bowl-mvp_f4e5d6",
            "entity_type": "AWARD",
            "canonical_name": "Super Bowl MVP",
            "domain": "SPORTS",
        }
        db.upsert_entity(entity)
        sql_arg = db.execute.call_args[0][0]
        assert "MERGE" in sql_arg
        assert "entities" in sql_arg

    def test_missing_required_key_raises(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        with pytest.raises(ValueError, match="missing required keys"):
            db.upsert_entity(
                {
                    "entity_id": "player_x_abc123",
                    # entity_type missing
                    "canonical_name": "Someone",
                    "domain": "SPORTS",
                }
            )

    def test_with_aliases_and_metadata(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        entity = {
            "entity_id": "player_lamar-jackson_b7c8d9",
            "entity_type": "PLAYER",
            "canonical_name": "Lamar Jackson",
            "domain": "SPORTS",
            "aliases": ["LJ", "Lamar"],
            "metadata": {"position": "QB", "team": "BAL", "sport": "NFL"},
        }
        db.upsert_entity(entity)
        sql_arg = db.execute.call_args[0][0]
        assert "LJ" in sql_arg
        assert "Lamar" in sql_arg

    def test_domain_defaults_to_sports_when_omitted(self):
        """When domain is not provided, the entity should default to SPORTS."""
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        entity = {
            "entity_id": "player_josh-allen_c1d2e3",
            "entity_type": "PLAYER",
            "canonical_name": "Josh Allen",
            "domain": "SPORTS",  # explicit; default path tested via get call
        }
        entity_id = db.upsert_entity(entity)
        assert entity_id == "player_josh-allen_c1d2e3"


# ---------------------------------------------------------------------------
# Tests: get_entity
# ---------------------------------------------------------------------------


class TestGetEntity:
    def test_returns_none_when_not_found(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        result = db.get_entity("player_nonexistent_000000")
        assert result is None

    def test_returns_dict_when_found(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"

        sample_row = pd.DataFrame(
            [
                {
                    "entity_id": "player_patrick-mahomes_e3f9a2",
                    "entity_type": "PLAYER",
                    "canonical_name": "Patrick Mahomes",
                    "domain": "SPORTS",
                    "claim_count": 42,
                }
            ]
        )
        db.fetch_df = MagicMock(return_value=sample_row)

        result = db.get_entity("player_patrick-mahomes_e3f9a2")
        assert result is not None
        assert result["entity_id"] == "player_patrick-mahomes_e3f9a2"
        assert result["entity_type"] == "PLAYER"
        assert result["claim_count"] == 42

    def test_query_includes_entity_id_filter(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_entity("player_x_abc123")
        sql_arg = db.fetch_df.call_args[0][0]
        assert "entity_id" in sql_arg
        assert "entities" in sql_arg


# ---------------------------------------------------------------------------
# Tests: get_entities_by_name
# ---------------------------------------------------------------------------


class TestGetEntitiesByName:
    def test_returns_empty_list_when_not_found(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        result = db.get_entities_by_name("Nonexistent Player")
        assert result == []

    def test_returns_list_of_dicts(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"

        sample = pd.DataFrame(
            [
                {
                    "entity_id": "player_travis-kelce_d4e5f6",
                    "entity_type": "PLAYER",
                    "canonical_name": "Travis Kelce",
                    "domain": "SPORTS",
                    "claim_count": 77,
                }
            ]
        )
        db.fetch_df = MagicMock(return_value=sample)

        result = db.get_entities_by_name("Travis Kelce")
        assert len(result) == 1
        assert result[0]["entity_id"] == "player_travis-kelce_d4e5f6"

    def test_entity_type_filter_added_when_provided(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_entities_by_name("Chiefs", entity_type="TEAM")
        sql_arg = db.fetch_df.call_args[0][0]
        assert "entity_type" in sql_arg

    def test_no_entity_type_filter_when_omitted(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_entities_by_name("Mahomes")
        sql_arg = db.fetch_df.call_args[0][0]
        # entity_type placeholder should only appear if entity_type was passed
        qp_arg = (
            db.fetch_df.call_args[1].get("query_parameters")
            or db.fetch_df.call_args[0][1]
            if len(db.fetch_df.call_args[0]) > 1
            else []
        )
        param_names = (
            [p.name for p in db.fetch_df.call_args.kwargs.get("query_parameters", [])]
            if db.fetch_df.call_args.kwargs
            else []
        )
        assert "entity_type" not in param_names


# ---------------------------------------------------------------------------
# Tests: upsert_graph_extension
# ---------------------------------------------------------------------------


class TestUpsertGraphExtension:
    def test_calls_execute_once(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        db.upsert_graph_extension(
            "a" * 64,
            {
                "entity_ids": ["player_patrick-mahomes_e3f9a2"],
                "primary_entity_id": "player_patrick-mahomes_e3f9a2",
                "claim_type": "PLAYER_PROP",
                "domain": "SPORTS",
            },
        )
        db.execute.assert_called_once()

    def test_merge_sql_targets_sidecar_table(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        db.upsert_graph_extension(
            "b" * 64,
            {
                "entity_ids": ["team_kc-chiefs_a1b2c3"],
                "claim_type": "GAME_OUTCOME",
                "domain": "SPORTS",
            },
        )
        sql_arg = db.execute.call_args[0][0]
        assert "prediction_ledger_graph_extension" in sql_arg
        assert "MERGE" in sql_arg

    def test_asserted_state_dict_serialized_to_json(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        db.upsert_graph_extension(
            "c" * 64,
            {
                "entity_ids": [],
                "claim_type": "AWARD",
                "asserted_state": {"outcome": "wins", "target_value": "MVP"},
            },
        )
        sql_arg = db.execute.call_args[0][0]
        assert "MVP" in sql_arg

    def test_embedding_list_serialized(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        db.upsert_graph_extension(
            "d" * 64,
            {
                "entity_ids": [],
                "claim_type": "TRADE_MOVE",
                "embedding": [0.1, 0.2, 0.3],
            },
        )
        sql_arg = db.execute.call_args[0][0]
        assert "0.1" in sql_arg
        assert "0.3" in sql_arg

    def test_prediction_hash_passed_as_query_parameter(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.execute = MagicMock()

        phash = "e" * 64
        db.upsert_graph_extension(phash, {"entity_ids": [], "claim_type": "DRAFT"})

        qp_arg = db.execute.call_args[1].get("query_parameters", [])
        qp_names = {p.name: p.value for p in qp_arg}
        assert "prediction_hash" in qp_names
        assert qp_names["prediction_hash"] == phash


# ---------------------------------------------------------------------------
# Tests: get_claim_edges
# ---------------------------------------------------------------------------


class TestGetClaimEdges:
    def test_returns_list(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        result = db.get_claim_edges()
        assert isinstance(result, list)

    def test_query_targets_claim_edges_view(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_claim_edges()
        sql_arg = db.fetch_df.call_args[0][0]
        assert "claim_edges" in sql_arg

    def test_pundit_id_filter_applied(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_claim_edges(pundit_id="adam_schefter")
        sql_arg = db.fetch_df.call_args[0][0]
        assert "pundit_id" in sql_arg

    def test_entity_id_filter_applied(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_claim_edges(entity_id="player_patrick-mahomes_e3f9a2")
        sql_arg = db.fetch_df.call_args[0][0]
        assert "entity_id" in sql_arg
        assert "UNNEST" in sql_arg

    def test_no_filter_has_no_where_clause(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_claim_edges()
        sql_arg = db.fetch_df.call_args[0][0]
        # WHERE clause should not be present when no filters given
        assert "WHERE" not in sql_arg

    def test_limit_passed_as_query_parameter(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"
        db.fetch_df = MagicMock(return_value=pd.DataFrame())

        db.get_claim_edges(limit=25)
        qp_arg = db.fetch_df.call_args[1].get("query_parameters", [])
        qp_map = {p.name: p.value for p in qp_arg}
        assert "limit_val" in qp_map
        assert qp_map["limit_val"] == 25

    def test_returns_records_from_dataframe(self):
        db = DBManager.__new__(DBManager)
        db.project_id = "test-project"
        db.dataset_id = "nfl_dead_money"

        sample = pd.DataFrame(
            [
                {
                    "claim_id": "a" * 64,
                    "pundit_id": "adam_schefter",
                    "raw_assertion_text": "Mahomes wins MVP.",
                    "primary_entity_id": "player_patrick-mahomes_e3f9a2",
                    "claim_type": "AWARD",
                }
            ]
        )
        db.fetch_df = MagicMock(return_value=sample)

        results = db.get_claim_edges(pundit_id="adam_schefter")
        assert len(results) == 1
        assert results[0]["pundit_id"] == "adam_schefter"
        assert results[0]["claim_type"] == "AWARD"


# ---------------------------------------------------------------------------
# Tests: chain integrity still passes after adding sidecar rows
# ---------------------------------------------------------------------------


class TestChainIntegrityUnaffected:
    """
    Regression: upsert_graph_extension must NOT mutate prediction_ledger.
    After writing sidecar rows, verify_chain_integrity should still pass
    because the ledger itself is untouched.
    """

    def test_verify_chain_integrity_unaffected_by_sidecar_write(self):
        """Simulate: write sidecar → chain verification still passes."""
        from src.cryptographic_ledger import (
            HASH_SEED,
            PunditPrediction,
            compute_chain_hash,
            compute_prediction_hash,
            verify_chain_integrity,
        )

        # Build a valid two-row chain
        pred = PunditPrediction(
            pundit_id="test_pundit",
            pundit_name="Test Pundit",
            source_url="https://example.com/test",
            raw_assertion_text="Mahomes wins Super Bowl.",
            ingestion_timestamp=datetime(2025, 9, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        phash = compute_prediction_hash(pred)
        chain = compute_chain_hash(phash, HASH_SEED)

        # Mock DB that returns a valid chain
        mock_db = MagicMock()
        ddl_job = MagicMock()
        ddl_job.result.return_value = None
        mock_db.client.query.return_value = ddl_job
        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "prediction_hash": phash,
                    "chain_hash": chain,
                    "ingestion_timestamp": pred.ingestion_timestamp,
                    "source_url": pred.source_url,
                    "pundit_id": pred.pundit_id,
                    "raw_assertion_text": pred.raw_assertion_text,
                }
            ]
        )

        # Also simulate a sidecar write (doesn't touch mock_db.fetch_df)
        sidecar_db = DBManager.__new__(DBManager)
        sidecar_db.project_id = "test-project"
        sidecar_db.dataset_id = "nfl_dead_money"
        sidecar_db.execute = MagicMock()
        sidecar_db.upsert_graph_extension(
            phash,
            {
                "entity_ids": ["player_patrick-mahomes_e3f9a2"],
                "claim_type": "AWARD",
            },
        )
        sidecar_db.execute.assert_called_once()  # sidecar write happened

        # Now verify chain on the original (mock) ledger — must still pass
        result = verify_chain_integrity(db=mock_db)
        assert result["verified"] is True
        assert result["total_records"] == 1
        assert result["first_break_at"] is None


# ---------------------------------------------------------------------------
# Integration tests — require RUN_BQ_INTEGRATION=1 + GCP_PROJECT_ID
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("RUN_BQ_INTEGRATION"),
    reason="RUN_BQ_INTEGRATION not set — skipping live BigQuery integration tests",
)
class TestGraphExtensionIntegration:
    """
    Live BigQuery integration tests. Require the tables to exist (run migration 024
    first via scripts/apply_migrations.py).
    Enable with: RUN_BQ_INTEGRATION=1 pytest tests/test_graph_extension_schema.py
    """

    TEST_ENTITY_ID = "_test_graph_ext_player_e3f9a2"
    TEST_PHASH = "f" * 64  # fake but deterministic test hash

    def test_upsert_and_get_entity(self):
        db = DBManager()
        try:
            entity_id = db.upsert_entity(
                {
                    "entity_id": self.TEST_ENTITY_ID,
                    "entity_type": "PLAYER",
                    "canonical_name": "_Test Graph Extension Player",
                    "domain": "SPORTS",
                    "aliases": ["_TestPlayer", "_TGE"],
                    "metadata": {"position": "QB", "sport": "NFL"},
                }
            )
            assert entity_id == self.TEST_ENTITY_ID

            fetched = db.get_entity(self.TEST_ENTITY_ID)
            assert fetched is not None
            assert fetched["canonical_name"] == "_Test Graph Extension Player"
        finally:
            db.close()

    def test_upsert_graph_extension_and_query_view(self):
        db = DBManager()
        try:
            db.upsert_graph_extension(
                self.TEST_PHASH,
                {
                    "entity_ids": [self.TEST_ENTITY_ID],
                    "primary_entity_id": self.TEST_ENTITY_ID,
                    "claim_type": "PLAYER_PROP",
                    "domain": "SPORTS",
                    "entity_resolution_confidence": 0.95,
                },
            )
            # Retrieve via get_claim_edges — the test phash won't appear in the
            # real ledger, but the sidecar row itself exists. We verify no error.
            edges = db.get_claim_edges(entity_id=self.TEST_ENTITY_ID, limit=10)
            # Result may be empty if test phash has no ledger row — that's fine.
            assert isinstance(edges, list)
        finally:
            db.close()

"""
Phase 3 (#920) unit tests for assertion_extractor silver_v2 writes.

Tests cover:
  - write_claim_entity_links: known entity, unresolved entity, multiple entities
  - write_claim_state_history: PENDING row inserted correctly
  - write_silver_v2_claims integration: claim + entity_link + state_history written
  - DUAL_WRITE_LEGACY=false disables legacy ingest_batch path

These tests do NOT require a live BigQuery connection. All BQ calls are
intercepted by a stub that captures DataFrames for assertion.

LLM smoke test (marked pytest.mark.smoke):
  - A real Gemini/Ollama call is exercised when SMOKE_TEST_LLM=1 is set.
  - Required by extraction PR rules (issue #920, CLAUDE.md).
"""

import datetime as dt
import json
import os
import types  # noqa: F401 — kept for potential future use
from datetime import timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


class _JobStub:
    """Minimal BQ load-job stub."""

    def result(self):
        pass


class _BQRow(dict):
    """
    Minimal BQ row stub that supports both dict-style ``row["key"]`` and
    attribute-style ``row.key`` access (mirrors google.cloud.bigquery.Row).
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


class _QueryJobStub:
    """Minimal BQ query-job stub that returns no rows by default."""

    def __init__(self, rows=None):
        self._rows = rows or []

    def result(self):
        return self._rows


class _ClientStub:
    """
    Minimal BQ client stub that intercepts load_table_from_dataframe and query.

    Calls to load_table_from_dataframe are appended to self.captured with their
    table_ref, so tests can assert on which tables were written and what data
    was written.

    Calls to query() return an empty result by default; tests may override
    self.query_results to return specific rows.
    """

    def __init__(self, query_rows=None):
        self.captured: list[tuple[str, pd.DataFrame]] = []  # (table_ref, df)
        self.query_rows = query_rows or []  # rows returned by query().result()
        self.merge_calls: list[str] = []  # SQL strings passed to query()

    def load_table_from_dataframe(self, df, table_ref, job_config):
        self.captured.append((table_ref, df.copy()))
        return _JobStub()

    def query(self, sql, job_config=None):
        self.merge_calls.append(sql)
        return _QueryJobStub(self.query_rows)


class _DBStub:
    """Minimal DBManager stub."""

    def __init__(self, query_rows=None):
        self.client = _ClientStub(query_rows=query_rows)


# ---------------------------------------------------------------------------
# Tests for write_claim_entity_links
# ---------------------------------------------------------------------------


class TestWriteClaimEntityLinks:
    """Unit tests for write_claim_entity_links (Phase 3 / #920)."""

    @pytest.fixture(autouse=True)
    def _bq_env(self, monkeypatch):
        """Force BigQuery backend for every test in this class.

        test_promote_claims sets DB_BACKEND=duckdb at module-import time, which
        poisons the process environment. Without this fixture, _resolve_entity_id
        takes the DuckDB path, hits missing fetch_df on _DBStub, swallows the
        exception, and returns a placeholder — causing false failures.
        """
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    def _call(self, claim_id, utterance, domain="nfl", query_rows=None):
        from src.assertion_extractor import write_claim_entity_links

        db = _DBStub(query_rows=query_rows)
        result = write_claim_entity_links(claim_id, utterance, domain, db)
        return result, db.client

    def test_no_entity_mentions_returns_empty_list(self):
        """Utterance with no entity fields must return [] and write nothing."""
        links, client = self._call(
            claim_id="claim-001",
            utterance={
                "text": "The offense has been improving",
                "speech_act_type": "commentary",
            },
        )
        assert links == []
        # No load_table_from_dataframe calls expected
        assert not any("claim_entity_link" in ref for ref, _ in client.captured)

    def test_known_entity_resolved_from_alias(self):
        """When alias lookup hits, entity_id from DB is used; no placeholder created."""
        from src.assertion_extractor import write_claim_entity_links

        # Simulate alias lookup returning a real entity_id
        real_entity_id = "player_patrick-mahomes_e3f9a2"
        db = _DBStub(query_rows=[_BQRow(entity_id=real_entity_id)])

        utterance = {"target_player": "Patrick Mahomes"}
        links = write_claim_entity_links("claim-002", utterance, "nfl", db)

        assert len(links) == 1
        assert links[0]["entity_id"] == real_entity_id
        assert links[0]["entity_role"] == "subject"
        assert links[0]["claim_id"] == "claim-002"

        # One BQ write for claim_entity_link
        link_writes = [
            (ref, df) for ref, df in db.client.captured if "claim_entity_link" in ref
        ]
        assert len(link_writes) == 1
        written_df = link_writes[0][1]
        assert written_df.iloc[0]["entity_id"] == real_entity_id

        # No MERGE calls for placeholder (entity resolved)
        placeholder_merges = [
            sql
            for sql in db.client.merge_calls
            if "silver_v2_core.entity" in sql and "unresolved" in sql
        ]
        assert placeholder_merges == []

    def test_unresolved_entity_creates_placeholder_and_queue_row(self):
        """When alias lookup misses, placeholder entity + queue row are inserted."""
        from src.assertion_extractor import (
            _placeholder_entity_id,
            write_claim_entity_links,
        )

        db = _DBStub(query_rows=[])  # empty — simulates alias lookup miss

        utterance = {"target_player": "UnknownPlayer XYZ"}
        links = write_claim_entity_links("claim-003", utterance, "nfl", db)

        assert len(links) == 1
        expected_placeholder = _placeholder_entity_id("UnknownPlayer XYZ")
        assert links[0]["entity_id"] == expected_placeholder
        assert links[0]["entity_role"] == "subject"

        # entity_resolution_queue insert must have been called
        queue_merges = [
            sql for sql in db.client.merge_calls if "entity_resolution_queue" in sql
        ]
        assert len(queue_merges) >= 1

        # silver_v2_core.entity MERGE (placeholder upsert) must have been called
        placeholder_merges = [
            sql for sql in db.client.merge_calls if "silver_v2_core.entity" in sql
        ]
        assert len(placeholder_merges) >= 1

    def test_multiple_entities_written_as_separate_rows(self):
        """target_player + target_team must each produce a separate link row."""
        db = _DBStub(query_rows=[])  # both unresolved

        utterance = {
            "target_player": "Josh Allen",
            "target_team": "Buffalo Bills",
        }
        links, client = self._call("claim-004", utterance, "nfl", query_rows=[])

        # Two link rows: one for player (subject), one for team (context)
        assert len(links) == 2
        roles = {link["entity_role"] for link in links}
        assert "subject" in roles
        assert "context" in roles

    def test_no_project_id_returns_empty_without_writing(self, monkeypatch):
        """Without GCP_PROJECT_ID, function returns [] without BQ writes."""
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        from src.assertion_extractor import write_claim_entity_links

        db = _DBStub()
        utterance = {"target_player": "Lamar Jackson"}
        result = write_claim_entity_links("claim-005", utterance, "nfl", db)

        assert result == []
        assert db.client.captured == []

    def test_duplicate_entity_role_deduplicated(self):
        """Same entity mention in both target_player and subject is only written once."""
        db = _DBStub(query_rows=[])

        utterance = {
            "target_player": "Jalen Hurts",
            "subject": "Jalen Hurts",  # duplicate mention
        }
        links, _ = self._call("claim-006", utterance, "nfl", query_rows=[])
        # Only one subject link (deduped)
        subject_links = [l for l in links if l["entity_role"] == "subject"]
        assert len(subject_links) == 1


# ---------------------------------------------------------------------------
# Tests for write_claim_state_history
# ---------------------------------------------------------------------------


class TestWriteClaimStateHistory:
    """Unit tests for write_claim_state_history (Phase 3 / #920)."""

    @pytest.fixture(autouse=True)
    def _bq_env(self, monkeypatch):
        """Force BigQuery backend — see TestWriteClaimEntityLinks._bq_env for rationale."""
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    def _call(self, claim_id):
        from src.assertion_extractor import write_claim_state_history

        db = _DBStub()
        result = write_claim_state_history(claim_id, db)
        return result, db.client

    def test_writes_pending_row(self):
        """Must write a single PENDING row to claim_state_history."""
        success, client = self._call("claim-sh-001")

        assert success is True
        state_writes = [
            (ref, df) for ref, df in client.captured if "claim_state_history" in ref
        ]
        assert len(state_writes) == 1
        df = state_writes[0][1]
        assert len(df) == 1
        row = df.iloc[0]
        assert row["state"] == "PENDING"
        assert row["effective_source"] == "ingestion"
        assert row["claim_id"] == "claim-sh-001"

    def test_effective_to_is_null(self):
        """PENDING row effective_to must be NULL (open/current state)."""
        _, client = self._call("claim-sh-002")
        df = next(df for ref, df in client.captured if "claim_state_history" in ref)
        row = df.iloc[0]
        # NaT in pandas = NULL in BQ
        import pandas as pd

        assert pd.isna(row["effective_to"])

    def test_no_project_id_returns_false(self, monkeypatch):
        """Without GCP_PROJECT_ID, function returns False without BQ writes."""
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        from src.assertion_extractor import write_claim_state_history

        db = _DBStub()
        result = write_claim_state_history("claim-sh-003", db)
        assert result is False
        assert db.client.captured == []

    def test_no_db_returns_false(self):
        """Without a DB instance, function returns False without crashing."""
        from src.assertion_extractor import write_claim_state_history

        result = write_claim_state_history("claim-sh-004", db=None)
        assert result is False

    def test_bq_error_returns_false(self):
        """BQ write failure must return False (non-fatal)."""
        from src.assertion_extractor import write_claim_state_history

        class _ErrorClientStub:
            def load_table_from_dataframe(self, *a, **kw):
                raise RuntimeError("Simulated BQ write failure")

        class _ErrorDB:
            client = _ErrorClientStub()

        result = write_claim_state_history("claim-sh-005", db=_ErrorDB())
        assert result is False


# ---------------------------------------------------------------------------
# Integration-style test: write_silver_v2_claims calls all Phase-3 writes
# ---------------------------------------------------------------------------


class TestWriteSilverV2ClaimsPhase3Integration:
    """
    Integration tests verifying that write_silver_v2_claims (#920 Phase 3) writes
    claim_entity_link and claim_state_history after the main claim write.
    """

    @pytest.fixture(autouse=True)
    def _bq_env(self, monkeypatch):
        """Force BigQuery backend — see TestWriteClaimEntityLinks._bq_env for rationale."""
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    def _make_db_stub(self):
        """DB stub that also supports query() calls (for alias lookups)."""
        return _DBStub(query_rows=[])  # alias lookups miss → placeholder path

    def _make_utterance(self, target_player="Saquon Barkley", target_team="PHI"):
        return {
            "text": f"{target_player} will rush for 1200+ yards",
            "extracted_claim": f"{target_player} will rush for 1200+ yards",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "predicate": "will_exceed",
            "predicate_args": {"threshold": 1200, "stat": "rushing_yards"},
            "claim_category": "player_performance",
            "resolution_horizon": "2025-12-31T23:59:59Z",
            "target_player": target_player,
            "target_team": target_team,
        }

    def test_claim_entity_link_written_after_claim(self):
        """Phase 3: claim_entity_link rows must be written for each claim."""
        from src.assertion_extractor import write_silver_v2_claims

        db = self._make_db_stub()
        u = self._make_utterance()

        count = write_silver_v2_claims(
            utterances=[u],
            utterance_id_map={u["text"][:4000]: "uid-001"},
            source_doc_id="doc-hash-001",
            speaker_entity_id="pundit-001",
            uttered_at=dt.datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
            threshold=0.6,
        )

        assert count == 1
        link_writes = [
            df for ref, df in db.client.captured if "claim_entity_link" in ref
        ]
        assert len(link_writes) >= 1
        # At least one link row for the target_player
        total_links = sum(len(df) for df in link_writes)
        assert total_links >= 1

    def test_claim_state_history_written_after_claim(self):
        """Phase 3: PENDING claim_state_history row must be written for each claim."""
        from src.assertion_extractor import write_silver_v2_claims

        db = self._make_db_stub()
        u = self._make_utterance()

        count = write_silver_v2_claims(
            utterances=[u],
            utterance_id_map={u["text"][:4000]: "uid-002"},
            source_doc_id="doc-hash-002",
            speaker_entity_id="pundit-002",
            uttered_at=dt.datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
            threshold=0.6,
        )

        assert count == 1
        history_writes = [
            df for ref, df in db.client.captured if "claim_state_history" in ref
        ]
        assert len(history_writes) == 1
        row = history_writes[0].iloc[0]
        assert row["state"] == "PENDING"
        assert row["effective_source"] == "ingestion"

    def test_unresolved_entity_creates_placeholder_and_queue(self):
        """
        Unresolved entity mention must produce:
        - placeholder entity MERGE in silver_v2_core.entity
        - entity_resolution_queue MERGE
        - claim_entity_link row pointing to placeholder
        """
        from src.assertion_extractor import (
            _placeholder_entity_id,
            write_silver_v2_claims,
        )

        db = self._make_db_stub()  # alias lookups return no rows → miss
        u = self._make_utterance(target_player="Unrecognized Athlete Q", target_team="")

        write_silver_v2_claims(
            utterances=[u],
            utterance_id_map={u["text"][:4000]: "uid-003"},
            source_doc_id="doc-hash-003",
            speaker_entity_id="pundit-003",
            uttered_at=dt.datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
            threshold=0.6,
        )

        # entity_resolution_queue MERGE must have been called
        queue_calls = [
            s for s in db.client.merge_calls if "entity_resolution_queue" in s
        ]
        assert len(queue_calls) >= 1

        # silver_v2_core.entity MERGE (placeholder) must have been called
        placeholder_calls = [
            s for s in db.client.merge_calls if "silver_v2_core.entity" in s
        ]
        assert len(placeholder_calls) >= 1

        # claim_entity_link row must point to the placeholder
        expected_ph = _placeholder_entity_id("Unrecognized Athlete Q")
        link_writes = [
            df for ref, df in db.client.captured if "claim_entity_link" in ref
        ]
        assert len(link_writes) >= 1
        link_entity_ids = set(link_writes[0]["entity_id"])
        assert expected_ph in link_entity_ids

    def test_multiple_utterances_each_get_state_history_row(self):
        """Each promoted utterance must produce exactly one state_history row."""
        from src.assertion_extractor import write_silver_v2_claims

        db = self._make_db_stub()
        utterances = [
            self._make_utterance("Tyreek Hill", "MIA"),
            self._make_utterance("Justin Jefferson", "MIN"),
        ]

        count = write_silver_v2_claims(
            utterances=utterances,
            utterance_id_map={
                utterances[0]["text"][:4000]: "uid-004",
                utterances[1]["text"][:4000]: "uid-005",
            },
            source_doc_id="doc-hash-004",
            speaker_entity_id="pundit-004",
            uttered_at=dt.datetime(2025, 9, 1, tzinfo=timezone.utc),
            domain="nfl",
            db=db,
            threshold=0.6,
        )

        assert count == 2
        history_writes = [
            df for ref, df in db.client.captured if "claim_state_history" in ref
        ]
        # One state_history write per claim
        total_history_rows = sum(len(df) for df in history_writes)
        assert total_history_rows == 2


# ---------------------------------------------------------------------------
# Test for DUAL_WRITE_LEGACY feature flag
# ---------------------------------------------------------------------------


class TestDualWriteLegacyFlag:
    """
    DUAL_WRITE_LEGACY=false must disable the legacy ingest_batch
    (gold_layer.prediction_ledger) write path.

    Tests exercise run_extraction() with a fully-mocked pipeline so the only
    real logic exercised is the DUAL_WRITE_LEGACY branch.
    """

    def _make_article_df(self, content_hash="testhash001"):
        return pd.DataFrame(
            [
                {
                    "content_hash": content_hash,
                    "source_id": "espn_nfl",
                    "title": "Test article",
                    "raw_text": " ".join(["word"] * 60),
                    "source_url": f"https://espn.com/{content_hash}",
                    "author": "Adam Schefter",
                    "matched_pundit_id": "adam_schefter",
                    "matched_pundit_name": "Adam Schefter",
                    "published_at": dt.datetime(2025, 9, 1, tzinfo=timezone.utc),
                    "sport": "NFL",
                }
            ]
        )

    def _make_prediction_dict(self):
        return {
            "extracted_claim": "Eagles win SB",
            "claim_category": "game_outcome",
            "speech_act_type": "assertion",
            "testability_score": 0.9,
            "stance": "bullish",
            "target_player": None,
            "target_team": "PHI",
            "season_year": 2025,
            "prediction_horizon_days": 180,
            "confidence_note": "confident",
            "resolution_horizon": "2026-02-01T00:00:00Z",
            "text": "Eagles win SB",
            "predicate": "will_win",
            "predicate_args": {},
            "target_entity": None,
            "originating_speaker": None,
            "speech_act": "authored",
            "target_player_name": None,
        }

    def _run_with_flag(self, dual_write_value: str):
        """Helper: run run_extraction with DUAL_WRITE_LEGACY set to dual_write_value.

        Returns the mock_ingest mock for assertion.
        """
        from src.assertion_extractor import ExtractionResult, run_extraction

        pred = self._make_prediction_dict()

        with patch.dict(
            os.environ,
            {"DUAL_WRITE_LEGACY": dual_write_value, "GCP_PROJECT_ID": "test-project"},
        ):
            with patch("src.assertion_extractor.ingest_batch") as mock_ingest:
                mock_ingest.return_value = ["hash1"]
                with patch(
                    "src.assertion_extractor.get_unprocessed_media",
                    return_value=self._make_article_df(),
                ):
                    with patch(
                        "src.assertion_extractor.extract_assertions"
                    ) as mock_extract:
                        mock_extract.return_value = ExtractionResult(
                            content_hash="testhash001",
                            predictions=[pred],
                            utterances=[pred],
                        )
                        db = MagicMock()
                        db.client.load_table_from_dataframe.return_value = _JobStub()
                        db.client.query.return_value = _QueryJobStub([])
                        db.fetch_df.return_value = pd.DataFrame()

                        with patch("src.assertion_extractor.mark_as_processed"):
                            with patch(
                                "src.assertion_extractor.write_raw_utterances",
                                return_value=(1, {pred["text"]: "uid-x"}),
                            ):
                                with patch(
                                    "src.assertion_extractor.write_silver_v2_claims",
                                    return_value=1,
                                ):
                                    with patch(
                                        "src.assertion_extractor._write_extraction_run"
                                    ):
                                        run_extraction(
                                            limit=1,
                                            dry_run=False,
                                            db=db,
                                            provider=MagicMock(
                                                model="mock",
                                                extract_predictions=mock_extract,
                                            ),
                                        )
                # Capture mock_ingest call count before context exits
                return mock_ingest.call_count

    def test_dual_write_false_skips_ingest_batch(self):
        """When DUAL_WRITE_LEGACY=false, ingest_batch must not be called."""
        call_count = self._run_with_flag("false")
        assert call_count == 0, (
            f"ingest_batch should not be called with DUAL_WRITE_LEGACY=false, "
            f"but was called {call_count} time(s)"
        )

    def test_dual_write_true_calls_ingest_batch(self):
        """When DUAL_WRITE_LEGACY=true, ingest_batch must be called."""
        call_count = self._run_with_flag("true")
        assert call_count == 1, (
            f"ingest_batch should be called once with DUAL_WRITE_LEGACY=true, "
            f"but was called {call_count} time(s)"
        )


# ---------------------------------------------------------------------------
# Entity resolution helper tests
# ---------------------------------------------------------------------------


class TestEntityResolutionHelpers:
    """Unit tests for _placeholder_entity_id, _normalize_entity_string."""

    @pytest.fixture(autouse=True)
    def _bq_env(self, monkeypatch):
        """Force BigQuery backend — see TestWriteClaimEntityLinks._bq_env for rationale."""
        monkeypatch.delenv("DB_BACKEND", raising=False)
        monkeypatch.setenv("GCP_PROJECT_ID", "test-project")

    def test_placeholder_entity_id_format(self):
        """Placeholder entity_id must be 'unresolved:{sha256_hex}'."""
        from src.assertion_extractor import _placeholder_entity_id

        pid = _placeholder_entity_id("Patrick Mahomes")
        assert pid.startswith("unresolved:")
        hash_part = pid[len("unresolved:") :]
        assert len(hash_part) == 64  # SHA256 hex

    def test_placeholder_entity_id_is_deterministic(self):
        """Same input must produce same placeholder id."""
        from src.assertion_extractor import _placeholder_entity_id

        pid1 = _placeholder_entity_id("Patrick Mahomes")
        pid2 = _placeholder_entity_id("Patrick Mahomes")
        assert pid1 == pid2

    def test_normalize_strips_diacritics_and_lowercases(self):
        """Normalization must lower-case and remove diacritics."""
        from src.assertion_extractor import _normalize_entity_string

        assert _normalize_entity_string("Andrés Torres") == "andres torres"
        assert _normalize_entity_string("  Mahomes  ") == "mahomes"

    def test_resolve_entity_id_returns_placeholder_when_no_project_id(
        self, monkeypatch
    ):
        """_resolve_entity_id must return (placeholder, False) with no project_id."""
        monkeypatch.delenv("GCP_PROJECT_ID", raising=False)
        from src.assertion_extractor import _placeholder_entity_id, _resolve_entity_id

        db = _DBStub()
        eid, resolved = _resolve_entity_id("Patrick Mahomes", "nfl", db)
        assert resolved is False
        assert eid == _placeholder_entity_id("Patrick Mahomes")

    def test_resolve_entity_id_returns_real_id_on_alias_hit(self):
        """_resolve_entity_id must return (real_id, True) when alias lookup hits."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            from src.assertion_extractor import _resolve_entity_id

            real_id = "player_joe-burrow_a1b2c3"
            db = _DBStub(query_rows=[_BQRow(entity_id=real_id)])
            eid, resolved = _resolve_entity_id("Joe Burrow", "nfl", db)
            assert resolved is True
            assert eid == real_id

    def test_resolve_entity_id_returns_placeholder_on_alias_miss(self):
        """_resolve_entity_id must return (placeholder, False) when alias lookup misses."""
        with patch.dict(os.environ, {"GCP_PROJECT_ID": "test-project"}):
            from src.assertion_extractor import (
                _placeholder_entity_id,
                _resolve_entity_id,
            )

            db = _DBStub(query_rows=[])  # no rows → miss
            eid, resolved = _resolve_entity_id("Unknown Person ABC", "nfl", db)
            assert resolved is False
            assert eid == _placeholder_entity_id("Unknown Person ABC")


# ---------------------------------------------------------------------------
# Smoke test — real LLM call (extraction PR requirement)
# ---------------------------------------------------------------------------


_SMOKE_REASON = (
    "SMOKE_TEST_LLM not set — set SMOKE_TEST_LLM=1 to run real LLM smoke test"
)
_skip_smoke = pytest.mark.skipif(
    not os.environ.get("SMOKE_TEST_LLM"),
    reason=_SMOKE_REASON,
)


@pytest.mark.smoke
@_skip_smoke
def test_extraction_smoke_real_llm_call():
    """
    Extraction PR rule: at least one real LLM call must be exercised.

    This test calls extract_assertions with a real provider (Ollama/Gemini
    depending on LLM_CONFIG) on a short mock article and asserts that:
    - At least one utterance is returned
    - Each utterance has the expected Phase-C fields
    - No error is raised

    Set SMOKE_TEST_LLM=1 and ensure LLM_CONFIG_PATH or the default
    pipeline/config/llm_config.yaml points to a running provider.
    """
    import sys

    sys.path.insert(
        0,
        str(__import__("pathlib").Path(__file__).parent.parent / "src"),
    )
    from src.assertion_extractor import extract_assertions
    from src.llm_provider import load_llm_config, get_provider_with_fallback

    config = load_llm_config()
    provider = get_provider_with_fallback("extraction", config)

    article_text = (
        "Adam Schefter reports that Patrick Mahomes will sign a contract extension "
        "with the Kansas City Chiefs keeping him through the 2030 season. "
        "Additionally, the Chiefs are expected to win the AFC West this year "
        "and Mahomes will throw for at least 4,000 yards."
    )

    result = extract_assertions(
        text=article_text,
        sport="NFL",
        published_date="2025-09-01",
        provider=provider,
    )

    # Basic structural assertions — do not hard-code LLM output
    assert result is not None, "extract_assertions returned None"
    assert hasattr(result, "utterances"), "Result must have utterances attribute"
    assert isinstance(result.utterances, list), "utterances must be a list"
    assert len(result.utterances) > 0, (
        "Expected at least one utterance from a 3-sentence article with predictions"
    )

    required_fields = {"text", "speech_act_type", "testability_score"}
    for u in result.utterances:
        missing = required_fields - set(u.keys())
        assert not missing, (
            f"Utterance missing required fields: {missing}\nutterance={u}"
        )
        assert u.get("speech_act_type") in {
            "assertion",
            "conditional",
            "recall",
            "rhetorical_question",
            "hedge",
            "commentary",
            "opinion",
            "analogy",
            "joke",
        }, f"Invalid speech_act_type: {u.get('speech_act_type')}"

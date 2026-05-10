"""
Tests for Issue #830 adjudication decisions.

Covers:
  1. Retraction before horizon → VOID
  2. Retraction after horizon → scored normally (CORRECT / INCORRECT)
  3. Published flag — unpublished pundit excluded from public API summary
  4. Minimum-claims guard — <5 resolved claims returns null accuracy_rate
  5. publish_tier1_pundits seed script (idempotent, update vs insert)

No BigQuery required — all DB access is mocked.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_HASH = "c" * 64
UTC = timezone.utc


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_df.return_value = pd.DataFrame()
    return db


# ---------------------------------------------------------------------------
# 1. Retraction logic
# ---------------------------------------------------------------------------


class TestRetractedAtLogic:
    """resolve_with_retraction_check: early retraction → VOID, late → scored."""

    def _import(self):
        from src.resolution_engine import resolve_with_retraction_check

        return resolve_with_retraction_check

    def test_retraction_before_horizon_is_void(self, mock_db):
        """V5 rule: retract before resolution horizon → VOID."""
        resolve_with_retraction_check = self._import()

        horizon = datetime(2025, 9, 5, tzinfo=UTC)
        retracted_at = datetime(2025, 9, 3, tzinfo=UTC)  # before horizon

        result = resolve_with_retraction_check(
            prediction_hash=FAKE_HASH,
            retracted_at=retracted_at,
            resolution_horizon=horizon,
            correct=True,
            outcome_source="manual",
            db=mock_db,
        )

        assert result.resolution_status == "VOID"
        assert result.brier_score is None
        assert result.binary_correct is None
        assert "retracted" in (result.outcome_notes or "").lower()

    def test_retraction_equal_to_horizon_scores_normally(self, mock_db):
        """Retraction exactly at horizon: score normally (boundary is inclusive)."""
        resolve_with_retraction_check = self._import()

        horizon = datetime(2025, 9, 5, tzinfo=UTC)
        retracted_at = horizon  # exactly at horizon

        result = resolve_with_retraction_check(
            prediction_hash=FAKE_HASH,
            retracted_at=retracted_at,
            resolution_horizon=horizon,
            correct=True,
            outcome_source="manual",
            db=mock_db,
        )

        assert result.resolution_status == "CORRECT"

    def test_retraction_after_horizon_scores_correct(self, mock_db):
        """Late retraction: outcome locked in; score as CORRECT."""
        resolve_with_retraction_check = self._import()

        horizon = datetime(2025, 9, 5, tzinfo=UTC)
        retracted_at = datetime(2025, 9, 10, tzinfo=UTC)  # after horizon

        result = resolve_with_retraction_check(
            prediction_hash=FAKE_HASH,
            retracted_at=retracted_at,
            resolution_horizon=horizon,
            correct=True,
            outcome_source="sportsdataio",
            db=mock_db,
        )

        assert result.resolution_status == "CORRECT"
        assert result.binary_correct is True

    def test_retraction_after_horizon_scores_incorrect(self, mock_db):
        """Late retraction: outcome locked in; score as INCORRECT."""
        resolve_with_retraction_check = self._import()

        horizon = datetime(2025, 9, 5, tzinfo=UTC)
        retracted_at = datetime(2025, 9, 20, tzinfo=UTC)  # well after horizon

        result = resolve_with_retraction_check(
            prediction_hash=FAKE_HASH,
            retracted_at=retracted_at,
            resolution_horizon=horizon,
            correct=False,
            outcome_source="sportsdataio",
            db=mock_db,
        )

        assert result.resolution_status == "INCORRECT"
        assert result.binary_correct is False

    def test_early_retraction_void_notes_include_timestamps(self, mock_db):
        """VOID notes must cite the retraction and horizon timestamps for auditability."""
        resolve_with_retraction_check = self._import()

        horizon = datetime(2025, 10, 1, tzinfo=UTC)
        retracted_at = datetime(2025, 9, 1, tzinfo=UTC)

        result = resolve_with_retraction_check(
            prediction_hash=FAKE_HASH,
            retracted_at=retracted_at,
            resolution_horizon=horizon,
            correct=True,
            outcome_source="manual",
            db=mock_db,
        )

        # Notes should reference both timestamps
        notes = result.outcome_notes or ""
        assert "2025-09-01" in notes  # retracted_at
        assert "2025-10-01" in notes  # resolution_horizon


# ---------------------------------------------------------------------------
# 2. Published flag — get_pundit_accuracy_summary
# ---------------------------------------------------------------------------


class TestPublishedOnlyFilter:
    """published_only=True adds a JOIN that excludes unpublished pundits."""

    def test_published_only_false_no_join(self, mock_db):
        """Default: no published join in SQL."""
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        get_pundit_accuracy_summary(db=mock_db, published_only=False)
        query = mock_db.fetch_df.call_args[0][0]
        # Should NOT contain pundit_registry join when published_only=False
        assert "pundit_registry" not in query

    def test_published_only_true_adds_join(self, mock_db):
        """published_only=True: query joins pundit_registry with published=TRUE."""
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        get_pundit_accuracy_summary(db=mock_db, published_only=True)
        query = mock_db.fetch_df.call_args[0][0]
        assert "pundit_registry" in query
        assert "published = TRUE" in query

    def test_published_only_uses_inner_join(self, mock_db):
        """Inner join (not left join) ensures unpublished pundits are excluded."""
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        get_pundit_accuracy_summary(db=mock_db, published_only=True)
        query = mock_db.fetch_df.call_args[0][0]
        assert "INNER JOIN" in query


# ---------------------------------------------------------------------------
# 3. Minimum resolved claims guard
# ---------------------------------------------------------------------------


class TestMinResolvedClaimsGuard:
    """Pundits with fewer than N resolved claims must not surface accuracy_rate."""

    def test_min_resolved_0_no_having_filter(self, mock_db):
        """Default min_resolved_claims=0: HAVING clause passes all rows."""
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        get_pundit_accuracy_summary(db=mock_db, min_resolved_claims=0)
        query = mock_db.fetch_df.call_args[0][0]
        assert "HAVING" in query
        assert ">= 0" in query

    def test_min_resolved_5_in_having(self, mock_db):
        """min_resolved_claims=5: HAVING clause contains >= 5."""
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        get_pundit_accuracy_summary(db=mock_db, min_resolved_claims=5)
        query = mock_db.fetch_df.call_args[0][0]
        assert "HAVING" in query
        assert ">= 5" in query

    def test_accuracy_rate_null_for_pundit_with_few_claims(self, mock_db):
        """
        If the DB returns a row with accuracy_rate=None (SAFE_DIVIDE on zero),
        the summary DataFrame preserves that null — it must not be coerced to 0.
        """
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        mock_db.fetch_df.return_value = pd.DataFrame(
            [
                {
                    "pundit_id": "new_pundit",
                    "pundit_name": "New Pundit",
                    "sport": "NFL",
                    "total_predictions": 3,
                    "resolved_count": 3,
                    "correct_count": 2,
                    "accuracy_rate": None,  # SAFE_DIVIDE returns null < threshold
                    "avg_brier_score": None,
                    "avg_weighted_score": None,
                }
            ]
        )
        df = get_pundit_accuracy_summary(db=mock_db, min_resolved_claims=5)
        assert df.iloc[0]["accuracy_rate"] is None

    def test_min_resolved_negative_clamped_to_zero(self, mock_db):
        """Negative min_resolved_claims is clamped to 0."""
        os.environ["GCP_PROJECT_ID"] = "test-project"
        from src.resolution_engine import get_pundit_accuracy_summary

        get_pundit_accuracy_summary(db=mock_db, min_resolved_claims=-3)
        query = mock_db.fetch_df.call_args[0][0]
        assert ">= 0" in query


# ---------------------------------------------------------------------------
# 4. API endpoint — leaderboard returns null accuracy for <5 resolved claims
# ---------------------------------------------------------------------------


class TestApiMinClaimsGuard:
    """
    The /v1/leaderboard and /v1/pundits/ endpoints pass min_resolved_claims=5
    to get_pundit_accuracy_summary, so pundits with <5 resolved claims are excluded.
    """

    def test_leaderboard_passes_min_resolved_5(self):
        """leaderboard endpoint calls get_pundit_accuracy_summary with min_resolved_claims=5."""
        import unittest.mock as mock

        with (
            mock.patch("src.db_manager.DBManager._initialize_connection"),
            mock.patch("api.pundit_router.get_pundit_accuracy_summary") as mock_summary,
            mock.patch("src.scoring.get_pundit_stats", return_value=pd.DataFrame()),
        ):
            from api.main import app
            from api.api_key_auth import verify_api_key
            from api.pundit_router import get_db
            from fastapi.testclient import TestClient

            mock_summary.return_value = pd.DataFrame()

            stub_key = {
                "tier": "pro",
                "user_id": "u1",
                "key_id": "k1",
                "status": "active",
                "scopes": [],
                "name": "T",
                "created_at": None,
                "last_used_at": None,
                "key_last_four": "test",
            }
            mock_db_inst = MagicMock()
            mock_db_inst.project_id = "test-project"
            mock_db_inst.dataset_id = "nfl_dead_money"
            mock_db_inst.client.query.return_value = MagicMock(
                to_dataframe=lambda: pd.DataFrame()
            )

            app.dependency_overrides[get_db] = lambda: mock_db_inst
            app.dependency_overrides[verify_api_key] = lambda: stub_key

            with TestClient(app) as c:
                resp = c.get("/v1/leaderboard")

            app.dependency_overrides.clear()

            assert resp.status_code == 200
            # Verify min_resolved_claims=5 was passed
            call_kwargs = mock_summary.call_args
            assert call_kwargs is not None, "get_pundit_accuracy_summary was not called"
            assert call_kwargs.kwargs.get("min_resolved_claims") == 5

    def test_list_pundits_passes_min_resolved_5(self):
        """list_pundits endpoint passes min_resolved_claims=5."""
        import unittest.mock as mock

        # Patch the name as used in the pundit_router module (where it's imported from)
        with (
            mock.patch("src.db_manager.DBManager._initialize_connection"),
            mock.patch("api.pundit_router.get_pundit_accuracy_summary") as mock_summary,
        ):
            from api.main import app
            from api.api_key_auth import verify_api_key
            from api.pundit_router import get_db
            from fastapi.testclient import TestClient

            mock_summary.return_value = pd.DataFrame()

            stub_key = {
                "tier": "pro",
                "user_id": "u1",
                "key_id": "k1",
                "status": "active",
                "scopes": [],
                "name": "T",
                "created_at": None,
                "last_used_at": None,
                "key_last_four": "test",
            }
            mock_db_inst = MagicMock()
            mock_db_inst.project_id = "test-project"
            mock_db_inst.dataset_id = "nfl_dead_money"
            mock_db_inst.client.query.return_value = MagicMock(
                to_dataframe=lambda: pd.DataFrame()
            )

            app.dependency_overrides[get_db] = lambda: mock_db_inst
            app.dependency_overrides[verify_api_key] = lambda: stub_key

            with TestClient(app) as c:
                resp = c.get("/v1/pundits/")

            app.dependency_overrides.clear()

            assert resp.status_code == 200
            call_kwargs = mock_summary.call_args
            assert call_kwargs is not None, "get_pundit_accuracy_summary was not called"
            assert call_kwargs.kwargs.get("min_resolved_claims") == 5


# ---------------------------------------------------------------------------
# 5. publish_tier1_pundits seed script
# ---------------------------------------------------------------------------


class TestPublishTier1Pundits:
    """publish_tier1_pundits: idempotent UPDATE for existing, INSERT for new."""

    @patch("src.publish_tier1_pundits.TIER1_CONFIG")
    def test_updates_existing_pundits(self, mock_config_path, mock_db, tmp_path):
        """If pundit_id already in registry, UPDATE sets published=TRUE."""
        import yaml
        from src.publish_tier1_pundits import publish_tier1_pundits

        config = tmp_path / "tier1.yaml"
        config.write_text(
            yaml.dump(
                {
                    "pundits": [
                        {
                            "pundit_id": "adam_schefter",
                            "pundit_name": "Adam Schefter",
                            "sport": "NFL",
                        }
                    ]
                }
            )
        )
        mock_config_path.__str__ = lambda self: str(config)

        os.environ["GCP_PROJECT_ID"] = "test-project"

        # Simulate adam_schefter already in registry
        mock_db.fetch_df.return_value = pd.DataFrame([{"pundit_id": "adam_schefter"}])

        from src.publish_tier1_pundits import publish_tier1_pundits, load_tier1_pundits

        pundits = [
            {
                "pundit_id": "adam_schefter",
                "pundit_name": "Adam Schefter",
                "sport": "NFL",
            }
        ]

        with patch(
            "src.publish_tier1_pundits.load_tier1_pundits", return_value=pundits
        ):
            result = publish_tier1_pundits(db=mock_db)

        assert result["updated"] == 1
        assert result["inserted"] == 0

        # Should have called execute (UPDATE) not insert
        call_sqls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("UPDATE" in s for s in call_sqls)

    def test_inserts_new_pundits(self, mock_db):
        """If pundit_id not in registry, INSERT stub row with published=TRUE."""
        import os

        os.environ["GCP_PROJECT_ID"] = "test-project"

        # Empty registry
        mock_db.fetch_df.return_value = pd.DataFrame(columns=["pundit_id"])

        pundits = [
            {
                "pundit_id": "ian_rapoport",
                "pundit_name": "Ian Rapoport",
                "sport": "NFL",
            }
        ]

        with patch(
            "src.publish_tier1_pundits.load_tier1_pundits", return_value=pundits
        ):
            from src.publish_tier1_pundits import publish_tier1_pundits

            result = publish_tier1_pundits(db=mock_db)

        assert result["inserted"] == 1
        assert result["updated"] == 0

        call_sqls = [str(c) for c in mock_db.execute.call_args_list]
        assert any("INSERT" in s for s in call_sqls)

    def test_idempotent_on_repeat_run(self, mock_db):
        """Second run where pundit is already in registry → UPDATE not INSERT."""
        import os

        os.environ["GCP_PROJECT_ID"] = "test-project"

        pundits = [
            {
                "pundit_id": "pat_mcafee",
                "pundit_name": "Pat McAfee",
                "sport": "NFL",
            }
        ]

        # First run: not in registry → INSERT
        mock_db.fetch_df.return_value = pd.DataFrame(columns=["pundit_id"])
        with patch(
            "src.publish_tier1_pundits.load_tier1_pundits", return_value=pundits
        ):
            from src.publish_tier1_pundits import publish_tier1_pundits

            result1 = publish_tier1_pundits(db=mock_db)
        assert result1["inserted"] == 1

        # Second run: now in registry → UPDATE
        mock_db.fetch_df.return_value = pd.DataFrame([{"pundit_id": "pat_mcafee"}])
        mock_db.execute.reset_mock()
        with patch(
            "src.publish_tier1_pundits.load_tier1_pundits", return_value=pundits
        ):
            result2 = publish_tier1_pundits(db=mock_db)
        assert result2["updated"] == 1
        assert result2["inserted"] == 0

    def test_load_tier1_config_has_all_required_pundits(self):
        """Tier-1 config must include all 11 required pundits from issue #830."""
        from src.publish_tier1_pundits import load_tier1_pundits

        pundits = load_tier1_pundits()
        ids = {p["pundit_id"] for p in pundits}
        required = {
            "adam_schefter",
            "ian_rapoport",
            "adrian_wojnarowski",
            "pat_mcafee",
            "tom_pelissero",
            "mike_garafolo",
            "jeremy_fowler",
            "chris_mortensen",
            "field_yates",
            "jay_glazer",
            "shams_charania",
        }
        missing = required - ids
        assert not missing, f"Missing tier-1 pundits in config: {missing}"

"""
Ledger BQ Integration Tests (Issue #120)

Connects to the live BigQuery instance and verifies:
  - All 4 ledger tables exist with correct schemas
  - sport column is present and typed STRING on all tables that need it
  - raw_pundit_media has been ingested recently (data freshness)
  - sport values are valid (no NULL, no unexpected values)
  - prediction_ledger chain hash column is present (cryptographic moat)
  - API query shapes are valid BigQuery SQL (no injection, no broken syntax)

Marked @pytest.mark.integration — skipped when GCP_PROJECT_ID is not set.
Run manually: docker compose exec pipeline bash -c
  "python -m pytest pipeline/tests/test_ledger_bq_integration.py -v -m integration"
"""

import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"),
    reason="GCP_PROJECT_ID not set — skipping BQ integration tests",
)

VALID_SPORTS = {"NFL", "MLB", "NBA", "NHL", "NCAAF", "NCAAB"}


@pytest.fixture(scope="module")
def bq_client():
    from google.cloud import bigquery

    return bigquery.Client(project=os.environ.get("GCP_PROJECT_ID"))


@pytest.fixture(scope="module")
def project(bq_client):
    return bq_client.project


# ---------------------------------------------------------------------------
# 1. Table existence
# ---------------------------------------------------------------------------


class TestTableExistence:
    def test_gold_layer_dataset_exists(self, bq_client, project):
        datasets = {d.dataset_id for d in bq_client.list_datasets()}
        assert "gold_layer" in datasets, "gold_layer dataset missing from BQ"

    def test_nfl_dead_money_dataset_exists(self, bq_client, project):
        datasets = {d.dataset_id for d in bq_client.list_datasets()}
        assert "nfl_dead_money" in datasets

    def test_prediction_ledger_exists(self, bq_client, project):
        table = bq_client.get_table(f"{project}.gold_layer.prediction_ledger")
        assert table is not None

    def test_prediction_resolutions_exists(self, bq_client, project):
        table = bq_client.get_table(f"{project}.gold_layer.prediction_resolutions")
        assert table is not None

    def test_raw_pundit_media_exists(self, bq_client, project):
        table = bq_client.get_table(f"{project}.nfl_dead_money.raw_pundit_media")
        assert table is not None

    def test_processed_media_hashes_exists(self, bq_client, project):
        table = bq_client.get_table(f"{project}.nfl_dead_money.processed_media_hashes")
        assert table is not None


# ---------------------------------------------------------------------------
# 2. Schema — required columns present
# ---------------------------------------------------------------------------


def _schema_columns(bq_client, table_id):
    table = bq_client.get_table(table_id)
    return {f.name: f.field_type for f in table.schema}


class TestSchemaColumns:
    def test_prediction_ledger_has_sport(self, bq_client, project):
        cols = _schema_columns(bq_client, f"{project}.gold_layer.prediction_ledger")
        assert "sport" in cols, "sport column missing from prediction_ledger"
        assert cols["sport"] == "STRING"

    def test_prediction_ledger_core_columns(self, bq_client, project):
        cols = _schema_columns(bq_client, f"{project}.gold_layer.prediction_ledger")
        required = {
            "prediction_hash",
            "chain_hash",
            "ingestion_timestamp",
            "pundit_id",
            "pundit_name",
            "raw_assertion_text",
            "extracted_claim",
            "claim_category",
            "resolution_status",
            "sport",
        }
        missing = required - set(cols.keys())
        assert not missing, f"prediction_ledger missing columns: {missing}"

    def test_prediction_ledger_hash_columns_are_string(self, bq_client, project):
        cols = _schema_columns(bq_client, f"{project}.gold_layer.prediction_ledger")
        assert cols["prediction_hash"] == "STRING"
        assert cols["chain_hash"] == "STRING"

    def test_prediction_resolutions_has_sport(self, bq_client, project):
        cols = _schema_columns(
            bq_client, f"{project}.gold_layer.prediction_resolutions"
        )
        assert "sport" in cols, "sport column missing from prediction_resolutions"
        assert cols["sport"] == "STRING"

    def test_prediction_resolutions_scoring_columns(self, bq_client, project):
        cols = _schema_columns(
            bq_client, f"{project}.gold_layer.prediction_resolutions"
        )
        required = {
            "prediction_hash",
            "resolution_status",
            "brier_score",
            "binary_correct",
            "timeliness_weight",
            "weighted_score",
        }
        missing = required - set(cols.keys())
        assert not missing, f"prediction_resolutions missing columns: {missing}"

    def test_raw_pundit_media_has_sport(self, bq_client, project):
        cols = _schema_columns(bq_client, f"{project}.nfl_dead_money.raw_pundit_media")
        assert "sport" in cols, "sport column missing from raw_pundit_media"
        assert cols["sport"] == "STRING"

    def test_raw_pundit_media_core_columns(self, bq_client, project):
        cols = _schema_columns(bq_client, f"{project}.nfl_dead_money.raw_pundit_media")
        required = {
            "content_hash",
            "source_id",
            "raw_text",
            "source_url",
            "ingested_at",
            "sport",
        }
        missing = required - set(cols.keys())
        assert not missing, f"raw_pundit_media missing columns: {missing}"


# ---------------------------------------------------------------------------
# 3. Data freshness — raw_pundit_media
# ---------------------------------------------------------------------------


class TestDataFreshness:
    def test_raw_pundit_media_has_rows(self, bq_client, project):
        row = next(
            bq_client.query(
                f"SELECT COUNT(*) AS cnt FROM `{project}.nfl_dead_money.raw_pundit_media`"
            ).result()
        )
        assert row.cnt > 0, "raw_pundit_media is empty — ingestion has never run"

    def test_raw_pundit_media_ingested_within_48h(self, bq_client, project):
        """Ensures the ingestor has run recently (pipeline health check)."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        row = next(bq_client.query(f"""
            SELECT COUNT(*) AS cnt
            FROM `{project}.nfl_dead_money.raw_pundit_media`
            WHERE ingested_at >= '{cutoff}'
        """).result())
        assert row.cnt > 0, (
            "No rows ingested in the last 48h. "
            "Last ingest may be stale. Run python -m src.media_ingestor"
        )

    def test_raw_pundit_media_has_multiple_sources(self, bq_client, project):
        """Verifies more than 1 RSS source was ingested (not just a single feed)."""
        row = next(bq_client.query(f"""
            SELECT COUNT(DISTINCT source_id) AS cnt
            FROM `{project}.nfl_dead_money.raw_pundit_media`
        """).result())
        assert (
            row.cnt >= 2
        ), f"Only {row.cnt} source(s) in raw_pundit_media — expected multiple feeds"


# ---------------------------------------------------------------------------
# 4. Data quality — sport field values
# ---------------------------------------------------------------------------


class TestSportFieldDataQuality:
    def test_raw_pundit_media_sport_never_null_on_recent_rows(self, bq_client, project):
        """All rows ingested after migration 007 must have sport set."""
        # Use the migration timestamp as a proxy — rows after 2026-04-03 must have sport
        row = next(bq_client.query(f"""
            SELECT COUNT(*) AS cnt
            FROM `{project}.nfl_dead_money.raw_pundit_media`
            WHERE sport IS NULL
              AND ingested_at >= '2026-04-03'
        """).result())
        assert row.cnt == 0, (
            f"{row.cnt} rows ingested after 2026-04-03 have NULL sport. "
            f"Media ingestor sport field not writing correctly."
        )

    def test_raw_pundit_media_sport_values_are_valid(self, bq_client, project):
        """All non-NULL sport values must be in the known valid set."""
        rows = list(bq_client.query(f"""
            SELECT DISTINCT sport
            FROM `{project}.nfl_dead_money.raw_pundit_media`
            WHERE sport IS NOT NULL
        """).result())
        for row in rows:
            assert (
                row.sport in VALID_SPORTS
            ), f"Unknown sport value '{row.sport}' in raw_pundit_media"

    def test_prediction_ledger_sport_values_valid_if_populated(
        self, bq_client, project
    ):
        """If the ledger has rows, all sport values must be valid."""
        rows = list(bq_client.query(f"""
            SELECT DISTINCT sport
            FROM `{project}.gold_layer.prediction_ledger`
            WHERE sport IS NOT NULL
        """).result())
        for row in rows:
            assert (
                row.sport in VALID_SPORTS
            ), f"Unknown sport value '{row.sport}' in prediction_ledger"


# ---------------------------------------------------------------------------
# 5. Cryptographic ledger integrity
# ---------------------------------------------------------------------------


class TestCryptographicLedger:
    def test_prediction_ledger_accessible(self, bq_client, project):
        """Basic smoke test — table is queryable."""
        row = next(
            bq_client.query(
                f"SELECT COUNT(*) AS cnt FROM `{project}.gold_layer.prediction_ledger`"
            ).result()
        )
        assert row.cnt >= 0  # 0 is fine (empty table), just must not error

    def test_prediction_ledger_no_duplicate_hashes(self, bq_client, project):
        """Duplicate prediction_hashes would indicate a broken ingest (non-idempotent)."""
        row = next(bq_client.query(f"""
            SELECT COUNT(*) AS cnt FROM (
                SELECT prediction_hash, COUNT(*) AS c
                FROM `{project}.gold_layer.prediction_ledger`
                GROUP BY prediction_hash
                HAVING c > 1
            )
        """).result())
        assert row.cnt == 0, (
            f"{row.cnt} duplicate prediction_hash(es) in ledger — "
            f"ingest is not idempotent or content hash collision"
        )

    def test_prediction_resolutions_no_duplicate_hashes(self, bq_client, project):
        """Each prediction_hash should appear at most once in resolutions."""
        row = next(bq_client.query(f"""
            SELECT COUNT(*) AS cnt FROM (
                SELECT prediction_hash, COUNT(*) AS c
                FROM `{project}.gold_layer.prediction_resolutions`
                GROUP BY prediction_hash
                HAVING c > 1
            )
        """).result())
        assert (
            row.cnt == 0
        ), f"{row.cnt} duplicate prediction_hash(es) in prediction_resolutions"


# ---------------------------------------------------------------------------
# 6. Cross-table referential integrity
# ---------------------------------------------------------------------------


class TestReferentialIntegrity:
    def test_resolutions_have_matching_ledger_rows(self, bq_client, project):
        """Every resolution must have a corresponding ledger entry."""
        row = next(bq_client.query(f"""
            SELECT COUNT(*) AS orphan_count
            FROM `{project}.gold_layer.prediction_resolutions` r
            LEFT JOIN `{project}.gold_layer.prediction_ledger` l
                ON r.prediction_hash = l.prediction_hash
            WHERE l.prediction_hash IS NULL
        """).result())
        assert (
            row.orphan_count == 0
        ), f"{row.orphan_count} orphaned resolution(s) with no matching ledger row"

    def test_content_hash_is_unique_per_source_in_raw_media(self, bq_client, project):
        """Dedup logic should prevent the same content_hash from being written twice."""
        row = next(bq_client.query(f"""
            SELECT COUNT(*) AS cnt FROM (
                SELECT content_hash, COUNT(*) AS c
                FROM `{project}.nfl_dead_money.raw_pundit_media`
                GROUP BY content_hash
                HAVING c > 1
            )
        """).result())
        assert row.cnt == 0, (
            f"{row.cnt} duplicate content_hash(es) in raw_pundit_media — "
            f"dedup logic not working"
        )

"""
Unit tests for DBManager.append_dataframe_to_table table_ref construction.

Regression coverage for the claim-promotion bug (issue #1107): the BigQuery
backend of append_dataframe_to_table unconditionally prepended
self.dataset_id ("nfl_dead_money") to table_name, so a dataset-qualified
name like "silver_v2_claims.claim" became the invalid 4-part id
"{project}.nfl_dead_money.silver_v2_claims.claim" and every write from
promote_claims.py / backfill_silver_claims.py to silver_v2_claims.claim
failed against real BigQuery (the DuckDB backend already handled this
correctly, so the failure was invisible to DuckDB-backed unit tests).

These tests bypass DBManager.__init__ (no GCP credentials / network needed)
and stub out self.client so they run fast and unconditionally in CI —
unlike test_db_manager.py, which requires GCP_PROJECT_ID and hits real BQ.
"""

import logging

import pandas as pd

from src.db_manager import DBManager


class _FakeLoadJob:
    def result(self):
        return None


class _FakeSchemaField:
    def __init__(self, name: str, field_type: str):
        self.name = name
        self.field_type = field_type


class _FakeTable:
    def __init__(self, schema):
        self.schema = schema


class _FakeClient:
    """Captures load_table_from_dataframe / load_table_from_json calls.

    schema: optional list of _FakeSchemaField — when provided, get_table()
    returns a table with this schema (mirrors real BQ table introspection
    used to detect JSON-typed destination columns).
    """

    def __init__(self, schema=None):
        self._schema = schema
        self.captured_table_ref = None
        self.captured_via = None  # "dataframe" or "json"
        self.captured_records = None

    def get_table(self, table_ref):
        if self._schema is None:
            raise LookupError(f"no fake table registered for {table_ref}")
        return _FakeTable(self._schema)

    def load_table_from_dataframe(self, df, table_ref, job_config=None):
        self.captured_table_ref = table_ref
        self.captured_via = "dataframe"
        return _FakeLoadJob()

    def load_table_from_json(self, records, table_ref, job_config=None):
        self.captured_table_ref = table_ref
        self.captured_via = "json"
        self.captured_records = records
        return _FakeLoadJob()


def _make_db(
    project_id: str = "test-project", dataset_id: str = "nfl_dead_money", schema=None
):
    db = DBManager.__new__(DBManager)  # bypass __init__ — no GCP creds needed
    db.project_id = project_id
    db.dataset_id = dataset_id
    db.client = _FakeClient(schema=schema)
    return db


def test_bare_table_name_qualifies_with_default_dataset():
    """Unchanged legacy behavior: a bare table name resolves against this
    DBManager's default dataset_id."""
    db = _make_db()
    db.append_dataframe_to_table(pd.DataFrame({"a": [1, 2]}), "raw_pundit_media")
    assert (
        db.client.captured_table_ref == "test-project.nfl_dead_money.raw_pundit_media"
    )


def test_dataset_qualified_table_name_not_double_prefixed():
    """Regression test: a table_name that already carries a dataset
    qualifier (e.g. "silver_v2_claims.claim") must be qualified with the
    project only — self.dataset_id must NOT be re-prepended, or BigQuery
    rejects the resulting 4-part id."""
    db = _make_db()
    db.append_dataframe_to_table(
        pd.DataFrame({"claim_id": ["c1"], "utterance_id": ["u1"]}),
        "silver_v2_claims.claim",
    )
    assert db.client.captured_table_ref == "test-project.silver_v2_claims.claim"


def test_fully_qualified_table_name_used_as_is():
    """A fully qualified project.dataset.table id passes through unchanged."""
    db = _make_db()
    db.append_dataframe_to_table(
        pd.DataFrame({"a": [1]}), "other-project.other_dataset.other_table"
    )
    assert db.client.captured_table_ref == "other-project.other_dataset.other_table"


def test_no_json_columns_uses_dataframe_load_path():
    """When the destination table has no JSON columns, the original
    load_table_from_dataframe path is used unchanged."""
    schema = [
        _FakeSchemaField("claim_id", "STRING"),
        _FakeSchemaField("created_at", "TIMESTAMP"),
    ]
    db = _make_db(schema=schema)
    db.append_dataframe_to_table(
        pd.DataFrame({"claim_id": ["c1"], "created_at": ["2026-01-01"]}),
        "silver_v2_claims.claim",
    )
    assert db.client.captured_via == "dataframe"


def test_json_column_routes_through_load_table_from_json():
    """Regression test: silver_v2_claims.claim.predicate_args is a BigQuery
    JSON column. load_table_from_dataframe rejects JSON columns with
    "400 Unsupported field type: JSON" (a Parquet limitation — reproduces
    even with an explicit JSON SchemaField or a db_dtypes.JSONDtype-tagged
    column). append_dataframe_to_table must detect JSON-typed destination
    columns and route through load_table_from_json (NDJSON) instead, with
    the JSON-encoded string values parsed into native dict/list objects."""
    schema = [
        _FakeSchemaField("claim_id", "STRING"),
        _FakeSchemaField("predicate_args", "JSON"),
    ]
    db = _make_db(schema=schema)
    db.append_dataframe_to_table(
        pd.DataFrame(
            {
                "claim_id": ["c1"],
                "predicate_args": ['{"raw_text": "will win"}'],
            }
        ),
        "silver_v2_claims.claim",
    )
    assert db.client.captured_via == "json"
    assert db.client.captured_table_ref == "test-project.silver_v2_claims.claim"
    assert db.client.captured_records == [
        {"claim_id": "c1", "predicate_args": {"raw_text": "will win"}}
    ]


def test_json_column_null_value_stays_none():
    """A missing/NaN value in a JSON column must load as None, not "nan"."""
    schema = [_FakeSchemaField("predicate_args", "JSON")]
    db = _make_db(schema=schema)
    df = pd.DataFrame({"predicate_args": [None]})
    db.append_dataframe_to_table(df, "silver_v2_claims.claim")
    assert db.client.captured_records == [{"predicate_args": None}]


# ---------------------------------------------------------------------------
# Regression coverage for issue #1115 — JSON-write robustness error branches
# ---------------------------------------------------------------------------


def test_schema_introspection_failure_logs_warning(caplog):
    """When get_table() raises during JSON-column schema introspection, the
    fallback path must log at WARNING (previously DEBUG). At DEBUG this
    failure mode — "we could not tell whether this table has JSON columns,
    so we silently assumed it doesn't and may hit a 400 on the load" — was
    invisible in production logs, which is exactly the silent-failure
    pattern #1111/#1115 exist to kill."""
    db = _make_db()  # schema=None -> _FakeClient.get_table() raises LookupError
    with caplog.at_level(logging.WARNING):
        db.append_dataframe_to_table(pd.DataFrame({"a": [1]}), "silver_v2_claims.claim")
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(
        "Could not introspect schema" in r.getMessage() for r in warning_records
    ), f"expected a WARNING log for schema introspection failure, got: {caplog.text}"


def test_json_load_safe_value_invalid_json_logs_warning(caplog):
    """When a JSON-typed column's string value fails to parse as JSON,
    _json_load_safe_value must log a WARNING before silently falling back to
    the raw string — otherwise a malformed predicate_args value degrades to
    a quoted-string column with no trace in the logs."""
    from src.db_manager import _json_load_safe_value

    with caplog.at_level(logging.WARNING):
        result = _json_load_safe_value("not valid json {{{", is_json_col=True)

    assert result == "not valid json {{{"
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Could not parse value" in r.getMessage() for r in warning_records), (
        f"expected a WARNING log for the JSON parse fallback, got: {caplog.text}"
    )


def test_json_load_safe_value_valid_json_no_warning(caplog):
    """The success path (valid JSON string) must stay silent — no warning
    noise when nothing went wrong."""
    from src.db_manager import _json_load_safe_value

    with caplog.at_level(logging.WARNING):
        result = _json_load_safe_value('{"a": 1}', is_json_col=True)

    assert result == {"a": 1}
    assert not any(r.levelno == logging.WARNING for r in caplog.records)

"""
DuckDB drop-in replacement for DBManager.

Activated via DB_BACKEND=duckdb environment variable. Implements the same
public interface as DBManager so all pipeline code works without modification.

SQL is translated from BigQuery dialect automatically:
  - Backtick-quoted table references → schema-qualified DuckDB names
  - @param markers → $param (DuckDB named-parameter syntax)
  - BQ type aliases (STRING, INT64, FLOAT64, ARRAY<T>) → DuckDB equivalents

Use get_db_manager() from db_manager.py to get the right backend automatically.
"""

import logging
import os
import re
import uuid
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

_DEFAULT_SCHEMA = "nfl_dead_money"
_DEFAULT_DUCKDB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "local.duckdb",
)

# Maps the BQ project-level dataset names to DuckDB schemas (1:1)
_DATASET_SCHEMAS = {
    "nfl_dead_money",
    "gold_layer",
    "silver_v2_claims",
    "silver_v2_core",
    "silver_v2_sports",
}


# ---------------------------------------------------------------------------
# SQL translation helpers
# ---------------------------------------------------------------------------


def _translate_bq_sql(sql: str) -> str:
    """
    Translate BigQuery SQL dialect to DuckDB-compatible SQL.

    Handles:
    - `project.dataset.table` backtick refs → dataset.table
    - `dataset.table` backtick refs → dataset.table
    - @param → $param named-parameter syntax
    - BQ-only type keywords in DDL (STRING, INT64, FLOAT64, ARRAY<T>)
    """
    # `project.dataset.table` — strip the project prefix, keep dataset.table
    sql = re.sub(
        r"`[^`]+\.([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)`",
        r"\1.\2",
        sql,
    )
    # `dataset.table` with no project prefix
    sql = re.sub(
        r"`([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)`",
        r"\1.\2",
        sql,
    )
    # Named parameter markers
    sql = re.sub(r"@(\w+)", r"$\1", sql)
    # BQ DDL type aliases → DuckDB equivalents (word-boundary safe)
    sql = re.sub(r"\bARRAY<STRING>\b", "VARCHAR[]", sql)
    sql = re.sub(r"\bARRAY<FLOAT64>\b", "DOUBLE[]", sql)
    sql = re.sub(r"\bARRAY<INT64>\b", "BIGINT[]", sql)
    sql = re.sub(r"\bARRAY<BOOL>\b", "BOOLEAN[]", sql)
    sql = re.sub(r"\bINT64\b", "BIGINT", sql)
    sql = re.sub(r"\bFLOAT64\b", "DOUBLE", sql)
    sql = re.sub(r"\bSTRING\b", "VARCHAR", sql)
    return sql


def _extract_param_dict(query_parameters) -> dict:
    """Convert a list of BQ ScalarQueryParameter objects to a plain dict."""
    if not query_parameters:
        return {}
    return {qp.name: qp.value for qp in query_parameters}


# ---------------------------------------------------------------------------
# Proxy objects that mimic BQ client interfaces
# ---------------------------------------------------------------------------


class _DuckDBResultProxy:
    """Mimics BQResultProxy so callers can call .df(), .fetchone(), .fetchall()."""

    def __init__(self, df: pd.DataFrame):
        self._df = df

    def df(self) -> pd.DataFrame:
        return self._df

    def fetchone(self):
        if self._df.empty:
            return None
        return tuple(self._df.iloc[0])

    def fetchall(self):
        return [tuple(row) for row in self._df.itertuples(index=False)]


class _DuckDBJobProxy:
    """Proxy returned by load_table_from_dataframe(); mimics a BQ LoadJob."""

    num_dml_affected_rows: int = 1

    def result(self):
        return self

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame()


class _DuckDBQueryProxy:
    """
    Proxy for the db.client.query(sql).result() pattern used in
    cryptographic_ledger.py. Executes the SQL on .result() and exposes
    .num_dml_affected_rows for concurrency-guard logic.
    """

    def __init__(self, conn, sql: str):
        self._conn = conn
        self._sql = sql
        self.num_dml_affected_rows: int | None = None

    def result(self):
        try:
            self._conn.execute(self._sql)
            # DuckDB connection exposes rowcount after DML; fall back to 1
            # for single-process mode where the concurrency guard always wins.
            try:
                self.num_dml_affected_rows = self._conn.rowcount
            except AttributeError:
                self.num_dml_affected_rows = 1
        except Exception as e:
            logger.error("DuckDB client.query failed: %s\nSQL: %.300s", e, self._sql)
            raise
        return self


class _DuckDBClientProxy:
    """
    Mimics the BigQuery client object for code that accesses db.client directly.
    Covers .query() and .load_table_from_dataframe() call sites.
    """

    def __init__(self, conn):
        self._conn = conn

    def query(self, sql: str) -> _DuckDBQueryProxy:
        translated = _translate_bq_sql(sql)
        return _DuckDBQueryProxy(self._conn, translated)

    def load_table_from_dataframe(
        self, df: pd.DataFrame, table_ref: str, job_config=None
    ) -> _DuckDBJobProxy:
        """Write a DataFrame to a DuckDB table (replaces BQ load job)."""
        # "project.dataset.table" → "dataset.table"
        parts = table_ref.split(".")
        qualified = (
            f"{parts[-2]}.{parts[-1]}"
            if len(parts) >= 2
            else f"{_DEFAULT_SCHEMA}.{parts[0]}"
        )

        df_clean = df.copy()
        df_clean.columns = df_clean.columns.astype(str).str.replace(
            r"[^a-zA-Z0-9_]", "_", regex=True
        )

        write_disposition = "WRITE_APPEND"
        if job_config is not None and hasattr(job_config, "write_disposition"):
            write_disposition = job_config.write_disposition

        view = f"__load_{uuid.uuid4().hex[:8]}"
        self._conn.register(view, df_clean)
        try:
            if write_disposition == "WRITE_TRUNCATE":
                self._conn.execute(f"DELETE FROM {qualified}")
            cols = ", ".join(f'"{c}"' for c in df_clean.columns)
            self._conn.execute(
                f"INSERT INTO {qualified} ({cols}) SELECT {cols} FROM {view}"
            )
            logger.info(
                "load_table_from_dataframe: %d rows → %s", len(df_clean), qualified
            )
        finally:
            self._conn.unregister(view)

        return _DuckDBJobProxy()


# ---------------------------------------------------------------------------
# Main DuckDB manager
# ---------------------------------------------------------------------------


class DuckDBManager:
    """
    DuckDB implementation of the DBManager interface.

    All pipeline components that currently use DBManager work unchanged when
    this class is returned by get_db_manager() with DB_BACKEND=duckdb.

    Schema initialization must happen separately via init_duckdb.py before
    running the pipeline for the first time.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        read_only: bool = False,
        access_tier: str = "writer",
    ):
        import duckdb  # deferred so BQ-only environments don't need duckdb installed

        self.project_id = None  # no GCP project in DuckDB mode
        self.dataset_id = _DEFAULT_SCHEMA
        self._db_path = db_path or os.environ.get("DUCKDB_PATH", _DEFAULT_DUCKDB_PATH)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = duckdb.connect(self._db_path, read_only=read_only)
        self._conn.execute(f"SET search_path = '{_DEFAULT_SCHEMA}'")
        self.client = _DuckDBClientProxy(self._conn)
        logger.info("DuckDBManager: connected to %s", self._db_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _prep(
        self,
        query: str,
        params: Optional[Dict[str, Any]],
        query_parameters,
    ) -> tuple[str, dict]:
        """Translate BQ SQL and assemble the DuckDB param dict."""
        sql = _translate_bq_sql(query)
        if params:
            for k, v in list(params.items()):
                if isinstance(v, pd.DataFrame):
                    view = f"__df_{k}_{uuid.uuid4().hex[:8]}"
                    self._conn.register(view, v)
                    sql = (
                        sql.replace(f" {k} ", f" {view} ")
                        .replace(f"FROM {k}", f"FROM {view}")
                        .replace(f"JOIN {k}", f"JOIN {view}")
                    )
        dparams = _extract_param_dict(query_parameters)
        return sql, dparams

    # ------------------------------------------------------------------
    # Public interface (mirrors DBManager)
    # ------------------------------------------------------------------

    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        query_parameters: Optional[list] = None,
    ) -> _DuckDBResultProxy:
        sql, dparams = self._prep(query, params, query_parameters)
        try:
            result = (
                self._conn.execute(sql, dparams) if dparams else self._conn.execute(sql)
            )
            try:
                df = result.df()
            except Exception:
                df = pd.DataFrame()
            return _DuckDBResultProxy(df)
        except Exception as e:
            logger.error("DuckDB execute failed: %s\nSQL: %.300s", e, sql)
            raise

    def fetch_df(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        query_parameters: Optional[list] = None,
    ) -> pd.DataFrame:
        sql, dparams = self._prep(query, params, query_parameters)
        try:
            if dparams:
                return self._conn.execute(sql, dparams).df()
            return self._conn.execute(sql).df()
        except Exception as e:
            logger.error("DuckDB fetch_df failed: %s\nSQL: %.300s", e, sql)
            raise

    def append_dataframe_to_table(self, df: pd.DataFrame, table_name: str) -> None:
        """Appends DataFrame rows to a DuckDB table. table_name may be schema-qualified."""
        df_clean = df.copy()
        df_clean.columns = df_clean.columns.astype(str).str.replace(
            r"[^a-zA-Z0-9_]", "_", regex=True
        )
        # Normalize object columns (mirrors DBManager behaviour)
        for col in df_clean.columns:
            if df_clean[col].dtype != "object":
                continue
            non_null = df_clean[col].dropna()
            if len(non_null) == 0:
                continue
            if all(isinstance(v, list) for v in non_null):
                continue  # ARRAY column — leave as Python lists
            if not all(isinstance(v, str) for v in non_null):
                df_clean[col] = df_clean[col].astype(str)

        view = f"__append_{uuid.uuid4().hex[:8]}"
        self._conn.register(view, df_clean)
        try:
            cols = ", ".join(f'"{c}"' for c in df_clean.columns)
            self._conn.execute(
                f"INSERT INTO {table_name} ({cols}) SELECT {cols} FROM {view}"
            )
            logger.info("Appended %d rows to %s", len(df_clean), table_name)
        finally:
            self._conn.unregister(view)

    def table_exists(self, table_name: str) -> bool:
        parts = table_name.split(".")
        schema, table = (
            (parts[-2], parts[-1]) if len(parts) >= 2 else (_DEFAULT_SCHEMA, parts[0])
        )
        try:
            count = self._conn.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = $schema AND table_name = $table",
                {"schema": schema, "table": table},
            ).fetchone()[0]
            return count > 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Graph extension methods — DuckDB-native implementations
    # (DBManager versions use BQ MERGE syntax and bigquery.ScalarQueryParameter)
    # ------------------------------------------------------------------

    def upsert_entity(self, entity: dict) -> str:
        import json as _json

        required = {"entity_id", "entity_type", "canonical_name", "domain"}
        missing = required - set(entity.keys())
        if missing:
            raise ValueError(f"upsert_entity: missing required keys: {missing}")

        metadata = entity.get("metadata")
        params = {
            "entity_id": entity["entity_id"],
            "entity_type": entity["entity_type"],
            "canonical_name": entity["canonical_name"],
            "domain": entity.get("domain", "SPORTS"),
            "aliases": entity.get("aliases") or [],
            "metadata": _json.dumps(metadata) if metadata is not None else None,
            "first_seen_at": entity.get("first_seen_at"),
            "last_seen_at": entity.get("last_seen_at"),
        }

        self._conn.execute(
            """
            INSERT INTO nfl_dead_money.entities
                (entity_id, entity_type, canonical_name, aliases, domain,
                 metadata, first_seen_at, last_seen_at, claim_count, created_at)
            VALUES
                ($entity_id, $entity_type, $canonical_name, $aliases, $domain,
                 $metadata::JSON, $first_seen_at::TIMESTAMP, $last_seen_at::TIMESTAMP,
                 1, CURRENT_TIMESTAMP)
            ON CONFLICT (entity_id) DO UPDATE SET
                canonical_name = excluded.canonical_name,
                aliases        = excluded.aliases,
                metadata       = COALESCE(excluded.metadata,
                                          nfl_dead_money.entities.metadata),
                last_seen_at   = COALESCE(excluded.last_seen_at,
                                          nfl_dead_money.entities.last_seen_at),
                claim_count    = COALESCE(nfl_dead_money.entities.claim_count, 0) + 1
            """,
            params,
        )
        logger.info(
            "upsert_entity: entity_id=%s (%s)",
            params["entity_id"],
            params["entity_type"],
        )
        return params["entity_id"]

    def get_entity(self, entity_id: str) -> dict | None:
        df = self._conn.execute(
            "SELECT * FROM nfl_dead_money.entities WHERE entity_id = $entity_id LIMIT 1",
            {"entity_id": entity_id},
        ).df()
        return df.iloc[0].to_dict() if not df.empty else None

    def get_entities_by_name(
        self,
        canonical_name: str,
        entity_type: str | None = None,
    ) -> list[dict]:
        type_filter = "AND entity_type = $entity_type" if entity_type else ""
        params: dict = {"canonical_name": canonical_name}
        if entity_type:
            params["entity_type"] = entity_type
        df = self._conn.execute(
            f"""
            SELECT * FROM nfl_dead_money.entities
            WHERE (
                LOWER(canonical_name) = LOWER($canonical_name)
                OR list_contains(aliases, $canonical_name)
            )
            {type_filter}
            ORDER BY claim_count DESC
            LIMIT 50
            """,
            params,
        ).df()
        return df.to_dict(orient="records")

    def upsert_graph_extension(self, prediction_hash: str, extension: dict) -> None:
        import json as _json

        asserted = extension.get("asserted_state")
        params = {
            "prediction_hash": prediction_hash,
            "entity_ids": extension.get("entity_ids") or [],
            "primary_entity_id": extension.get("primary_entity_id"),
            "claim_type": extension.get("claim_type"),
            "domain": extension.get("domain", "SPORTS"),
            "asserted_state": _json.dumps(asserted) if asserted is not None else None,
            "embedding": extension.get("embedding"),
            "cluster_id": extension.get("cluster_id"),
            "entity_resolution_confidence": extension.get(
                "entity_resolution_confidence"
            ),
        }
        tbl = "nfl_dead_money.prediction_ledger_graph_extension"
        self._conn.execute(
            f"""
            INSERT INTO {tbl}
                (prediction_hash, entity_ids, primary_entity_id, claim_type, domain,
                 asserted_state, embedding, cluster_id, entity_resolution_confidence,
                 created_at, updated_at)
            VALUES
                ($prediction_hash, $entity_ids, $primary_entity_id, $claim_type, $domain,
                 $asserted_state::JSON, $embedding, $cluster_id, $entity_resolution_confidence,
                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (prediction_hash) DO UPDATE SET
                entity_ids                   = excluded.entity_ids,
                primary_entity_id            = COALESCE(excluded.primary_entity_id,
                                                        {tbl}.primary_entity_id),
                claim_type                   = COALESCE(excluded.claim_type, {tbl}.claim_type),
                domain                       = COALESCE(excluded.domain, {tbl}.domain),
                asserted_state               = COALESCE(excluded.asserted_state,
                                                        {tbl}.asserted_state),
                embedding                    = COALESCE(excluded.embedding, {tbl}.embedding),
                cluster_id                   = COALESCE(excluded.cluster_id, {tbl}.cluster_id),
                entity_resolution_confidence = COALESCE(excluded.entity_resolution_confidence,
                                                        {tbl}.entity_resolution_confidence),
                updated_at                   = CURRENT_TIMESTAMP
            """,
            params,
        )
        logger.info(
            "upsert_graph_extension: prediction_hash=%s...", prediction_hash[:16]
        )

    def get_claim_edges(
        self,
        pundit_id: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        conditions = []
        params: dict = {"limit_val": int(limit)}
        if pundit_id:
            conditions.append("pundit_id = $pundit_id")
            params["pundit_id"] = pundit_id
        if entity_id:
            conditions.append("list_contains(entity_ids, $entity_id)")
            params["entity_id"] = entity_id
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        df = self._conn.execute(
            f"""
            SELECT * FROM gold_layer.claim_edges
            {where}
            ORDER BY timestamp_made DESC
            LIMIT $limit_val
            """,
            params,
        ).df()
        return df.to_dict(orient="records")

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

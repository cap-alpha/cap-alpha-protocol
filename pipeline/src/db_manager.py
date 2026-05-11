import json
import logging
import os
import uuid
from typing import Any, Dict, Optional

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

logger = logging.getLogger(__name__)


class BQResultProxy:
    def __init__(self, job):
        self.job = job

    def df(self):
        return self.job.to_dataframe()

    def fetchone(self):
        res = list(self.job.result())
        return tuple(res[0].values()) if res else None

    def fetchall(self):
        res = list(self.job.result())
        return [tuple(r.values()) for r in res]


class DBManager:
    """
    Technology-agnostic database manager implemented for Google BigQuery.
    Handles DataFrames natively by spinning up ephemeral Cloud temp tables.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        read_only: bool = False,
        access_tier: str = "writer",
    ):
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.dataset_id = "nfl_dead_money"  # Hardcoded convention for this pipeline
        self.client = None
        self._temp_tables = []
        self._initialize_connection()

    def _initialize_connection(self):
        """Initializes the BigQuery client."""
        try:
            if not self.project_id:
                raise EnvironmentError(
                    "GCP_PROJECT_ID environment variable is missing."
                )

            credentials_json = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
            if credentials_json:
                credentials_dict = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_dict
                )
                self.client = bigquery.Client(
                    project=self.project_id, credentials=credentials
                )
            else:
                self.client = bigquery.Client(project=self.project_id)

            logger.info(
                f"Connected to BigQuery Project: {self.project_id}, Dataset: {self.dataset_id}"
            )
        except Exception as e:
            logger.error(f"Failed to connect to BigQuery: {e}")
            raise

    def _handle_dataframe_params(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> tuple[str, Optional[Dict[str, Any]]]:
        """
        Intercepts pandas DataFrames in params {"df": df}, uploads them to temp BQ tables,
        and rewrites 'FROM df' natively to 'FROM my_project.dataset.tmp_UUID'.
        """
        if not params or not isinstance(params, dict):
            return query, params

        bind_params = {}
        for k, v in params.items():
            if isinstance(v, pd.DataFrame):
                # We spin up a temp BigQuery table
                temp_name = f"tmp_{k}_{uuid.uuid4().hex[:8]}"
                table_ref = f"{self.project_id}.{self.dataset_id}.{temp_name}"

                logger.info(
                    f"DBManager Proxy: Uploading DataFrame '{k}' to BigQuery Ephemeral Temp Table: {table_ref}"
                )

                # Sanitize column names for BigQuery compatibility
                df = v.copy()
                df.columns = df.columns.astype(str).str.replace(
                    r"[^a-zA-Z0-9_]", "_", regex=True
                )
                # Cast objects to string to prevent Parquet schema mismatch crashes
                for col in df.columns:
                    if df[col].dtype == "object":
                        df[col] = df[col].astype(str)

                job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                job = self.client.load_table_from_dataframe(
                    df, table_ref, job_config=job_config
                )
                job.result()  # wait for load to complete

                # Track for later cleanup
                self._temp_tables.append(table_ref)

                # Rewrite query (simple find and replace for table name identifier)
                # Replaces standalone occurrences of the parameter name with the temp table reference
                query = (
                    query.replace(f" {k} ", f" `{table_ref}` ")
                    .replace(f"FROM {k}", f"FROM `{table_ref}`")
                    .replace(f"JOIN {k}", f"JOIN `{table_ref}`")
                    .replace(f"INTO {k} ", f"INTO `{table_ref}` ")
                )
            else:
                bind_params[k] = v

        return query, (bind_params if bind_params else None)

    def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        query_parameters: Optional[list] = None,
    ):
        """Executes a SQL query on BigQuery.

        Args:
            query: SQL query string. Use @param_name placeholders for safe parameterization.
            params: Dict of DataFrames (uploaded as temp tables).
            query_parameters: List of bigquery.ScalarQueryParameter / ArrayQueryParameter
                              for safe @param substitution. Use this for any external or
                              data-derived values to prevent SQL injection.
        """
        try:
            processed_query, bind_params = self._handle_dataframe_params(query, params)

            dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
            job_config = bigquery.QueryJobConfig(default_dataset=dataset_ref)
            if query_parameters:
                job_config.query_parameters = query_parameters
            job = self.client.query(processed_query, job_config=job_config)
            job.result()  # Wait for query to complete to catch errors and prevent premature temp table deletion
            return BQResultProxy(job)
        except Exception as e:
            logger.error(f"Query execution failed: {e}\nQuery: {query}")
            raise

    def fetch_df(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
        query_parameters: Optional[list] = None,
    ) -> pd.DataFrame:
        """Executes a query and returns a Pandas DataFrame.

        Args:
            query: SQL query string. Use @param_name placeholders for safe parameterization.
            params: Dict of DataFrames (uploaded as temp tables).
            query_parameters: List of bigquery.ScalarQueryParameter / ArrayQueryParameter
                              for safe @param substitution. Use this for any external or
                              data-derived values to prevent SQL injection.
        """
        try:
            processed_query, bind_params = self._handle_dataframe_params(query, params)
            dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
            job_config = bigquery.QueryJobConfig(default_dataset=dataset_ref)
            if query_parameters:
                job_config.query_parameters = query_parameters
            job = self.client.query(processed_query, job_config=job_config)
            return job.to_dataframe()
        except Exception as e:
            logger.error(f"Failed to fetch DataFrame: {e}")
            raise

    def append_dataframe_to_table(self, df: pd.DataFrame, table_name: str):
        """Appends a Pandas DataFrame directly to a BigQuery table."""
        if self.client is None:
            raise RuntimeError("Database connection not initialized.")

        try:
            logger.info(f"DBManager: Appending dataframe to '{table_name}'...")
            table_ref = f"{self.project_id}.{self.dataset_id}.{table_name}"

            # Sanitize column names for BigQuery compatibility
            df_cleaned = df.copy()
            df_cleaned.columns = df_cleaned.columns.astype(str).str.replace(
                r"[^a-zA-Z0-9_]", "_", regex=True
            )

            # Normalize object-dtype columns for pyarrow/BQ compatibility.
            for col in df_cleaned.columns:
                if df_cleaned[col].dtype != "object":
                    continue
                non_null = df_cleaned[col].dropna()
                if len(non_null) == 0:
                    # All-null column — leave as Python None; BQ schema determines type.
                    continue
                if all(isinstance(v, list) for v in non_null):
                    # ARRAY column — leave as Python lists; pyarrow handles them.
                    continue
                if all(isinstance(v, str) for v in non_null):
                    # Nullable string — preserve None without coercion.
                    df_cleaned[col] = df_cleaned[col].where(
                        df_cleaned[col].notna(), None
                    )
                else:
                    # Mixed non-string scalars — coerce to string.
                    df_cleaned[col] = df_cleaned[col].astype(str)

            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
            job = self.client.load_table_from_dataframe(
                df_cleaned, table_ref, job_config=job_config
            )
            job.result()  # Wait for upload to complete
            logger.info(
                f"DBManager: Successfully appended {len(df_cleaned)} rows to '{table_name}'."
            )
        except Exception as e:
            logger.error(f"Failed to append DataFrame to table '{table_name}': {e}")
            raise

    def table_exists(self, table_name: str) -> bool:
        """Checks if a table exists in the BigQuery dataset."""
        try:
            dataset_ref = self.client.dataset(self.dataset_id)
            table_ref = dataset_ref.table(table_name)
            self.client.get_table(table_ref)
            return True
        except Exception:
            return False

    # -----------------------------------------------------------------------
    # Graph Extension — entity nodes and sidecar metadata (Issue #807)
    # -----------------------------------------------------------------------

    def upsert_entity(self, entity: dict) -> str:
        """Insert or update an entity node. Returns entity_id.

        Uses a MERGE statement so the operation is idempotent: if the entity
        already exists (same entity_id) it updates mutable fields; otherwise
        it inserts. The entity_id must be provided by the caller in the format
        '{type}_{slug}_{shorthash6}', e.g. 'player_patrick-mahomes_e3f9a2'.

        Required keys: entity_id, entity_type, canonical_name, domain.
        Optional keys: aliases, metadata, first_seen_at, last_seen_at.
        """
        required = {"entity_id", "entity_type", "canonical_name", "domain"}
        missing = required - set(entity.keys())
        if missing:
            raise ValueError(f"upsert_entity: missing required keys: {missing}")

        project_id = self.project_id
        entity_id = entity["entity_id"]
        entity_type = entity["entity_type"]
        canonical_name = entity["canonical_name"]
        domain = entity.get("domain", "SPORTS")
        aliases = entity.get("aliases") or []
        metadata = entity.get("metadata")
        first_seen_at = entity.get("first_seen_at")
        last_seen_at = entity.get("last_seen_at")

        import json as _json

        aliases_literal = (
            "["
            + ", ".join(f"'{a.replace(chr(39), chr(39) * 2)}'" for a in aliases)
            + "]"
        )
        metadata_literal = (
            f"JSON '{_json.dumps(metadata)}'" if metadata is not None else "NULL"
        )
        first_seen_literal = f"TIMESTAMP '{first_seen_at}'" if first_seen_at else "NULL"
        last_seen_literal = f"TIMESTAMP '{last_seen_at}'" if last_seen_at else "NULL"

        merge_sql = f"""
            MERGE `{project_id}.{self.dataset_id}.entities` AS T
            USING (SELECT @entity_id AS entity_id) AS S
            ON T.entity_id = S.entity_id
            WHEN MATCHED THEN
                UPDATE SET
                    canonical_name = @canonical_name,
                    aliases        = {aliases_literal},
                    metadata       = {metadata_literal},
                    last_seen_at   = COALESCE({last_seen_literal}, T.last_seen_at),
                    claim_count    = COALESCE(T.claim_count, 0) + 1
            WHEN NOT MATCHED THEN
                INSERT (
                    entity_id, entity_type, canonical_name, aliases,
                    domain, metadata, first_seen_at, last_seen_at,
                    claim_count, created_at
                )
                VALUES (
                    @entity_id, @entity_type, @canonical_name, {aliases_literal},
                    @domain, {metadata_literal}, {first_seen_literal}, {last_seen_literal},
                    1, CURRENT_TIMESTAMP()
                )
        """
        qp = [
            bigquery.ScalarQueryParameter("entity_id", "STRING", entity_id),
            bigquery.ScalarQueryParameter("entity_type", "STRING", entity_type),
            bigquery.ScalarQueryParameter("canonical_name", "STRING", canonical_name),
            bigquery.ScalarQueryParameter("domain", "STRING", domain),
        ]
        self.execute(merge_sql, query_parameters=qp)
        logger.info("upsert_entity: entity_id=%s (%s)", entity_id, entity_type)
        return entity_id

    def get_entity(self, entity_id: str) -> dict | None:
        """Fetch entity by ID. Returns None if not found."""
        project_id = self.project_id
        query = f"""
            SELECT *
            FROM `{project_id}.{self.dataset_id}.entities`
            WHERE entity_id = @entity_id
            LIMIT 1
        """
        qp = [bigquery.ScalarQueryParameter("entity_id", "STRING", entity_id)]
        df = self.fetch_df(query, query_parameters=qp)
        if df.empty:
            return None
        row = df.iloc[0].to_dict()
        return row

    def get_entities_by_name(
        self,
        canonical_name: str,
        entity_type: str | None = None,
    ) -> list[dict]:
        """Look up entities by canonical name for entity resolution.

        Performs a case-insensitive exact match on canonical_name.
        Also checks the aliases array for the name.
        Optionally filters by entity_type.
        """
        project_id = self.project_id
        type_filter = "AND entity_type = @entity_type" if entity_type else ""
        query = f"""
            SELECT *
            FROM `{project_id}.{self.dataset_id}.entities`
            WHERE (
                LOWER(canonical_name) = LOWER(@canonical_name)
                OR EXISTS (
                    SELECT 1 FROM UNNEST(aliases) AS a
                    WHERE LOWER(a) = LOWER(@canonical_name)
                )
            )
            {type_filter}
            ORDER BY claim_count DESC
            LIMIT 50
        """
        qp = [
            bigquery.ScalarQueryParameter("canonical_name", "STRING", canonical_name),
        ]
        if entity_type:
            qp.append(
                bigquery.ScalarQueryParameter("entity_type", "STRING", entity_type)
            )
        df = self.fetch_df(query, query_parameters=qp)
        return df.to_dict(orient="records")

    def upsert_graph_extension(self, prediction_hash: str, extension: dict) -> None:
        """Write graph metadata for a claim to the sidecar table.

        Idempotent: MERGE on prediction_hash. Safe to call multiple times
        (e.g. when the embedding or cluster_id is backfilled later).

        Keys accepted in extension dict:
          entity_ids, primary_entity_id, claim_type, domain,
          asserted_state (dict → stored as JSON), embedding (list[float]),
          cluster_id, entity_resolution_confidence.
        """
        import json as _json

        project_id = self.project_id

        entity_ids = extension.get("entity_ids") or []
        primary_entity_id = extension.get("primary_entity_id")
        claim_type = extension.get("claim_type")
        domain = extension.get("domain", "SPORTS")
        asserted_state = extension.get("asserted_state")
        embedding = extension.get("embedding")
        cluster_id = extension.get("cluster_id")
        entity_resolution_confidence = extension.get("entity_resolution_confidence")

        entity_ids_literal = (
            "["
            + ", ".join(f"'{eid.replace(chr(39), chr(39) * 2)}'" for eid in entity_ids)
            + "]"
        )
        asserted_state_literal = (
            f"JSON '{_json.dumps(asserted_state)}'"
            if asserted_state is not None
            else "NULL"
        )
        embedding_literal = (
            "[" + ", ".join(str(float(v)) for v in embedding) + "]"
            if embedding is not None
            else "NULL"
        )

        qp = [
            bigquery.ScalarQueryParameter("prediction_hash", "STRING", prediction_hash),
            bigquery.ScalarQueryParameter(
                "primary_entity_id", "STRING", primary_entity_id
            ),
            bigquery.ScalarQueryParameter("claim_type", "STRING", claim_type),
            bigquery.ScalarQueryParameter("domain", "STRING", domain),
            bigquery.ScalarQueryParameter("cluster_id", "STRING", cluster_id),
            bigquery.ScalarQueryParameter(
                "entity_resolution_confidence",
                "FLOAT64",
                entity_resolution_confidence,
            ),
        ]

        merge_sql = f"""
            MERGE `{project_id}.{self.dataset_id}.prediction_ledger_graph_extension` AS T
            USING (SELECT @prediction_hash AS prediction_hash) AS S
            ON T.prediction_hash = S.prediction_hash
            WHEN MATCHED THEN
                UPDATE SET
                    entity_ids                   = {entity_ids_literal},
                    primary_entity_id            = COALESCE(@primary_entity_id, T.primary_entity_id),
                    claim_type                   = COALESCE(@claim_type, T.claim_type),
                    domain                       = COALESCE(@domain, T.domain),
                    asserted_state               = COALESCE({asserted_state_literal}, T.asserted_state),
                    embedding                    = COALESCE({embedding_literal}, T.embedding),
                    cluster_id                   = COALESCE(@cluster_id, T.cluster_id),
                    entity_resolution_confidence = COALESCE(
                                                     @entity_resolution_confidence,
                                                     T.entity_resolution_confidence
                                                   ),
                    updated_at                   = CURRENT_TIMESTAMP()
            WHEN NOT MATCHED THEN
                INSERT (
                    prediction_hash, entity_ids, primary_entity_id,
                    claim_type, domain, asserted_state, embedding,
                    cluster_id, entity_resolution_confidence,
                    created_at, updated_at
                )
                VALUES (
                    @prediction_hash, {entity_ids_literal}, @primary_entity_id,
                    @claim_type, @domain, {asserted_state_literal}, {embedding_literal},
                    @cluster_id, @entity_resolution_confidence,
                    CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP()
                )
        """
        self.execute(merge_sql, query_parameters=qp)
        logger.info(
            "upsert_graph_extension: prediction_hash=%s...", prediction_hash[:16]
        )

    def get_claim_edges(
        self,
        pundit_id: str | None = None,
        entity_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query the claim_edges view with optional filters.

        Returns joined ledger + graph-extension rows. Sidecar columns will
        be None/null for claims not yet enriched by the entity-resolution
        pipeline.

        Args:
            pundit_id: Filter by pundit slug, e.g. 'adam_schefter'.
            entity_id: Filter to claims mentioning this entity_id in
                       the entity_ids array of the sidecar table.
            limit: Maximum rows to return (default 100, max enforced by BQ
                   query cost — callers should paginate for large sets).
        """
        project_id = self.project_id
        conditions = []
        qp = [
            bigquery.ScalarQueryParameter("limit_val", "INT64", int(limit)),
        ]

        if pundit_id:
            conditions.append("pundit_id = @pundit_id")
            qp.append(bigquery.ScalarQueryParameter("pundit_id", "STRING", pundit_id))
        if entity_id:
            conditions.append(
                "EXISTS (SELECT 1 FROM UNNEST(entity_ids) AS eid WHERE eid = @entity_id)"
            )
            qp.append(bigquery.ScalarQueryParameter("entity_id", "STRING", entity_id))

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        query = f"""
            SELECT *
            FROM `{project_id}.gold_layer.claim_edges`
            {where_clause}
            ORDER BY timestamp_made DESC
            LIMIT @limit_val
        """
        df = self.fetch_df(query, query_parameters=qp)
        return df.to_dict(orient="records")

    def close(self):
        """Cleans up ephemeral dataframes before closing the connection."""
        for temp_ref in self._temp_tables:
            try:
                pass
                self.client.delete_table(temp_ref, not_found_ok=True)
                logger.info(f"DBManager Proxy: Cleaned up Ephemeral Table: {temp_ref}")
            except Exception as e:
                logger.warning(f"Failed to drop ephemeral table {temp_ref}: {e}")
        self._temp_tables.clear()
        self.client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_db_manager(**kwargs):
    """
    Factory that returns the right DB manager based on the DB_BACKEND env var.

    DB_BACKEND=duckdb   → DuckDBManager  (local DuckDB file, zero cloud cost)
    DB_BACKEND=bigquery → DBManager      (Google BigQuery, default)

    All keyword args are forwarded to the manager constructor unchanged so callers
    can pass db_path, read_only, access_tier, etc.

    Switch between backends:
        export DB_BACKEND=duckdb    # use local DuckDB
        unset  DB_BACKEND           # revert to BigQuery
    """
    backend = os.environ.get("DB_BACKEND", "bigquery").lower()
    if backend == "duckdb":
        from src.duckdb_manager import DuckDBManager

        return DuckDBManager(**kwargs)
    return DBManager(**kwargs)

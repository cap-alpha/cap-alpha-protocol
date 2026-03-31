import os
import uuid
import logging
import pandas as pd
from typing import Optional, Any, Dict
from google.cloud import bigquery
from google.oauth2 import service_account
import json

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
    def __init__(self, db_path: Optional[str] = None, read_only: bool = False, access_tier: str = 'writer'):
        self.project_id = os.environ.get("GCP_PROJECT_ID")
        self.dataset_id = "nfl_dead_money"  # Hardcoded convention for this pipeline
        self.client = None
        self._temp_tables = []
        self._initialize_connection()

    def _initialize_connection(self):
        """Initializes the BigQuery client."""
        try:
            if not self.project_id:
                raise EnvironmentError("GCP_PROJECT_ID environment variable is missing.")

            credentials_json = os.environ.get('GCP_SERVICE_ACCOUNT_JSON')
            if credentials_json:
                credentials_dict = json.loads(credentials_json)
                credentials = service_account.Credentials.from_service_account_info(credentials_dict)
                self.client = bigquery.Client(project=self.project_id, credentials=credentials)
            else:
                self.client = bigquery.Client(project=self.project_id)
                
            logger.info(f"Connected to BigQuery Project: {self.project_id}, Dataset: {self.dataset_id}")
        except Exception as e:
            logger.error(f"Failed to connect to BigQuery: {e}")
            raise

    def _handle_dataframe_params(self, query: str, params: Optional[Dict[str, Any]] = None) -> tuple[str, Optional[Dict[str, Any]]]:
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
                
                logger.info(f"DBManager Proxy: Uploading DataFrame '{k}' to BigQuery Ephemeral Temp Table: {table_ref}")
                
                # Sanitize column names for BigQuery compatibility
                df = v.copy()
                df.columns = df.columns.astype(str).str.replace(r'[^a-zA-Z0-9_]', '_', regex=True)
                # Cast objects to string to prevent Parquet schema mismatch crashes
                for col in df.columns:
                    if df[col].dtype == 'object':
                        df[col] = df[col].astype(str)
                
                job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                job = self.client.load_table_from_dataframe(df, table_ref, job_config=job_config)
                job.result()  # wait for load to complete
                
                # Track for later cleanup
                self._temp_tables.append(table_ref)
                
                # Rewrite query (simple find and replace for table name identifier)
                # Replaces standalone occurrences of the parameter name with the temp table reference
                query = query.replace(f" {k} ", f" `{table_ref}` ").replace(f"FROM {k}", f"FROM `{table_ref}`").replace(f"JOIN {k}", f"JOIN `{table_ref}`").replace(f"INTO {k} ", f"INTO `{table_ref}` ")
            else:
                bind_params[k] = v
                
        return query, (bind_params if bind_params else None)

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None):
        """Executes a SQL query on BigQuery."""
        try:
            processed_query, bind_params = self._handle_dataframe_params(query, params)
            
            # BigQuery parameterization is slightly different (uses @param) but we just use format for simplicity here if bind_params passed non-DF constants.
            # Warning: BigQuery python SDK expects parameters via QueryJobConfig, if complex params are passed we'd setup a JobConfig here.
            # For this pipeline, usually params are purely DataFrames {"df": df} which we intercepted above!
            
            dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
            job_config = bigquery.QueryJobConfig(default_dataset=dataset_ref)
            job = self.client.query(processed_query, job_config=job_config)
            job.result()  # Wait for query to complete to catch errors and prevent premature temp table deletion
            return BQResultProxy(job)
        except Exception as e:
            logger.error(f"Query execution failed: {e}\nQuery: {query}")
            raise

    def fetch_df(self, query: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
        """Executes a query and returns a Pandas DataFrame."""
        try:
            processed_query, bind_params = self._handle_dataframe_params(query, params)
            dataset_ref = bigquery.DatasetReference(self.project_id, self.dataset_id)
            job_config = bigquery.QueryJobConfig(default_dataset=dataset_ref)
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
            df_cleaned.columns = df_cleaned.columns.astype(str).str.replace(r'[^a-zA-Z0-9_]', '_', regex=True)
            
            # Cast object types to string to avoid Parquet type mismatch exceptions
            for col in df_cleaned.columns:
                if df_cleaned[col].dtype == 'object':
                    df_cleaned[col] = df_cleaned[col].astype(str)
                    
            job_config = bigquery.LoadJobConfig(write_disposition="WRITE_APPEND")
            job = self.client.load_table_from_dataframe(df_cleaned, table_ref, job_config=job_config)
            job.result()  # Wait for upload to complete
            logger.info(f"DBManager: Successfully appended {len(df_cleaned)} rows to '{table_name}'.")
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

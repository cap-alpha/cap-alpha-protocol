import duckdb
import os
import logging
import pandas as pd
from typing import Optional, Any, Dict
from src.config_loader import get_db_path

logger = logging.getLogger(__name__)

class DBManager:
    """
    Technology-agnostic database manager.
    Currently supports DuckDB and MotherDuck.
    """
    def __init__(self, db_path: Optional[str] = None, read_only: bool = False):
        self.db_path = db_path or get_db_path()
        self.read_only = read_only
        self.con = None
        self._initialize_connection()

    def _initialize_connection(self):
        """Initializes the database connection."""
        try:
            # Check if we are using MotherDuck
            if "md:" in self.db_path or os.getenv("MOTHERDUCK_TOKEN"):
                logger.info(f"Connecting to MotherDuck/DuckDB at {self.db_path}")
                self.con = duckdb.connect(self.db_path, read_only=self.read_only)
            else:
                logger.info(f"Connecting to local DuckDB at {self.db_path} (read_only={self.read_only})")
                self.con = duckdb.connect(self.db_path, read_only=self.read_only)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def execute(self, query: str, params: Optional[Dict[str, Any]] = None):
        """Executes a SQL query with explicit DataFrame registration for broad scope visibility."""
        try:
            bind_params = params
            if params:
                if isinstance(params, dict):
                    # Separate DataFrames for registration from bind parameters
                    df_params = {k: v for k, v in params.items() if isinstance(v, pd.DataFrame)}
                    bind_params = {k: v for k, v in params.items() if not isinstance(v, pd.DataFrame)}
                    
                    for name, df in df_params.items():
                        self.con.register(name, df)
                    
                    # If bind_params is empty, pass None to avoid issues if execute expects no params
                    if not bind_params:
                        bind_params = None
                else:
                    bind_params = params

            return self.con.execute(query, bind_params)
        except Exception as e:
            logger.error(f"Query execution failed: {e}\nQuery: {query}")
            raise

    def fetch_df(self, query: str, params: Optional[Dict[str, Any]] = None):
        """Executes a query and returns a Pandas DataFrame."""
        try:
            bind_params = params
            if params:
                if isinstance(params, dict):
                    df_params = {k: v for k, v in params.items() if isinstance(v, pd.DataFrame)}
                    bind_params = {k: v for k, v in params.items() if not isinstance(v, pd.DataFrame)}
                    
                    for name, df in df_params.items():
                        self.con.register(name, df)
                    
                    if not bind_params:
                        bind_params = None
                else:
                    bind_params = params

            return self.con.execute(query, bind_params).df()
        except Exception as e:
            logger.error(f"Failed to fetch DataFrame: {e}")
            raise

    def table_exists(self, table_name: str) -> bool:
        """Checks if a table exists in the database."""
        try:
            res = self.con.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{table_name}'").fetchone()
            return res[0] > 0
        except Exception:
            return False

    def close(self):
        """Closes the database connection."""
        if self.con:
            self.con.close()
            self.con = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

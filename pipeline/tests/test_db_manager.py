import pytest
import pandas as pd
import os
from src.db_manager import DBManager


# These tests require GCP_PROJECT_ID to be set (runs against real BigQuery)
pytestmark = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"),
    reason="GCP_PROJECT_ID not set — skipping BigQuery integration tests",
)

TEST_TABLE = "test_db_manager_tmp"


@pytest.fixture
def db_manager():
    """Create a DBManager instance connected to BigQuery."""
    db = DBManager()
    yield db
    # Cleanup: drop any test tables we created
    try:
        db.execute(f"DROP TABLE IF EXISTS {TEST_TABLE}")
    except Exception:
        pass
    db.close()


def test_db_manager_initialization():
    """Test that DBManager initializes and connects to BigQuery."""
    db = DBManager()
    assert db.client is not None
    assert db.project_id is not None
    assert db.dataset_id == "nfl_dead_money"
    db.close()
    assert db.client is None


def test_execute_query(db_manager):
    """Test executing a simple query."""
    db_manager.execute(
        f"CREATE OR REPLACE TABLE {TEST_TABLE} (id INT64, name STRING)"
    )
    db_manager.execute(f"INSERT INTO {TEST_TABLE} VALUES (1, 'Alice')")
    result = db_manager.execute(f"SELECT * FROM {TEST_TABLE}").fetchall()
    assert result == [(1, "Alice")]


def test_fetch_df(db_manager):
    """Test fetching a DataFrame."""
    db_manager.execute(
        f"CREATE OR REPLACE TABLE {TEST_TABLE} (id INT64, value FLOAT64)"
    )
    db_manager.execute(f"INSERT INTO {TEST_TABLE} VALUES (1, 10.5), (2, 20.0)")

    df = db_manager.fetch_df(f"SELECT * FROM {TEST_TABLE} ORDER BY id")
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert df.iloc[0]["value"] == 10.5


def test_table_exists(db_manager):
    """Test checking if a table exists."""
    assert not db_manager.table_exists("non_existent_table_random_xyz")
    db_manager.execute(
        f"CREATE OR REPLACE TABLE {TEST_TABLE} (id INT64)"
    )
    assert db_manager.table_exists(TEST_TABLE)


def test_execute_with_dataframe_registration(db_manager):
    """Test executing a query that joins against a registered DataFrame."""
    df = pd.DataFrame({"id": [1, 2], "val": ["a", "b"]})

    db_manager.execute(
        f"CREATE OR REPLACE TABLE {TEST_TABLE} (id INT64, name STRING)"
    )
    db_manager.execute(f"INSERT INTO {TEST_TABLE} VALUES (1, 'One'), (2, 'Two')")

    result_df = db_manager.fetch_df(
        f"""
        SELECT t.name, d.val
        FROM {TEST_TABLE} t
        JOIN my_df d ON t.id = d.id
        ORDER BY t.id
    """,
        params={"my_df": df},
    )

    assert len(result_df) == 2
    assert result_df.iloc[0]["val"] == "a"


def test_context_manager():
    """Test using DBManager as a context manager."""
    with DBManager() as db:
        assert db.client is not None
        db.execute(f"CREATE OR REPLACE TABLE {TEST_TABLE} (id INT64)")
    assert db.client is None


def test_error_handling(db_manager):
    """Test that errors are raised for invalid queries."""
    with pytest.raises(Exception):
        db_manager.execute("SELECT * FROM non_existent_table_random_xyz")

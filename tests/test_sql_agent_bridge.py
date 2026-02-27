import pytest
import duckdb
import json
import os
from pipeline.src.sql_agent_bridge import get_sql_from_llm, execute_query

# A simple transient in-memory DuckDB for testing
@pytest.fixture
def mock_db():
    db_path = ":memory:"
    con = duckdb.connect(db_path)
    # Setup mock schema
    con.execute("""
        CREATE TABLE fact_player_efficiency (
            player_id VARCHAR,
            player_name VARCHAR,
            team VARCHAR,
            position VARCHAR,
            year INTEGER,
            cap_hit_millions DOUBLE,
            risk_score DOUBLE,
            surplus_value DOUBLE,
            is_red_list BOOLEAN
        );
    """)
    con.execute("INSERT INTO fact_player_efficiency VALUES ('1', 'Patrick Mahomes', 'KC', 'QB', 2024, 45.0, 0.1, 15.0, false);")
    con.execute("INSERT INTO fact_player_efficiency VALUES ('2', 'Deshaun Watson', 'CLE', 'QB', 2024, 63.8, 0.95, -20.0, true);")
    con.close()
    return db_path

def test_execute_query_valid(mock_db):
    """Test that a valid SQL query returns the correct JSON rows."""
    sql = "SELECT player_name, cap_hit_millions FROM fact_player_efficiency WHERE position='QB' ORDER BY cap_hit_millions DESC"
    result_json = execute_query(mock_db, sql)
    
    data = json.loads(result_json)
    
    assert len(data) == 2
    assert data[0]["player_name"] == "Deshaun Watson"
    assert data[1]["player_name"] == "Patrick Mahomes"

def test_execute_query_invalid(mock_db):
    """Test that an invalid SQL query safely returns an error payload for the orchestrator."""
    sql = "SELECT garbage_column FROM fact_player_efficiency"
    result_json = execute_query(mock_db, sql)
    
    data = json.loads(result_json)
    assert "error" in data
    assert "failed_sql" in data

@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY") and not os.environ.get("GOOGLE_API_KEY"), reason="Requires Gemini API Key")
def test_get_sql_from_llm():
    """Integration test to verify LLM returns structurally valid SQL (Basic sanity check)."""
    question = "Who is the highest paid player?"
    sql = get_sql_from_llm(question)
    
    # We can't perfectly assert non-deterministic output, but it must be a SELECT statement.
    assert sql.strip().upper().startswith("SELECT")
    assert "fact_player_efficiency" in sql.lower()

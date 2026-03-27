from src.db_manager import DBManager
import argparse
import json
import os
import google.generativeai as genai

# Setup Gemini API key
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    from dotenv import load_dotenv
    load_dotenv()
    api_key = os.environ.get("GOOGLE_API_KEY")

genai.configure(api_key=api_key)

# The Database schema
SCHEMA_PROMPT = """
You are a PostgreSQL/DuckDB SQL expert working with the Cap Alpha Protocol database.

The database `nfl_dead_money.duckdb` has a `gold` Medallion layer meant for executive querying.
Here is the schema for the primary table `fact_player_efficiency`:

Column | Type | Description
--- | --- | ---
player_id | VARCHAR | Unique ID
player_name | VARCHAR | The name of the player
team | VARCHAR | 3-Letter team abbreviation (e.g., PHI, KC, SF)
position | VARCHAR | The positional grouping (QB, WR, RB, TE, EDGE, etc)
year | INTEGER | The season year
cap_hit_millions | DOUBLE | The salary cap hit for the year in millions
risk_score | DOUBLE | 0 to 1 score indicating contract risk (1 is highest efficiency risk)
surplus_value | DOUBLE | The actual market value produced minus the cap hit.
is_red_list | BOOLEAN | Indicates if the player is dangerously overpaid

Given a user's natural language question, respond EXCLUSIVELY with a syntactically correct DuckDB SQL query. No markdown formatting, no explanations. 
Just the raw SELECT statement.

Example:
User: "Who are the highest paid QBs?"
SELECT player_name, cap_hit_millions FROM fact_player_efficiency WHERE position='QB' ORDER BY cap_hit_millions DESC LIMIT 5;
"""

def get_sql_from_llm(question: str) -> str:
    """Uses Gemini to translate a plain English question into SQL."""
    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        response = model.generate_content(f"{SCHEMA_PROMPT}\n\nUser Question: {question}")
        
        sql = response.text.strip()
        # Clean up any potential markdown formatting the LLM might sneak in
        if sql.startswith("```sql"):
            sql = sql[6:]
        if sql.endswith("```"):
            sql = sql[:-3]
            
        return sql.strip()
    except Exception as e:
        print(f"Error communicating with LLM: {str(e)}")
        return ""

def execute_query(db_path: str, sql: str) -> str:
    """Executes the raw SQL against DuckDB with an error retry loop."""
    try:
        con = DBManager()
        # We cap results to avoid overflowing the LLM orchestrator context window
        if "LIMIT" not in sql.upper() and not sql.upper().startswith("SELECT COUNT"):
            sql = sql.rstrip(";") + " LIMIT 20;"
            
        df = con.execute(sql).df()
        
        # Format the result back into a JSON string for the orchestrator
        return df.to_json(orient='records')
    except Exception as e:
        # Expected guardrail action (Pass error back so calling AI can fix it)
        return json.dumps({"error": str(e), "failed_sql": sql})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DuckDB SQL Agent Bridge")
    parser.add_argument("query", type=str, help="The natural language query to run.")
    parser.add_argument("--db", type=str, default="./nfl_dead_money.duckdb", help="Path to DuckDB.")
    
    args = parser.parse_args()
    
    # 1. Ask LLM for SQL
    generated_sql = get_sql_from_llm(args.query)
    
    if generated_sql:
        # 2. Execute SQL against the database
        result_json = execute_query(args.db, generated_sql)
        
        # 3. Output to stdout (Which is captured by the Next.js API Route)
        print(json.dumps({
            "thought": f"Generated SQL: {generated_sql}",
            "sql": generated_sql,
            "data": json.loads(result_json) if not result_json.startswith('{"error"') else result_json
        }))
    else:
        print(json.dumps({"error": "Failed to generate SQL."}))

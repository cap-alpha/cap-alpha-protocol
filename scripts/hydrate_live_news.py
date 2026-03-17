import os
import time
import json
import duckdb
from duckduckgo_search import DDGS
import google.generativeai as genai
from datetime import datetime

# Initialize APIs
ddgs = DDGS()
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash-002")
model = genai.GenerativeModel(model_name)

def get_db_connection():
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    if not md_token:
        # Fallback to local if not running in production pipeline
        return duckdb.connect("nfl_data.duckdb")
    return duckdb.connect(f"md:nfl?motherduck_token={md_token}")

def get_top_players(con, threshold_rank=100):
    """
    Dynamically retrieve top players based on a non-static cap threshold.
    For instance, taking the top 100 players by total_guaranteed or apy.
    """
    try:
        # We query the highest paid active players based on a dynamic 90th percentile cap hit threshold in the current year.
        query = f"""
        WITH current_year AS (
            SELECT MAX(year) as max_year FROM fact_player_efficiency
        ),
        stats AS (
            SELECT percentile_cont(0.90) WITHIN GROUP (ORDER BY cap_hit_millions) as threshold 
            FROM fact_player_efficiency, current_year
            WHERE cap_hit_millions > 0 AND year = current_year.max_year
        )
        SELECT 
            player_name, 
            cap_hit_millions 
        FROM fact_player_efficiency, stats, current_year
        WHERE cap_hit_millions >= stats.threshold 
          AND year = current_year.max_year
        ORDER BY cap_hit_millions DESC
        """
        df = con.execute(query).df()
        return df['player_name'].tolist()
    except Exception as e:
        print(f"Error fetching top players from DB: {e}. Falling back to default list.")
        return ["Dak Prescott", "Russell Wilson", "Travis Kelce"]

def synthesize_news(player, news_results):
    """
    Use Gemini to extract an Intelligence Sentence from the news results.
    """
    prompt = f"""
    You are an NFL Cap and Operations Intelligence Analyst.
    Review the following news search results for {player}.
    Extract one precise, non-hyped "Intelligence Sentence" prioritizing Contract Talks, Trade Rumors, Injuries, or Cap Implications.
    Return JSON format: {{"type": "Warning|Rumor|Information", "text": "<sentence>"}}
    If no relevant intelligence exists in the text, return empty JSON {{}}.
    
    News Data: {news_results}
    """
    try:
        response = model.generate_content(prompt)
        # Parse output for JSON
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        return json.loads(text)
    except Exception as e:
        print(f"  Failed to synthesize news for {player}: {e}")
        return None

def inject_motherduck(con, player, intel):
    """
    Inject the synthesized intelligence into MotherDuck.
    """
    if not intel or not intel.get("text"):
        return
    
    timestamp = datetime.now().isoformat()
    try:
        # Ensure table exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS media_lag_metrics (
                player_name VARCHAR,
                event_type VARCHAR,
                intelligence_text VARCHAR,
                source_url VARCHAR,
                recorded_at TIMESTAMP
            )
        """)
        
        # Insert the record
        con.execute(
            "INSERT INTO media_lag_metrics VALUES (?, ?, ?, NULL, ?)", 
            (player, intel.get("type"), intel.get("text"), timestamp)
        )
    except Exception as e:
        print(f"  DB Injection failed: {e}")

def main():
    print("--- Starting Live Data Hydration ---")
    con = get_db_connection()
    target_players = get_top_players(con)
    print(f"Targeting {len(target_players)} top-tier players above threshold.")
    
    for player in target_players:
        try:
            print(f"\n[Hydrating] {player}...")
            time.sleep(1.5) # Rate limit duckduckgo
            
            # Focused search to avoid fantasy noise
            results = list(ddgs.news(f"{player} nfl contract OR injury OR rumor -fantasy", max_results=3))
            
            if not results:
                print(f"  No recent news found.")
                continue

            intel = synthesize_news(player, results)
            if intel and intel.get("text"):
                print(f"  Result: [{intel.get('type')}] {intel.get('text')}")
                # Inject to DB
                inject_motherduck(con, player, intel)
            else:
                print("  No relevant intelligence synthesized.")
            
        except Exception as e:
            print(f"  Error fetching news: {e}")
            
    print("\n--- Hydration Complete ---")

if __name__ == "__main__":
    main()

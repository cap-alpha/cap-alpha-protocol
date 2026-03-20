import os
import time
import json
import duckdb
from duckduckgo_search import DDGS
from google import genai
from datetime import datetime

# Initialize APIs
ddgs = DDGS()
api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)
model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash")

def get_db_connection():
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    if not md_token:
        raise ValueError("MOTHERDUCK_TOKEN environment variable not set.")
    return duckdb.connect(f"md:nfl_dead_money?motherduck_token={md_token}")

def get_active_rosters(con):
    """
    Retrieve all teams and their active rosters for the current year.
    Returns a dict: {team_name: [list of player_names]}
    """
    try:
        query = """
        WITH current_year AS (
            SELECT MAX(year) as max_year FROM fact_player_efficiency
        )
        SELECT team, player_name
        FROM fact_player_efficiency, current_year
        WHERE year = current_year.max_year
          AND cap_hit_millions > 0
        """
        df = con.execute(query).df()
        rosters = {}
        for _, row in df.iterrows():
            team = row['team']
            if team not in rosters:
                rosters[team] = []
            rosters[team].append(row['player_name'])
        return rosters
    except Exception as e:
        print(f"Error fetching rosters: {e}")
        return {}

def synthesize_news(player, news_results):
    """
    Use Gemini to extract an Intelligence Sentence and Sentiment Score.
    """
    prompt = f"""
    You are an NFL Cap and Operations Intelligence Analyst.
    Review the following news search results which mention {player}.
    Extract one precise, non-hyped "Intelligence Sentence" prioritizing Contract Talks, Trade Rumors, Injuries, or Cap Implications.
    Also generate a "sentiment_score" from -1.0 (extremely negative/toxic) to 1.0 (extremely positive/stable).
    Return JSON format: {{"type": "Warning|Rumor|Information", "text": "<sentence>", "sentiment_score": 0.0}}
    If no relevant intelligence exists for {player} in the text, return empty JSON {{}}.
    
    News Data: {news_results}
    """
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3]
        elif text.startswith("```"):
            text = text[3:-3]
        return json.loads(text)
    except Exception as e:
        print(f"  Failed to synthesize news for {player}: {e}")
        return None

def inject_motherduck(con, player, intel, has_news):
    """
    Inject the synthesized intelligence into MotherDuck, explicitly flagging 'has_news'.
    """
    if not intel:
        intel = {"type": "Information", "text": "No recent news detected.", "sentiment_score": 0.0}
    
    timestamp = datetime.now().isoformat()
    score = intel.get("sentiment_score", 0.0)
    try:
        # Ensure table exists with the new 'has_news' boolean flag
        con.execute("""
            CREATE TABLE IF NOT EXISTS media_lag_metrics (
                player_name VARCHAR,
                event_type VARCHAR,
                intelligence_text VARCHAR,
                sentiment_score DOUBLE,
                source_url VARCHAR,
                recorded_at TIMESTAMP,
                has_news BOOLEAN
            )
        """)
        
        # Check idempotency: avoid inserting the exact same intelligence text for this player within 24h
        check_query = """
            SELECT COUNT(*) 
            FROM media_lag_metrics 
            WHERE player_name = ? 
              AND intelligence_text = ? 
              AND recorded_at > CURRENT_TIMESTAMP - INTERVAL 24 HOUR
        """
        exists = con.execute(check_query, (player, intel.get("text"))).fetchone()[0]
        if exists > 0:
            print(f"  [Idempotency] Skipping duplicate intel string for {player}.")
            return False

        # Insert the record
        con.execute(
            "INSERT INTO media_lag_metrics VALUES (?, ?, ?, ?, NULL, ?, ?)", 
            (player, intel.get("type"), intel.get("text"), score, timestamp, has_news)
        )
        return True
    except Exception as e:
        print(f"  DB Injection failed: {e}")
        return False

def check_alert_telemetry(con, player, intel):
    """
    Compare current sentiment against contract value to generate automated telemetry
    alerts for plunging public consensus on high-capital assets.
    """
    score = intel.get("sentiment_score", 0.0)
    if score >= -0.4:
        return # Not toxic enough to fire an alert

    try:
        query = f"""
        WITH current_year AS (
            SELECT MAX(year) as max_year FROM fact_player_efficiency
        )
        SELECT cap_hit_millions 
        FROM fact_player_efficiency, current_year
        WHERE player_name = '{player.replace("'", "''")}'
          AND year = current_year.max_year
        """
        df = con.execute(query).df()
        if not df.empty:
            cap_hit = df['cap_hit_millions'].iloc[0]
            # Alert threshold: Cap Hit > 15M and Sentiment < -0.4
            if cap_hit > 15.0:
                print(f"  [TELEMETRY ALERT] 🚨 CRITICAL SENTIMENT DISCONNECT 🚨")
                print(f"  Asset: {player} | Cap Liability: ${cap_hit}M | Sentiment: {score}")
                print(f"  Event: {intel.get('text')}")
                print(f"  Trajectory: Accelerating Liability. Recommend Hedging.")
    except Exception as e:
        print(f"  Telemetry alert logic failed: {e}")

def main():
    print("--- Starting Franchise-Level Live Data Hydration ---")
    con = get_db_connection()
    team_rosters = get_active_rosters(con)
    print(f"Targeting {len(team_rosters)} active franchises for news cross-referencing.")
    
    for team, players in team_rosters.items():
        try:
            print(f"\n[Hydrating Franchise] {team}...")
            time.sleep(1.5) # Rate limit duckduckgo
            
            # Focused search by franchise to capture macro news
            results = list(ddgs.news(f"{team} nfl contract OR injury OR rumor -fantasy", max_results=5))
            
            if not results:
                print(f"  No recent news found for {team}.")
                # Log 'no news' for all franchise players
                for p in players:
                    inject_motherduck(con, p, None, has_news=False)
                continue

            # Combine all headline/body text to search for player mentions
            combined_text = " ".join([f"{r.get('title', '')} {r.get('body', '')}" for r in results]).lower()

            for player in players:
                # Use last name as a fuzzy match proxy because news often just uses last names
                last_name = player.split()[-1].lower() if len(player.split()) > 1 else player.lower()
                
                if player.lower() in combined_text or (len(last_name) > 3 and last_name in combined_text):
                    print(f"  > Hit detected for {player}.")
                    intel = synthesize_news(player, results)
                    if intel and intel.get("text"):
                        print(f"    Result: [{intel.get('type')}] {intel.get('text')}")
                        if inject_motherduck(con, player, intel, has_news=True):
                            check_alert_telemetry(con, player, intel)
                    else:
                        # Mentioned, but LLM deemed it non-actionable
                        inject_motherduck(con, player, None, has_news=False)
                else:
                    # Not mentioned in franchise news block
                    inject_motherduck(con, player, None, has_news=False)
            
        except Exception as e:
            print(f"  Error fetching news for {team}: {e}")
            
    print("\n--- Hydration Complete ---")

if __name__ == "__main__":
    main()

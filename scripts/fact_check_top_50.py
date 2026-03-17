import os
import sys
import json
import logging
import time
import duckdb
from collections import defaultdict
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

def get_db_connection():
    md_token = os.environ.get("MOTHERDUCK_TOKEN")
    if md_token:
        try:
            return duckdb.connect(f"md:nfl?motherduck_token={md_token}")
        except:
            return duckdb.connect(f"md:nfl_dead_money?motherduck_token={md_token}")
    db_path = os.path.join(os.path.dirname(__file__), "..", "pipeline", "nfl_data.duckdb")
    return duckdb.connect(db_path)

def main():
    target_team = sys.argv[1] if len(sys.argv) > 1 else None
    
    logger.info("Connecting to Database...")
    con = get_db_connection()
    
    # Try fetching top 50 predicted risky players
    try:
        query = """
            SELECT player_name, team, AVG(predicted_risk_score) as risk_avg
            FROM prediction_results
            WHERE year >= 2024
            GROUP BY player_name, team
            ORDER BY risk_avg DESC
            LIMIT 50
        """
        top_50 = con.execute(query).df().to_dict('records')
    except Exception as e:
        logger.error(f"Error fetching predictions: {e}")
        return

    logger.info(f"Fetched {len(top_50)} top risk players from prediction_results.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("No GEMINI_API_KEY found.")
        return
        
    client = genai.Client()
    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
    
    contradictions = []

    logger.info(f"Initializing Agentic Fact-Check Routine via Google Search Grounding using {model_name}...")
    
    # Group by team
    team_groups = defaultdict(list)
    for row in top_50:
        team = row["team"]
        if not team:
            team = "Free Agent"
        team_groups[team].append(row["player_name"])
        
    if target_team and target_team in team_groups:
        team_groups = {target_team: team_groups[target_team]}
        logger.info(f"Limiting to specific team: {target_team}")
        
    team_list = list(team_groups.items())
    
    for idx, (team, players) in enumerate(team_list):
        logger.info(f"[{idx+1}/{len(team_list)}] Checking team {team} ({len(players)} players)...")
        
        player_list_str = ", ".join(players)
        
        prompt = f"""
        You are an elite NFL Data Auditor and Cap Analyst.
        Our predictive model has classified the following NFL players from the {team} as HIGH-RISK ASSETS (predicted to be a bust, cut, benched, or suffer severe efficiency decline) for the 2024/2025 season:
        
        Players: {player_list_str}
        
        Use Google Search to find the most recent, up-to-date reality regarding EACH of these players (contracts, extensions, performance, injuries).
        Analyze if our model's assertion is a "big problem" or completely wrong for each specific player. 
        For example, if the player just signed a massive new extension, had an All-Pro season, or is universally praised, then reality contradicts the model. 
        If they were benched, cut, injured, or are playing poorly, reality confirms the model.

        Return EXACTLY a JSON block wrapped in ```json ... ``` with this schema (a list of objects, one for each player):
        [
            {{
                "player": "Player Name",
                "contradicts_model": true/false,
                "severity": "High/Medium/Low" (how badly the model missed),
                "summary": "1-2 sentence explanation of the real-world situation"
            }}
        ]
        """

        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                )
            )
            
            # Extract JSON from markdown response since native JSON MIME is unsupported with Search tool
            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:-3].strip()
            elif text.startswith("```"):
                text = text[3:-3].strip()
                
            results = json.loads(text)
            if not isinstance(results, list):
                results = [results]
            
            for result in results:
                player = result.get("player", "Unknown")
                if result.get("contradicts_model"):
                    logger.warning(f"  ❌ CONTRADICTION DETECTED [{result.get('severity')}]: {player} - {result.get('summary')}")
                    contradictions.append({
                        "player": player,
                        "team": team,
                        "severity": result.get("severity"),
                        "summary": result.get("summary")
                    })
                else:
                    logger.info(f"  ✅ MODEL CONFIRMED: {player} - {result.get('summary')}")
                
        except Exception as e:
            logger.error(f"  ⚠️ Error calling Gemini for team {team}: {e}")
            
        if idx < len(team_list) - 1:
            # Hard sleep to respect the 5 Requests Per Minute Free Tier Quota
            logger.info("  ⏳ Sleeping for 15 seconds to respect rate limits between teams...")
            time.sleep(15)

    logger.info("--- FACT CHECK SUMMARY ---")
    logger.info(f"Total teams checked: {len(team_list)}")
    logger.info(f"Contradictions found: {len(contradictions)}")
    for c in contradictions:
        logger.info(f" - {c['player']} ({c['team']} | {c['severity']}): {c['summary']}")
        
    # Write report artifact
    os.makedirs("/Users/andrewsmith/portfolio/nfl-dead-money/reports", exist_ok=True)
    with open("/Users/andrewsmith/portfolio/nfl-dead-money/reports/fact_check_report.json", "w") as f:
        json.dump(contradictions, f, indent=2)

if __name__ == "__main__":
    main()

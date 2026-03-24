#!/usr/bin/env python3
"""
Hourly Reddit Social Hydration Script
Identifies Cap, Roster, and Injury Intelligence from r/nfl and r/fantasyfootball.
Generates Multi-Resolution timeline events using Gemini for Semantic Zooming capabilities.
"""
import os
import json
import hashlib
import sqlite3
import pandas as pd
from datetime import datetime
from google import genai
from dotenv import load_dotenv
import feedparser
import time
import requests

import duckdb

# Setup paths & environment
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, "web", ".env.local")
load_dotenv(ENV_PATH)

MOTHERDUCK_TOKEN = os.getenv("MOTHERDUCK_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not MOTHERDUCK_TOKEN or not GEMINI_API_KEY:
    raise RuntimeError("Missing MOTHERDUCK_TOKEN or GEMINI_API_KEY in web/.env.local")

# Initialize clients
client = genai.Client(api_key=GEMINI_API_KEY)
model_name = "gemini-2.5-flash"

def get_event_id(url: str, player_name: str) -> str:
    s = f"{url}-{player_name}"
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def get_active_rosters(con):
    """
    Fetch the list of all active NFL players grouped by team from MotherDuck.
    Uses the modern feature store (spotrac_roster).
    """
    print("Fetching active rosters from MotherDuck...")
    try:
        query = """
            SELECT team, name as player_name 
            FROM spotrac_roster 
            WHERE roster_status = 'Active' OR roster_status = 'Reserve/Injured'
        """
        df = con.execute(query).df()
        
        team_rosters = {}
        for _, row in df.iterrows():
            team = row['team']
            player = row['player_name']
            if team not in team_rosters:
                team_rosters[team] = []
            team_rosters[team].append(player)
            
        print(f"Loaded rosters for {len(team_rosters)} teams.")
        return team_rosters
    except Exception as e:
        print(f"Failed to load rosters: {e}")
        return {}

def synthesize_social(player, post_data):
    """
    Use Gemini to extract Multi-Resolution Intelligence from a Reddit post.
    """
    prompt = f"""
    You are an NFL Cap and Operations Intelligence Analyst.
    Review the following Reddit Post and comments which mention {player}.
    Extract multi-resolution intelligence prioritizing Contract Talks, Trade Rumors, Injuries, or Cap Implications.
    
    Provide:
    1. "type": "Warning|Rumor|Information|Injury|Contract"
    2. "resolution_high_level": A single, concise sentence summarizing the event.
    3. "resolution_detailed": 1-2 paragraphs analyzing the context and cap/roster implications based on the Reddit sentiment.
    4. "sentiment_score": from -1.0 (extremely negative/toxic/injury) to 1.0 (extremely positive/stable).
    
    Return JSON format: {{"type": "...", "resolution_high_level": "...", "resolution_detailed": "...", "sentiment_score": 0.0}}
    If no relevant intelligence exists for {player} in the text (e.g. it's just a meme or generic praise), return empty JSON {{}}.
    
    Reddit Data: {post_data}
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
        print(f"  Failed to synthesize social post for {player}: {e}")
        return None

def inject_motherduck(con, player, team, intel, raw_content, source_url, source_platform="REDDIT"):
    """
    Inject the synthesized intelligence into MotherDuck using the player_timeline_events table.
    """
    if not intel or not intel.get("resolution_high_level"):
        return False
    
    timestamp = datetime.now().isoformat()
    score = intel.get("sentiment_score", 0.0)
    high_level = intel.get("resolution_high_level", "No summary.")
    detailed = intel.get("resolution_detailed", "")
    event_type = intel.get("type", "Information")
    
    event_id = get_event_id(source_url, player)

    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS player_timeline_events (
                event_id VARCHAR,
                player_name VARCHAR,
                team_name VARCHAR,
                event_type VARCHAR,
                event_date TIMESTAMP,
                source_url VARCHAR,
                source_platform VARCHAR,
                sentiment_score DOUBLE,
                resolution_high_level VARCHAR,
                resolution_detailed VARCHAR,
                raw_content VARCHAR
            )
        """)
        
        # Check idempotency via event_id
        check_query = "SELECT COUNT(*) FROM player_timeline_events WHERE event_id = ?"
        exists = con.execute(check_query, (event_id,)).fetchone()[0]
        if exists > 0:
            print(f"  [Idempotency] Skipping duplicate event_id for {player}.")
            return False

        # Insert the record
        con.execute(
            "INSERT INTO player_timeline_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
            (event_id, player, team, event_type, timestamp, source_url, source_platform, score, high_level, detailed, raw_content)
        )
        return True
    except Exception as e:
        print(f"  DB Injection failed: {e}")
        return False

def check_alert_telemetry(con, player, intel):
    """
    Checks if an alert needs to be pushed to the risk mitigation system.
    """
    score = intel.get("sentiment_score", 0.0)
    
    if score <= -0.6:
        try:
            query = """
                SELECT 
                    cap_hit, roster_status 
                FROM spotrac_roster 
                WHERE name = ? 
                ORDER BY year DESC LIMIT 1
            """
            result = con.execute(query, (player,)).fetchone()
            if result:
                cap_hit = float(result[0])
                if cap_hit > 15.0:
                    print(f"  [TELEMETRY ALERT] 🚨 CRITICAL SOCIAL SENTIMENT DISCONNECT 🚨")
                    print(f"  Asset: {player} | Cap Liability: ${cap_hit}M | Sentiment: {score}")
                    print(f"  Event: {intel.get('resolution_high_level')}")
                    print(f"  Recommendation: Evaluate immediate restructure or trade-hedge contingencies.")
        except Exception as e:
            print(f"  Telemetry alert logic failed: {e}")

def main():
    print("=== Commencing Hourly Omnichannel Social Hydration (Reddit Engine) ===")
    
    # 1. Connect to MotherDuck
    conStr = f"md:nfl_cap_alpha?motherduck_token={MOTHERDUCK_TOKEN}"
    try:
        con = duckdb.connect(conStr)
        print("Connected to MotherDuck via Medallion Engine.")
    except Exception as e:
        print(f"CRITICAL: Failed to connect to MotherDuck: {e}")
        return
        
    # 2. Extract Target Matrix
    team_rosters = get_active_rosters(con)
    if not team_rosters:
        print("No active rosters found. Aborting.")
        return
        
    # Create an inverse map for fast lookup
    player_to_team = {}
    for team, players in team_rosters.items():
        for p in players:
            player_to_team[p.lower()] = (p, team)

    # 3. Pull Reddit Posts via RSS (Credential-Free) -> We grab 'hot' and 'new'
    subreddits = ['nfl', 'fantasyfootball']
    posts_to_analyze = []
    
    print("Fetching active discussions from Reddit via RSS...")
    # Reddit frequently blocks default python user agents for RSS, so we need a custom one.
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 App/NFLDeadMoneyBot'}
    
    for sub in subreddits:
        for feed_type in ['.rss', '/new.rss']:
            url = f"https://www.reddit.com/r/{sub}{feed_type}"
            try:
                # Use requests to fetch with custom user agent, then parse with feedparser
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    for entry in feed.entries[:30]:  # Top 30 from each feed
                        posts_to_analyze.append(entry)
                else:
                    print(f"Warning: Got status {response.status_code} requesting {url}")
                time.sleep(2) # Be polite to Reddit servers
            except Exception as e:
                print(f"Error fetching from r/{sub}{feed_type}: {e}")
            
    # Deduplicate posts by link
    unique_posts = {post.link: post for post in posts_to_analyze}.values()
    print(f"Gathered {len(unique_posts)} unique recent Reddit posts for evaluation.")
    
    hits = 0
    # 4. Synthesize + Inject
    for post in unique_posts:
        title = post.title.lower()
        # RSS 'summary' often contains HTML of the post body
        selftext = post.get('summary', '').lower()
        combined_text = f"{title} {selftext}"
        
        # Check against active players
        matches = []
        for player_lower, (actual_name, team) in player_to_team.items():
            parts = player_lower.split()
            last_name = parts[-1]
            if player_lower in combined_text or (len(last_name) > 4 and last_name in combined_text):
                matches.append((actual_name, team))
                
        # Deduplicate matched players
        matches = list(set(matches))
        
        if matches:
            print(f"\nReddit Post: '{post.title[:60]}...'")
            print(f"Detected {len(matches)} active assets.")
            
            post_data = {
                "title": post.title,
                "text": post.get('summary', ''),
                "url": post.link
            }
            
            for player, team in matches:
                intel = synthesize_social(player, json.dumps(post_data))
                if intel and intel.get("resolution_high_level"):
                    print(f"  > [{player}]: {intel.get('resolution_high_level')}")
                    raw_content = json.dumps(post_data)
                    if inject_motherduck(con, player, team, intel, raw_content, post_data["url"], source_platform="REDDIT"):
                        check_alert_telemetry(con, player, intel)
                        hits += 1
                else:
                    print(f"  > [{player}]: Mentions detected but Gemini deemed non-actionable.")

    print(f"\n=== Reddit Hydration Complete. Analyzed {len(unique_posts)} posts, injected {hits} new timeline events. ===")

if __name__ == "__main__":
    main()

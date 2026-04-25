import urllib.request
import feedparser
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time
import os
import sys
import urllib.parse
from datetime import datetime

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from pipeline.src.db_manager import DBManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NewsRSSHoover:
    """
    Ingests unstructured news headlines and summaries via Google News RSS.
    Implements Franchise-Level News Batching: queries by team, cross-references
    active rosters, and parses mentions to scale to 100% of the active NFL cohort.
    """
    def __init__(self):
        self.db = DBManager()
        self.db.execute("CREATE SCHEMA IF NOT EXISTS bronze_layer")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS bronze_layer.raw_media_sentiment (
                player_name VARCHAR,
                source VARCHAR,
                raw_text VARCHAR,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def gather_team_news(self, team_name: str, players: list) -> bool:
        """Fetches the Google News RSS feed for a team and attributes hits to active players."""
        logger.info(f"Hoovering Franchise-Level Google News intelligence for {team_name}...")
        try:
            # URL encode the search query for the franchise
            query = urllib.parse.quote(f'"{team_name}" NFL (injury OR rumor OR contract OR trade) -fantasy')
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                logger.warning(f"  No recent news found for {team_name}")
                return False
                
            logger.info(f"  Found {len(feed.entries)} macro news articles for {team_name}.")
            
            # Combine the titles and summaries of the top 15 articles into one context block
            content_blocks = []
            for entry in feed.entries[:15]:
                title = entry.get('title', '')
                summary_html = entry.get('summary', '')
                soup = BeautifulSoup(summary_html, 'html.parser')
                summary_text = soup.get_text(separator=' ', strip=True)
                content_blocks.append(f"{title}. {summary_text}")
                
            compiled_content = "\\n\\n---\\n\\n".join(content_blocks).lower()
            
            hits = 0
            # Cross-reference active roster against the franchise news payload
            for player in players:
                # Use last name as a fuzzy match proxy due to journalism standards
                last_name = player.split()[-1].lower() if len(player.split()) > 1 else player.lower()
                
                if player.lower() in compiled_content or (len(last_name) > 3 and last_name in compiled_content):
                    hits += 1
                    # Insert into database with full team context
                    self.db.execute(
                        "INSERT INTO bronze_layer.raw_media_sentiment (player_name, source, raw_text) VALUES (?, 'google_news_rss_franchise_batch', ?)",
                        (player, compiled_content)
                    )
            
            logger.info(f"✅ Successfully cross-referenced {hits} players out of {len(players)} active roster names for {team_name}.")
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch news for {team_name}: {e}")
            return False

def get_active_rosters():
    """Queries BigQuery for all players grouped by active franchise."""
    logger.info("Discovering Active Rosters and Franchises from BigQuery...")
    db = DBManager()
    
    if not db.table_exists("fact_player_efficiency"):
        logger.warning("fact_player_efficiency not found. Using bootstrap list.")
        return {"Denver Broncos": ["Russell Wilson"], "Green Bay Packers": ["Aaron Rodgers"]}
        
    query = """
        SELECT team, player_name 
        FROM fact_player_efficiency 
        WHERE cap_hit_millions > 0
    """
    try:
        df = db.fetch_df(query)
        rosters = {}
        for _, row in df.iterrows():
            team = row['team']
            if team not in rosters:
                rosters[team] = []
            rosters[team].append(row['player_name'])
        
        logger.info(f"Successfully loaded {len(rosters)} active franchises for batch processing.")
        return rosters
    except Exception as e:
        logger.error(f"Failed to query targets: {e}")
        return {}

if __name__ == "__main__":
    hoover = NewsRSSHoover()
    rosters = get_active_rosters()
    
    for team, players in rosters.items():
        hoover.gather_team_news(team, players)
        time.sleep(1.5)  # Respect rate limits between franchise calls

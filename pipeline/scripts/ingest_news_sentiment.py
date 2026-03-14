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
    Replaces Wikipedia for more real-time 'market edge' insights on injuries and rumors.
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

    def gather_player_news(self, player_name: str) -> bool:
        """Fetches the Google News RSS feed for a player and saves the text to Bronze."""
        logger.info(f"Hoovering Google News intelligence for {player_name}...")
        try:
            # URL encode the search query
            query = urllib.parse.quote(f'"{player_name}" NFL (injury OR rumor OR contract OR trade)')
            rss_url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
            
            feed = feedparser.parse(rss_url)
            
            if not feed.entries:
                logger.warning(f"No recent news found for {player_name}")
                return False
                
            logger.info(f"Found {len(feed.entries)} news articles for {player_name}.")
            
            # Combine the titles and summaries of the top 10 articles into one context block
            content_blocks = []
            for entry in feed.entries[:10]:
                title = entry.get('title', '')
                # Clean HTML from summary
                summary_html = entry.get('summary', '')
                soup = BeautifulSoup(summary_html, 'html.parser')
                summary_text = soup.get_text(separator=' ', strip=True)
                
                # Format: "Title. Summary"
                content_blocks.append(f"{title}. {summary_text}")
                
            compiled_content = "\\n\\n---\\n\\n".join(content_blocks)
            
            # Insert into database
            self.db.execute(
                "INSERT INTO bronze_layer.raw_media_sentiment (player_name, source, raw_text) VALUES (?, 'google_news_rss', ?)",
                (player_name, compiled_content)
            )
            
            logger.info(f"✅ Successfully ingested {len(compiled_content)} characters of news for {player_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch news for {player_name}: {e}")
            return False

def get_high_value_targets():
    """Queries MotherDuck for all players with a cap hit > $10M or high risk."""
    logger.info("Discovering high-value targets from MotherDuck...")
    db = DBManager()
    
    # We query fact_player_efficiency. 
    # Fallback to a hardcoded list if the table doesn't exist yet (for bootstrap mode).
    if not db.table_exists("fact_player_efficiency"):
        logger.warning("fact_player_efficiency not found. Using bootstrap list.")
        return ["Russell Wilson", "Aaron Rodgers", "Deshaun Watson", "Ezekiel Elliott", "Jamal Adams"]
        
    query = """
        SELECT DISTINCT player_name 
        FROM fact_player_efficiency 
        WHERE cap_hit_millions >= 10 OR risk_score > 0.65
    """
    try:
        df = db.fetch_df(query)
        targets = df['player_name'].tolist()
        logger.info(f"Found {len(targets)} high-value targets for NLP parsing.")
        return targets
    except Exception as e:
        logger.error(f"Failed to query targets: {e}")
        return []

if __name__ == "__main__":
    hoover = NewsRSSHoover()
    targets = get_high_value_targets()
    
    for player in targets:
        hoover.gather_player_news(player)
        time.sleep(1)  # Respect rate limits

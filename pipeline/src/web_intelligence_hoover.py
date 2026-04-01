import logging
import os
import sys
import time

import pandas as pd
import wikipedia

# Add pipeline root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from pipeline.src.db_manager import DBManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class WikipediaHoover:
    """
    Ingests unstructured biographical text from Wikipedia for specific players.
    This replaces traditional web scraping (which suffers from API rate limits)
    while providing highly dense summaries of a player's career, injuries, and controversies.
    """

    def __init__(self):
        self.db = DBManager()
        # Initialize schema and table
        self.db.execute("CREATE SCHEMA IF NOT EXISTS bronze_layer")
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS bronze_layer.raw_media_sentiment (
                player_name VARCHAR,
                source VARCHAR,
                raw_text VARCHAR,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def gather_player_intelligence(self, player_name: str) -> bool:
        """Fetches the Wikipedia page for a player and saves the text to Bronze."""
        logger.info(f"Hoovering Wikipedia intelligence for {player_name}...")
        try:
            # We append 'American football' to disambiguate common names if needed,
            # though wikipedia library usually auto-redirects well.
            search_query = f"{player_name} American football"
            results = wikipedia.search(search_query)

            if not results:
                logger.warning(f"No Wikipedia results found for {player_name}")
                return False

            page_title = results[0]
            logger.info(f"Found page: {page_title}. Downloading content...")

            page = wikipedia.page(page_title, auto_suggest=False)
            content = page.content

            # Simple insertion
            self.db.execute(
                "INSERT INTO bronze_layer.raw_media_sentiment (player_name, source, raw_text) VALUES (?, 'wikipedia', ?)",
                (player_name, content),
            )

            logger.info(
                f"✅ Successfully ingested {len(content)} characters for {player_name}"
            )
            return True

        except wikipedia.exceptions.DisambiguationError as e:
            logger.error(f"Disambiguation error for {player_name}: {e.options}")
            return False
        except Exception as e:
            logger.error(f"Failed to hoover {player_name}: {e}")
            return False


if __name__ == "__main__":
    hoover = WikipediaHoover()

    # "Proof of Alpha" elite targets to save on bandwidth
    targets = [
        "Russell Wilson",
        "Aaron Rodgers",
        "Deshaun Watson",
        "Ezekiel Elliott",
        "Jamal Adams",
    ]

    for player in targets:
        hoover.gather_player_intelligence(player)
        time.sleep(2)  # Respect API limits

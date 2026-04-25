import sys
import os

try:
    import selenium
    import pandas
    import bs4

    print("Dependencies found.")
except ImportError as e:
    print(f"Missing dependency: {e}")
    sys.exit(1)

# Add src to path
sys.path.append(os.getcwd())
try:
    from src.spotrac_scraper_v2 import SpotracScraper

    print("Scraper imported successfully.")
except Exception as e:
    print(f"Scraper import failed: {e}")
    sys.exit(1)

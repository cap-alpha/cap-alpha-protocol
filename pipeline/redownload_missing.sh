#!/bin/bash
set -e

# Rebuild missing data files
python pipeline/src/spotrac_scraper_v2.py player-rankings 2015
python pipeline/src/spotrac_scraper_v2.py player-rankings 2016
python pipeline/src/spotrac_scraper_v2.py player-rankings 2017
python pipeline/src/spotrac_scraper_v2.py player-rankings 2024
python pipeline/src/spotrac_scraper_v2.py player-rankings 2025

python pipeline/src/spotrac_scraper_v2.py team-cap 2015
python pipeline/src/spotrac_scraper_v2.py team-cap 2024
python pipeline/src/spotrac_scraper_v2.py team-cap 2026

# Run the long one last
python pipeline/src/spotrac_scraper_v2.py player-contracts 2024

echo "✅ All missing data successfully re-downloaded."

# Run Scraping Pipeline

Execute the full data scraping pipeline inside the Docker container.

## Steps
1. Ensure Docker services are running: `make up`
2. Run the full scrape: `make pipeline-scrape`
3. Monitor output for errors (rate limits, blocked requests, missing data)
4. If scrape succeeds, verify output data exists in BigQuery bronze layer
5. Optionally run NLP hydration: `make pipeline-nlp`
6. Report summary: records scraped per source, any failures

## Available Scrape Targets
- `spotrac_scraper_v2.py team-cap` — Team salary cap data
- `spotrac_scraper_v2.py player-salaries` — Player salary breakdowns
- `spotrac_scraper_v2.py player-rankings` — Player cap value rankings
- `spotrac_scraper_v2.py player-contracts` — Contract details
- `overthecap_scraper.py` — Contract guaranteed money (backup source)
- `pfr_roster_scraper.py` — Pro Football Reference roster data

## On Failure
- Rate limit: Wait and retry, check for Selenium driver issues
- Missing Chrome: Verify `CHROME_BIN` and `CHROMEDRIVER_BIN` env vars in container

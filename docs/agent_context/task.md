# Data Automation Sprint

- [x] Create a consolidated `pipeline/run_daily.py` to orchestrate all pipeline steps
- [x] Create a `Dockerfile.cloudrun` optimized for headless Chrome, Selenium, Python, and dbt
- [x] Determine Google Cloud Project ID and set up GCP infrastructure
- [ ] Deploy the pipeline to Google Cloud Run Jobs using `gcloud` or MCP
- [ ] Set up Google Cloud Scheduler to trigger the job daily at 2:00 AM UTC
- [ ] Verify execution and confirm data syncs to MotherDuck/Vercel Postgres
- [ ] Verify identical prediction output in Vercel Postgres/MotherDuck

## Omnichannel Social Intelligence Sprint
- [x] Decide on social media ingestion architecture (Apify vs Official APIs vs RSS/Reddit)
- [x] Create `scripts/hydrate_reddit_social.py` using `praw` to pull from r/nfl and r/fantasyfootball hourly
- [x] Migrate `media_lag_metrics` to a new `player_timeline_events` MotherDuck schema backing multi-resolution detail (`raw`, `detailed`, `high_level`)
- [x] Implement Gemini prompt to extract high-level summaries and detailed event contexts simultaneously
- [x] Build a dedicated Google Cloud Run Job & Scheduler (or GitHub Action) for the hourly Reddit/news fetch loop

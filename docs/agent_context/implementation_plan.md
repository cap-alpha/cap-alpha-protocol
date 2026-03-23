# Omnichannel Social Integration & Multi-Resolution Timeline Schema

We will forgo paid APIs and aggregator services, and instead focus entirely on **Reddit** (`r/nfl`, `r/fantasyfootball`) for our high-signal social ingestion. Additionally, we will overhaul our MotherDuck schema to support "Semantic Zooming" across the player timeline.

## Proposed Changes

### 1. Multi-Resolution Timeline Schema (MotherDuck)
We are deprecating the shallow `media_lag_metrics` table in favor of a robust `player_timeline_events` table that stores the event at varying levels of detail natively, allowing the React frontend to simply toggle state based on the user's zoom level.

```sql
CREATE TABLE IF NOT EXISTS player_timeline_events (
    event_id VARCHAR,             -- SHA256 Hash of url+player for idempotency
    player_name VARCHAR,          
    team_name VARCHAR,            
    event_type VARCHAR,           -- INJURY, TRADE, RUMOR, CONTRACT, SENTIMENT
    event_date TIMESTAMP,         
    source_url VARCHAR,           
    source_platform VARCHAR,      -- REDDIT, DDG_NEWS, OFFICIAL
    
    -- Multi-Resolution Data Tiers
    sentiment_score DOUBLE,       -- -1.0 to 1.0
    resolution_high_level VARCHAR,-- Z-1: 1 concise sentence (e.g. "Patrick Mahomes restructured his contract.")
    resolution_detailed VARCHAR,  -- Z-2: 1-2 paragraphs (e.g. "Freed up $21.5M in cap space. Base converted to signing bonus.")
    raw_content VARCHAR           -- Z-3: Raw markdown/text of the scraped Reddit post or News body.
)
```

### 2. Upgrading Ingestion Scripts

#### [NEW] `scripts/hydrate_reddit.py`
A new script leveraging `praw` to scan hot/new posts from `r/nfl` hourly. It will cross-reference post titles/text against active rosters and use Gemini to generate the `high_level` and `detailed` summaries simultaneously before pushing to MotherDuck.

#### [MODIFY] `scripts/hydrate_live_news.py`
Update the existing DuckDuckGo news hydrator to use the new Gemini prompt structure (requesting both high-level and detailed summaries) and insert into the `player_timeline_events` table.

### 3. Execution Automation
Since we are using Cloud Run Jobs for the main pipeline, we will deploy a **second, much smaller Cloud Run Job** specifically for `hydrate_reddit.py` and `hydrate_live_news.py`, attached to an **hourly** Cloud Scheduler trigger. This completely separates the fast-moving social intelligence from the slow-moving daily contract ETL pipeline.

## Verification Plan
1. Send a test execution fetching the top 20 `r/nfl` posts via `praw`.
2. Inspect MotherDuck to verify Gemini correctly synthesized both the 1-sentence (`high_level`) and comprehensive (`detailed`) fields.
3. Validate idempotency by running the script twice within the hour to ensure no duplicate event IDs are created.

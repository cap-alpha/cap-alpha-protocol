> **[DEPRECATED — 2026-04-02]**
> Superseded by `strategy/MONETIZATION.md`. Tracks 1-2 were never implemented. Track 3 evolved into the Pundit Prediction Ledger.
> Retained for historical context only. Do not use for strategic planning.

# Advanced Intelligence & Monetization Tracks (Tracks 1-3)

## Track 1: The "Rumor Mill" Ingestion Pipeline
**Objective**: Convert qualitative, unstructured news (rumors, locker room drama, injuries, holdouts) into a quantitative **Volatility Multiplier** that penalizes or boosts the Cap Alpha asset valuation.

### Architecture & Data Flow
1. **Ingestion Layer (`ingest_sentiment.py`)**: 
   - An Airflow DAG running daily (or hourly closer to the trade deadline).
   - Scrapes key NFL insiders (e.g., Adam Schefter, Ian Rapoport) or team-specific subreddits/beat reporters.
2. **Agentic Processing (The LLM Step)**:
   - Feeds raw unstructured text to a localized LLM prompt with strict JSON-mode enforcement. 
   - Uses **Named Entity Recognition (NER)** to extract the player and **Sentiment Analysis** to score the severity of the event.
3. **Data Contract (DuckDB Medallion)**:
   - **Bronze**: Raw text strings and timestamps.
   - **Silver**: Parsed JSON `{"player_id": int, "sentiment_score": float, "event_type": str, "confidence": float}`.
   - **Gold**: A rolled-up weekly `volatility_multiplier` feature added to your main Feature Store.

---

## Track 2: Market Demand & Persona Simulation
**Objective**: Stress-test your freemium model and paywall by simulating how different user demographics (Bettor, GM, Agent, Fan) spend their credits.

### Architecture & Data Flow
1. **Simulation Engine (`simulate_market_demand.py`)**: 
   - A Python script that randomly samples outputs from your existing pipeline (e.g., a scouting report for a high-cap asset).
2. **Agentic Processing (The Product Council)**:
   - Instantiates your existing `product_council` personas. 
   - Example Prompt: *"You are an NFL Bettor with 50 site credits remaining. You see the following top-level teaser for Player X. Do you spend 5 credits to unlock the full 'Cap Impact' report? Output your decision and reasoning."*
3. **Data Contract (The Ledger)**:
   - A SQLite or DuckDB table tracking simulated interactions: `{"simulation_id": uuid, "persona": "Bettor", "asset_id": "player_123", "credits_spent": 5, "reasoning": "High variance asset, needed deeper insight."}`.
4. **Reporting (The Dashboard)**:
   - A simple query that aggregations the ledger to show you the **Simulated Conversion Rate** by persona and by feature type.

---

## Track 3: The "Proof of Alpha" Ledger
**Objective**: Generate ruthless, cryptographic-style "receipts" that prove the Cap Alpha Protocol's predictive power over consensus markets, displayed directly to the user as marketing.

### Architecture & Data Flow
1. **Point-in-Time (PIT) Extractor (`generate_alpha_receipts.py`)**: 
   - A script that looks backwards into your backtesting data to find the highest-delta "wins" (e.g., when your model predicted a massive drop in efficiency 3 weeks before Vegas adjusted their lines).
2. **Agentic Processing (The CBO / Marketing Persona)**:
   - Passes the raw statistical delta (e.g., *Model Cap Valuation: $5M vs Actual Contract: $15M*) to the **Chief Brand Officer** or **VP of Marketing** persona.
   - Outputs punchy, investment-grade marketing copy.
3. **Frontend Integration (`ProofOfAlphaCarousel.tsx`)**:
   - A dedicated React component on your landing page. 
   - Data Contract: `{"date": "2024-10-12", "player_name": "Player X", "prediction": "Sell", "outcome": "ACL Tear / Benched", "roi": "+450%", "pitch": "Cap Alpha flagged this asset as toxic 14 days before consensus."}`

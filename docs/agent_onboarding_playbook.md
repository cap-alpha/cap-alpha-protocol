# Agent Onboarding Playbook

**System Architecture State**:
- **Data Backend**: Google BigQuery (Medallion: Bronze -> Silver -> Gold).
- **Data Sources**: SportsDataIO (official feeds), OverTheCap (contracts), Spotrac (salary data), Pro Football Reference (historical stats), Google News RSS (sentiment).
- **BigQuery Dialect**: All SQL must compile natively for BigQuery (`STRING` not `VARCHAR`, `FLOAT64`/`INT64`, `SAFE_CAST()`, `MOD()` not `%`).
- **ML Model**: XGBoost risk model trained on 308-feature set (see `models/model_meta_*.json`). Walk-forward backtesting 2015-2025.
- **Frontend**: Next.js 14 (App Router), Tailwind + Radix UI + Recharts, Clerk auth.
- **Code Execution**: Always execute scripts from the virtual environment (`.venv/bin/python`).

**Product Direction**:
The core monetizable product is the **Pundit Prediction Ledger** — a cryptographically verified tracker of public pundit predictions scored against real NFL outcomes. This sits on top of the existing NFL contract/FMV data platform.

Key features to preserve and build on:
- FMV tracking per player
- Contract data pipeline (cap hit, dead cap, signing bonus, guarantees)
- Per-player news feed and sentiment
- XGBoost risk model and feature store

**Next Steps**:
Check GitHub milestones for current priorities:
1. **Foundation: Clean Data Platform** — BigQuery schema quality, data validation
2. **The Pundit Prediction Ledger** — Media ingestion, NLP extraction, crypto hashing, resolution engine
3. **Player Intelligence** — FMV dashboard, unified timeline, news feed
4. **Monetization & API** — Public REST API, tiered access, landing page

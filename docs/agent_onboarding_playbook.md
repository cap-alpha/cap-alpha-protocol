# Agent Onboarding Playbook

**System Architecture State**:
- **Data Ingestion**: Moved from explicit scheduled Github Actions for heavy ETL to **Google Cloud Run Jobs**. We are in the process of automating the `pipeline/run_daily.py` job via Google Cloud Scheduler.
- **Social Media**: Omnichannel Social Hydration is active. We are using `praw` (Reddit API) over Apify/Official APIs for cost and stability. A new `player_timeline_events` schema in MotherDuck replaces `media_lag_metrics` to support native Z-1 (High-Level) and Z-2 (Detailed) "semantic zooming" for the UI.
- **Code Execution**: Always execute scripts from the virtual environment (e.g., `.venv/bin/python`).

**Next Immediate Steps for Incoming Agent**:
Review `docs/agent_context/task.md` and `docs/agent_context/implementation_plan.md` for the latest snapshot of the sprint backlog. The previous agent achieved full dynamic 2026 chronology (eliminating all hardcoded years), fixed the live news hydration action using `duckduckgo-search` bridging into MotherDuck, and resolved Next.js frontend crashing (via `crypto_ledger`).

**Critical Execution Constraint**: Do not attempt to run python scripts native to macOS. TCC/SIP File Locks (`Operation not permitted`) will severely block MotherDuck local writes or GitHub cache logs. You MUST use `docker compose exec pipeline bash -c "..."` or execute via GitHub Actions.

# Agent Onboarding Playbook

**System Architecture State**:
- **Data Ingestion**: Moved from explicit scheduled Github Actions for heavy ETL to **Google Cloud Run Jobs**. We are in the process of automating the `pipeline/run_daily.py` job via Google Cloud Scheduler.
- **Social Media**: Omnichannel Social Hydration is active. We are using `praw` (Reddit API) over Apify/Official APIs for cost and stability. A new `player_timeline_events` schema in MotherDuck replaces `media_lag_metrics` to support native Z-1 (High-Level) and Z-2 (Detailed) "semantic zooming" for the UI.
- **Code Execution**: Always execute scripts from the virtual environment (e.g., `.venv/bin/python`).

**Next Immediate Steps for Incoming Agent**:
Review `docs/agent_context/task.md` and `docs/agent_context/implementation_plan.md` for the latest snapshot of the sprint backlog. We are currently operating in a **MULTI-AGENT** context. Check `MASTER_SPRINT_PLAN.md` to see which tasks are marked `[/]` to avoid stepping on other agents. We have claimed `SP20-1` (Sub-Second Latency & Performance Optimization - Frontend Edge Caching). If you are resuming this exact thread, execute SP20-1.

**Critical Execution Constraint**: Do not attempt to run python scripts native to macOS. TCC/SIP File Locks (`Operation not permitted`) will severely block MotherDuck local writes or GitHub cache logs. You MUST use `docker compose exec pipeline bash -c "..."` or execute via GitHub Actions.

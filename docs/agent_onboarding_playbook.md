# Agent Onboarding Playbook

**System Architecture State**:
- **Data Ingestion**: Moved from explicit scheduled Github Actions for heavy ETL to **Google Cloud Run Jobs**. We are in the process of automating the `pipeline/run_daily.py` job via Google Cloud Scheduler.
- **Social Media**: Omnichannel Social Hydration is active. We are using `praw` (Reddit API) over Apify/Official APIs for cost and stability. A new `player_timeline_events` schema in MotherDuck replaces `media_lag_metrics` to support native Z-1 (High-Level) and Z-2 (Detailed) "semantic zooming" for the UI.
- **Code Execution**: Always execute scripts from the virtual environment (e.g., `.venv/bin/python`).

**Next Immediate Steps for Incoming Agent**:
Review `docs/agent_context/task.md` and `docs/agent_context/implementation_plan.md` for the latest snapshot of the sprint backlog. The previous agent completed the Reddit script but was paused before finalizing the Cloud Run Scheduler deployment due to a `/chk` handoff command.

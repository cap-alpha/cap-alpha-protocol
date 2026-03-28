# Agent Onboarding Playbook

> [!IMPORTANT] 
> **EXECUTIVE DIRECTIVE: QUOTA ROI MAXIMIZATION**
> The human operator's top-level imperative is to **maximally leverage Agentic compute quota**. Across all projects, you MUST proactively recommend high-ROI autonomous tasks, suggest parallel workflows, and offer to run deep, computationally expensive tasks (like adversarial fuzzing, data backfills, or UI/UX audits) when the user steps away. Never wait idly if compute can be burned on infrastructure hardening.

**System Architecture State**:
- **Data Backend**: Transitioned completely from MotherDuck local files to **Google BigQuery Native**. The Medallion pipeline (Bronze -> Silver -> Gold) successfully hydrates 2026 data. Schemas are strictly compiled via `contracts/compile.py`.
- **Data Scrapers**: Swapped Spotrac for **OverTheCap** (`/salary-cap/{slug}`) as the primary contracts source to completely bypass Cloudflare bot mitigation (403s). 
- **BigQuery Dialect**: All internally generated SQL MUST compile natively for BigQuery. This means mapping `VARCHAR` to `STRING`, using `FLOAT64`/`INT64`, bypassing `%` with `MOD()`, and leveraging `SAFE_CAST()` over `TRY_CAST()`.
- **Social Media**: Omnichannel Social Hydration is active. We are using `praw` (Reddit API) over Apify/Official APIs for cost and stability. A new `player_timeline_events` schema in MotherDuck replaces `media_lag_metrics` to support native Z-1 (High-Level) and Z-2 (Detailed) "semantic zooming" for the UI.
- **Data Versioning**: DVC (Data Version Control) is now enabled. `data/raw` and `models/*.pkl` are tracked by DVC, backed by Google Cloud Storage bucket `gs://rl-trading-strategy-flywheel-data/nfl_dead_money_dvc_storage`. Ensure `dvc pull` is executed if you need local access to heavy ML assets or raw CSV datasets.
- **Code Execution**: Always execute scripts from the virtual environment (e.g., `.venv/bin/python`).

**Next Immediate Steps for Incoming Agent**:
Review `docs/agent_context/task.md` and `docs/agent_context/implementation_plan.md` for the latest snapshot of the sprint backlog. We are always operating in a **MULTI-AGENT** context. Check `MASTER_SPRINT_PLAN.md` to see which tasks are marked `[ ]` to avoid stepping on other agents. We have claimed `SP20-1` (Sub-Second Latency & Performance Optimization - Frontend Edge Caching). If you are resuming this exact thread, execute SP20-1.

**Critical Execution Constraint**: Do not attempt to run python scripts native to macOS. TCC/SIP File Locks (`Operation not permitted`) will severely block MotherDuck local writes or GitHub cache logs. You MUST use `docker compose exec pipeline bash -c "..."` or execute via GitHub Actions.

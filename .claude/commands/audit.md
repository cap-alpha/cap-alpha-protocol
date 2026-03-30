# Documentation & Code Audit

Cross-check documentation against actual codebase to detect drift and contradictions.

## Steps
1. Read these canonical docs:
   - `.github/copilot-instructions.md` (agent coding guide)
   - `docs/agent_onboarding_playbook.md` (system architecture state)
   - `docs/sprints/MASTER_SPRINT_PLAN.md` (current work)

2. For each claim in the docs, verify against code:
   - **Tech stack**: Check actual imports, configs, Dockerfiles
   - **Data sources**: Check scraper files in `pipeline/src/` — which actually exist and run?
   - **Database backend**: Check `dbt/profiles.yml`, pipeline DB connections
   - **ML model**: Check `pipeline/src/train_model.py`, `models/model_meta_*.json`
   - **Feature count**: Check latest `model_meta_*.json` for `feature_count`
   - **SQL dialect**: Scan `dbt/models/**/*.sql` for non-BigQuery syntax

3. Report findings as:
   - ✅ Verified (doc matches code)
   - ⚠️ Outdated (doc doesn't match but directionally correct)
   - ❌ Wrong (doc contradicts code)

4. Fix any ❌ issues directly. Flag ⚠️ issues for human review.

## Do NOT
- Create new markdown summary files unless explicitly asked
- Change code to match wrong docs — always trust the code over the docs

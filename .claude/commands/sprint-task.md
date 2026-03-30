# Sprint Task Execution

Pick up and execute a specific task from the Master Sprint Plan.

## Inputs
- Task ID (e.g., "SP22-1") or description of what to work on

## Steps
1. Read `docs/sprints/MASTER_SPRINT_PLAN.md` to find the task
2. Understand the task requirements and acceptance criteria
3. Check related code/files to understand current state
4. Implement the task
5. Run `make preflight` to validate
6. Mark the task as `[x]` in `docs/sprints/MASTER_SPRINT_PLAN.md`
7. Summarize what was done and any decisions made

## Rules
- Follow the AI Collaboration Contract: update MASTER_SPRINT_PLAN.md as you work
- Do NOT start a new Epic without human sign-off
- All execution happens inside Docker containers via `make` targets
- All SQL must be BigQuery dialect (STRING not VARCHAR, SAFE_CAST, INT64/FLOAT64)

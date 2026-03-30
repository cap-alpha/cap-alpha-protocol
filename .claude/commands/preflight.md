# Preflight Validation

Run the full preflight validation gate before committing any changes.

## Steps
1. Run `make preflight` (chains lint → unit tests → dbt compile)
2. If any step fails, diagnose and fix the issue
3. Re-run until all checks pass
4. Report a summary of results: passed/failed counts, any warnings

## On Failure
- **Lint failures**: Run `docker compose --env-file docker_env.txt exec pipeline bash -c "black pipeline/src/ && isort pipeline/src/"` to auto-fix
- **Test failures**: Read the failing test, trace the root cause, fix, re-run
- **dbt compile failures**: Check for SQL syntax errors in `dbt/models/` — remember all SQL must be BigQuery dialect

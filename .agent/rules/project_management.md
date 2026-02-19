
# Project Management Rules

1. **Source of Truth**: `docs/project_management/ISSUES_BACKLOG.md` is the single source of truth for all project tasks.
2. **Sync Requirement**: Whenever `ISSUES_BACKLOG.md` is modified, the agent MUST run the `/sync_issues` workflow immediately to propagate changes to GitHub.
3. **Closing Issues**: When a task is completed, mark it as `[x]` in the backlog AND ensure the corresponding GitHub issue is updated/closed (handled by sync script).
4. **Issue Creation**: Do not create issues via `gh` CLI manually. Add them to `ISSUES_BACKLOG.md` first, then sync.

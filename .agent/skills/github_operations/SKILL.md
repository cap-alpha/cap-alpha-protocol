---
name: GitHub Operations
description: Standardized workflows for managing GitHub Issues, PRs, and Labels via Markdown.
---

# GitHub Operations Skill

This skill provides a "ChatOps" layer for GitHub Project Management. It creates a bi-directional sync between a local markdown file (`ISSUES_BACKLOG.md`) and GitHub Issues, allowing you to manage your project entirely from your editor.

## Capability
- **Sync Issues**: Create/Update GitHub issues from a local Markdown file.
- **Label Management**: Standardized label set (infra, bug, feature, etc.) with consistent colors.
- **Workflows**: Slash commands for common operations (`/sync_issues`, `/pr`, `/deploy`).

## Installation
To enable this skill in a new project, run the following setup steps:

1.  **Copy Scripts**:
    - `cp .agent/skills/github_operations/scripts/* scripts/`
2.  **Copy Templates**:
    - `cp .agent/skills/github_operations/templates/ISSUES_BACKLOG.md docs/project_management/`
3.  **Copy Workflows**:
    - `cp .agent/skills/github_operations/workflows/* .agent/workflows/`
4.  **Install Dependencies**:
    - Ensure `gh` CLI is installed (`brew install gh`) and authenticated (`gh auth login`).
    - Python 3 with `requests` (optional, scripts currently use `subprocess`).

## Usage

### 1. Sync Issues
Edit `docs/project_management/ISSUES_BACKLOG.md`. Add a new section:
```markdown
## Feat: New Feature
**Title**: [Feat] Amazing New Thing
**Labels**: feature, ux
**Body**:
> Context...
```
Then run `/sync_issues` (or `python3 scripts/sync_issues.py`).

### 2. Standard Labels
Run `python3 scripts/setup_labels.py` to enforce the standard color scheme.

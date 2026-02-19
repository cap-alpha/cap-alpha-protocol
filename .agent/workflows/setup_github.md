---
description: Setup GitHub CLI and Project Management
---

# GitHub Setup Workflow

This workflow ensures that `gh` CLI is installed, authenticated with correct permissions, and ready to manage the project.

## 1. Safety Check (Install)
// turbo
```bash
if ! command -v gh &> /dev/null; then
    brew install gh
else
    echo "gh is already installed"
fi
```

## 2. Authentication (Critical Step)
**Context**: The default login often lacks `repo` scope for private repositories or issue creation.
**Action**: Run this command to authorize with full repo permissions.

```bash
gh auth login --hostname github.com -p https -w -s repo,project
```
*   Select `GitHub.com`
*   Select `HTTPS`
*   Select `Yes` to authenticate
*   **Copy the Code** and Authorize in Browser

## 3. Verify Status
// turbo
```bash
gh auth status
```

## 4. Initialize Project Board (Optional)
// turbo
```bash
# Check if issues exist, if not, create standard labels
gh label create "infrastructure" --color "000000" --description "Backend/DevOps Tasks" || true
gh label create "feature" --color "336699" --description "New Functionality" || true
gh label create "bug" --color "d73a4a" --description "Something isn't working" || true
```

## 5. Import Backlog (If `ISSUES_BACKLOG.md` exists)
If you have a backlog file, you can script the import:

```bash
# Example Script (Adjust titles as needed)
# gh issue create --title "[Infra] Provision Database" --body "..." --label "infrastructure"
```

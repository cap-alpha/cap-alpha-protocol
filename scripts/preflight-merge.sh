#!/usr/bin/env bash
# preflight-merge.sh — gate script that blocks gh-lars pr merge when CI is red or empty.
#
# Usage: scripts/preflight-merge.sh <pr-number>
#
# Exits 0 (pass) when all three conditions are met:
#   1. At least one CI check is registered (statusCheckRollup is non-empty)
#   2. No non-advisory check has conclusion == "FAILURE"
#      (PENDING / IN_PROGRESS checks have conclusion == "" — they are NOT failures)
#   3. At least one check matching lint|test|preflight|build|extraction is registered
#      and either has conclusion == "SUCCESS" or is still running (conclusion == "")
#      Running checks are allowed — the GitHub merge queue waits for them before landing
#
# Exits 1 (fail) with a specific blocker message otherwise.
#
# Advisory checks: check names containing "[advisory]" are exempt from failure blocking.
# They may fail without blocking the merge.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
    echo "Usage: $0 <pr-number>" >&2
    echo "" >&2
    echo "  Runs CI preflight checks before merging a PR." >&2
    echo "  Blocks merge if CI is empty, has non-advisory FAILUREs," >&2
    echo "  or lacks a real CI check (lint|test|preflight|build|extraction)." >&2
    exit 1
}

if [ $# -lt 1 ]; then
    usage
fi

PR_NUMBER="$1"

# Validate PR number is numeric
if ! [[ "$PR_NUMBER" =~ ^[0-9]+$ ]]; then
    echo "ERROR: PR number must be a positive integer, got: $PR_NUMBER" >&2
    exit 1
fi

# Fetch status check rollup via gh-lars (mints GitHub App token automatically)
ROLLUP_JSON=""
if ! ROLLUP_JSON="$("${SCRIPT_DIR}/gh-lars" pr view "$PR_NUMBER" --json statusCheckRollup 2>&1)"; then
    echo "ERROR: Failed to fetch PR #${PR_NUMBER} status checks." >&2
    echo "  $ROLLUP_JSON" >&2
    exit 1
fi

# Count total checks registered
TOTAL_CHECKS=$(echo "$ROLLUP_JSON" | jq '.statusCheckRollup | length')

# --- Gate 1: at least one check must be registered ---
if [ "$TOTAL_CHECKS" -eq 0 ]; then
    echo ""
    echo "✗ PR #${PR_NUMBER} — BLOCKED: No CI checks registered — cannot merge"
    echo ""
    echo "  statusCheckRollup is empty. This means CI has not started yet, or"
    echo "  the PR was created against a branch that has no workflow triggers."
    echo ""
    echo "  Wait for CI to register, or investigate why no checks are running."
    exit 1
fi

# --- Gate 2: no non-advisory FAILURE checks ---
FAILING_CHECKS=$(echo "$ROLLUP_JSON" | jq -r '
  .statusCheckRollup[]
  | select(.conclusion == "FAILURE" and (.name | test("\\[advisory\\]") | not))
  | .name
')

if [ -n "$FAILING_CHECKS" ]; then
    FAIL_COUNT=$(echo "$FAILING_CHECKS" | wc -l | tr -d ' ')
    echo ""
    echo "✗ PR #${PR_NUMBER} — BLOCKED: ${FAIL_COUNT} non-advisory CI check(s) FAILED"
    echo ""
    echo "  Failing checks:"
    echo "$FAILING_CHECKS" | while IFS= read -r name; do
        echo "    ✗ $name"
    done
    echo ""
    echo "  Fix these failures before merging, or escalate."
    echo "  (Checks with '[advisory]' in the name are exempt and were ignored.)"
    exit 1
fi

# --- Gate 3: at least one real CI check (lint|test|preflight|build|extraction) must be
#     registered and not have conclusively failed. Checks still running (IN_PROGRESS,
#     QUEUED, PENDING) are allowed through — the GitHub merge queue will wait for them.
#     We only block here when NO real CI check exists at all (only sanity/lightweight
#     checks registered), which means CI workflows didn't trigger properly.
#
#     Key distinction: use `conclusion` not `state`.
#       conclusion == ""  → check is still running (not yet conclusive)   → ALLOW
#       conclusion == "SUCCESS" | "SKIPPED"                               → ALLOW
#       conclusion == "FAILURE" | "CANCELLED" | "TIMED_OUT" | "STARTUP_FAILURE" → caught by Gate 2
# ---
REAL_CI_CHECKS=$(echo "$ROLLUP_JSON" | jq -r '
  .statusCheckRollup[]
  | select(.name | test("lint|test|preflight|build|extraction"; "i"))
  | .name
')

if [ -z "$REAL_CI_CHECKS" ]; then
    echo ""
    echo "✗ PR #${PR_NUMBER} — BLOCKED: No real CI check (lint|test|preflight|build|extraction) registered"
    echo ""
    echo "  Only pr_sanity.yml or similar lightweight checks appear to have run."
    echo "  Real CI (lint, test, preflight, build, or extraction) must be present before merging."
    exit 1
fi

# Check if any real CI checks are still running — these are fine for --auto queuing
REAL_CI_RUNNING=$(echo "$ROLLUP_JSON" | jq -r '
  .statusCheckRollup[]
  | select(
      (.name | test("lint|test|preflight|build|extraction"; "i"))
      and (.conclusion == "" or .conclusion == null)
    )
  | .name
')

REAL_CI_SUCCESS=$(echo "$ROLLUP_JSON" | jq -r '
  .statusCheckRollup[]
  | select(
      .conclusion == "SUCCESS"
      and (.name | test("lint|test|preflight|build|extraction"; "i"))
    )
  | .name
')

if [ -z "$REAL_CI_SUCCESS" ] && [ -z "$REAL_CI_RUNNING" ]; then
    echo ""
    echo "✗ PR #${PR_NUMBER} — BLOCKED: No real CI check (lint|test|preflight|build|extraction) passed"
    echo ""
    echo "  Real CI checks are registered but none succeeded or are running."
    echo "  Check if CI jobs were cancelled or skipped unexpectedly."
    exit 1
fi

if [ -n "$REAL_CI_RUNNING" ]; then
    RUNNING_COUNT=$(echo "$REAL_CI_RUNNING" | wc -l | tr -d ' ')
    # Still running is OK — GitHub merge queue will wait. Note it but don't block.
    echo ""
    echo "  Note: ${RUNNING_COUNT} real CI check(s) still running — --auto will queue and wait."
fi

# All gates passed — report success
ADVISORY_FAILURES=$(echo "$ROLLUP_JSON" | jq -r '
  .statusCheckRollup[]
  | select(.conclusion == "FAILURE" and (.name | test("\\[advisory\\]")))
  | .name
' | wc -l | tr -d ' ')

echo ""
echo "✓ PR #${PR_NUMBER} is clear to merge (${TOTAL_CHECKS} checks, 0 blocking failures)"

if [ "$ADVISORY_FAILURES" -gt 0 ]; then
    echo "  Note: ${ADVISORY_FAILURES} advisory check(s) failed — these are non-blocking."
fi

echo ""
exit 0

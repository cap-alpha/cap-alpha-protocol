#!/usr/bin/env bash
# preflight-merge.sh — gate script that blocks gh-lars pr merge when CI is red or empty.
#
# Usage: scripts/preflight-merge.sh <pr-number>
#
# Exits 0 (pass) when all three conditions are met:
#   1. At least one CI check is registered (statusCheckRollup is non-empty)
#   2. No non-advisory check has conclusion == "FAILURE"
#   3. At least one check matching lint|test|preflight|build|extraction has conclusion == "SUCCESS"
#      (proves real CI ran, not just pr_sanity.yml alone)
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

# --- Gate 3: at least one real CI check (lint|test|preflight|build|extraction) must be SUCCESS ---
REAL_CI_SUCCESS=$(echo "$ROLLUP_JSON" | jq -r '
  .statusCheckRollup[]
  | select(
      .conclusion == "SUCCESS"
      and (.name | test("lint|test|preflight|build|extraction"; "i"))
    )
  | .name
')

if [ -z "$REAL_CI_SUCCESS" ]; then
    # Also check if any such checks are still in progress (pending is not a failure)
    REAL_CI_PENDING=$(echo "$ROLLUP_JSON" | jq -r '
      .statusCheckRollup[]
      | select(
          .status == "IN_PROGRESS"
          and (.name | test("lint|test|preflight|build|extraction"; "i"))
        )
      | .name
    ')

    if [ -n "$REAL_CI_PENDING" ]; then
        PENDING_COUNT=$(echo "$REAL_CI_PENDING" | wc -l | tr -d ' ')
        echo ""
        echo "✗ PR #${PR_NUMBER} — BLOCKED: Real CI checks are still running (${PENDING_COUNT} pending)"
        echo ""
        echo "  Pending checks:"
        echo "$REAL_CI_PENDING" | while IFS= read -r name; do
            echo "    ⏳ $name"
        done
        echo ""
        echo "  Wait for these to complete before merging."
        exit 1
    fi

    echo ""
    echo "✗ PR #${PR_NUMBER} — BLOCKED: No real CI check (lint|test|preflight|build|extraction) passed"
    echo ""
    echo "  Only pr_sanity.yml or similar lightweight checks appear to have run."
    echo "  Real CI (lint, test, preflight, build, or extraction) must succeed before merging."
    exit 1
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

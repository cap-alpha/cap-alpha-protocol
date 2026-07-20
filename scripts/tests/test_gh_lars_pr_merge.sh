#!/usr/bin/env bash
# test_gh_lars_pr_merge.sh — regression test for issue #1079.
#
# #1079 reported that `scripts/gh-lars pr merge <n> --rebase --auto` could
# silently exit after the preflight gate without ever invoking `gh pr merge`,
# so auto-merge never got armed even though the wrapper printed a "clear to
# merge" success message.
#
# This test runs the REAL scripts/gh-lars + scripts/preflight-merge.sh from
# this checkout inside an isolated sandbox with a stubbed `gh` binary and a
# stubbed gh-app-token.sh, so it makes no network calls and touches no real
# GitHub state. It asserts, for each preflight outcome, exactly which `gh`
# invocations the wrapper actually made.
#
# Usage: scripts/tests/test_gh_lars_pr_merge.sh
# Exit 0 = all assertions passed. Exit 1 = a regression was detected.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SANDBOX="$(mktemp -d)"
trap 'rm -rf "$SANDBOX"' EXIT

FAILURES=0

fail() {
    echo "FAIL: $1" >&2
    FAILURES=$((FAILURES + 1))
}

pass() {
    echo "PASS: $1"
}

# --- sandbox setup -----------------------------------------------------
mkdir -p "$SANDBOX/scripts" "$SANDBOX/bin"
cp "$REPO_ROOT/scripts/gh-lars" "$SANDBOX/scripts/gh-lars"
cp "$REPO_ROOT/scripts/preflight-merge.sh" "$SANDBOX/scripts/preflight-merge.sh"
chmod +x "$SANDBOX/scripts/gh-lars" "$SANDBOX/scripts/preflight-merge.sh"

# Stub gh-app-token.sh — no real network/PEM required for the test.
cat > "$SANDBOX/scripts/gh-app-token.sh" <<'EOF'
#!/usr/bin/env bash
echo "test-token-not-real"
EOF
chmod +x "$SANDBOX/scripts/gh-app-token.sh"

CALL_LOG="$SANDBOX/gh_calls.log"

# write_gh_stub <rollup-json> — installs a fake `gh` on PATH that logs every
# invocation to CALL_LOG and answers `pr view ... --json statusCheckRollup`
# with the given rollup JSON body.
write_gh_stub() {
    local rollup_json="$1"
    cat > "$SANDBOX/bin/gh" <<EOF_OUTER
#!/usr/bin/env bash
echo "\$*" >> "$CALL_LOG"
if [[ "\$1 \$2" == "pr view" ]]; then
  cat <<'EOF_JSON'
$rollup_json
EOF_JSON
  exit 0
fi
exit 0
EOF_OUTER
    chmod +x "$SANDBOX/bin/gh"
}

run_gh_lars() {
    : > "$CALL_LOG"
    PATH="$SANDBOX/bin:$PATH" GH_APP_ID=1 GH_INSTALLATION_ID=1 \
        "$SANDBOX/scripts/gh-lars" "$@" > "$SANDBOX/last_stdout.log" 2> "$SANDBOX/last_stderr.log"
    echo $?
}

merge_calls() {
    grep -c '^pr merge ' "$CALL_LOG" || true
}

# =========================================================================
# Case 1: all CI green — gh-lars must actually invoke `gh pr merge <n> ...`
# =========================================================================
write_gh_stub '{"statusCheckRollup":[{"name":"test","conclusion":"SUCCESS"},{"name":"lint","conclusion":"SUCCESS"}]}'
EXIT_CODE=$(run_gh_lars pr merge 999 --rebase --auto)

if [[ "$EXIT_CODE" != "0" ]]; then
    fail "case 1 (green CI): expected exit 0, got $EXIT_CODE. stderr: $(cat "$SANDBOX/last_stderr.log")"
elif [[ "$(merge_calls)" != "1" ]]; then
    fail "case 1 (green CI): expected exactly 1 'gh pr merge' invocation, got $(merge_calls). Full call log: $(cat "$CALL_LOG")"
elif ! grep -q '^pr merge 999 --rebase --auto$' "$CALL_LOG"; then
    fail "case 1 (green CI): 'gh pr merge' was not called with the expected args. Full call log: $(cat "$CALL_LOG")"
else
    pass "case 1: green CI -> gh-lars pr merge forwards to 'gh pr merge 999 --rebase --auto'"
fi

# =========================================================================
# Case 2: a non-advisory FAILURE check — gh-lars must NOT invoke `gh pr merge`
# and must exit non-zero.
# =========================================================================
write_gh_stub '{"statusCheckRollup":[{"name":"test","conclusion":"FAILURE"},{"name":"lint","conclusion":"SUCCESS"}]}'
EXIT_CODE=$(run_gh_lars pr merge 999 --rebase --auto)

if [[ "$EXIT_CODE" == "0" ]]; then
    fail "case 2 (red CI): expected non-zero exit, got 0 — preflight failure must block the merge"
elif [[ "$(merge_calls)" != "0" ]]; then
    fail "case 2 (red CI): 'gh pr merge' was invoked despite failing CI — this is the #1079 regression in reverse (merge slips through a red gate). Full call log: $(cat "$CALL_LOG")"
else
    pass "case 2: red CI -> gh-lars pr merge blocks with exit $EXIT_CODE and never calls 'gh pr merge'"
fi

# =========================================================================
# Case 3: --force-merge-bypass-preflight — must skip preflight and still
# forward to `gh pr merge` with the bypass flag stripped.
# =========================================================================
write_gh_stub '{"statusCheckRollup":[{"name":"test","conclusion":"FAILURE"}]}'
EXIT_CODE=$(run_gh_lars pr merge 999 --rebase --auto --force-merge-bypass-preflight)

if [[ "$EXIT_CODE" != "0" ]]; then
    fail "case 3 (bypass): expected exit 0, got $EXIT_CODE. stderr: $(cat "$SANDBOX/last_stderr.log")"
elif [[ "$(merge_calls)" != "1" ]]; then
    fail "case 3 (bypass): expected exactly 1 'gh pr merge' invocation, got $(merge_calls). Full call log: $(cat "$CALL_LOG")"
elif ! grep -q '^pr merge 999 --rebase --auto$' "$CALL_LOG"; then
    fail "case 3 (bypass): bypass flag was not stripped before forwarding to gh. Full call log: $(cat "$CALL_LOG")"
else
    pass "case 3: --force-merge-bypass-preflight skips preflight and forwards to 'gh pr merge 999 --rebase --auto'"
fi

# =========================================================================
echo ""
if [[ "$FAILURES" -gt 0 ]]; then
    echo "gh-lars pr-merge regression test: $FAILURES assertion(s) FAILED" >&2
    exit 1
fi
echo "gh-lars pr-merge regression test: all assertions passed"
exit 0

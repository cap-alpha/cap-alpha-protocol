#!/usr/bin/env bash
# gh-app-token.sh — Mint or reuse a GitHub App installation token.
#
# Auth identity: the `nfl-dead-money-triage` GitHub App, owned by `ucalegon206`,
# installed on `cap-alpha/cap-alpha-protocol`. Installation tokens last 1 hour
# and are cached at $CACHE_FILE; we refresh when <5 min remain.
#
# Output: the installation token on stdout (single line, no trailing newline-only output).
# Errors: write to stderr with non-zero exit.
#
# Override defaults via env: GH_APP_ID, GH_INSTALLATION_ID, GH_APP_PEM.

set -euo pipefail

APP_ID="${GH_APP_ID:-3545386}"
INSTALLATION_ID="${GH_INSTALLATION_ID:-128138694}"
PEM_PATH="${GH_APP_PEM:-${HOME}/.ghconfig/triage-app.pem}"
CACHE_DIR="${HOME}/.cache/nfl-dead-money"
CACHE_FILE="${CACHE_DIR}/gh-app-token.json"

if [[ ! -f "$PEM_PATH" ]]; then
    echo "gh-app-token: private key not found at $PEM_PATH" >&2
    echo "  Set GH_APP_PEM env var or place the App's .pem at the default path." >&2
    exit 1
fi

mkdir -p "$CACHE_DIR"

# Try cache first.
if [[ -f "$CACHE_FILE" ]]; then
    cached_token=$(python3 - "$CACHE_FILE" <<'PYEOF' 2>/dev/null || true
import json, sys
from datetime import datetime, timezone
cache_file = sys.argv[1]
try:
    d = json.load(open(cache_file))
    exp = datetime.fromisoformat(d["expires_at"].replace("Z", "+00:00"))
    if (exp - datetime.now(timezone.utc)).total_seconds() > 300:
        print(d["token"])
except Exception:
    pass
PYEOF
    )
    if [[ -n "${cached_token:-}" ]]; then
        printf '%s' "$cached_token"
        exit 0
    fi
fi

# Cache miss or stale — mint a fresh JWT, exchange for an installation token.

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

header_b64=$(printf '{"typ":"JWT","alg":"RS256"}' | b64url)
iat=$(date -u +%s)
exp=$(( iat + 540 ))   # 9 min — GitHub caps at 10
payload_b64=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$iat" "$exp" "$APP_ID" | b64url)
signing_input="${header_b64}.${payload_b64}"
sig_b64=$(printf '%s' "$signing_input" | openssl dgst -sha256 -sign "$PEM_PATH" -binary | b64url)
jwt="${signing_input}.${sig_b64}"

response=$(curl -sf -X POST \
    -H "Authorization: Bearer $jwt" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/app/installations/${INSTALLATION_ID}/access_tokens") || {
    echo "gh-app-token: failed to exchange JWT for installation token (App ID $APP_ID, install $INSTALLATION_ID)" >&2
    exit 1
}

python3 - "$response" "$CACHE_FILE" <<'PYEOF'
import json, os, sys
response_str, cache_file = sys.argv[1], sys.argv[2]
d = json.loads(response_str)
with open(cache_file, "w") as f:
    json.dump({"token": d["token"], "expires_at": d["expires_at"]}, f)
os.chmod(cache_file, 0o600)
sys.stdout.write(d["token"])
PYEOF

#!/usr/bin/env bash
# gh-app-token.sh — Mint or reuse a GitHub App installation token.
#
# Required env vars (no defaults — set in .env.personas):
#   GH_APP_ID           — numeric GitHub App ID
#   GH_INSTALLATION_ID  — numeric installation ID (find via: gh api /app/installations)
#
# Optional env var:
#   GH_APP_PEM          — path to RSA private key (default: ~/.ghconfig/triage-app.pem)
#
# Installation tokens last 1 hour and are cached at $CACHE_FILE; we refresh
# when <5 min remain.
#
# Output: the installation token on stdout (single line, no trailing newline).
# Errors: written to stderr with non-zero exit.

set -euo pipefail

if [[ -z "${GH_APP_ID:-}" ]]; then
    echo "gh-app-token: GH_APP_ID must be set (numeric GitHub App ID)." >&2
    echo "  Set it in .env.personas or export GH_APP_ID." >&2
    exit 1
fi
APP_ID="$GH_APP_ID"

if ! [[ "$APP_ID" =~ ^[0-9]+$ ]]; then
    echo "gh-app-token: GH_APP_ID must be numeric, got: $APP_ID" >&2
    exit 1
fi

if [[ -z "${GH_INSTALLATION_ID:-}" ]]; then
    echo "gh-app-token: GH_INSTALLATION_ID must be set (numeric installation ID)." >&2
    echo "  Set it in .env.personas or export GH_INSTALLATION_ID." >&2
    exit 1
fi
if ! [[ "$GH_INSTALLATION_ID" =~ ^[0-9]+$ ]]; then
    echo "gh-app-token: GH_INSTALLATION_ID must be numeric, got: $GH_INSTALLATION_ID" >&2
    exit 1
fi
INSTALLATION_ID="${GH_INSTALLATION_ID}"

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
# iss must be a numeric claim per GitHub App JWT spec — no quotes around APP_ID.
payload_b64=$(printf '{"iat":%d,"exp":%d,"iss":%d}' "$iat" "$exp" "$APP_ID" | b64url)
signing_input="${header_b64}.${payload_b64}"
sig_b64=$(printf '%s' "$signing_input" | openssl dgst -sha256 -sign "$PEM_PATH" -binary | b64url)
jwt="${signing_input}.${sig_b64}"

response_file=$(mktemp)
curl_config_file=$(mktemp)
chmod 600 "$curl_config_file"
cat >"$curl_config_file" <<EOF
url = "https://api.github.com/app/installations/${INSTALLATION_ID}/access_tokens"
header = "Authorization: Bearer $jwt"
header = "Accept: application/vnd.github+json"
header = "X-GitHub-Api-Version: 2022-11-28"
EOF
http_status=$(curl -sS --config "$curl_config_file" -X POST \
    -o "$response_file" \
    -w '%{http_code}') || {
    rm -f "$response_file" "$curl_config_file"
    echo "gh-app-token: curl failed when exchanging JWT for installation token (App ID $APP_ID, install $INSTALLATION_ID)" >&2
    exit 1
}
rm -f "$curl_config_file"

response=$(cat "$response_file")
if [[ ! "$http_status" =~ ^2 ]]; then
    echo "gh-app-token: failed to exchange JWT for installation token (App ID $APP_ID, install $INSTALLATION_ID, HTTP $http_status)" >&2
    if [[ -n "$response" ]]; then
        printf '%s\n' "$response" >&2
    fi
    rm -f "$response_file"
    exit 1
fi
rm -f "$response_file"

python3 - "$response" "$CACHE_FILE" <<'PYEOF'
import json, os, sys, tempfile
response_str, cache_file = sys.argv[1], sys.argv[2]
d = json.loads(response_str)
cache_dir = os.path.dirname(cache_file) or "."
os.makedirs(cache_dir, exist_ok=True)
fd, temp_cache_file = tempfile.mkstemp(dir=cache_dir)
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump({"token": d["token"], "expires_at": d["expires_at"]}, f)
    os.replace(temp_cache_file, cache_file)
except Exception:
    try:
        os.unlink(temp_cache_file)
    except FileNotFoundError:
        pass
    raise
sys.stdout.write(d["token"])
PYEOF

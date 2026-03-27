#!/bin/bash

echo "========================================================"
echo "    CAP ALPHA PROTOCOL - MANUAL ADVERSARIAL SWEEP"
echo "========================================================"
echo "This script allows the human operator to manually verify"
echo "API defenses against raw injection without a browser UI."
echo "Ensure the Next.js server is running on localhost:3000."
echo "========================================================"

BASE_URL="http://localhost:3000"

echo "[1/4] Testing SSR Leakage - Invalid Database Parameter (SQLi / Type Bypassing)"
curl -s -o /dev/null -w "%{http_code}\n" "${BASE_URL}/player/1=1;%20DROP%20TABLE%20players"

echo "[2/4] Testing Authenticated Directory Access without JWT (Expected 401/403/Redirect)"
curl -s -o /dev/null -w "%{http_code}\n" "${BASE_URL}/dashboard/gm"

echo "[3/4] Testing Edge API Cache Injection"
curl -s -o /dev/null -w "%{http_code}\n" "${BASE_URL}/api/search-index?cache_poison=true"

echo "[4/4] Testing Malformed Next.js Action Payloads"
# Next.js Server Actions enforce strictly signed action IDs. This asserts it drops it safely.
curl -s -X POST "${BASE_URL}/" \
    -H "Next-Action: foo-bar-baz" \
    -H "Content-Type: text/plain;charset=UTF-8" \
    -d "[]" -o /dev/null -w "%{http_code}\n"

echo "========================================================"
echo "Done."

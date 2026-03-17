#!/bin/bash

# Sprint 9: Persona Architecture Verification
# Verifies that the new Dashboard namespaces resolve correctly and serve their respective content.

set -e

BASE_URL="http://localhost:3000"

echo "Running Verification Tests for Persona Routing Architecture..."

# 1. Verify GM Dashboard
echo "\nTesting: $BASE_URL/dashboard/gm"
GM_RES=$(curl -s "$BASE_URL/dashboard/gm")
if echo "$GM_RES" | grep -q "Front Office"; then
    echo "✅ PASS: GM Dashboard mounted successfully."
else
    echo "❌ FAIL: GM Dashboard did not mount."
    exit 1
fi

# 2. Verify Agent Dashboard
echo "\nTesting: $BASE_URL/dashboard/agent"
AGENT_RES=$(curl -s "$BASE_URL/dashboard/agent")
if echo "$AGENT_RES" | grep -q "Surplus Value Leaderboard"; then
    echo "✅ PASS: Agent Dashboard mounted successfully."
else
    echo "❌ FAIL: Agent Dashboard did not mount."
    exit 1
fi

# 3. Verify Fan Dashboard
echo "\nTesting: $BASE_URL/dashboard/fan"
FAN_RES=$(curl -s "$BASE_URL/dashboard/fan")
if echo "$FAN_RES" | grep -q "Franchise Power Rankings"; then
    echo "✅ PASS: Fan Dashboard mounted successfully."
else
    echo "❌ FAIL: Fan Dashboard did not mount."
    exit 1
fi

# 4. Verify Sharp Dashboard
echo "\nTesting: $BASE_URL/dashboard/bettor"
BETTOR_RES=$(curl -s "$BASE_URL/dashboard/bettor")
if echo "$BETTOR_RES" | grep -q "Consensus Lead Time"; then
    echo "✅ PASS: Sharp Dashboard mounted successfully."
else
    echo "❌ FAIL: Sharp Dashboard did not mount."
    exit 1
fi

echo "\n🏆 ALL SPRINT 9 ROUTING VERIFICATION TESTS PASSED."
exit 0

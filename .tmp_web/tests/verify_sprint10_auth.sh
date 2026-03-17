#!/bin/bash

# verify_sprint10_auth.sh
# Validates the Clerk `middleware.ts` RBAC rules by testing raw HTTP Route Responses
# Asserting that Pro limits are sealed, and Freemium limits are open.

BASE_URL="http://localhost:3000"
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "====================================="
echo "Testing Sprint 10 Auth Router Headers"
echo "====================================="

verify_route() {
    ENDPOINT=$1
    EXPECTED_STATUS=$2
    
    echo -n "Testing $ENDPOINT... "
    
    # Extract just the HTTP status code
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X GET "$BASE_URL$ENDPOINT")
    
    if [ "$STATUS" == "$EXPECTED_STATUS" ]; then
        echo -e "${GREEN}PASS (HTTP $STATUS)${NC}"
    else
        echo -e "${RED}FAIL (Expected $EXPECTED_STATUS, got $STATUS)${NC}"
    fi
}

# 1. Freemium Routes (Must be 200 OK)
verify_route "/" "200"
verify_route "/dashboard/fan" "200"

# 2. Pro Routes (Must be 307 Temporary Redirect to Clerk Sign-In)
verify_route "/dashboard/gm" "307"
verify_route "/dashboard/agent" "307"
verify_route "/dashboard/bettor" "307"
verify_route "/scenarios" "307"

echo "====================================="

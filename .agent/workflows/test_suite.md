---
description: Run Comprehensive Test Suite (Unit + E2E)
---

1. Run Unit Tests via Jest/Vitest
// turbo
2. docker compose run --rm web npm run test --if-present

3. Run E2E Tests via Playwright
// turbo
4. make test-e2e

## 5. Daily Gemini Data Discrepancy Audit (UAT Validation)
When running tests, particularly User Acceptance Testing (UAT):
- **ALWAYS use Gemini (`search_web` Tool)** to look up at least 2-3 players who had breaking NFL news *that specific day*.
- Manually run verification scripts (or UI queries) against our internal BigQuery database for those exact players.
- **Cross-Reference:** Ensure that the stats, contract details, and news feeds in our database perfectly mirror the facts reported on external reference sites (e.g., ESPN, NFL.com, Spotrac, PFR) retrieved by the Gemini web search.
- **Objective:** Determine if any data dimensions are missing from our Gold layer, and construct explicit engineering plans to ingest the missing vectors if discrepancies are found.

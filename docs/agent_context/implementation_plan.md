# Structural Architecture Update (Permanent Fix)

## 0. Global Design Constraints
> [!IMPORTANT]
> **BigQuery-Only Architecture:** The platform's entire telemetry and production data layer is strictly bound to Google BigQuery (`my-project-1525668581184`). We DO NOT execute local pipeline SQL files or query `duckdb`/`.db` files for the web application's states. All analytical UI states and fallbacks must be hydrated purely through BigQuery SDK queries.

## 1. The "Joe Flacco" Class Problem
The reason Joe Flacco's latest 2026 data did not appear despite him signing this morning is due to a structural flaw in `web/app/actions.ts`. 

Previously, the query hardcoded `WHERE year = 2025` to avoid hitting empty pre-season 2026 pipelines for players who hadn't signed. However, this brutally truncated players who *did* have new elite 2026 tracking data.

### [MODIFY] `web/app/actions.ts`
We will rewrite the BigQuery string to utilize a Window Function (`ROW_NUMBER() OVER(PARTITION BY player_name ORDER BY year DESC)`). 
- **The Result:** Instead of hardcoding a global year, BigQuery will automatically group every player and **only return their absolute most recent active contract**. 
- If a player was traded in 2026, it grabs 2026. If a player retired in 2024, it grabs 2024. This permanently resolves the desync for the entire league effortlessly.

## 2. Dev-Environment Timeout Hardening
The `500` error thrown after leaving `npm run dev` idle is caused by the connection pool closing silently in Next.js Hot Module Reloading (HMR), causing the active `fetchHydratedDataFromDb` cache to hang when regenerating.

### [MODIFY] `web/app/actions.ts`
- Implement explicit `timeoutMs: 10000` (10 second) cutoffs within the `@google-cloud/bigquery` `createQueryJob` parameters.
- Add try/catch bounds that return proper generic 404s instead of lethal 500 Application Error boundaries if the DB socket disconnects or hangs, gracefully failing the UI for the user.

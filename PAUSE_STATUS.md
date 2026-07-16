# Project Paused — 2026-07-16

All active work on `nfl-dead-money` / Pundit Prediction Ledger is paused as
of 2026-07-16. Code is preserved. Money-burning services are stopped.

## What was done at pause

### Automated (via Claude Code session)
- **Vercel** — `cap-alpha.co` alias removed from `app` project (site returns 404;
  bandwidth billing zero). Vercel project itself intact, deployments preserved.
- **GCP** — billing account unlinked from `cap-alpha-protocol` project
  (`gcloud billing projects unlink cap-alpha-protocol`). All billable services
  paused (BigQuery queries, Cloud Scheduler, Cloud Build, etc.). Data preserved
  at least through the GCP grace period.
- **GitHub Actions scheduled workflows** — 9 workflows had their `schedule:`
  triggers commented out in this PR. `workflow_dispatch:` (manual trigger)
  remains available. Reverting this PR fully restores all schedules.
- **Vercel crons** — 2 daily cron entries removed from `web/vercel.json`
  (`onboarding-emails`, `resolution-notifications`).

### Manual (owner must complete)

| # | Service | Link | Action |
|---|---|---|---|
| 1 | Anthropic | https://console.anthropic.com/settings/keys | Revoke the `ANTHROPIC_API_KEY` used by CI. Under Billing → disable auto-refill if set. |
| 2 | Google AI Studio | https://aistudio.google.com/apikey | Disable/delete the Gemini API key used for extraction (separate purse from GCP billing). |
| 3 | Clerk | https://dashboard.clerk.com/ | Find the `cap-alpha` app → Settings → downgrade to free (or delete). |
| 4 | Sentry | https://sentry.io/settings/ | Find the cap-alpha project → Settings → **Disable ingestion**. Stops event billing immediately. |
| 5 | Stripe | https://dashboard.stripe.com/settings/account | If in live mode: pause payouts / disable API keys. If test mode only: nothing to do. |

## What was preserved

- Full git history and all branches
- BigQuery datasets and tables (via project preservation; grace period applies)
- Vercel project + deployment history (only the `cap-alpha.co` alias was removed)
- All secrets (GitHub Actions, Vercel env vars)
- Local worktrees and `.venv/`

## To resume the project

1. Re-link GCP billing: `gcloud billing projects link cap-alpha-protocol --billing-account=<ID>`.
2. Re-alias Vercel: `vercel alias set <deployment-url> cap-alpha.co`.
3. Revert this PR to restore all 9 scheduled workflows and 2 Vercel crons.
4. Re-issue Anthropic + Gemini API keys; store in `ANTHROPIC_API_KEY` (repo
   secret) and the appropriate Gemini env var.
5. Re-enable Clerk / Sentry / Stripe as needed.

## Ownership

Paused by request of Andrew Smith (owner) during a Claude Code session on
2026-07-16. Reason: pausing all payments while decisions about the product
direction are made.

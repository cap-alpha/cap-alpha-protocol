# GitHub Issues Backlog

Use this file to populate your Kanban board (Project/Issues) on GitHub.

## Infra: Database Setup (Vercel Postgres)
**Title**: [Infra] Provision Vercel Postgres and Integrate with Next.js
**Labels**: infrastructure, backend, critical-path
**Body**:
> **Context**:
> We need a persistent storage layer for User Data (Scenarios, Saved Teams). DuckDB is transient in serverless environments.
>
> **Acceptance Criteria**:
> - [ ] Create a Vercel Postgres Database (Neon) via Vercel Dashboard.
> - [ ] Link the project to the database (`vercel link`).
> - [ ] Verify connection string `POSTGRES_URL` is available in Vercel Environment variables.
> - [ ] Update `next.config.js` if necessary for edge runtime compatibility.

## Infra: ORM Integration (Drizzle)
**Title**: [Infra] Install and Configure Drizzle ORM
**Labels**: infrastructure, backend, developer-experience
**Body**:
> **Context**:
> To interact with Postgres safely and with full TypeScript support, we will use Drizzle ORM.
>
> **Acceptance Criteria**:
> - [ ] Install `drizzle-orm` and `drizzle-kit`.
> - [ ] Create `drizzle.config.ts`.
> - [ ] Create initial `schema.ts` defining the `users` and `user_scenarios` tables.
> - [ ] Run initial migration (`drizzle-kit push` or `generate`).
> - [ ] Create a `db/index.ts` utility for easy imports.

## Feat: User Data Sync
**Title**: [Feat] Sync Clerk User/Organization Events to Postgres
**Labels**: feature, authentication, backend
**Body**:
> **Context**:
> We need to mirror Clerk user data in our database for relational integrity (User -> Scenarios).
>
> **Acceptance Criteria**:
> - [ ] Create API Route `/api/webhooks/clerk`.
> - [ ] Validate Clerk Webhook Signature (Security).
> - [ ] Handle `user.created` event: Insert row into `users` table.
> - [ ] Handle `user.updated` and `user.deleted` events.

## Feat: Save Scenarios
**Title**: [Feat] Save "Cut Scenarios" to User Profile
**Labels**: feature, product, monetization
**Body**:
> **Context**:
> Allows users to save their "Cut Calculator" results for later review. "Armchair GMs" want to build a portfolio of decisions.
>
> **Acceptance Criteria**:
> - [ ] Create API Route `POST /api/scenarios`.
> - [ ] Create Server Action `saveScenario(playerId, cutType, savings)`.
> - [ ] UI: "Save Scenario" button on Cut Calculator (mocked currently, needs implementation).
> - [ ] UI: "My Scenarios" Dashboard page.

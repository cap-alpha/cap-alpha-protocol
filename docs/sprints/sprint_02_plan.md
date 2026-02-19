# Sprint 2 Implementation Plan: The Persistence Layer

**Goal**: Enable "Casual Carl" to save his work.
**Stack**: Vercel Postgres (Neon) + Drizzle ORM + Clerk.

## 🛠 Step 1: Database Provisioning (User Action)
**Why**: We need a place to store data.
**Action**:
1.  Go to Vercel Dashboard -> Project -> Storage.
2.  Click "Create Database" -> "Postgres".
3.  Select Region (US East - N. Virginia).
4.  Accept Defaults.
5.  **Critical**: Go to "Environment Variables" and verify `POSTGRES_URL` is added to Development.
6.  **Pull**: Run `vercel env pull .env.local` to get the keys locally.

## 🛠 Step 2: Schema Design (Drizzle)
**Why**: Type-safety over raw SQL.
**Tables**:
*   `users`: Sync from Clerk (clerk_id, email, subscription_tier).
*   `scenarios`: The "save file".
    *   `id`: UUID
    *   `user_id`: FK to users.
    *   `name`: "Dak Cut 2026"
    *   `roster_state`: JSONB (The full roster snapshot).
    *   `created_at`: Timestamp.

## 🛠 Step 3: API Layer
**Why**: Secure access.
*   `POST /api/webhooks/clerk`: Sync user creation.
*   `POST /api/scenarios`: Save current state.
*   `GET /api/scenarios`: List saved states.

## 🛠 Step 4: UI Integration
**Why**: The User "Feature".
*   Add "Save Scenario" button to `CutCalculator`.
*   Add "My Scenarios" page to `PlayerDetailView` (or new profile page).

# ADR-001: Storage Stack Selection

**Date**: 2026-02-18
**Status**: Accepted
**Author**: Engineering Team (Agency)

## Context
We need to transition from a "stateless" calculator to a "stateful" platform where users can save roster scenarios.
*   **Persona**: Casual Carl needs to save his "Dak Cut".
*   **Scale**: Expecting spikes during NFL Drop events (Free Agency).
*   **Environment**: Next.js (Serverless) on Vercel.

## Decision
We will use **Vercel Postgres (Neon)** as the database and **Drizzle ORM** as the access layer.

### 1. Database: Vercel Postgres (Managed Neon)
*   ✅ **Pros**:
    *   **Serverless Native**: Scales to zero (Cost effective for early stage).
    *   **Integrated**: One-click provision in Vercel Dashboard.
    *   **Branching**: Supports database branching for preview deployments (future proofing).
*   ❌ **Cons**:
    *   **Vendor Lock-in**: Tightly coupled to Vercel ecosystem (though underlying is standard Postgres).

### 2. ORM: Drizzle
*   ✅ **Pros**:
    *   **Performance**: Zero runtime overhead (unlike Prisma).
    *   **Cold Starts**: Critical for serverless functions (lambda).
    *   **Type Safety**: TypeScript-first.
*   ❌ **Cons**:
    *   **Maturity**: Newer than Prisma, smaller community.

## Consequences
*   We must manage migrations via `drizzle-kit`.
*   We are committed to the Vercel ecosystem for the near term.
*   We enable "Milestone 2" (Monetization) by gating database writes.

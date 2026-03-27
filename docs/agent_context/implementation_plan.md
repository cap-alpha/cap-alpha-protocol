# Sprint 20-1: Edge Caching & SSG Execution Plan

## 0. Global Design Constraints
> [!IMPORTANT]
> **Performance SLA:** Every page load across the entire web application must resolve in under 1.0s to deliver an elite, lightning-fast executive UX.

## 1. Static Asset & Directory SSG
- The `web/app/` directories will be audited to identify forced server-side rendering (SSR) loops that DO NOT require per-request live hydration.
- The Global Search Index component (`web/components/global-search.tsx`) will be optimized with edge caching to prevent redundant execution.
- Next.js static generation techniques (e.g. `generateStaticParams`, `revalidate`) will be applied to team and static directory routes.

## 2. Testing Constraints (No Mocks)
- As governed by the `/ci` workflow, we will ensure that modifications to data fetching hooks maintain 100% test coverage without using mocked UI state. We will rely firmly on the e2e Playwright container execution.

## 3. Status
- Drafted for multi-agent handoff initialization.

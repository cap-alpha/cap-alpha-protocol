## NEXUS Handoff Document

### Metadata
- **From**: The Product Architect / Studio Producer
- **To**: Frontend Developers & UX Architect
- **Phase**: Phase 3 — Build & Iterate
- **Task Reference**: Sprint 9 (Persona-Driven Architecture Overhaul)
- **Priority**: Critical
- **Timestamp**: 2026-03-14T16:56:00-07:00

### Context
- **Project**: Cap Alpha Protocol — Persona Transition
- **Current State**: The global `/dashboard/page.tsx` exists but suffers from "one size fits none." The decision has been made to split the application into 4 distinct, persona-tailored experiences (GM, Agent, Quant, Fan).
- **Relevant Files**: 
  - `web/app/page.tsx`
  - `web/components/proof-of-alpha-carousel.tsx` (reference for interactive component)
- **Dependencies**: Next.js App Router.

### Deliverable Request
- **What is needed**: 
  1. Delete the global `/dashboard/page.tsx`.
  2. Implement an interactive `PersonaShowcase` component on the root landing page (`/`) that allows users to toggle between the 4 personas, displaying custom marketing copy and "Proof of Alpha" receipts for each.
  3. Scaffold the 4 isolated routing namespaces (`/dashboard/gm`, `/dashboard/agent`, `/dashboard/fan`, `/dashboard/bettor`).
- **Acceptance criteria**: 
  - The landing page must dynamically highlight value propositions for all 4 personas without reloading.
  - Clicking the CTA within a persona view must route the user to that specific dashboard.
- **Constraints**: No database modifications required. Re-use existing `getHydratedData` logic. 
- **Reference materials**: Product Council SKILL documentation defining the 4 personas.

### Quality Expectations
- **Must pass**: "10-Foot Design Review" for the new dashboards. They must be instantly recognizable and optimized for their specific "Job to be Done".
- **Evidence required**: Visual screenshots of the `PersonaShowcase` and all 4 dashboard landing states.
- **Handoff to next**: Reality Checker (QA Phase 4) for Integration Testing.

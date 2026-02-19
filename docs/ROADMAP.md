# Product Roadmap: Cap Alpha Protocol

# Product Roadmap: Cap Alpha Protocol

## 🎯 Strategic Vision
To build the "Bloomberg Terminal" for NFL Salary Cap management, enabling users to analyze, simulate, and predict roster value with institutional-grade precision.

> **Process Note**: We follow the [Sprint Rituals](process/SPRINT_RITUALS.md) cycle:
> 1.  User Persona Test (UAT)
> 2.  Expert Council Audit
> 3.  Prioritization Vote

---

## 🚦 Phase 1: Foundation (Q1 2026)
**Theme**: "Data Integrity & Visualization"
- [x] **Core Pipeline**: Medallion Architecture (Bronze/Silver/Gold) for Roster Data.
- [x] **Data Visualization**: Interactive Data Grid with Sorting/Filtering.
- [x] **Visual Analytics**: "Value Trajectory" Charts (Actual vs Predicted).
- [x] **Mobile Responsiveness**: Adaptive layouts for Phones/Tablets.

## 🚀 Phase 2: The "Hook" (Current Status)
**Theme**: "Monetization & Engagement" (The "Armchair GM" conversion)
- [x] **Cut Calculator**: Pre/Post June 1 Logic ("The Guillotine").
- [x] **Position Benchmarking**: Histogram Distribution (Context Engine).
- [x] **Authentication**: Clerk Integration for User Accounts.
- [x] **Role-Based UI**: Mock "Paywall" for Advanced Metrics.

---

## 🏗️ Phase 3: Infrastructure Hardening (Next Sprint)
**Theme**: "Persistence & Scale"
- [ ] **Data Persistence**: Migrate User Data (Scenarios, Saved Cuts) to **Vercel Postgres**.
- [ ] **ORM Layer**: Implement **Drizzle ORM** for type-safe database interactions.
- [ ] **Sync Engine**: Clerk Webhooks -> Postgres synchronization.

## 🧪 Phase 4: Advanced Simulation (Future)
**Theme**: "The War Room"
- [ ] **Trade Machine**: Multi-Team Trade Simulator with Dead Cap logic.
- [ ] **Scenario Saving**: "Save this Roster" feature for GMs.
- [ ] **Team Builder**: Drag-and-drop Roster Construction.
- [ ] **Export Engine**: PDF/CSV Reports for "Front Office" presentations.

## 📊 Feature Status Matrix

| Feature | Status | Priority | Owner |
| :--- | :--- | :---: | :--- |
| **Roster Grid** | 🟢 Live | P0 | Engineering |
| **Cut Calculator** | 🟢 Live | P0 | Product |
| **Benchmarking** | 🟢 Live | P1 | Data Science |
| **User Accounts** | 🟡 Partial | P1 | Engineering |
| **Save Scenarios** | 🔴 Backlog | P2 | Product |
| **Trade Machine** | 🔴 Backlog | P3 | Strategy |

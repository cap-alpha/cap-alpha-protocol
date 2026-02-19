# Product Roadmap: Cap Alpha Protocol

# Product Roadmap: Cap Alpha Protocol

## 🎯 Strategic Vision
To build the "Bloomberg Terminal" for NFL Salary Cap management, enabling users to analyze, simulate, and predict roster value with institutional-grade precision.

> **Process Note**: We follow the [Sprint Rituals](process/SPRINT_RITUALS.md) cycle:
> 1.  User Persona Test (UAT)
> 2.  Expert Council Audit
> 3.  Prioritization Vote

> **Business Goals**: See [Commercial Milestones](business/COMMERCIAL_MILESTONES.md) for our path to revenue.
> **Engineering Health**: See [Maturity Model](engineering/MATURITY_MODEL.md) for our path to "Google-Level" rigour.
> **Marketing Strategy**: See [Launch Plan](marketing/LAUNCH_PLAN.md) for March 11 Campaign.

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

## 🗓️ Unified Sprint Plan (The "Double Helix")

We track **Technical Maturity** (Productionization) alongside **Business Maturity** (Monetization). One cannot advance without the other.

| Sprint | Phase | 🏗️ Production Goal (Infra) | 💸 Monetization Goal (Business) |
| :--- | :--- | :--- | :--- |
| **S1 (Now)** | **"The Hook"** | **Localhost/Preview**: Next.js App functional on Vercel (Stateless). | **Validation**: 10 users verify the "Cut Calculator" works via DM/Twitter. |
| **S2 (Next)** | **"Persistence"** | **Vercel Postgres + Clerk Webhooks**: Robust user data storage. | **First Dollar**: Gate "Save Scenario" behind Login. Convert 1 user. |
| **S3 (Future)** | **"Scale"** | **Motherduck + Caching**: Sub-100ms queries for Roster Data. | **Micro-SaaS**: 100 Active Users. Marketing push on Reddit. |
| **S4 (Future)** | **"Enterprise"** | **CI/CD + Testing**: 95% Coverage, auto-deploy. | **B2B License**: Sell "Clean Exports" to 1 Podcaster ($50/mo). |

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

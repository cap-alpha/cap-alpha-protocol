# Sprint 1 Retro & Sprint 2 Planning

**Date**: 2026-02-18
**Theme**: From "The Hook" to "Persistence"

---

## 🎭 Step 1: User Acceptance Testing (The "Field Report")

We put the **Cut Calculator** and **Position Benchmarking** in front of our Personas.

| Persona | Feature | Reaction | Feedback / Complaint |
| :--- | :--- | :--- | :--- |
| **Casual Carl** (Armchair GM) | **Cut Calculator** | 🤩 "Whoa, I can cut Dak!" | "I cut him, but then I refreshed and it's gone. **I want to save this** to show my group chat." |
| **Podcaster Pete** (Creator) | **Benchmark Chart** | 🙂 "Clean visuals." | "I can't export this image without screenshotting. Also, **I want to save a full roster** for my show." |
| **Hardcore Harry** (Analyst) | **Pre/Post June 1** | 🧐 "Math checks out." | "Why can't I see the *impact* on next year? I need **Multi-Year logic**." |

**Consensus**: Everyone loves the *action* (Cutting), but hates the *amnesia* (No Save).

---

## 🏛 Step 2: The Expert Council (The Audit)

**Bill Belichick (The GM)**:
> "Carl is right for once. A roster move isn't a one-time event; it's a record. If he can't save his work, he's not building a team, he's just playing video games. **Build the 'Save' feature. It creates buy-in.**"

**CFO (The Money)**:
> "Agreed. 'Saving' is the sticky feature. Once they save 3 scenarios, they own the platform. This is our path to the $5 subscription (Milestone 2). **Prioritize Persistence.**"

**Andrew Ng (The Scientist)**:
> "Harry's request for Multi-Year logic is valid but premature. Our data pipeline (DuckDB) needs to be robust before we project 2027. **Persistence first, detailed projection second.**"

---

## 🗳 Step 3: The Vote (Sprint 2 Backlog)

**Winner**: **Persistence (User Data Infrastructure)**.

**Sprint 2 Goal**: Enable "Casual Carl" to save his "Dak Prescott Cut" scenario.

**Backlog (Priority Order)**:
1.  **[Infra] Vercel Postgres**: We need a place to put the data.
2.  **[Infra] Drizzle ORM**: We need to write to it safely.
3.  **[Feat] Clerk Sync**: We need to know *who* Carl is.
4.  **[Feat] Save Scenario**: The button that solves Carl's pain.

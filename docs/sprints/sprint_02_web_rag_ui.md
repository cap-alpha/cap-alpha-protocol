# Sprint 02: Cap Alpha Chat Assistant UI (Web Team)

**Target Date:** March 1, 2026
**Objective:** Implement the user-facing natural language integration, allowing Pro users (Agents/GMs) to directly interrogate the RAG pipeline via a unified chat interface in the Vercel application.

## 1. Vercel AI SDK Integration (Backend Orchestration)
- **Task:** Create the Next.js `app/api/chat/route.ts` bridging the frontend UI state to the Gemini LLM and Python data endpoints.
- **Technical Spec:** 
    - **Libraries:** `@ai-sdk/google`, `ai` (Vercel AI SDK Core).
    - **Model:** `google('models/gemini-2.5-pro')` or equivalent.
    - **Tool Calling:** Define strict Zod schemas for two specific Server-Side Tools the LLM can call:
        1. `queryDatabase`: Triggers a Python shell script (`sql_agent_bridge.py`) and returns JSON rows.
        2. `searchIntelligenceReports`: Queries the local ChromaDB and returns top $K$ markdown chunks.
- **Acceptance Criteria:** The API route supports streaming (`streamText`), successfully intercepts tool calls, waits for the Python output, and synthesizes a final stream back to the client.

## 2. Conversational Chat Interface (Frontend UX)
- **Task:** Build the interactive React component leveraging the `useChat` hook.
- **Technical Spec:** 
    - **Components:** Construct `web/components/intelligence-chat.tsx` utilizing Tailwind CSS.
    - **State Management:** Use Vercel's `useChat` to automatically manage `messages`, `input`, `handleInputChange`, and `handleSubmit`.
    - **UI Polish:** Add skeleton loaders or "Agent is thinking..." typography while the backend executes Python tool calls. Render Markdown correctly in the chat bubbles using `react-markdown`.
- **Acceptance Criteria:** A user can successfully type a message, press Enter, and see a streamed markdown response identical to ChatGPT's UX cleanly overlaid on the Dashboard.

## 3. Data Provenance "Proof" UI (The Suit/Shark Trust Mechanism)
- **Task:** Expose exactly *how* the Agent arrived at its quantitative answer so executives trust the math.
- **Technical Spec:** 
    - **Components:** Create a standalone `web/components/citation-drawer.tsx` (using Radix UI or shadcn/ui Accordion).
    - **Mechanism:** In `route.ts`, pass down the `toolInvocations` payload via the AI SDK stream. When the frontend detects that `queryDatabase` was called, render a pill button below the chat bubble: `[View SQL Query]`.
    - **Acceptance Criteria:** Clicking the pill expands a syntax-highlighted block showing the exact DuckDB `SELECT` statement and the raw JSON table result returned by Python, proving no LLM hallucination occurred.

## 4. UX Strategy & Monetization Funnel
- **Objective:** Architect the UI layout across three core conversion pages integrating the Chat Assistant as the premium feature.
- **Task:** Implement the "Job to be Done" funnel guiding Users from Free public data to the Paid Private intelligence RAG layer.
- **Technical Spec:**
    - **"Real" Team Page (Baseline):** A top-level display of current structured roster details.
    - **"Fantasy" Team Page (Activation Hook):** A personalized configuration/sync view ensuring the user enters the core product loop.
    - **Player Specific Page (The "Aha" Moment):** Combines standard stats with premium RAG analysis (e.g., Fair Market Value curves, risk telemetry).
    - **Monetization Gates:** Establish visual indicators (locks, blurs) separating the public basic data and the Pro RAG inferences.

---
**Sign-off / Status:** 
- [ ] Planning Approved
- [ ] In Progress
- [ ] Completed

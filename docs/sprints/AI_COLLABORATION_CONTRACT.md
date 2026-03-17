# AI & Human Collaboration Contract

**Purpose:** This document establishes the binding operational protocol between the Human architect and the AI agent.

## The Problem
The AI operates with an ephemeral "working memory" (e.g., internal `task.md` or `implementation_plan.md` files) that the Human cannot natively inspect. Without synchronization, this creates a black box where the Human is unaware of planned scope, architectural pivots, or task completion status until work is finalized.

## The Solution (The Synchronization Protocol)
To ensure transparency and mutual agreement, the AI must adhere to the following strict synchronization rules:

### 1. The Single Source of Truth
The `.md` files located in `docs/sprints/` (specifically `MASTER_SPRINT_PLAN.md`) represent the definitive, binding contract of work. 

### 2. Mandatory Synchronization
Whenever the AI modifies its internal planning or tracking documents (`task.md` or `implementation_plan.md`), it **MUST** immediately mirror those changes into the repository's `docs/sprints/MASTER_SPRINT_PLAN.md`.

### 3. The Approval Gate
The AI may not begin Execution of a new Epic or Sprint without a confirmed sign-off from the Human on the updated `MASTER_SPRINT_PLAN.md`. 
1. The AI proposes tasks.
2. The AI writes them to `docs/sprints/MASTER_SPRINT_PLAN.md`.
3. The Human reviews the repo file.
4. The Human approves, rejects, or reprioritizes.
5. The AI executes.

## Enforcing the Contract
*If the Human asks "what are you doing?", it indicates the AI has violated rule #2.*

## 4. Maximizing Human+AI Synergy
To operate as an elite Human+AI team across *all* projects, the Human and AI commit to the following high-velocity patterns:

1. **Front-Load Constraints**: The Human provides strict boundary conditions (e.g., visual style, libraries, performance targets) immediately when defining a task. This eliminates iterative guessing.
2. **Local Environment Autonomy**: The Human ensures the local dev environment mirrors production (via `.env` variables) so the AI can run test suites (`/test_suite`) and validate its own work autonomously without waiting for Human QA.
3. **Delegated Refactoring**: The Human never performs massive, repetitive codebase changes manually. Instead, the Human clearly defines the pattern and delegates the multi-file execution to the AI.
4. **Raw Error Traces**: When something breaks, the Human pastes the raw, literal stack trace or console error into the chat, rather than summarizing it.
5. **Slash Command Mastery**: The Human ruthlessly leverages specialized workflows (`/go`, `/todo`, `/test_suite`, `/ui_ux_audit`, `/deploy`) to trigger complex, multi-step autonomous behavior.

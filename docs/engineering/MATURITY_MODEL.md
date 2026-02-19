# Engineering Maturity Model: The "Google Standard" Gap Analysis

**Date**: 2026-02-18
**Current Level**: **Startup (Level 2)**
**Target Level**: **Scale-Up (Level 3)**
**Google Level**: **Level 5 (Hermetic/Autonomous)**

---

## 🚦 Scorecard

| Domain | Rating (1-5) | Status | Gap to "Google Standard" |
| :--- | :---: | :--- | :--- |
| **Process & Rituals** | ⭐⭐⭐⭐ | **Strong**. We have ADRs, Rituals, and Roadmaps. | Google has automated policy enforcement (Presubmits). |
| **CI/CD** | ⭐⭐ | **Weak**. We use `--no-verify` to bypass local failures. | **Hermetic Builds**. Builds should *never* fail due to "environment" (Docker needed). |
| **Testing** | ⭐⭐ | **Flaky**. Tests exist but fail locally. | **Flakiness = 0**. A flaky test at Google is deleted immediately. |
| **Observability** | ⭐ | **None**. We rely on user reports. | **Sentry/Datadog**. We need to know about errors *before* the user tweets. |
| **Infrastructure** | ⭐⭐⭐ | **Cloud-Native**. Vercel/Neon is solid. | **IaC**. We click around in dashboards. Google defines infra as code (Terraform). |
| **Security** | ⭐⭐⭐ | **Good**. Clerk handles Auth. | **Zero Trust**. We are currently "bypassing" auth for local dev. |

---

## 🚀 The "Google Path" (Action Plan)

To reach **Level 3 (Professional Engineering)**, we need to close three specific gaps:

### 1. The "It Works on My Machine" Problem (Docker)
*   **Google Way**: Everything runs in a container (Borg).
*   **Our Fix**: We need a `docker-compose.yml` that spins up a local Postgres + Linux Python environment so tests *always* run the same way as CI.

### 2. The "Flying Blind" Problem (Observability)
*   **Google Way**: Monarch/Borgmon monitors every RPC.
*   **Our Fix**: Install **Sentry** (Free Tier). It captures stack traces when "Casual Carl" crashes the app.

### 3. The "Yolo Push" Problem (Strict CI)
*   **Google Way**: The "Submit Queue" (CQ).
*   **Our Fix**: Enable "Branch Protection" on `main`. Requires passing CI to merge. No more `--no-verify`.

---

## 🧠 Strategic Advice
Don't try to be Google (Level 5) yet. Google's tooling is designed for 50,000 engineers.
**Be a Series A Startup (Level 3).**
*   **Focus**: Velocity > Perfection.
*   **But**: Never ship broken code (CI Gates).
*   **And**: Know when it breaks (Sentry).

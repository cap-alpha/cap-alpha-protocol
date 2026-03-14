# Sprint 05: Automated ML Flywheel

## Goal Description
Per the user's directive to prioritize the model and achieve continuous, hands-off data ingestion, this sprint focuses on automating the Cap Alpha Protocol ML data pipeline. We will establish a self-reinforcing iteration cycle (the "Flywheel") that requires zero manual execution commands.

## Milestone 1: Automated Ingestion & Unattended Training (Sprint 05)
- **Goal:** The system must automatically fetch new NFL data every Tuesday at 3:00 AM EST without human intervention, and subsequently retrain the model.
- **Key Tasks:**
  - Implement a GitHub Actions cron job (or Airflow DAG equivalent) to trigger `pipeline/src/spotrac_scraper_v2.py`.
  - Ensure the scraper logic automatically targets the proper current calendar year/week.
  - Connect the scraper extraction directly to the Bronze layer in `md:nfl_dead_money`.
  - Automate the `make pipeline-train` script to execute upon successful Bronze layer hydration.
- **Success Criteria:** The `prediction_results` table in MotherDuck updates weekly with zero manual commands from the user.

## Milestone 2: The Continuous Error Loop (Sprint 06 Strategy)
- **Goal:** The model identifies its own weaknesses and drafts remediation plans automatically (Andrew Ng Standard).
- **Key Tasks:**
  - Schedule `analyze_model_misses.py` to run as the final phase after every training cycle.
  - Pipe the resulting Gemini-generated hypothesis report to the GitHub issue tracker for human (Data Science / SRE) review.
- **Success Criteria:** A new GitHub issue is systematically opened every week titled "Model Miss Diagnostic," containing AI-driven analysis of the latest False Positives/Negatives.

## Milestone 3: Live Verification & Trade Execution (Sprint 07 Strategy)
- **Goal:** Prove the model works in real-time front-office scenarios, enforcing the newly implemented Uncertainty Quantification (Isolation Forest).
- **Key Tasks:**
  - Connect the Next.js `War Room` (Trade Machine) UI natively to the live `prediction_results` table in MotherDuck.
  - Block or heavily flag trades in the UI where the model's `high_uncertainty_flag == 1`.
- **Success Criteria:** The Web App displays Live Risk scores natively pulled from the automated ML Flywheel, directly influencing roster decisions based on epistemic uncertainty boundaries (Yann LeCun Standard).

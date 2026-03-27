# Algorithmic Improvements Roadmap (SP15-3)
**Status**: Strategic Formulation
**Target Completion**: Sprint 15, Post-Mortem Era

## Executive Summary
Following the initial performance of the Alpha Flywheel and the `fact_player_efficiency` predictions, several structural anomalies and identified weaknesses have emerged during temporal out-of-sample backtesting. This roadmap explicitly defines the algorithmic evolutions required to harden the Cap Alpha Protocol into a stable, highly performant prediction market engine.

---

## Part 1: Addressing the "Historical Leakage" Weakness
**Symptom:** XGBoost predictions performed exceptionally well (R2 > 0.90) in training but collapsed during true OOS (Out-of-Sample) forward walking because of hidden data leakage in feature engineering (e.g. implicitly leaking end-of-season outcomes into week 1 predictions).
**Solution:**
1. **Strict PIT (Point-In-Time) Datetimes:** Restructure the BigQuery Feature Store so that every single feature row corresponds precisely to what was known *prior* to Tuesday at 5:00 PM EST (Waiver Wire/Transaction deadline).
2. **Rolling Window Backtesting:** Transition from randomized `scikit-learn` K-Fold Cross Validation to strict **Time Series Split Validation**. A model predicting Week 8 performance must solely be trained on data generated from Week 1 to Week 7.

## Part 2: Addressing "Uncertainty Blindness"
**Symptom:** The current model emits single point-estimate predictions for `Expected Dead Cap Error` (EDCE) without providing probability density or confidence intervals, making it difficult for the Adversarial Trade Engine to weigh high-variance trades.
**Solution:**
1. **Conformal Prediction Adoption:** Implement Conformal Prediction wrappers around the core XGBoost regressors to output bounded confidence intervals (e.g. 90% confidence that Dead Cap Risk falls between $2M and $15M).
2. **Bayesian Priors for Rookies:** The model wildly overrates unproven rookies because their base salaries are artificially low. Introduce Bayesian priors based on Draft Capital (Round/Pick) to stabilize baseline risk scores before 16 games of empirical NFL data is gathered.

## Part 3: Addressing "Media Sentiment Echo Chambers"
**Symptom:** The LLM hydration script `hydrate_live_news.py` currently struggles when the media narrative explicitly manipulates contract perceptions (e.g. "astroturfing" a player's value upwards before a trade).
**Solution:**
1. **Cross-Sectional Lead-Lag Clustering:** Implement anomaly detection that measures the *divergence* between raw quantitative metrics (EPA/Play, Route Win Rate) and media sentiment NLP scoring. When media sentiment is rising while quantitative performance is falling, the algorithm must flag the player as a "Toxic Alpha" candidate.
2. **Source Weight Vectoring:** Transition from simple averaging of Gemini news summaries to an Authoritative Decay Model (Brier Scoring pundits and news outlets based on historical prediction accuracy).

## Execution Milestones
- **Phase 1 (Data Engineering):** Implement strict PIT guarantees in `medallion_pipeline.py`.
- **Phase 2 (ML Engineering):** Wrap the live `prediction_results` table outputs in Conformal Prediction intervals.
- **Phase 3 (Product Integration):** Render the confidence bands natively on the Next.js `PlayerTimeline` component to visually communicate asset risk to stakeholders.

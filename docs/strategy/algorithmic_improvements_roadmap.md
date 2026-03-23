# Algorithmic Improvements Roadmap

**Context:** Formulated from the 2024 Model Misses Post-Mortem. Objective is to correct the sub-80% predictive accuracy by resolving specific structural blindspots regarding player aging, volatility, and cross-dependencies.

## 1. Positional Decay Curves (OL vs. Skill)
**Problem:** The model fails to anticipate the catastrophic injury cliff for premium Offensive Linemen, currently treating all aging patterns with uniform generic features.
**Architecture Change:**
*   **Feature Engineering:** Implement interaction terms in the Feature Store that apply steeper, non-linear decay penalties specifically to OL past age 29.
*   **Compounding Risk Modeling:** Use cumulative career snaps as an exponential weight against current age to properly identify linemen on the verge of breakdown.

## 2. Volatility Reward Parameter (Upside Capture)
**Problem:** High-variance players (WRs, DL) are falsely classified as high-risk/busts, masking their elite game-breaking upside that yields high ROI.
**Architecture Change:**
*   **New Metric:** Calculate a `Variance Reward Index` capturing right-tail outlier performances.
*   **Loss Function Tuning:** Adjust the tree-based model (e.g., XGBoost) loss functions to penalize false negatives on high-variance profiles more heavily, prioritizing upside capture over median stability for these specific positional archetypes.

## 3. Cross-Sectional QB-OL Dependency Mapping
**Problem:** Offensive Linemen efficiency is modeled in a vacuum, ignoring the severe impact of their Quarterback's playstyle and pressure-handling.
**Architecture Change:**
*   **Cross-Linked Features:** Ingest and map the QB's Pressure-to-Sack (P2S) ratio directly onto the feature vectors of their respective OL unit.
*   **Dependency Engine:** Treat OL blocking grades as conditionally dependent on the QB's time-to-throw (TTT) and scramble-rate metrics.

## 4. Temporal Noise Smoothing (Classification Hysteresis)
**Problem:** The "Stafford Distortion" where continuous rolling updates cause violent week-to-week oscillations in predicted classifications for players dealing with micro-injuries.
**Architecture Change:**
*   **Signal Dampening:** Apply an Exponential Moving Average (EMA) layer over the weekly rolling `efficiency_ratios` to smooth single-week noise.
*   **Hysteresis Thresholds:** Implement a momentum threshold—the model must observe sustained evidence (e.g., a margin delta of >15%) to flip a classification state sequentially, completely eliminating "flickering" predictions.

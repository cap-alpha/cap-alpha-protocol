# Sprint 06: Advanced ML Model Structural Pitfalls

## Epic Goal
Now that the ML Flywheel and continuous early-warning system are automated, we must resolve fundamental data science structural biases that plague production machine learning pipelines. This sprint specifically focuses on ensuring the Cap Alpha Protocol model correctly simulates causality and temporal honesty over a multi-year timeframe.

## Priority 1: The "Cold Start" Early-Season Amnesia
- **The Problem:** The NFL is highly volatile early in the season. Currently, if we reset our player feature aggregations to `0` at Week 1, the model flies blind during the first four weeks of the season—arguably the most critical trade window before player values solidify. 
- **The Task:** Implement `L17` (Trailing 17-Game) rolling window features in `pipeline/src/feature_factory.py`. By carrying over the end of the previous season's production, the model maintains mathematical continuity entering Week 1.

## Priority 2: Lookahead Bias (Target/Feature Leakage)
- **The Problem:** The model accidentally using data from the future to predict the past. If the pipeline aggregates an injury that occurred in Week 12 and accidentally exposes that feature flag during a Week 4 inference loop, the model "learns" to predict future bust status by cheating.
- **The Task:** Audit the DuckDB database for temporal leakage. Institute a strict Point-In-Time (PIT) enforcement architecture where the feature matrix generated for `predict(X)` is proven to only contain knowledge available prior to kickoff of that specific week.

## Priority 3: Concept Drift & The NFL Meta
- **The Problem:** The NFL game changes. A 4000-yard passing season meant one thing in 2011, and something entirely different in 2024 (especially given the 17-game schedule change). If we pass the XGBoost model 15 years of flat data, it will treat 2011 mechanics equally with 2024 mechanics, diluting its predictive power on modern defensive schemes (e.g., Two-High Safety shells).
- **The Task:** Introduce **Sample Weighting** into the XGBoost `DMatrix` within `pipeline/src/train_model.py`. Recent seasons (2021-2024) should decay into heavier weights than older seasons (2011-2015) to force the algorithm to adapt to the modern meta.

## Priority 4: Survivorship Bias
- **The Problem:** Bad players get cut. If a highly-paid free agent is cut in Week 6 because he was playing catastrophically poor football, he stops accumulating data. If our pipeline drops players who "disappear" mid-season, we actually delete the most critical examples of "True Busts" from the training set, causing the model to artificially overestimate baseline efficiency.
- **The Task:** Trace the ETL pipeline for "missing" player data mid-season. Enforce strict 0% efficiency imputation for players cut while carrying dead cap hits. 

## Priority 5: Class Imbalance
- **The Problem:** Catastrophic "Dead Money Busts" are statistically rare (e.g., 5-8% of contracts). If the model predicts "Not A Bust" for every player on the dataset, it will natively achieve 92%+ accuracy while effectively generating zero actionable intelligence for the Trade Engine.
- **The Task:** Shift the main valuation metric away from raw `Accuracy` and towards `F1-score` and precision-recall AUC. Investigate implementing SMOTE (Synthetic Minority Over-sampling Technique) to artificially generate edge-case failing contracts for the XGBoost trees to train on.

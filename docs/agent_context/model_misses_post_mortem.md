# Model Misses Post-Mortem (2024)

## Executive Summary
Walk-forward validation for the 2024 season dataset revealed an overall predictive accuracy of **77.18%**. Because this falls below our targeted 80%+ threshold, a post-mortem was triggered. Analysis of the model's most severe misses (highest actual cap hits vs. incorrect predictions) exposed distinct weaknesses in specific positional archetypes.

## Severe Misses Breakdown (Top Deviations >= $90M Cap Impact)

### 1. False Negatives (Predicted "Safe", Actually Busted)
The most striking trend is the model's blind spot regarding premium Offensive Linemen (OL). The model confidently predicted safety, but these athletes ultimately registered as busts.

*   **Rashawn Slater (LT, LAC)** - Cap Hit: $114M | Predicted: 0 | Actual: 1
*   **Tyler Smith (G, DAL)** - Cap Hit: $96M | Predicted: 0 | Actual: 1
*   **Brian O'Neill (RT, MIN)** - Cap Hit: $92.5M | Predicted: 0 | Actual: 1

**Hypothesis:** The model likely over-indexes on historical snap counts and generic durability metrics for OL, masking the combinatorial risk of playing alongside injury-prone QBs or in high-pressure defensive divisions. It fails to account for the catastrophic cliff OL face when injuries *do* happen.

### 2. False Positives (Predicted "Bust", Actually Popped)
Conversely, the model aggressively flagged high-variance skill players and premium interior defenders as busts, but they provided massive efficiency ratios (ROI).

*   **D.K. Metcalf (WR, PIT)** - Cap Hit: $132M | Predicted: 1 | Actual: 0
*   **Quinnen Williams (DL, DAL)** - Cap Hit: $96M | Predicted: 1 | Actual: 0

**Hypothesis:** The model heavily punishes volatility in receiving yards (WR) and sack variance (DL). It incorrectly classified them as high-risk, completely mispricing their elite game-breaking upside that ultimately translated to high `approximate_value_per_dollar`.

### 3. The "Stafford Distortion" (Temporal Noise)
*   **Matthew Stafford (QB, LAR)** - The dataset shows extreme intra-season volatility for Stafford, with predictions violently oscillating between 0 and 1 week-to-week alongside fluctuating `efficiency_ratios` (0.67 to 0.77).
*   **Hypothesis:** The model is structurally struggling with week-to-week rolling updates for aging QBs playing through micro-injuries, creating data duplication or "flickering" classifications.

## Recommended Architectural Roadmap (Sprint 15-3)
1.  **Introduce Positional Decay Curves:** Different positions age and break down differently. OL need a steeper injury-variance penalty compared to WRs.
2.  **Volatility Reward Parameter:** Introduce a feature that rewards extreme high-end variance for WR/DL (Upside Capture), rather than purely punishing them for inconsistency.
3.  **Cross-Sectional QB-OL Dependency:** The model must evaluate OL not in a vacuum, but cross-linked with their QB's pressure to sack ratio (P2S).

# Cap Alpha Protocol (CAP)

**Institutional-Grade Intelligence Engine for NFL Capital Velocity & Roster Optimization**

> **Status**: Production (v2.1 - Active)
> **Architecture**: Medallion (DuckDB) | Temporal Feature Store | Next.js
> **Performance**: R² = **0.91** (High-Cap Portfolio Management)

## Executive Summary

The **Cap Alpha Protocol** is a quantitative auditing and predictive inference system designed to price **Second-Order Volatility** in the $20B NFL human capital market. By integrating 15 years of longitudinal contract and play-by-play data, the CAP identifies "Liquidity Traps"—inefficiencies where unforced errors ("The Discipline Tax") and structural contract decay silently deplete franchise enterprise value.

Built for **Maximum Fidelity**, the protocol follows two architectural mandates:
1.  **Temporal Integrity**: A strict Date-Based Feature Store (`valid_from`, `valid_until`) ensures zero temporal leakage across 41,000+ observations.
2.  **Portfolio Segmentation**: Statistical focus on high-cap assets (Contracts > $10M) where signal-to-noise is highest (R²=0.91), providing actionable intelligence for franchise decision-makers.

---

## Documentation Architecture

This repository is structured as a mono-repo containing the data pipeline, analysis engine, and frontend application.

| Documentation | Description | Target Audience |
| :--- | :--- | :--- |
| **[INDEX.md](INDEX.md)** | **Master Documentation Index** - Start here for deep technical details. | Developers, Architects |
| **[pipeline/README.md](pipeline/README.md)** | ETL, Airflow DAGs, and Python script usage. | Data Engineers |
| **[web/README.md](web/README.md)** | Next.js Frontend setup and architecture. | Frontend Engineers |
| **[PREDICTION_FEATURE_SET.md](PREDICTION_FEATURE_SET.md)** | Definition of the 28-feature risk vector. | Data Scientists |

---

## System Architecture

### 1. Medallion Data Architecture (DuckDB)
Processing flow for 15+ years of NFL financial data:
- **Bronze**: Raw HTML scrapes (Spotrac, PFR) stored as JSON/Parquet.
- **Silver**: Cleaned, typed tables (`dim_players`, `fact_contracts`, `fact_player_efficiency`).
- **Gold**: Feature Store (`feature_values`) and Prediction Results.

### 2. Date-Based Feature Store
A custom-built Feature Store that manages time-travel. Unlike standard "Year-based" models, this system handles precise dates (e.g., September 1st Cutoff).
- **Table**: `feature_values`
- **Retrieval**: `FeatureStore.get_historical_features(as_of_date)`

### 3. XGBoost "Risk Engine"
A Walk-Forward Validation pipeline that trains on past data to predict future inefficiencies.
- **Target**: `edce_risk` (Efficiency Decay)
- **Validation**: Rolling window backtest (2018-2025).

---

## Setup & Usage

### Prerequisites
- Docker Engine & Docker Compose (Required for bypassing macOS SIP/Sandbox limits)
- Make

### Quickstart (Data Pipeline via Containerization)
**CRITICAL**: Do not run Python natively. Due to macOS restrictions on SQLite/DuckDB file locks and headless browser automation, all operations must run inside Docker.

```bash
# 1. Build and boot the immutable container environment
docker compose up -d

# 2. Materialize Features (Populate Feature Store)
docker compose exec pipeline bash -c "python src/materialize_features.py"

# 3. Train Risk Model
docker compose exec pipeline bash -c "python src/train_model.py"

# 4. Run E2E Playwright Suite (Without host caching EPERM blocks)
docker compose run e2e
```
*Alternatively, use the provided `Makefile` (e.g., `make pipeline`, `make test-e2e`) for streamlined aliases.*

---

## Results Summary (2026 Audit)

The **"Low Cap Chaos"** hypothesis was confirmed. The model is highly predictive for substantial contracts but stochastic for minimum-wage players.

| Cap Bucket | Count | R2 Score | Strategy |
| :--- | :--- | :--- | :--- |
| **High Cap (>$10M)** | 39,734 | **0.91** | **Trust Implicitly** |
| Mid Cap ($2M-$10M) | 114,424 | **0.51** | Use as Signal |
| Low Cap (<$2M) | 332,001 | 0.03 | **Ignore** |

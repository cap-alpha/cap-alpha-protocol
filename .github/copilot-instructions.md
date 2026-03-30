# AI Coding Agent Instructions - NFL Dead Money Analysis

## Project Overview

**Purpose**: Analyze NFL salary cap dead money (money paid to non-contributing players) to identify patterns and predictability.

**Tech Stack**: Python 3.x | Docker Compose | dbt (BigQuery backend) | XGBoost | Pytest | Plotly | Next.js 14

**Architecture**: Medallion pipeline (Bronze → Silver → Gold) in BigQuery + ML feature store + Next.js frontend

---

## Critical Workflows & Commands

### Testing & Validation (Use Makefile)
```bash
make preflight         # Pre-commit gate: lint + unit tests + dbt compile
make test-unit         # Fast unit tests only
make test              # Full test suite (unit + integration)
make lint              # Check formatting (black, isort)
make dbt-compile       # Validate dbt SQL syntax against BigQuery
make help              # Show all available targets
```

### Data Pipeline (Docker-based)
```bash
make up                           # Start all Docker services
make pipeline-scrape              # Scrape Spotrac (team-cap, salaries, rankings, contracts)
make pipeline-train               # Train XGBoost risk model
make pipeline-nlp                 # Hydrate 768-D NLP sentiment vectors
make pipeline-validate            # Run target leakage diagnostics
make test-e2e                     # Playwright E2E tests in container
```

### Notebooks & Analysis
- **Production**: `notebooks/07_production_dead_money_dashboard.ipynb` (loads scraped data, visualizations)
- **Exploratory Analysis**: Notebook includes a lightweight DecisionTreeRegressor for EDA; the production model is XGBoost (see `pipeline/src/train_model.py`)

---

## Architecture Layers & Data Flow

### 1. **Bronze (Scraping/Ingestion)** → BigQuery `bronze_*` tables
- `pipeline/src/spotrac_scraper_v2.py`: Team cap, player salaries, rankings, contracts
- `pipeline/src/overthecap_scraper.py`: Contract guaranteed money (backup source)
- `pipeline/src/pfr_roster_scraper.py`, `pfr_draft_scraper.py`, `pfr_game_logs.py`: Historical performance
- `pipeline/src/sportsdataio_client.py`: Official API feed for player metadata
- `scripts/hydrate_live_news.py`: Gemini-powered news/sentiment ingestion

### 2. **Silver (Transformation)** → BigQuery `silver_*` tables
- `pipeline/src/silver_sportsdataio_transform.py`: Player metadata normalization
- `pipeline/src/feature_factory.py`: 308-feature matrix (financial, performance, NLP sentiment vectors)
- `pipeline/src/generate_sentiment_features.py`: 768-D NLP embeddings
- dbt staging models: `dbt/models/staging/` (type normalization, dedup)

### 3. **Gold (Analytics/ML)** → BigQuery `gold_*` tables + dbt marts
- dbt mart models: `dbt/models/marts/` (fact tables, dimensions)
- `pipeline/src/train_model.py`: XGBoost risk model (walk-forward validation)
- `pipeline/src/simulate_history.py`: Historical backtesting
- `pipeline/src/strategic_engine.py`: Team-level strategic audit reports

### 4. **Serving**
- Next.js 14 frontend (`web/`) reading from BigQuery
- Model artifacts tracked via DVC in `models/` with `registry.json`
- Reports and visualizations in `reports/` and `notebooks/`

---

## Key Conventions & Patterns

### Data Quality Approach
- **Synthetic Players**: Dataset includes synthetic/placeholder names (e.g., "Von Walker 5"). Flag with `is_king=False` prefix; **retained by design** (not filtered).
- **Team vs Player Reconciliation**: `DeadMoneyValidator.test_team_player_reconciliation_csv()` allows ±5% variance (legitimate due to accounting differences).
- **Salary Cap Reference**: `pipeline/src/salary_cap_reference.py` hardcodes official NFL caps (2011-2024) for validation. Base cap ≠ Spotrac "Total Cap" (latter includes carryover).

### Testing Philosophy
- **Pytest fixtures** in `pipeline/tests/test_*.py` load real CSVs from `data/processed/` (not mocked)
- **Validator tests**: Data file availability checks + logic tests (e.g., cap components, dead % ranges)
- **Pre-commit**: `make preflight` runs lint + unit tests + dbt compile before commit

### Naming Conventions
- Variables: `snake_case`; CSV columns: `snake_case` (converted from Spotrac title case)
- Team codes: Normalize via `TEAM_CODE_MAP` (e.g., `TAM` → `TB`, `SFO` → `SF`)
- Files: Descriptive names with timestamps in raw data (`spotrac_team_cap_{year}_{timestamp}.csv`)

### Error Handling
- Scrapers log detailed progress; raise `DataQualityError` on validation failure (not silent)
- Docker pipeline fails on non-zero exit code; logs captured via `make` targets
- Validator exits code 0 even with warnings (non-blocking design)

---

## Integration Points & Dependencies

### External Data Sources
1. **Spotrac** (`www.spotrac.com`): Selenium-scraped team caps, player salaries, rankings, contracts (primary source)
2. **OverTheCap** (`www.overthecap.com`): Contract guaranteed money, signing bonuses (supplementary)
3. **Pro Football Reference**: Rosters, game logs, draft data (via `pfr_*.py` scrapers)
4. **SportsDataIO** (`api.sportsdata.io`): Official API feed for player metadata
5. **Google News / Gemini**: Live news sentiment via `hydrate_live_news.py`
6. **NFL.com**: Official salary caps (hardcoded reference in `salary_cap_reference.py`)

### Cross-Component Communication
- **Docker Compose**: All pipeline execution runs inside containers via `make` targets
- **Pipeline → BigQuery**: Python scripts write directly to BigQuery bronze/silver/gold datasets
- **dbt → BigQuery**: Transforms silver→gold layer; profiles configured for BigQuery
- **GitHub Actions**: CI pipeline (`.github/workflows/ci.yml`) runs pytest on push/PR
- **Model artifacts**: XGBoost `.pkl` files tracked with DVC, metadata in `models/model_meta_*.json`

---

## Common Tasks & Examples

### Add a New Validation Test
1. Add test function to `pipeline/tests/test_dead_money_validator.py` (pytest class-based)
2. Use pytest fixtures to load CSVs: `dead_money_df = pd.read_csv('data/processed/compensation/player_dead_money.csv')`
3. Run locally: `make test-unit`; commit triggers pre-commit hooks

### Investigate Data Anomaly
1. Check `docs/SALARY_CAP_ANOMALY_INVESTIGATION.md` for known issues (e.g., 2016 CLE, 2019 SF)
2. Run `make pipeline-validate` to see cross-validation results
3. For salary cap: Compare Spotrac total vs official NFL cap via `pipeline/src/salary_cap_reference.py` (±15% tolerance expected due to carryover)

### Update Salary Cap Reference
1. Edit `pipeline/src/salary_cap_reference.py` dict (official caps from NFL.com)
2. Update `pipeline/tests/test_salary_cap_validation.py` expectations
3. Run: `make preflight`

### Add Notebook Analysis
1. Work in `notebooks/07_production_dead_money_dashboard.ipynb` (production analysis)
2. Load data from `data/processed/compensation/` (use absolute imports with `sys.path`)
3. Save outputs to `notebooks/outputs/`

---

## Important Context & Gotchas

- **BigQuery SQL dialect**: All dbt models must use BigQuery types (`STRING` not `VARCHAR`, `INT64`/`FLOAT64`, `SAFE_CAST()`, `NUMERIC` not `DECIMAL`).
- **Spotrac "Total Cap" ≠ Official NFL Salary Cap**: Spotrac includes carryover credits; base cap is fixed per year. Individual teams can vary ±15-20%.
- **Docker-first execution**: All pipeline scripts run inside containers. Use `make` targets, not raw Python.
- **XGBoost production model**: 308-feature matrix trained with walk-forward validation. Model metadata in `models/model_meta_*.json`.
- **Synthetic data**: Some player records are synthetic (detected by numbered name suffixes). Kept for analysis (not filtered).
- **DVC for large files**: Model `.pkl` files and raw data tracked with DVC, not committed to git directly.
- **Sprint plan is source of truth**: All work is tracked in `docs/sprints/MASTER_SPRINT_PLAN.md`. Update it as you work.

---

## Quick Reference

| Component | Location | Key Files |
|-----------|----------|-----------|
| Scraping | `pipeline/src/` | `spotrac_scraper_v2.py`, `overthecap_scraper.py`, `pfr_*.py` |
| ML Training | `pipeline/src/` | `train_model.py`, `feature_factory.py`, `simulate_history.py` |
| NLP/Sentiment | `pipeline/src/`, `scripts/` | `generate_sentiment_features.py`, `hydrate_live_news.py` |
| dbt Models | `dbt/models/` | staging, intermediate, marts layers |
| Tests | `pipeline/tests/` | `test_spotrac_scraper_v2.py`, `test_data_quality.py`, etc. |
| Model Artifacts | `models/` | `registry.json`, `model_meta_*.json`, `*.pkl.dvc` |
| Frontend | `web/` | Next.js 14 App Router |
| Sprint Plan | `docs/sprints/` | `MASTER_SPRINT_PLAN.md` (canonical work tracker) |
| Reference | `docs/` | `SALARY_CAP_SOURCES.md`, `SALARY_CAP_ANOMALY_INVESTIGATION.md` |

---

## Execution Guidelines for AI Agents

- **Start with `make help`**: All workflows available via Makefile targets
- **Run `make preflight` before committing**: Validates lint, tests, and dbt SQL syntax
- **All execution inside Docker**: Use `make` targets, never run raw Python outside containers
- **Check sprint plan first**: Read `docs/sprints/MASTER_SPRINT_PLAN.md` to understand current priorities
- **Update sprint plan as you work**: Mark tasks `[x]` when complete, `[/]` when in-progress
- **SQL must be BigQuery dialect**: `STRING`, `INT64`, `FLOAT64`, `SAFE_CAST()`, `NUMERIC`
- **Respect data retention policy**: Keep synthetic players in dataset; flag them, don't filter
- **Document anomalies**: Add to `docs/SALARY_CAP_ANOMALY_INVESTIGATION.md` if discovering new issues
- **Reference `pipeline/src/` for patterns**: Look at existing scrapers, transforms, and tests for conventions

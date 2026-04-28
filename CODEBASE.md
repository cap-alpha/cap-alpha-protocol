# Codebase Conceptual Model

> **For agents:** Read this after CLAUDE.md and before diving into any task. It tells you what things are and where to find them.

---

## Domain Model

```
Pundit ──publishes──► raw_pundit_media (Bronze)
                             │
                    assertion_extractor.py (LLM)
                             │
                             ▼
                    prediction_ledger (Gold, SHA-256 chain)
                             │
                    resolution_engine.py
                             │
                             ▼
                    prediction_resolutions (Gold)
                             │
                    credit_score = f(Brier score, timeliness weight)
```

| Term | Meaning |
|------|---------|
| **Pundit** | Named media personality tracked by the system (writer, podcaster, YouTuber) |
| **Assertion** | Raw unstructured text claim extracted from pundit media |
| **Prediction** | Structured form of an assertion: `{claim_category, target_player, stance, season_year}` |
| **Ledger** | Append-only BigQuery table (`gold_layer.prediction_ledger`) with SHA-256 chain — tamper-evident |
| **Resolution** | Outcome verdict: `PENDING | CORRECT | INCORRECT | VOID` |
| **Brier Score** | Probabilistic accuracy: `(predicted_prob - actual)²` — lower is better |
| **Timeliness Weight** | Multiplier `[1.0–2.0]` — predictions made further in advance score higher |
| **Credit Score** | Per-pundit aggregate: weighted Brier/binary scores × timeliness |
| **Dead Money** | Guaranteed cap liability remaining when a player is cut |
| **Medallion** | Bronze (raw scraped) → Silver (cleaned) → Gold (ML-ready / ledger) |

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   DATA SOURCES                       │
│  Spotrac · PFR · RSS feeds · YouTube · Podcasts      │
└──────────────────────┬──────────────────────────────┘
                       │ scrape / ingest
┌──────────────────────▼──────────────────────────────┐
│              PIPELINE  (pipeline/src/)               │
│                                                      │
│  run_daily.py ──orchestrates──►                      │
│    media_ingestor.py      → BQ: raw_pundit_media     │
│    assertion_extractor.py → BQ: prediction_ledger    │
│    resolution_engine.py   → BQ: prediction_resolutions│
│    feature_factory.py     → BQ: feature_store        │
│    train_model.py         → models/                  │
└──────────────────────┬──────────────────────────────┘
                       │ reads BigQuery
┌──────────────────────▼──────────────────────────────┐
│               API  (pipeline/api/)                   │
│  FastAPI · main.py · pundit_router.py                │
│  /v1/pundits/ · /v1/predictions/ · /v1/leaderboard   │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP / Server Actions
┌──────────────────────▼──────────────────────────────┐
│              FRONTEND  (web/)                        │
│  Next.js 14 · TypeScript · Clerk auth                │
│  /ledger/[pundit_id] · /draft/[year] · /dashboard   │
└─────────────────────────────────────────────────────┘
```

---

## Key Files by Concern

### Ingestion
| File | Does |
|------|------|
| `pipeline/src/media_ingestor.py` | Pulls RSS/articles, matches pundits, writes `raw_pundit_media` |
| `pipeline/src/spotrac_scraper_v2.py` | Scrapes team cap & player contracts from Spotrac |
| `pipeline/src/pfr_scraper.py` | Pro Football Reference game/player stats |
| `pipeline/src/historical_article_ingestor.py` | Backfills older pundit content |
| `pipeline/config/media_sources.yaml` | Feed URLs and pundit roster — **edit here to add sources** |

### Extraction (LLM)
| File | Does |
|------|------|
| `pipeline/src/assertion_extractor.py` | Calls LLM to extract structured predictions from raw text |
| `pipeline/src/llm_provider.py` | Pluggable LLM backend — swap Ollama/Gemini/Claude here |
| `pipeline/config/llm_config.yaml` | Active provider config (currently `ollama qwen2.5:32b`) |

### Ledger & Resolution
| File | Does |
|------|------|
| `pipeline/src/cryptographic_ledger.py` | SHA-256 chain writes to `gold_layer.prediction_ledger` |
| `pipeline/src/resolution_engine.py` | Matches predictions → outcomes, computes Brier + timeliness |
| `pipeline/src/resolve_daily.py` | Daily resolution entry point |

### ML
| File | Does |
|------|------|
| `pipeline/src/feature_factory.py` | Builds feature vectors for model training |
| `pipeline/src/feature_store.py` | BigQuery-backed feature store (reads gold layer) |
| `pipeline/src/train_model.py` | XGBoost training; outputs to `pipeline/models/` |
| `pipeline/config/ml_config.yaml` | Hyperparameters, feature selection |

### Data Quality
| File | Does |
|------|------|
| `pipeline/src/bq_data_quality.py` | Post-ingestion BQ quality checks |
| `pipeline/src/schema_validator.py` | Enforces NOT NULL / type contracts on BQ tables |
| `pipeline/src/data_quality_tests.py` | Pytest-runnable DQ gates |

### Infrastructure
| File | Does |
|------|------|
| `pipeline/src/db_manager.py` | **All BigQuery access goes here** — single client, ephemeral temp tables |
| `pipeline/src/config.py` | Runtime config object, reads `pipeline/config/settings.yaml` |
| `pipeline/src/run_daily.py` | Main daily orchestrator — start here to trace any pipeline flow |

### API
| File | Does |
|------|------|
| `pipeline/api/main.py` | FastAPI app mount + health check |
| `pipeline/api/pundit_router.py` | `/v1/pundits/`, `/v1/predictions/`, `/v1/leaderboard`, `/v1/integrity/verify` |

### Frontend
| Path | Does |
|------|------|
| `web/app/ledger/[pundit_id]/` | Pundit detail: prediction history + credit score |
| `web/app/draft/[year]/` | Draft prediction tracker |
| `web/app/dashboard/` | User dashboard (role-based) |
| `web/app/api/` | Next.js API routes (proxy to FastAPI or direct BQ) |
| `web/app/actions/` | Server Actions for mutations |

---

## BigQuery Layout

**Dataset:** `nfl_dead_money` (env: `GCP_PROJECT_ID`)

| Layer | Table | Written by |
|-------|-------|-----------|
| Bronze | `raw_pundit_media` | `media_ingestor.py` |
| Bronze | `bronze_player_contracts` | `spotrac_scraper_v2.py` |
| Bronze | `bronze_spotrac_team_cap_<year>` | `spotrac_scraper_v2.py` |
| Gold | `gold_layer.prediction_ledger` | `cryptographic_ledger.py` |
| Gold | `gold_layer.prediction_resolutions` | `resolution_engine.py` |
| Gold | `gold_layer.feature_store` | `feature_factory.py` |
| dbt marts | `dim_teams`, `fct_dead_money_by_player`, `fct_dead_money_by_year` | dbt (`dbt/`) |

**Rules:** `STRING` not `VARCHAR`, `FLOAT64`/`INT64`, `SAFE_CAST` not `TRY_CAST`, `MOD()` not `%`. All access via `db_manager.py`.

---

## Task → Where to Look

| Task involves… | Start here |
|----------------|-----------|
| Adding a new pundit or RSS feed | `pipeline/config/media_sources.yaml` |
| Changing LLM provider or prompt | `pipeline/src/llm_provider.py`, `pipeline/config/llm_config.yaml` |
| Extraction logic / assertion schema | `pipeline/src/assertion_extractor.py` |
| Resolution logic or scoring | `pipeline/src/resolution_engine.py` |
| Ledger integrity / SHA-256 chain | `pipeline/src/cryptographic_ledger.py` |
| BigQuery query / schema change | `pipeline/src/db_manager.py` + relevant src file |
| Daily pipeline flow | `pipeline/src/run_daily.py` |
| ML features or model retraining | `pipeline/src/feature_factory.py`, `pipeline/src/train_model.py` |
| API endpoint (pundits, scores) | `pipeline/api/pundit_router.py` |
| Frontend page or UI component | `web/app/<route>/` |
| Auth / user tier gating | `web/app/api/webhooks/clerk/`, Clerk middleware |
| Billing / subscriptions | `web/app/api/webhooks/stripe/`, `pipeline/src/` monetization files |
| Data quality check | `pipeline/src/bq_data_quality.py`, `pipeline/tests/test_data_quality.py` |
| Tests | `pipeline/tests/` — run via `make test` |
| Config / env vars | `pipeline/config/settings.yaml`, `.env` (never committed) |

---

## Entry Points

```bash
make test              # pytest (unit only, no Docker)
make lint              # ruff check
make check             # lint + test
make pipeline-scrape   # Spotrac scraping (Docker)
python -m src.run_daily          # full daily pipeline
python -m src.assertion_extractor # LLM extraction only
python -m src.resolve_daily       # resolution only
```

Scheduling: `pipeline/dags/nfl_daily_nlp_pipeline.py` (Airflow, 12pm UTC daily).

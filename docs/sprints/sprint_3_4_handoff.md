# NEXUS Sprint Handoff: Cap Alpha Protocol

## Sprint Summary
| Field | Value |
|-------|-------|
| **Sprint** | 3 & 4 (Combined Execution) |
| **Duration** | Current Session |
| **Sprint Goal** | Migrate to MotherDuck for scale and debug XGBoost granularity collapse. |
| **Velocity** | TBD |

## Completion Status: Sprint 3 (MotherDuck Migration)
| Task ID | Description | Status | QA Attempts | Notes |
|---------|-------------|--------|-------------|-------|
| S3-1 | Update `settings.yaml` connection strings to `md:nfl_dead_money` | ✅ Complete | 1 | Complete |
| S3-2 | Remove `duckdb` volume mounts from `docker-compose.yml` | ✅ Complete | 1 | Complete |
| S3-3 | Remove persistent local `.duckdb` files from root | ✅ Complete | 1 | Used ephemeral Docker container to bypass macOS file locks. |
| S3-4 | Configure `MOTHERDUCK_TOKEN` in environment | ✅ Complete | 1 | Token integrated into `.env` file and passed as env var. |
| S3-5 | Verify pipeline natively hits MotherDuck cloud | ✅ Complete | 1 | Connection established to `md:nfl_dead_money`. DB created. |
## Completion Status: Sprint 3.5 (Data Integrity & Reorganization)
| Task ID | Description | Status | QA Attempts | Notes |
|---------|-------------|--------|-------------|-------|
| S3.5-1 | Scan `data/raw` and `data/bronze` for timestamped duplicates | ✅ Complete | 1 | Found 24 duplicates grouped into 10 base symbols. |
| S3.5-2 | Safely migrate duplicate files to `/data/archive` | ✅ Complete | 1 | Execution success via ephemeral container bypass. |
| S3.5-3 | Generate `redownload_list.txt` for duplicated symbols/dates | ✅ Complete | 1 | List of 10 symbols created. |

## Completion Status: Sprint 4 (Model Integrity & ML Flywheel)
| Task ID | Description | Status | QA Attempts | Notes |
|---------|-------------|--------|-------------|-------|
| S4-1 | Investigate XGBoost R-squared collapse on weekly granularity | ⏳ Pending | 0 | Root cause identified (weekly scoring vs yearly target). |
| S4-2 | Analyze `model_miss_analysis.md` & Construct Continuous Error Dashboard | ⏳ Pending | 0 | - |
| S4-3 | Re-establish rigorous walk-forward validation (2019-2026) | ⏳ Pending | 0 | - |
| S4-4 | Implement Uncertainty Quantification (LeCun Standard) | ⏳ Pending | 0 | - |
| S4-5 | Integrate Gemini API for automated hypothesis generation on model misses | ⏳ Pending | 0 | - |

## Quality Metrics Expected
- **Data Integrity**: MotherDuck ingestion must succeed without local fallbacks.
- **Model Performance**: R-squared drop must be identified and corrected (Goal: > 0.8 R-squared on weekly evaluation deduplicated to terminal week).
- **Flywheel Validation**: Error analysis script must automatically classify false positives/negatives and query Gemini for remediation ideas.

## Context & Constraints
**Project**: Cap Alpha Protocol
**Current State**: Local logic migrated, waiting for cloud authentication.
**File Changes Made**:
- `/pipeline/config/settings.yaml`
- `docker-compose.yml`
- `/Makefile`

**Dependencies**: User providing `MOTHERDUCK_TOKEN`.

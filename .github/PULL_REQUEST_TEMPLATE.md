## Summary

<!-- What does this PR do? 1-3 bullet points. -->

-

## Motivation

<!-- Link the issue this PR closes, e.g. "Closes #123". -->

Closes #

## One-concern check

- [ ] This PR addresses exactly one logical concern (no bundling of unrelated fixes).

> If you found a second bug while fixing this one, open a new issue and a separate PR for it.

## Test plan

<!-- How was this tested? -->

- [ ] `make check` passes locally
- [ ] Relevant unit tests added or updated

---

## Data migration
<!-- If this PR creates or modifies a BigQuery table/column, answer these: -->
- [ ] No schema changes in this PR
- **OR** this PR adds/modifies schema:
  - Data state at t=0: <!-- empty | pre-populated by DEFAULT | requires backfill -->
  - Backfill: <!-- "not needed", "included in this PR as script/migration", or "tracked in issue #NNN" -->

---

## Extraction risk

> **Required if your diff touches any of these paths:**
> - `pipeline/src/assertion_extractor.py`
> - `pipeline/src/llm_provider.py`
> - `pipeline/config/llm_config.yaml`
> - `pipeline/migrations/`
> - `pipeline/scripts/check_extraction_health.py`
>
> `--dry-run` alone is **not** sufficient. At least one real Gemini call must be executed.

- [ ] I added or updated an extraction smoke/integration test that exercises a real LLM call (not dry-run only).

  Test file: <!-- link or path to the test, e.g. `pipeline/tests/test_extraction_smoke.py` -->

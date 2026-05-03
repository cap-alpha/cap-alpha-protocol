## Summary

<!-- What does this PR do? One or two sentences. -->

## Test plan

- [ ] Unit tests pass (`make test`)
- [ ] Lint passes (`make lint`)

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

---
description: Architecture and conventions for the self-healing daily pipeline (Healer + circuit breakers + drift)
---

# Self-healing pipeline skill

Reference for any work that touches the daily ingest → extract → resolve loop.
The goal is "breakages of all kinds get tended to" — auto-detect, auto-remediate
where the playbook is known, escalate cleanly when novel.

## Building blocks (already in `pipeline/src/`)

| Module | Role |
|---|---|
| `healing.py` | `Healer` wraps any callable; matches errors to playbooks; retries with exponential backoff; auto-files GitHub issues for novel signatures |
| `source_health.py` | `CircuitBreakerRegistry` — per-source CLOSED → OPEN → HALF_OPEN; persists to `gold_layer.source_health`; opens after 3 consecutive failures, cools for 60min |
| `pipeline_telemetry.py` | `PipelineRun` — per-stage timing/counts; persists to `gold_layer.pipeline_runs` |
| `run_daily.py` | Orchestrator. `--self-heal` flag wraps each stage in `Healer` |

## When to add a new playbook

A new playbook goes into `register_default_playbooks()` (or a sibling
registrar) when **all three** are true:

1. The error has a stable signature you can match on (status code, exception
   class, message substring).
2. The remediation is mechanical — backoff, fallback model, refresh token,
   re-fetch from a different source. Anything requiring human judgment
   stays out of the playbook.
3. The breakage has happened ≥2 times. Don't pre-build playbooks for
   hypothetical errors.

Skeleton:

```python
healer.register(
    Playbook(
        name="<short_descriptive_name>",
        matches=lambda exc: <bool>,
        remediate=lambda exc, attempt_n: <bool>,  # True = already fixed, False = backoff and retry
        max_attempts=<3-5>,
        backoff_s=<10-30>,
    )
)
```

`remediate` returning `True` means "I've fixed the underlying state; please
retry without sleeping." Returning `False` means "no state change; sleep and
retry." Most playbooks return `False` — only fancy ones (token refresh,
provider failover) return `True`.

## When to add a new circuit breaker

Any external resource that's been seen to fail in production. Wire it like:

```python
cb = CircuitBreakerRegistry.load_from_bigquery(db)
for source in sources:
    if cb.is_open(source.id):
        continue
    try:
        result = fetch(source)
        cb.record_success(source.id, source.kind)
    except Exception as e:
        cb.record_failure(source.id, str(e), source.kind)
cb.persist(db)
```

Don't open the breaker on individual *items* (a single video that 403s) —
breakers are per-*source* (the channel). One bad item shouldn't take down a
whole feed; one bad feed should be skipped for an hour.

## What still needs building (next-up)

- LLM-fallback playbook: Gemini Pro → Flash → Haiku on rate limit / schema
  validation failure. Pairs with provider abstraction in `llm_provider.py`.
- Drift detector: alarm if `target_player_name` fill-rate drops below 50%
  over a rolling window (today the structured-field fill-rate is the
  smoking gun on extraction quality).
- Per-pundit health: same circuit-breaker pattern, source-id keyed by
  pundit. Auto-quarantines dead accounts after 3 consecutive empty fetches.
- Auto-issue closer: if `healing_events` shows the same novel signature has
  not recurred in 7 days, auto-close the filed issue.

## Anti-patterns

- ❌ Wrapping the whole pipeline in one big `try/except` — that loses the
  per-stage signature the Healer needs.
- ❌ Catching `BaseException` and re-raising in a way that strips the type —
  `_signature()` keys on `type(exc).__name__`.
- ❌ Running `--self-heal` against a stage that's *known* broken (e.g., a
  config typo). The Healer will retry-and-escalate, wasting credits. Fix the
  config first, run with `--self-heal` once it's stable.
- ❌ Persisting `source_health` rows without first calling `is_open()` on
  every probe — the HALF_OPEN transition only happens via `is_open()`.

## Cost discipline

- Default fallback delays are 10s / 30s. Don't drop below 5s without a
  measured reason; thrashing on transient 5xx burns rate-limit budget faster
  than it saves time.
- Novel-issue filer is rate-limited by signature: same signature files at
  most one issue per process. If you reload state across runs, dedupe on the
  signature column in `healing_events` before filing.

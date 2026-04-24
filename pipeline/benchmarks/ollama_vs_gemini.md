# Ollama vs Gemini — Extraction Quality Benchmark

**Date:** 2026-04-20
**Hardware:** M4 Pro, 48GB RAM
**Ollama version:** 0.15.2
**Dataset:** 10 PFT articles from production data

## Results

| Metric | Gemini 2.5 Flash (cloud) | Qwen 2.5 32B (local) |
|---|---|---|
| Predictions extracted | ~5 from 10 articles | 5 from 10 articles |
| Avg time per article | ~4s | 15.7s |
| Total time (10 articles) | ~40s | 157s |
| Cost | ~$0.02/article | $0 |
| JSON compliance | 100% (native schema) | ~60% array, 40% dict (handled by parser) |

## Model findings

| Model | Size | Result |
|---|---|---|
| `llama3.1:70b` | ~42GB | **OOM crash** — exceeds M4 Pro 48GB with OS overhead |
| `qwen2.5:32b` | 19GB | **Winner** — fits comfortably, excellent structured output |
| `llama3.1:8b` | 4.9GB | Suitable for binary pre-filter stage only (#180) |

## Quality sample (Qwen 2.5 32B)

- ✅ "Arvell Reese will be drafted second overall in the 2026 NFL draft" (`draft_pick`)
- ✅ "DeWayne Carter will be cleared for training camp in 2025" (`player_performance`)
- ✅ "Titans will exercise the fifth-year option on Peter Skoronski's contract" (`contract`)
- ✅ "Dexter Lawrence will be on the active roster for all games in the 2026 season" (`player_performance`)

## Recommendation

- **Default extraction model:** `qwen2.5:32b` via Ollama — zero cost, same extraction count as Gemini
- **Pre-filter model:** `llama3.1:8b` — fast, cheap binary classifier (#180)
- **Cloud fallback:** Gemini/Claude available via config for quality audits or when Ollama is unavailable
- **70B revisit:** if hardware upgrades to 64GB+

## Models installed (as of benchmark)

```
qwen2.5:32b    19 GB
llama3.1:8b    4.9 GB
llama3:latest  4.7 GB
```

## Docker integration

The pipeline container reaches host Ollama via:
```
OLLAMA_BASE_URL=http://host.docker.internal:11434
```
Add this to `docker_env.txt` when running extraction inside Docker.

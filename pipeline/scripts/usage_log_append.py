"""Append a delta row to .claude/usage_log.jsonl without recomputing history.

Issue #329: prior monitors re-summed every transcript on each run, double-counting
prior sessions and producing a $4k false reading on 2026-04-26 (true ~$1,895).

Algorithm:
  1. Read the last row of .claude/usage_log.jsonl -> last_cumulative_usd, last_ts.
  2. Scan ~/.claude/projects/<project>/*.jsonl for assistant turns with ts > last_ts.
  3. Sum tokens per model over that delta only, multiply by per-M-tok rates.
  4. new_cumulative = last_cumulative + delta. Append one row.

Usage:
    python pipeline/scripts/usage_log_append.py
    python pipeline/scripts/usage_log_append.py --dry-run

Per-M-tok rates (USD), as published 2026-04-26:
    Opus    in 15  / out 75 / cache_read 1.50 / cache_create 18.75
    Sonnet  in  3  / out 15 / cache_read 0.30 / cache_create  3.75
    Haiku   in 0.80/ out  4 / cache_read 0.08 / cache_create  1.00
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
USAGE_LOG = REPO_ROOT / ".claude" / "usage_log.jsonl"
TRANSCRIPT_DIR = (
    Path.home()
    / ".claude"
    / "projects"
    / "-Users-andrewsmith-portfolio-nfl-dead-money"
)

RATES = {
    "opus": {"in": 15.0, "out": 75.0, "cache_read": 1.50, "cache_create": 18.75},
    "sonnet": {"in": 3.0, "out": 15.0, "cache_read": 0.30, "cache_create": 3.75},
    "haiku": {"in": 0.80, "out": 4.0, "cache_read": 0.08, "cache_create": 1.00},
}


def model_family(model_id: str) -> str | None:
    m = (model_id or "").lower()
    if "opus" in m:
        return "opus"
    if "sonnet" in m:
        return "sonnet"
    if "haiku" in m:
        return "haiku"
    return None


def load_last_cumulative() -> tuple[float, str | None]:
    if not USAGE_LOG.exists():
        return 0.0, None
    last = None
    with USAGE_LOG.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = line
    if not last:
        return 0.0, None
    row = json.loads(last)
    return float(row.get("cumulative_usd", 0.0)), row.get("last_ts")


def iter_assistant_turns(since_ts: str | None):
    """Yield (ts, model_family, usage_dict) for assistant turns newer than since_ts."""
    if not TRANSCRIPT_DIR.exists():
        return
    for path in sorted(TRANSCRIPT_DIR.glob("*.jsonl")):
        try:
            with path.open() as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("type") != "assistant":
                        continue
                    ts = evt.get("timestamp") or evt.get("ts")
                    if since_ts and ts and ts <= since_ts:
                        continue
                    msg = evt.get("message") or {}
                    usage = msg.get("usage") or {}
                    if not usage:
                        continue
                    fam = model_family(msg.get("model", ""))
                    if fam is None:
                        continue
                    yield ts, fam, usage
        except OSError:
            continue


def cost_for(fam: str, usage: dict) -> float:
    r = RATES[fam]
    return (
        usage.get("input_tokens", 0) * r["in"]
        + usage.get("output_tokens", 0) * r["out"]
        + usage.get("cache_read_input_tokens", 0) * r["cache_read"]
        + usage.get("cache_creation_input_tokens", 0) * r["cache_create"]
    ) / 1_000_000.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    last_cumulative, last_ts = load_last_cumulative()
    by_model = {"opus": 0.0, "sonnet": 0.0, "haiku": 0.0}
    newest_ts = last_ts

    for ts, fam, usage in iter_assistant_turns(last_ts):
        by_model[fam] += cost_for(fam, usage)
        if ts and (newest_ts is None or ts > newest_ts):
            newest_ts = ts

    delta = sum(by_model.values())
    new_cumulative = last_cumulative + delta

    row = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "delta_usd": round(delta, 4),
        "cumulative_usd": round(new_cumulative, 4),
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
        "last_ts": newest_ts,
    }

    print(json.dumps(row, indent=2))

    if args.dry_run:
        return 0

    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with USAGE_LOG.open("a") as fh:
        fh.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

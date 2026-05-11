#!/usr/bin/env python3
"""
Demo Accuracy Report — NFL Prediction Ledger (Golden Seed Corpus).

Queries the local DuckDB and prints a formatted leaderboard + breakdown.

Usage:
    python pipeline/scripts/demo_accuracy_report.py [--db-path PATH]

Env:
    DUCKDB_PATH  -- path to local.duckdb (default: pipeline/data/local.duckdb)
"""

import argparse
import os
import sys
from collections import defaultdict

DUCKDB_PATH_DEFAULT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "local.duckdb",
)

CATEGORY_LABELS = {
    "super_bowl": "Super Bowl LIX",
    "nfl_draft": "Draft Picks",
    "division_winner": "Division Winners",
    "season_outcome": "Season Outcomes",
    "playoff": "Playoff Teams",
    "player_award": "Player Awards",
    "free_agency": "Free Agency / Trades",
    "player_stat": "Player Stats",
}


def run_report(db_path: str) -> None:
    import duckdb

    conn = duckdb.connect(db_path, read_only=True)

    # ------------------------------------------------------------------ #
    # 1. Pull golden-seed rows (llm_model = 'human-curator')
    # ------------------------------------------------------------------ #
    rows = conn.execute(
        """
        SELECT
            l.pundit_id,
            l.pundit_name,
            l.extracted_claim,
            l.raw_assertion_text,
            l.claim_norm_key,
            r.resolution_status,
            r.binary_correct,
            r.outcome_notes,
            r.resolved_at
        FROM gold_layer.prediction_ledger l
        JOIN gold_layer.prediction_resolutions r
            ON l.prediction_hash = r.prediction_hash
        WHERE l.llm_model = 'human-curator'
        ORDER BY l.pundit_name, l.ingestion_timestamp
        """
    ).fetchall()

    conn.close()

    if not rows:
        print("No golden-seed rows found. Run load_golden_seed.py first.")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 2. Aggregate by pundit
    # ------------------------------------------------------------------ #
    pundit_stats: dict[str, dict] = {}
    category_stats: dict[str, dict] = defaultdict(lambda: {"correct": 0, "total": 0})
    sample_correct = []
    sample_incorrect = []

    for row in rows:
        pundit_id, pundit_name, claim, raw_text, norm_key, status, correct, notes, _ = (
            row
        )

        if pundit_name not in pundit_stats:
            pundit_stats[pundit_name] = {
                "total": 0,
                "correct": 0,
                "incorrect": 0,
                "void": 0,
            }
        ps = pundit_stats[pundit_name]
        ps["total"] += 1
        if status == "CORRECT":
            ps["correct"] += 1
        elif status == "INCORRECT":
            ps["incorrect"] += 1
        else:
            ps["void"] += 1

        # Category from norm_key prefix (pundit_id|claim) — we infer from claim text
        cat = _infer_category(claim, norm_key)
        category_stats[cat]["total"] += 1
        if status == "CORRECT":
            category_stats[cat]["correct"] += 1

        # Collect samples
        if status == "CORRECT" and len(sample_correct) < 5:
            sample_correct.append((pundit_name, claim, notes))
        elif status == "INCORRECT" and len(sample_incorrect) < 5:
            sample_incorrect.append((pundit_name, claim, notes))

    # ------------------------------------------------------------------ #
    # 3. Render report
    # ------------------------------------------------------------------ #
    total_predictions = len(rows)
    total_correct = sum(1 for r in rows if r[5] == "CORRECT")
    overall_pct = (
        100.0 * total_correct / total_predictions if total_predictions else 0.0
    )

    print()
    print("=" * 62)
    print("  NFL Prediction Ledger — Demo Accuracy Report")
    print("  Golden Seed Corpus (2024-25 Season + 2025 NFL Draft)")
    print("=" * 62)

    # ---- Pundit Leaderboard ----
    print()
    print("Pundit Leaderboard")
    print("-" * 62)
    header = f"{'Rank':<5} {'Pundit':<22} {'Claims':>6} {'Correct':>7} {'Wrong':>7} {'Acc':>7}"
    print(header)
    print("-" * 62)

    sorted_pundits = sorted(
        pundit_stats.items(),
        key=lambda kv: (
            kv[1]["correct"] / kv[1]["total"] if kv[1]["total"] > 0 else 0,
            kv[1]["correct"],
        ),
        reverse=True,
    )

    for rank, (name, ps) in enumerate(sorted_pundits, 1):
        acc = 100.0 * ps["correct"] / ps["total"] if ps["total"] else 0.0
        bar = _acc_bar(acc)
        print(
            f"{rank:<5} {name:<22} {ps['total']:>6} {ps['correct']:>7} "
            f"{ps['incorrect']:>7} {acc:>6.0f}%  {bar}"
        )

    # ---- Category Breakdown ----
    print()
    print("Category Breakdown")
    print("-" * 62)
    for cat, stats in sorted(category_stats.items()):
        label = CATEGORY_LABELS.get(cat, cat)
        pct = 100.0 * stats["correct"] / stats["total"] if stats["total"] else 0.0
        bar = _acc_bar(pct)
        print(
            f"  {label:<26} {stats['correct']}/{stats['total']} correct  "
            f"({pct:.0f}%)  {bar}"
        )

    # ---- Sample Claims ----
    print()
    print("Sample Claims — Correct Calls")
    print("-" * 62)
    for pundit, claim, notes in sample_correct:
        short_claim = claim[:55] + "…" if len(claim) > 55 else claim
        print(f'  [+] {pundit}: "{short_claim}"')
        print(f"      -> {notes}")

    print()
    print("Sample Claims — Missed Calls")
    print("-" * 62)
    for pundit, claim, notes in sample_incorrect:
        short_claim = claim[:55] + "…" if len(claim) > 55 else claim
        print(f'  [-] {pundit}: "{short_claim}"')
        print(f"      -> {notes}")

    # ---- Summary ----
    print()
    print("=" * 62)
    print(
        f"  Total: {total_predictions} predictions  |  "
        f"{total_correct} correct  |  "
        f"{total_predictions - total_correct} incorrect  |  "
        f"Overall accuracy: {overall_pct:.1f}%"
    )
    print("=" * 62)
    print()


def _infer_category(claim: str, norm_key: str) -> str:
    cl = claim.lower()
    if "super bowl" in cl and (
        "win" in cl
        or "mvp" in cl
        or "score" in cl
        or "yards" in cl
        or "appear" in cl
        or "hold" in cl
        or "three-peat" in cl
        or "complete" in cl
    ):
        return "super_bowl"
    if (
        "draft" in cl
        or "#1 overall" in cl
        or "#2 overall" in cl
        or "#3 overall" in cl
        or "#4 overall" in cl
        or "#5 overall" in cl
        or "overall" in cl
    ):
        return "nfl_draft"
    if (
        "division" in cl
        or "afc east" in cl
        or "afc north" in cl
        or "afc south" in cl
        or "afc west" in cl
        or "nfc east" in cl
        or "nfc north" in cl
        or "nfc south" in cl
        or "nfc west" in cl
    ):
        return "division_winner"
    if "afc" in cl or "nfc" in cl and ("win" in cl or "champion" in cl):
        return "season_outcome"
    if "playoff" in cl or "make the" in cl or "postseason" in cl:
        return "playoff"
    if "nfc championship" in cl:
        return "playoff"
    if "mvp" in cl or "rookie of the year" in cl or "award" in cl:
        return "player_award"
    if (
        "sign" in cl
        or "free agent" in cl
        or "trade" in cl
        or "remain" in cl
        or "stay" in cl
    ):
        return "free_agency"
    if "yards" in cl or "touchdown" in cl or "stat" in cl:
        return "player_stat"
    if "super bowl" in cl:
        return "super_bowl"
    return "season_outcome"


def _acc_bar(pct: float, width: int = 10) -> str:
    filled = round(pct / 100 * width)
    return "[" + "#" * filled + "." * (width - filled) + "]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db-path",
        default=os.environ.get("DUCKDB_PATH", DUCKDB_PATH_DEFAULT),
        help="Path to the local DuckDB file.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.db_path):
        print(f"ERROR: DuckDB file not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)

    run_report(args.db_path)


if __name__ == "__main__":
    main()

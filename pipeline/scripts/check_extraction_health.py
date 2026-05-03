"""
CI health check: fails with exit code 1 if the extraction pipeline wrote 0 utterances
in the last N minutes. Run after the extraction step in CI.

Usage: python pipeline/scripts/check_extraction_health.py --window-minutes 120
"""

import argparse
import sys
import os

# Allow running as `python scripts/check_extraction_health.py` from the pipeline/ dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify extraction pipeline produced output in the last N minutes."
    )
    parser.add_argument(
        "--window-minutes",
        type=int,
        default=120,
        help="Look-back window in minutes (default: 120)",
    )
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Minimum number of utterances required (default: 1)",
    )
    args = parser.parse_args()

    from src.db_manager import DBManager

    db = DBManager()

    query = f"""
        SELECT COUNT(*) AS n
        FROM silver_v2_claims.raw_utterance
        WHERE created_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {args.window_minutes} MINUTE)
    """

    try:
        row = db.fetch_df(query)
        count = int(row.iloc[0]["n"])
    except Exception as e:
        print(
            f"ERROR: Could not query silver_v2_claims.raw_utterance: {e}",
            file=sys.stderr,
        )
        return 1

    if count < args.min_count:
        print(
            f"ERROR: Extraction health check FAILED — "
            f"{count} utterances written in the last {args.window_minutes} minutes "
            f"(min required: {args.min_count}). "
            f"Check LLM_EXTRACTION_PROVIDER / LLM_EXTRACTION_MODEL config and "
            f"review assertion_extractor logs for API errors.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {count} utterances written in last {args.window_minutes} minutes "
        f"(min required: {args.min_count})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

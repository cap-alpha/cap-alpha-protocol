#!/usr/bin/env python3
"""
backfill_silver_claims.py — promote qualifying raw_utterances to silver_v2_claims.claim

Reads all silver_v2_claims.raw_utterance rows where:
  speech_act_type IN ('assertion', 'conditional', 'recall')
  AND testability_score >= 0.6

And inserts a corresponding claim row for each.  Idempotent — already-promoted
utterances are skipped (claim_id is a deterministic UUIDv5 from utterance_id).

Usage:
    python pipeline/scripts/backfill_silver_claims.py            # promote all qualifying
    python pipeline/scripts/backfill_silver_claims.py --dry-run  # count only, no writes
    python pipeline/scripts/backfill_silver_claims.py --ids u1 u2 u3  # specific IDs

Environment:
    DB_BACKEND=duckdb          use local DuckDB (default when USE_LOCAL_DB=1)
    DUCKDB_PATH=<path>         path to DuckDB file (default: pipeline/data/local.duckdb)
    USE_LOCAL_DB=1             alias for DB_BACKEND=duckdb
"""

import argparse
import logging
import os
import sys

# Ensure pipeline/src is on the path when invoked as a script
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backfill_silver_claims")


def main():
    parser = argparse.ArgumentParser(
        description="Promote qualifying raw_utterances to silver_v2_claims.claim"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count qualifying utterances without writing any rows",
    )
    parser.add_argument(
        "--ids",
        nargs="*",
        metavar="UTTERANCE_ID",
        help="Specific utterance IDs to promote (default: all qualifying)",
    )
    args = parser.parse_args()

    # Respect USE_LOCAL_DB alias
    if os.environ.get("USE_LOCAL_DB", "").lower() in ("1", "true", "yes"):
        os.environ.setdefault("DB_BACKEND", "duckdb")

    # Deferred import so env vars are set first
    from src.db_manager import get_db_manager
    from src.promote_claims import (
        _QUALIFYING_SPEECH_ACTS,
        _TESTABILITY_THRESHOLD,
        promote_utterances_to_claims,
    )

    if args.dry_run:
        logger.info("DRY RUN — counting qualifying utterances only")
        db = get_db_manager()

        # Build filter for specific IDs if requested
        if args.ids:
            placeholders = ", ".join(f"'{uid}'" for uid in args.ids)
            id_filter = f"AND utterance_id IN ({placeholders})"
        else:
            id_filter = ""

        acts = ", ".join(f"'{a}'" for a in sorted(_QUALIFYING_SPEECH_ACTS))
        count_query = f"""
            SELECT count(*)
            FROM silver_v2_claims.raw_utterance
            WHERE speech_act_type IN ({acts})
              AND testability_score >= {_TESTABILITY_THRESHOLD}
              {id_filter}
        """
        total = db.fetch_df(count_query).iloc[0, 0]

        # Count already promoted
        existing_query = "SELECT count(*) FROM silver_v2_claims.claim"
        existing = db.fetch_df(existing_query).iloc[0, 0]

        logger.info(
            "Qualifying utterances: %d | Already promoted: %d | Would promote: %d",
            int(total),
            int(existing),
            int(total),
        )
        print(
            f"dry-run: {int(total)} qualifying utterances "
            f"({int(existing)} already in claim table)"
        )
        return

    logger.info("Starting backfill of silver_v2_claims.claim ...")
    db = get_db_manager()
    n = promote_utterances_to_claims(
        utterance_ids=args.ids if args.ids else None,
        db=db,
    )
    logger.info("Backfill complete: %d new claim rows written", n)
    print(f"Backfill complete: {n} new claim rows written to silver_v2_claims.claim")


if __name__ == "__main__":
    main()

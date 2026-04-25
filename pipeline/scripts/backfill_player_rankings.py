#!/usr/bin/env python3
"""
Historical backfill for player rankings (2015-2024).
Snapshots each year with delays between runs to avoid triggering anti-bot protection.
Idempotent: skips years that already have CSVs.
"""

import argparse
import logging
import time
from datetime import datetime
from pathlib import Path
import subprocess
import sys

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.absolute()


def backfill(
    start_year: int = 2015,
    end_year: int = 2024,
    outdir: Path = None,
    delay_secs: int = 30,
    force: bool = False,
):
    if outdir is None:
        outdir = PROJECT_ROOT / "data" / "raw"
    outdir.mkdir(parents=True, exist_ok=True)

    years = list(range(start_year, end_year + 1))
    log.info(f"🔄 Backfilling player rankings for years: {years}")
    log.info(f"   Output dir: {outdir}")
    log.info(f"   Delay between runs: {delay_secs}s")
    log.info(f"   Total estimated time: ~{len(years) * (15 + delay_secs) / 60:.1f} min")

    successful = []
    failed = []

    for i, year in enumerate(years, start=1):
        csv_path = outdir / f"player_rankings_{year}.csv"

        # Check if already exists
        if csv_path.exists() and not force:
            log.info(f"[{i}/{len(years)}] ✓ {year}: CSV exists, skipping")
            successful.append(year)
            continue

        log.info(f"\n[{i}/{len(years)}] 🚀 Snapshotting {year}...")

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "player_rankings_snapshot.py"),
            "--year",
            str(year),
            "--retries",
            "3",
        ]

        try:
            result = subprocess.run(
                cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=180
            )
            if result.returncode == 0:
                log.info(f"   ✓ Success: {result.stdout.strip()}")
                successful.append(year)
            else:
                err = result.stderr or result.stdout
                log.error(f"   ❌ Failed: {err[:200]}")
                failed.append(year)
        except subprocess.TimeoutExpired:
            log.error(f"   ❌ Timeout")
            failed.append(year)
        except Exception as e:
            log.error(f"   ❌ Error: {e}")
            failed.append(year)

        # Wait before next run (except for last year)
        if i < len(years):
            log.info(f"   ⏳ Waiting {delay_secs}s before next year...")
            time.sleep(delay_secs)

    # Summary
    log.info("\n" + "=" * 70)
    log.info("📊 BACKFILL SUMMARY")
    log.info("=" * 70)
    log.info(f"✓ Successful: {len(successful)}/{len(years)} - {successful}")
    if failed:
        log.error(f"❌ Failed: {len(failed)}/{len(years)} - {failed}")
        return False
    else:
        log.info("🎉 All years completed successfully!")
        return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Backfill player rankings for historical years"
    )
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--end-year", type=int, default=2024)
    ap.add_argument("--outdir", type=str, default=None)
    ap.add_argument(
        "--delay", type=int, default=30, help="Delay between runs (seconds)"
    )
    ap.add_argument(
        "--force", action="store_true", help="Re-snapshot even if CSV exists"
    )
    args = ap.parse_args()

    outdir = Path(args.outdir) if args.outdir else None
    success = backfill(
        start_year=args.start_year,
        end_year=args.end_year,
        outdir=outdir,
        delay_secs=args.delay,
        force=args.force,
    )
    sys.exit(0 if success else 1)

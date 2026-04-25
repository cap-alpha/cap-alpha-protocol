#!/usr/bin/env python3
"""
Migrate raw data from data_raw/ to Medallion data/bronze/{source}/{year}/ structure.
"""

import os
import shutil
import re
from pathlib import Path

SOURCE_DIR = Path("data_raw")
TARGET_DIR = Path("data/bronze")


def extract_year(filename):
    """Extract year from filename like 'spotrac_player_rankings_2015_20260130_225831.csv'
    OR 'game_logs_2021.csv' OR 'rosters_2024.csv'"""
    # Try pattern: _YYYY_ (middle of filename)
    match = re.search(r"_(\d{4})_", filename)
    if match:
        year = int(match.group(1))
        if 2011 <= year <= 2030:
            return str(year)

    # Try pattern: _YYYY.ext (end of filename before extension)
    match = re.search(r"_(\d{4})\.\w+$", filename)
    if match:
        year = int(match.group(1))
        if 2011 <= year <= 2030:
            return str(year)

    return "unknown"


def extract_source(filename):
    """Extract source from filename."""
    if filename.startswith("spotrac"):
        return "spotrac"
    elif filename.startswith("pfr"):
        return "pfr"
    else:
        return "other"


def migrate_file(src_path, dry_run=False):
    """Migrate a single file to the new structure."""
    filename = src_path.name
    source = extract_source(filename)
    year = extract_year(filename)

    target_path = TARGET_DIR / source / year / filename

    if dry_run:
        print(f"  {src_path} -> {target_path}")
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, target_path)
        print(f"  ✓ {filename} -> {source}/{year}/")


def migrate_directory(src_dir, dir_name, dry_run=False):
    """Migrate a subdirectory (like dead_money/, pfr/)."""
    # These are already organized by source, need to organize by year
    for file in src_dir.iterdir():
        if file.is_file() and not file.name.startswith("."):
            year = extract_year(file.name)
            target_path = TARGET_DIR / dir_name / year / file.name

            if dry_run:
                print(f"  {file} -> {target_path}")
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file, target_path)
                print(f"  ✓ {file.name} -> {dir_name}/{year}/")


def main(dry_run=True):
    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating data_raw/ to data/bronze/...")
    print()

    # 1. Migrate top-level CSV files
    print("📁 Migrating top-level files...")
    for item in SOURCE_DIR.iterdir():
        if item.is_file() and item.suffix in [".csv", ".html", ".txt", ".jsonl"]:
            migrate_file(item, dry_run)

    print()

    # 2. Migrate subdirectories
    subdirs = ["dead_money", "penalties", "pfr", "snapshots"]
    for subdir in subdirs:
        subdir_path = SOURCE_DIR / subdir
        if subdir_path.exists() and subdir_path.is_dir():
            print(f"📁 Migrating {subdir}/...")
            migrate_directory(subdir_path, subdir, dry_run)

    print()
    print(
        "✅ Migration complete!"
        if not dry_run
        else "✅ Dry run complete. Run with --execute to apply."
    )


if __name__ == "__main__":
    import sys

    dry_run = "--execute" not in sys.argv
    main(dry_run=dry_run)

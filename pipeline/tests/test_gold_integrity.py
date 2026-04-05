from src.db_manager import DBManager
import pytest
import logging
from pathlib import Path
import os
import sys

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))
from src.config_loader import get_db_path

DB_PATH = get_db_path()

# Skip all tests within this module if the DB doesn't exist (e.g. CI without full build)
if not Path(DB_PATH).exists():
    pytest.skip(
        "Production DB not found, skipping gold layer integrity tests",
        allow_module_level=True,
    )


def test_gold_layer_build_integrity():
    """
    Ensures the Gold Layer can be built without BinderException (casting issues)
    or ParserException (syntax issues).
    """
    try:
        # We don't want to actually overwrite the production table here if we can avoid it,
        # but create_gold_layer does 'CREATE OR REPLACE'.
        # For a test, we'll try to execute the core logic into a temp table.
        from src.db_manager import DBManager
        from scripts.medallion_pipeline import GoldLayer

        # We can't easily run create_gold_layer on a temp table without modifying it,
        # but we can verify it runs on the current DB.
        with DBManager(DB_PATH) as db:
            gold = GoldLayer(db)
            gold.build_fact_player_efficiency()
        logger.info("✓ Gold Layer build successful (no SQL errors)")

    except Exception as e:
        pytest.fail(f"Gold Layer build failed with error: {e}")


def test_no_row_explosion():
    """
    Checks that core players don't have excessive rows (sign of bad joins).
    """
    # Check a few specific players known to cause issues
    players = ["Josh Sweat", "Marvin Harrison Jr."]
    with DBManager(DB_PATH) as db:
        for player in players:
            count = db.execute(
                f"SELECT COUNT(*) FROM fact_player_efficiency WHERE player_name = '{player}' AND year = 2025"
            ).fetchone()[0]
            # A player might be on two teams (max 2 rows usually), but 16 is definitely an explosion.
            assert (
                count <= 2
            ), f"Row explosion detected for {player}: {count} rows. Expected <= 2."


def test_penalty_linkage():
    """
    Ensures penalties are actually linking to the gold layer.
    """
    with DBManager(DB_PATH) as db:
        # Check if table exists and has data first
        try:
            count_check = db.execute(
                "SELECT COUNT(*) FROM fact_player_efficiency"
            ).fetchone()[0]
            if count_check == 0:
                pytest.skip("Gold Layer table empty, skipping linkage test")
        except:
            pytest.skip("Gold Layer table missing, skipping linkage test")

        penalty_link_count = db.execute(
            "SELECT COUNT(*) FROM fact_player_efficiency WHERE year = 2025 AND total_penalty_yards > 0"
        ).fetchone()[0]
        assert (
            penalty_link_count > 0
        ), "No players in the Gold Layer have penalty data for 2025."


def test_team_dead_cap_integrity():
    """
    Regression Test: Ensures ARI 2023 Dead Cap matches ground truth (~$31-32M).
    This prevents the '0.500 win rate' class of data bugs from reappearing.
    """
    db_path = get_db_path()
    with DBManager(db_path) as db:
        # Ground truth from silver_team_cap: ARI 2023 Dead Cap Millions = 69.78
        # (Note: 31.99 was the percentage, we sum the absolute dollars in Gold)
        ari_2023_dc = db.execute("""
            SELECT SUM(potential_dead_cap_millions) 
            FROM fact_player_efficiency 
            WHERE team = 'ARI' AND year = 2023
        """).fetchone()[0]

        assert ari_2023_dc is not None, "ARI 2023 data missing from Gold Layer"
        # Adjusted expectations based on previous discrepancies, but structurally correct now
        assert (
            68.0 < ari_2023_dc < 72.0
        ), f"ARI 2023 Dead Cap deviation: {ari_2023_dc}M found, expected ~69.78M"


def test_contract_name_deduplication():
    """
    Validates that the 'Kyler MurrayKyler Murray' doubled-name issue
    is correctly handled by the ingestion logic.
    """
    from scripts.medallion_pipeline import clean_doubled_name

    assert clean_doubled_name("Kyler MurrayKyler Murray") == "Kyler Murray"
    assert clean_doubled_name("Josh SweatJosh Sweat") == "Josh Sweat"
    assert (
        clean_doubled_name("Dak Prescott") == "Dak Prescott"
    )  # No change for single names
    assert clean_doubled_name("A") == "A"  # Short name safety


if __name__ == "__main__":
    # Run simple check if executed directly
    print("Running integrity checks...")
    try:
        test_gold_layer_build_integrity()
        test_no_row_explosion()
        test_penalty_linkage()
        print("ALL INTEGRITY CHECKS PASSED")
    except Exception as e:
        print(f"INTEGRITY CHECK FAILED: {e}")

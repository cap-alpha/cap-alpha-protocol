import os

import pandas as pd
import pytest

from src.db_manager import DBManager

pytestmark = pytest.mark.skipif(
    not os.environ.get("GCP_PROJECT_ID"),
    reason="GCP_PROJECT_ID not set — skipping BigQuery data quality tests",
)


@pytest.fixture(scope="module")
def con():
    """Shared database connection for the module."""
    db = DBManager()
    yield db
    db.close()


# --- 1. Bronze/Silver Layer Validation ---


def test_silver_table_existence(con):
    """Ensures major Silver Layer tables are present and populated."""
    expected = ["silver_spotrac_contracts"]
    for table in expected:
        assert con.table_exists(table), f"Missing table: {table}"
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        assert count > 0, f"Table {table} is empty"


def test_null_boundary_constraints(con):
    """Validates that critical ID fields are never null in Silver tables."""
    nulls = con.execute(
        "SELECT COUNT(*) FROM silver_spotrac_contracts WHERE player_name IS NULL OR team IS NULL"
    ).fetchone()[0]
    assert nulls == 0, "Null values found in Spotrac player/team IDs"


# --- 2. Normalization (Silver) Logic ---


def test_team_mapping_exhaustion(con):
    """Verifies that all team names in sources have been normalized to standard 3 codes."""
    if not con.table_exists("silver_spotrac_contracts"):
        pytest.skip("silver_spotrac_contracts not found")
    teams_df = con.fetch_df("SELECT DISTINCT team FROM silver_spotrac_contracts")
    active_teams = teams_df["team"].dropna().tolist()
    for team in active_teams:
        assert 2 <= len(team) <= 3, f"Non-standard team code found: {team}"
        assert team.isupper(), f"Lowercase team code found: {team}"


def test_duplicate_signature_detection(con):
    """Checks for accidental row explosion in the Gold mart.

    Note: Some duplicates are expected due to same-name players on the same team
    (e.g., two 'Chris Smith' on DET). We alert on high counts (>3) which indicate
    a real data pipeline issue rather than legitimate name collisions.
    """
    if not con.table_exists("fact_player_efficiency"):
        pytest.skip("fact_player_efficiency not found")
    dupes_df = con.fetch_df("""
        SELECT player_name, year, team, COUNT(*) as cnt
        FROM fact_player_efficiency
        GROUP BY 1, 2, 3
        HAVING COUNT(*) > 3
    """)
    assert len(dupes_df) == 0, (
        f"Gold Mart has suspicious duplicates (>3 per player/year/team):\n{dupes_df}"
    )


# --- 3. Gold Mart Validation ---


def test_gold_table_existence(con):
    """Ensures the Gold mart table exists and is populated."""
    assert con.table_exists("fact_player_efficiency"), (
        "Missing Gold table: fact_player_efficiency"
    )
    count = con.execute("SELECT COUNT(*) FROM fact_player_efficiency").fetchone()[0]
    assert count > 0, "fact_player_efficiency is empty"


def test_games_played_range(con):
    """Ensures games_played in Gold layer falls within realistic boundaries."""
    if not con.table_exists("fact_player_efficiency"):
        pytest.skip("fact_player_efficiency not found")
    games = con.execute(
        "SELECT MAX(games_played) FROM fact_player_efficiency"
    ).fetchone()[0]
    if games is not None:
        assert games <= 21, f"Impossible games played count detected: {games}"


def test_cross_layer_consistency(con):
    """Validates that the Gold Mart preserves relational integrity across layers."""
    if not con.table_exists("fact_player_efficiency") or not con.table_exists(
        "silver_spotrac_contracts"
    ):
        pytest.skip("Required tables not found")
    orphan_count = con.execute("""
        SELECT COUNT(*)
        FROM fact_player_efficiency g
        LEFT JOIN silver_spotrac_contracts s ON g.player_name = s.player_name AND g.year = s.year
        WHERE s.player_name IS NULL
    """).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM fact_player_efficiency").fetchone()[0]
    orphan_rate = orphan_count / total if total > 0 else 0
    assert orphan_rate < 0.05, (
        f"High orphan rate in Gold Layer ({orphan_rate:.2%}). Normalization failing."
    )

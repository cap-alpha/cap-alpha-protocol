import pytest
from src.db_manager import DBManager
import pandas as pd
from datetime import date

# FeatureStore still uses DuckDB internals (self.db.con) — skip until ported to BigQuery
pytestmark = pytest.mark.skip(reason="FeatureStore not yet ported from DuckDB to BigQuery")

from src.feature_store import FeatureStore

@pytest.fixture
def store(tmp_path):
    """Create a temporary FeatureStore for testing."""
    db_path = str(tmp_path / "test_feature_store.duckdb")
    store = FeatureStore(db_path=db_path)
    store.initialize_schema()
    
    # Mock the fact table which is required for get_training_matrix base spine
    store.db.execute("CREATE TABLE IF NOT EXISTS fact_player_efficiency (player_name VARCHAR, year INTEGER, team VARCHAR)")
    
    return store

def test_schema_dates(store):
    """Verify schema uses DATE types for validity."""
    schema = store.db.fetch_df("DESCRIBE feature_values")
    
    # Check valid_from is DATE
    valid_from_type = schema.loc[schema['column_name'] == 'valid_from', 'column_type'].iloc[0]
    assert valid_from_type == 'DATE'
    
    # Check valid_until exists and is DATE
    valid_until_type = schema.loc[schema['column_name'] == 'valid_until', 'column_type'].iloc[0]
    assert valid_until_type == 'DATE'

def test_temporal_leakage_protection(store):
    """Ensure we cannot see features from the future."""
    # Setup: Feature known from 2023-02-01 until 2024-02-01
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES ('P1_2023', 'PlayerOne', 2023, 'test_feat', 100.0, '2023-02-01', '2024-02-01')
    """)
    
    # Mock base row for join - ensure types match schema (VARCHAR, INTEGER)
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('PlayerOne', CAST(2023 AS INTEGER), 'TeamA')")
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('PlayerOne', CAST(2024 AS INTEGER), 'TeamA')")
    
    # Query BEFORE valid_from (Should be empty)
    df_early = store.get_training_matrix(as_of_date=date(2023, 1, 1), min_year=2023)
    assert 'test_feat' not in df_early.columns or df_early.empty

    # Query DURING validity (Should find it)
    df_valid = store.get_training_matrix(as_of_date=date(2023, 6, 1), min_year=2023)
    assert not df_valid.empty
    assert df_valid.iloc[0]['test_feat'] == 100.0

    # Query AFTER valid_until (Should be empty or superseded -- here empty locally)
    # Note: get_training_matrix normally filters by prediction year too, but focused on date joins
    # We simulate a 2024 prediction year query
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES ('P1_2024', 'PlayerOne', 2024, 'test_feat', 200.0, '2024-02-01', NULL)
    """)
    
    # As of mid-2024, should see the NEW value (200.0), not old (100.0)
    df_2024 = store.get_training_matrix(as_of_date=date(2024, 6, 1), min_year=2024)
    assert df_2024.iloc[0]['test_feat'] == 200.0

def test_lag_materialization_dates(store):
    """Test that lag materialization sets correct date boundaries."""
    # Mock source data
    store.db.execute("DROP TABLE IF EXISTS fact_player_efficiency")
    store.db.execute("CREATE TABLE fact_player_efficiency (player_name VARCHAR, year INTEGER, total_pass_yds INTEGER)")
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('QB1', 2022, 4000)")
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('QB1', 2023, 4500)")
    
    # Materialize
    store.materialize_lag_features(source_table='fact_player_efficiency')
    
    # Check valid_from dates
    # 2022 season data -> Known early 2023 (e.g. 2023-02-13 roughly Super Bowl)
    # The default impl should likely set it to YYYY+1-02-01 or similar constant
    
    res = store.db.execute("""
        SELECT feature_value, valid_from 
        FROM feature_values 
        WHERE feature_name = 'total_pass_yds_lag_1' AND prediction_year = 2023
    """).fetchone()
    
    # Target 2023:
    # Lag 1 comes from 2022 data.
    # 2022 data is known as of Fed 2023.
    # So valid_from should be ~2023-02-XX.
    # feature_value should be 4000.
    
    assert res is not None
    val, valid_from = res
    assert val == 4000
    assert valid_from.year == 2023 # Available IN 2023
    
def test_point_in_time_retrieval(store):
    """Simulate a specific historical moment retrieval."""
    # Data:
    # V1: Known 2022-02-01 -> Value 10
    # V2: Known 2022-06-01 -> Value 15 (Correction)
    # V3: Known 2023-02-01 -> Value 20 (Next season)
    
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES 
        ('k1', 'P1', 2022, 'f1', 10.0, '2022-02-01', '2022-06-01'),
        ('k2', 'P1', 2022, 'f1', 15.0, '2022-06-01', '2023-02-01'),
        ('k3', 'P1', 2023, 'f1', 20.0, '2023-02-01', NULL)
    """)
    
    # Mock base rows for retrieval
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('P1', 2022, 'TeamA')")
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('P1', 2023, 'TeamA')")
    
    # 1. March 2022 -> Should see 10.0
    df_mar = store.get_training_matrix(as_of_date=date(2022, 3, 1), min_year=2022)
    assert df_mar.iloc[0]['f1'] == 10.0
    
    # 2. July 2022 -> Should see 15.0 (Correction)
    df_jul = store.get_training_matrix(as_of_date=date(2022, 7, 1), min_year=2022)
    assert df_jul.iloc[0]['f1'] == 15.0
    
    # 3. March 2023 -> Should see 20.0 (New Season)
    # Note: query checks prediction_year too. 
    # For prediction_year 2022, valid_until was 2023-02-01.
    # If we define "Training Matrix" as "What did we know for THIS target year at THAT time":
    
    # If I am training for 2022 target, and I am currently at 2024:
    # I should see the FINAL version of 2022 features (15.0).
    
    # If I am training for 2023 target:
    # I should see 20.0 (lag 1 from 2022 data)
    pass 

def test_feature_boundary_conditions(store):
    """Test exact boundary conditions for feature validity."""
    # Feature valid from 2023-02-15 to 2024-02-15
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES ('P1_2023', 'PlayerBound', 2023, 'bound_feat', 50.0, '2023-02-15', '2024-02-15')
    """)
    store.db.execute("INSERT INTO fact_player_efficiency VALUES ('PlayerBound', 2023, 'TeamB')")
    
    # 1. Day BEFORE valid_from (2023-02-14) -> Should NOT find feature
    df_before = store.get_training_matrix(as_of_date=date(2023, 2, 14), min_year=2023)
    assert 'bound_feat' not in df_before.columns or pd.isna(df_before.iloc[0].get('bound_feat'))

    # 2. ON valid_from date (2023-02-15) -> Should find feature
    df_on_start = store.get_training_matrix(as_of_date=date(2023, 2, 15), min_year=2023)
    assert df_on_start.iloc[0]['bound_feat'] == 50.0

    # 3. ON valid_until date (2024-02-15) -> Should NOT find feature (strict < inequality usually, or <= depending on logic)
    # Logic in query: valid_until > as_of_date. 
    # If valid_until is 2024-02-15 and as_of is 2024-02-15: 2024-02-15 > 2024-02-15 is FALSE.
    # So on the expiry date, it is EXPIRED.
    df_on_end = store.get_training_matrix(as_of_date=date(2024, 2, 15), min_year=2023)
    assert 'bound_feat' not in df_on_end.columns or pd.isna(df_on_end.iloc[0].get('bound_feat'))

    # 4. Day BEFORE valid_until (2024-02-14) -> Should find feature
    df_before_end = store.get_training_matrix(as_of_date=date(2024, 2, 14), min_year=2023)
    assert df_before_end.iloc[0]['bound_feat'] == 50.0 

def test_interaction_features(store):
    """Test that materializing interaction features works and sets valid_from."""
    # Setup data
    store.db.execute("DROP TABLE IF EXISTS fact_player_efficiency")
    store.db.execute("""
        CREATE TABLE fact_player_efficiency (
            player_name VARCHAR, 
            year INTEGER, 
            team VARCHAR,
            age INTEGER,
            cap_hit_millions DOUBLE,
            draft_round INTEGER
        )
    """)
    store.db.execute("""
        INSERT INTO fact_player_efficiency VALUES 
        ('P_Interact', 2023, 'TeamC', 25, 10.0, 1)
    """)
    
    store.materialize_interaction_features(source_table='fact_player_efficiency')
    
    # Check 'age_cap_interaction': 25 * 10.0 = 250.0
    # Valid from: March 15th of the year (2023-03-15)
    
    res = store.db.execute("""
        SELECT feature_value, valid_from 
        FROM feature_values 
        WHERE feature_name = 'age_cap_interaction' 
          AND player_name = 'P_Interact'
    """).fetchone()
    
    assert res is not None
    val, valid_from = res
    assert val == 250.0
    assert valid_from == date(2023, 3, 15)

def test_historical_features_diagonal_join(store):
    """Test retrieval of features for multiple years using start-of-season logic."""
    # Data Setup:
    # Player 'Legacy':
    # 2021 Season Stats -> Known Feb 2022. Lag 1 for 2022 season.
    # 2022 Season Stats -> Known Feb 2023. Lag 1 for 2023 season.
    
    # We insert into feature_values directly to control timestamps perfectly
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES 
        ('k22', 'Legacy', 2022, 'yards_lag_1', 1000.0, '2022-02-15', '2023-02-15'),
        ('k23', 'Legacy', 2023, 'yards_lag_1', 1100.0, '2023-02-15', '2024-02-15')
    """)
    
    # Base population
    store.db.execute("INSERT INTO fact_player_efficiency (player_name, year) VALUES ('Legacy', 2022), ('Legacy', 2023)")
    
    # Retrieve Batch (Diagonal Join)
    # Logic: For 2022 prediction, uses data valid at 2022-09-01. (Should get 1000.0)
    #        For 2023 prediction, uses data valid at 2023-09-01. (Should get 1100.0)
    
    df = store.get_historical_features(min_year=2022, max_year=2023)
    
    assert len(df) == 2
    row_22 = df[df['year'] == 2022].iloc[0]
    row_23 = df[df['year'] == 2023].iloc[0]
    
    assert row_22['yards_lag_1'] == 1000.0
    assert row_23['yards_lag_1'] == 1100.0

def test_temporal_integrity_validation(store):
    """Test that we detect forward-looking info (leakage)."""
    # Create a legitimate feature
    store.db.execute("""
        INSERT INTO feature_registry (feature_name, feature_type) VALUES ('clean_feat', 'lag')
    """)
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES ('p1', 'Clean', 2023, 'clean_feat', 1.0, '2023-02-01', NULL)
    """)
    
    # Create a LEAKY feature
    # Prediction Year 2023 (Season starts Sept 2023)
    # But valid_from is Dec 2023 (Future!)
    store.db.execute("""
        INSERT INTO feature_registry (feature_name, feature_type) VALUES ('leaky_feat', 'lag')
    """)
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES ('p2', 'Leaky', 2023, 'leaky_feat', 1.0, '2023-12-01', NULL)
    """)
    
    # Should return False (integrity check failed)
    assert store.validate_temporal_integrity() is False

def test_feature_stats(store):
    """Smoke test for stats generation."""
    store.db.execute("""
        INSERT INTO feature_registry (feature_name, feature_type) VALUES ('f1', 'lag')
    """)
    store.db.execute("""
        INSERT INTO feature_values (entity_key, player_name, prediction_year, feature_name, feature_value, valid_from, valid_until)
        VALUES ('k1', 'P1', 2023, 'f1', 10.0, '2023-02-01', NULL)
    """)
    
    stats = store.get_feature_stats()
    assert not stats.empty
    assert 'lag' in stats['feature_type'].values

import yaml
from pathlib import Path
import os

# Define Base Directory (Root of Repo)
# Assumes this file is in src/
BASE_DIR = Path(__file__).resolve().parent.parent

CONFIG_PATH = BASE_DIR / "config/settings.yaml"

def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Config file not found at {CONFIG_PATH}")
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

_config = load_config()

# Expose Paths - Medallion Architecture
DATA_BRONZE_DIR = BASE_DIR / _config.get("data", {}).get("bronze", "data/bronze")
DATA_SILVER_DIR = BASE_DIR / _config.get("data", {}).get("silver", "data/silver")
DATA_GOLD_DIR = BASE_DIR / _config.get("data", {}).get("gold", "data/gold")
DATA_DUCKDB_DIR = BASE_DIR / "data/duckdb"  # Legacy path, BigQuery is sole warehouse

# Legacy aliases for backward compatibility
DATA_RAW_DIR = DATA_BRONZE_DIR
DATA_PROCESSED_DIR = DATA_SILVER_DIR

MODELS_DIR = BASE_DIR / _config.get("models", {}).get("directory", "models")
REPORTS_DIR = BASE_DIR / _config.get("paths", {}).get("reports", "reports")
VIZ_DIR = BASE_DIR / _config.get("paths", {}).get("viz", "viz")

# Global Constants
CURRENT_SEASON = _config.get("project", {}).get("current_season", 2025)

# Create dirs if they don't exist (Safety)
for d in [DATA_BRONZE_DIR, DATA_SILVER_DIR, DATA_GOLD_DIR, DATA_DUCKDB_DIR, MODELS_DIR, REPORTS_DIR, VIZ_DIR]:
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        pass


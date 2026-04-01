"""
Shared configuration loader for the NFL Dead Money project.
Centralizes access to settings.yaml to avoid hardcoded paths.
"""

import logging
import os
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Find config relative to this file or from project root
_CONFIG_PATHS = [
    Path(__file__).parent.parent / "config" / "settings.yaml",
    Path("config/settings.yaml"),
]

_config = None


def get_config():
    """Load and cache the project configuration."""
    global _config
    if _config is None:
        for path in _CONFIG_PATHS:
            if path.exists():
                with open(path) as f:
                    _config = yaml.safe_load(f)
                logger.debug(f"Loaded config from {path}")
                break
        if _config is None:
            raise FileNotFoundError(
                f"Could not find settings.yaml in any of: {_CONFIG_PATHS}"
            )
    return _config


def get_db_path():
    """
    Get the database path from config or environment.
    Returns the dataset name for BigQuery (connection handled by DBManager via GCP_PROJECT_ID).
    """
    env_path = os.getenv("DB_PATH")
    if env_path:
        logger.info(f"Using DB_PATH from environment: {env_path}")
        return env_path

    config = get_config()
    # Support both legacy 'database.path' and current 'database.dataset'
    db_path = config.get("database", {}).get("dataset") or config.get(
        "database", {}
    ).get("path")

    if not db_path:
        db_path = "nfl_dead_money"

    logger.info(f"Using DB path from config: {db_path}")
    return db_path


def get_bronze_dir():
    """Get the bronze data directory from config."""
    config = get_config()
    return Path(config.get("data", {}).get("bronze", "data/bronze"))


def get_model_dir():
    """Get the model directory from config."""
    config = get_config()
    return Path(config.get("models", {}).get("directory", "models"))

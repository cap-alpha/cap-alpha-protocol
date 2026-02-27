"""
Shared configuration loader for the NFL Dead Money project.
Centralizes access to settings.yaml to avoid hardcoded paths.
"""
import yaml
from pathlib import Path
import os
import logging
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
    Environment variable DB_PATH takes precedence over config.
    Fails explicitly if neither is set.
    """
    # Environment override takes precedence
    env_path = os.getenv("DB_PATH")
    if env_path:
        logger.info(f"Using DB_PATH from environment: {env_path}")
        return env_path
    
    # Fall back to config
    config = get_config()
    db_path = config.get("database", {}).get("path")
    
    if not db_path:
        raise ValueError(
            "Database path not configured. Set DB_PATH environment variable "
            "or configure database.path in config/settings.yaml"
        )
    
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

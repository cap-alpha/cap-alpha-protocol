import json
import logging
import os
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class MLGovernance:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = (
                Path(__file__).resolve().parent.parent / "config" / "ml_config.yaml"
            )
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        self.registry_path = Path(self.config["model_registry"]["registry_path"])
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_registry()

    def _load_registry(self):
        if self.registry_path.exists():
            with open(self.registry_path, "r") as f:
                self.registry = json.load(f)
        else:
            self.registry = {"production_model": None, "candidates": [], "history": []}

    def _save_registry(self):
        with open(self.registry_path, "w") as f:
            json.dump(self.registry, f, indent=2)

    def _get_git_sha(self):
        """Get current git commit SHA for artifact lineage."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def register_candidate(self, model_path, metrics, feature_names):
        entry = {
            "path": str(model_path),
            "timestamp": datetime.now().isoformat(),
            "git_sha": self._get_git_sha(),
            "metrics": metrics,
            "feature_names": feature_names,
            "status": "candidate",
        }
        self.registry["candidates"].append(entry)
        self._save_registry()
        logger.info(
            f"Registered new candidate model: {model_path} (SHA: {entry['git_sha'][:8]})"
        )

    def promote_to_production(self, model_path):
        # Archive current production if it exists
        if self.registry["production_model"]:
            current_prod = self.registry["production_model"]
            current_prod["status"] = "archived"
            self.registry["history"].append(current_prod)

        # Find the candidate and promote
        for i, candidate in enumerate(self.registry["candidates"]):
            if candidate["path"] == str(model_path):
                candidate["status"] = "production"
                self.registry["production_model"] = candidate
                self.registry["candidates"].pop(i)
                self._save_registry()
                logger.info(f"🚀 PROMOTED {model_path} to PRODUCTION")
                return True

        logger.error(f"Failed to promote {model_path}: Not found in candidates.")
        return False

    def get_production_model_info(self):
        return self.registry.get("production_model")

    def get_latest_candidate(self):
        if not self.registry["candidates"]:
            return None
        return self.registry["candidates"][-1]

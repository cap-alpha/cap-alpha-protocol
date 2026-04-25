"""
Export the FastAPI OpenAPI spec to docs/api/openapi.json.

Usage:
    python pipeline/scripts/export_openapi.py
    python pipeline/scripts/export_openapi.py --out path/to/output.json
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root or pipeline/
_PIPELINE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PIPELINE_DIR))

# Patch DB initialization so the import doesn't require live GCP credentials
from unittest.mock import patch  # noqa: E402

with patch("src.db_manager.DBManager._initialize_connection"):
    from api.main import app  # noqa: E402


def export(out_path: Path) -> None:
    spec = app.openapi()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(spec, f, indent=2)
    print(f"OpenAPI spec written to {out_path}  ({len(spec.get('paths', {}))} paths)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export FastAPI OpenAPI spec to JSON")
    default_out = (
        Path(__file__).resolve().parent.parent.parent / "docs" / "api" / "openapi.json"
    )
    parser.add_argument(
        "--out",
        default=str(default_out),
        help=f"Output path (default: {default_out})",
    )
    args = parser.parse_args()
    export(Path(args.out))


if __name__ == "__main__":
    main()

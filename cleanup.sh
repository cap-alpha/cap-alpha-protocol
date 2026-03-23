#!/bin/bash
# cleanup.sh
# Usage: sudo ./cleanup.sh (if permission is denied)

echo "Unlocking and deleting restrictive virtual environments and cached browsers..."

targets=(
    ".tmp_env_libs"            # Created: Feb 22 18:56:49 2026
    ".venv_broken"             # Created: Dec  7 12:56:49 2025
    ".venv_pipeline"           # Created: Feb 11 10:10:23 2026
    "bridge_venv"              # Created: Feb  7 13:21:18 2026
    "bridge_venv_v2"           # Created: Feb  8 04:29:14 2026
    "integration_venv"         # Created: Feb  7 15:52:10 2026
    "pipeline_env"             # Created: Feb 15 15:53:20 2026
    "test_venv"                # Created: Feb  7 13:14:13 2026
    "venv_fresh"               # Created: Feb 14 17:35:45 2026
    "venv_toxic_medallion"     # Created: Feb  7 11:08:54 2026
    "web/.playwright_tmp"      # Created: Feb 27 11:45:21 2026
    "web/.playwright_browsers" # Created: Feb 27 11:45:22 2026
)

for target in "${targets[@]}"; do
    if [ -d "$target" ]; then
        echo "Processing $target..."
        # Remove immutable flags if set (macOS)
        chflags -R nouchg "$target" 2>/dev/null
        # Force write permissions
        chmod -R u+rwX "$target" 2>/dev/null
        # Delete forcefully
        rm -rf "$target"
    fi
done

echo "Deleting log files..."
rm -f *.log
rm -f web/*.log

echo "Cleanup complete!"

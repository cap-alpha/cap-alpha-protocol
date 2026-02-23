import os
import shutil

target_dir = "/Users/andrewsmith/Documents/portfolio/nfl-dead-money/web/node_modules"
npm_cache = "/Users/andrewsmith/.npm"

for d in [target_dir, npm_cache]:
    try:
        shutil.rmtree(d, ignore_errors=True)
        print(f"Successfully cleared {d}")
    except Exception as e:
        print(f"Failed to clear {d}: {e}")

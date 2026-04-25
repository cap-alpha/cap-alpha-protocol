import os
import re
import shutil


def restore_archived_data():
    data_dir = "data"
    archive_dir = os.path.join(data_dir, "archive")
    target_dir = os.path.join(data_dir, "raw")
    symbols = [
        "spotrac_player_contracts_2024",
        "spotrac_player_rankings_2015",
        "spotrac_player_rankings_2016",
        "spotrac_player_rankings_2017",
        "spotrac_player_rankings_2024",
        "spotrac_player_rankings_2025",
        "spotrac_team_cap_2015",
        "spotrac_team_cap_2024",
        "spotrac_team_cap_2024_2026w05",
        "spotrac_team_cap_2026_2026w03",
    ]

    print(f"Restoring {len(symbols)} symbols from archive to {target_dir}...")

    # regex matches: raw_spotrac_player_contracts_2024_20260203_092440.csv
    # Group 1 = symbol, Group 2 = timestamp, Group 3 = ext
    pattern = re.compile(r"^(?:raw_|bronze_)?(.*?)_(\d{8}_\d{6})\.(\w+)$")

    restored_count = 0

    for symbol in symbols:
        candidates = []
        for file in os.listdir(archive_dir):
            if symbol in file:
                # Extract the timestamp to sort by newest
                match = re.search(r"_(\d{8}_\d{6})\.", file)
                if match:
                    candidates.append(
                        {
                            "filename": file,
                            "filepath": os.path.join(archive_dir, file),
                            "timestamp": match.group(1),
                        }
                    )

        if not candidates:
            print(f"  ❌ No archived candidates found for {symbol}")
            continue

        # Sort by timestamp descending (newest first)
        candidates.sort(key=lambda x: x["timestamp"], reverse=True)
        best = candidates[0]

        # Original name structure: {symbol}_{timestamp}.csv
        dest_filename = f"{symbol}_{best['timestamp']}.csv"
        dest_path = os.path.join(target_dir, dest_filename)

        print(f"  ✅ Restoring {symbol} -> {dest_filename}")
        shutil.copy2(best["filepath"], dest_path)
        restored_count += 1

    print(f"\nSuccessfully restored {restored_count}/{len(symbols)} complete files.")


if __name__ == "__main__":
    restore_archived_data()

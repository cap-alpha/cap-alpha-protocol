import json
import pathlib
import sys


def filter_history(start_year=2022, end_year=2024):
    input_path = pathlib.Path("reports/historical_predictions.json")
    if not input_path.exists():
        print(f"Error: {input_path} not found.")
        sys.exit(1)

    with open(input_path, "r") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} records.")

    # Filter for expanding window simulation range
    filtered_data = [
        row for row in data if start_year <= row.get("year", 0) <= end_year
    ]

    print(f"Filtered to {len(filtered_data)} records ({start_year}-{end_year}).")

    # Write back
    with open(input_path, "w") as f:
        json.dump(filtered_data, f, indent=2)

    print(f"Saved to {input_path}")


if __name__ == "__main__":
    filter_history()

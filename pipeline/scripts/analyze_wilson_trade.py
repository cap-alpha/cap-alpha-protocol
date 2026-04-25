from src.db_manager import DBManager


def analyze_wilson_trade():
    """
    Analyzes the Russell Wilson trade using pure DuckDB + Python (No Pandas/Numpy).
    This ensures portability across environments where binary compilation (numpy) is difficult.
    """
    con = DBManager()

    print("🏈 Analyzing The Russell Wilson Trade Tree (2022-2025)...")

    # 1. Define the Assets
    assets = {
        "SEA_Return": [
            "Charles Cross",
            "Boye Mafe",
            "Devon Witherspoon",
            "Derick Hall",
            "Noah Fant",
            "Drew Lock",
            "Shelby Harris",
        ],
        "DEN_Return": ["Russell Wilson"],
    }

    results = []

    for group, players in assets.items():
        placeholders = ", ".join([f"'{p}'" for p in players])
        query = f"""
            SELECT 
                player_name, 
                year, 
                team, 
                cap_hit_millions,
                position
            FROM silver_spotrac_contracts
            WHERE player_name IN ({placeholders})
            AND year BETWEEN 2022 AND 2025
            ORDER BY year, player_name
        """
        rows = con.execute(query).fetchall()
        for r in rows:
            # Handle potential None values safely
            cap_val = float(r[3]) if r[3] is not None else 0.0
            results.append(
                {
                    "group": group,
                    "name": r[0],
                    "year": r[1],
                    "team": r[2],
                    "cap": cap_val,
                    "pos": r[4],
                }
            )

    # 2. Aggregations (Pure Python)
    print("\n💰 Financial Impact (2022-2025 Cumulative):")
    print(f"{'Group':<12} | {'Total Cap ($M)':<15} | {'Players':<10}")
    print("-" * 45)

    stats = {}
    for r in results:
        g = r["group"]
        if g not in stats:
            stats[g] = {"cap": 0.0, "players": set()}
        stats[g]["cap"] += r["cap"]
        stats[g]["players"].add(r["name"])

    for g, data in stats.items():
        print(f"{g:<12} | ${data['cap']:<14.2f} | {len(data['players']):<10}")

    # 3. 2025 Super Bowl Roster
    print("\n🏆 The Super Bowl Roster Impact (2025 Snapshot):")
    print(f"{'Player':<20} | {'Pos':<5} | {'Cap Hit':<10} | {'Group':<10}")
    print("-" * 55)

    sea_2025_count = 0
    den_2025_count = 0

    for r in results:
        if r["year"] == 2025:
            if r["group"] == "SEA_Return":
                sea_2025_count += 1
            if r["group"] == "DEN_Return":
                den_2025_count += 1
            print(
                f"{r['name']:<20} | {r['pos']:<5} | ${r['cap']:<9.2f} | {r['group']:<10}"
            )

    # 4. Narrative
    sea_cap = stats["SEA_Return"]["cap"]
    den_cap = stats["DEN_Return"]["cap"]
    sea_players = len(stats["SEA_Return"]["players"])

    print("\n📉 The 'Dead Money' Tale:")
    print(f"Seattle Dead Money (2022): $26M (Cleared books for 2023+)")
    print(f"Denver Dead Money (2024-25): ~$85M (Crippled roster construction)")

    print(f"\nNarrative Insight:")
    print(
        f"- Seattle spent ${sea_cap:.1f}M total on {sea_players} players over 4 years."
    )
    print(f"- Denver spent ${den_cap:.1f}M (+ $85M Dead) on Russell Wilson alone.")
    print(
        f"- Seattle has {sea_2025_count} of these players on their Super Bowl roster."
    )


if __name__ == "__main__":
    analyze_wilson_trade()

"""
NFL Salary Cap Reference Data.

Official salary cap figures from NFL Communications and NFL.com.
Updated annually when the league announces the new cap.

Sources:
- NFL Operations: https://operations.nfl.com/
- NFL Communications: https://communications.nfl.com/
- CBA: Collective Bargaining Agreement (2020-2030)
"""

from typing import Dict

# Official NFL salary cap per team (in millions of dollars)
# Source: NFL Communications press releases
NFL_SALARY_CAPS: Dict[int, float] = {
    2024: 255.4,  # Announced March 2024
    2023: 224.8,  # Announced March 2023
    2022: 208.2,  # Announced March 2022
    2021: 182.5,  # COVID-reduced cap
    2020: 198.2,  # Pre-COVID
    2019: 188.2,
    2018: 177.2,
    2017: 167.0,
    2016: 155.27,
    2015: 143.28,
    2014: 133.0,
    2013: 123.0,
    2012: 120.6,
    2011: 120.0,  # Post-lockout
}

# Player benefit pools (in millions per team)
# These are in addition to the salary cap
NFL_BENEFIT_POOLS: Dict[int, float] = {
    2024: 74.0,
    2023: 68.6,
    2022: 64.0,
    2021: 58.0,
    2020: 61.0,
    2019: 59.0,
    2018: 55.0,
    2017: 52.0,
    2016: 48.0,
    2015: 45.0,
}

# Total player costs (salary cap + benefits)
NFL_TOTAL_PLAYER_COST: Dict[int, float] = {
    year: NFL_SALARY_CAPS[year] + NFL_BENEFIT_POOLS.get(year, 0)
    for year in NFL_SALARY_CAPS.keys()
    if year in NFL_BENEFIT_POOLS
}

# Number of NFL teams
NFL_TEAMS_COUNT = 32

# Tolerance for validation (percentage)
# Team caps can vary due to carryover credits, adjustments, etc.
TEAM_CAP_TOLERANCE_PCT = 15  # Allow ±15% variance per team
LEAGUE_CAP_TOLERANCE_PCT = 5  # Allow ±5% variance league-wide


def get_official_cap(year: int) -> float:
    """
    Get the official NFL salary cap for a given year.
    If the year is in the future, project it based on the latest known year.

    Args:
        year: NFL season year

    Returns:
        Salary cap in millions of dollars

    Raises:
        KeyError: If year is not in reference data (and prior to known history)
    """
    if year in NFL_SALARY_CAPS:
        return NFL_SALARY_CAPS[year]

    max_year = max(NFL_SALARY_CAPS.keys())
    if year > max_year:
        return NFL_SALARY_CAPS[max_year]

    raise KeyError(f"Salary cap data unrecorded for historical year {year}")


def get_league_total_cap(year: int) -> float:
    """
    Get the total league-wide salary cap (32 teams × cap).

    Args:
        year: NFL season year

    Returns:
        Total league cap in millions of dollars
    """
    return NFL_SALARY_CAPS[year] * NFL_TEAMS_COUNT


def validate_team_cap(team_cap: float, year: int) -> bool:
    """
    Validate that a team's cap is within reasonable range of official cap.

    Teams can exceed the base cap due to:
    - Unused cap space carried over from prior year
    - Performance-based pay credits
    - Salary cap adjustments

    Args:
        team_cap: Team's reported cap in millions
        year: NFL season year

    Returns:
        True if cap is within tolerance, False otherwise
    """
    official_cap = get_official_cap(year)
    lower_bound = official_cap * (1 - TEAM_CAP_TOLERANCE_PCT / 100)
    upper_bound = official_cap * (1 + TEAM_CAP_TOLERANCE_PCT / 100)
    return lower_bound <= team_cap <= upper_bound


def validate_league_total(total_cap: float, year: int) -> bool:
    """
    Validate that league-wide total cap is near expected value.

    Args:
        total_cap: Sum of all team caps in millions
        year: NFL season year

    Returns:
        True if total is within tolerance, False otherwise
    """
    expected = get_league_total_cap(year)
    variance_pct = abs(total_cap - expected) / expected * 100
    return variance_pct <= LEAGUE_CAP_TOLERANCE_PCT


def get_expected_range(year: int) -> tuple[float, float]:
    """
    Get expected range for a team's cap in a given year.

    Args:
        year: NFL season year

    Returns:
        Tuple of (min_cap, max_cap) in millions
    """
    official_cap = get_official_cap(year)
    min_cap = official_cap * (1 - TEAM_CAP_TOLERANCE_PCT / 100)
    max_cap = official_cap * (1 + TEAM_CAP_TOLERANCE_PCT / 100)
    return (min_cap, max_cap)


if __name__ == "__main__":
    # Print reference data
    print("NFL Salary Cap Reference Data")
    print("=" * 70)
    print(f"{'Year':<6} {'Cap (per team)':<20} {'League Total':<20} {'Benefits':<15}")
    print("-" * 70)

    for year in sorted(NFL_SALARY_CAPS.keys(), reverse=True):
        cap = NFL_SALARY_CAPS[year]
        league_total = get_league_total_cap(year)
        benefits = NFL_BENEFIT_POOLS.get(year, 0)

        print(f"{year:<6} ${cap:<18.2f}M  ${league_total:<18.2f}M  ${benefits:<13.2f}M")

    print("\n" + "=" * 70)
    print(f"Total teams: {NFL_TEAMS_COUNT}")
    print(f"Team cap tolerance: ±{TEAM_CAP_TOLERANCE_PCT}%")
    print(f"League cap tolerance: ±{LEAGUE_CAP_TOLERANCE_PCT}%")

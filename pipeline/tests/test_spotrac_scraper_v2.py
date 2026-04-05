import pandas as pd
import pandas as pd
from src.spotrac_scraper_v2 import SpotracParser


def test_normalize_player_contract_df_new_columns():
    parser = SpotracParser()

    # Mock data mirroring Spotrac headers
    data = {
        "Player": ["Patrick Mahomes", "Josh Allen"],
        "Team": ["KC", "BUF"],
        "Pos.": ["QB", "QB"],
        "Age": ["29", "28"],
        "Base Salary": ["$45,000,000", "$30,000,000"],
        "Prorated Bonus": ["$10,500,000", "$15,000,000"],
        "Roster Bonus": ["$2,000,000", "$5,000,000"],
        "Guaranteed At Sign": ["$141,481,905", "$100,000,000"],
        "Cap Hit": ["$57,500,000", "$50,000,000"],
        "Dead Cap": ["$100,000,000", "$80,000,000"],
    }
    df = pd.DataFrame(data)

    # Process through the parser
    normalized_df = parser.normalize_player_contract_df(df, 2024)

    # Assertions for the new columns
    assert "base_salary_millions" in normalized_df.columns
    assert "prorated_bonus_millions" in normalized_df.columns
    assert "roster_bonus_millions" in normalized_df.columns
    assert "guaranteed_salary_millions" in normalized_df.columns

    # Verify values
    mahomes = normalized_df[normalized_df["player_name"] == "Patrick Mahomes"].iloc[0]
    assert mahomes["base_salary_millions"] == 45.0
    assert mahomes["prorated_bonus_millions"] == 10.5
    assert mahomes["roster_bonus_millions"] == 2.0
    assert mahomes["guaranteed_salary_millions"] == 141.481905

    allen = normalized_df[normalized_df["player_name"] == "Josh Allen"].iloc[0]
    assert allen["base_salary_millions"] == 30.0
    assert allen["prorated_bonus_millions"] == 15.0
    assert allen["roster_bonus_millions"] == 5.0
    assert allen["guaranteed_salary_millions"] == 100.0


if __name__ == "__main__":
    test_normalize_player_contract_df_new_columns()
    print("ALL TESTS PASSED")

import unittest
import sys
import os

# Add scripts to path to import scrape_penalties
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../scripts")))

from scrape_penalties import validate_data


class TestPenaltyValidation(unittest.TestCase):

    def test_no_data_raises_error(self):
        """Test that empty data raises a critical error."""
        with self.assertRaises(ValueError) as context:
            validate_data([], 2024)
        self.assertIn("No penalty data scraped", str(context.exception))

    def test_insane_penalty_yards(self):
        """Test that > 2000 yards for a team raises error."""
        bad_data = [
            {"team_city": "BadTeam", "penalty_yards": "2500"},
            {"team_city": "BadTeam", "penalty_yards": "10"},
        ]
        with self.assertRaises(ValueError) as context:
            validate_data(bad_data, 2024)
        self.assertIn("exceeds sanity limit", str(context.exception))

    def test_ghost_team_filtering(self):
        """Test that rows with empty team names are filtered out."""
        data = [
            {"team_city": "GoodTeam", "penalty_yards": "50"},
            {"team_city": "", "penalty_yards": "5000"},  # Ghost row
        ]
        clean = validate_data(data, 2024)
        self.assertEqual(len(clean), 1)
        self.assertEqual(clean[0]["team_city"], "GoodTeam")

    def test_valid_data(self):
        """Test that normal data passes."""
        data = [
            {"team_city": "SEA", "penalty_yards": "50"},
            {"team_city": "NE", "penalty_yards": "20"},
        ]
        clean = validate_data(data, 2024)
        self.assertEqual(len(clean), 2)


if __name__ == "__main__":
    unittest.main()

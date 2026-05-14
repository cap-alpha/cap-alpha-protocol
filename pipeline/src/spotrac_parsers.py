"""
Spotrac Parser — pure parse/normalize/validate logic.

Extracted from spotrac_scraper_v2.py so that the testable surface (HTML parsing,
column normalisation, data quality checks) can be covered by unit tests without
requiring a live Selenium/browser session.

The Selenium driver class (SpotracScraper) and the scrape_and_save_* wrappers
remain in spotrac_scraper_v2.py and import from here.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _build_run_tags(run_timestamp: Optional[datetime] = None) -> tuple[str, str]:
    """Return iso-week tag and timestamp strings for consistent filenames."""
    ts = run_timestamp or datetime.utcnow()
    iso = ts.isocalendar()
    iso_week_tag = f"{iso.year}w{iso.week:02d}"
    timestamp = ts.strftime("%Y%m%d_%H%M%S")
    return iso_week_tag, timestamp


class DataQualityError(Exception):
    """Raised when data quality checks fail"""

    pass


def _deduplicate_headers(headers: List[str]) -> List[str]:
    """Ensure all headers are unique by appending a suffix to duplicates."""
    seen = {}
    new_headers = []
    for h in headers:
        if not h:
            h = "unnamed"
        if h in seen:
            seen[h] += 1
            new_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            new_headers.append(h)
    return new_headers


class SpotracParser:
    """Handles parsing and normalization of Spotrac HTML content."""

    def __init__(self):
        from bs4 import BeautifulSoup

        self.bs = BeautifulSoup

    def parse_table(
        self, html: str, selector: Optional[str] = None
    ) -> Tuple[List[str], List[List[str]]]:
        """Extract headers and rows from first valid table in HTML."""
        soup = self.bs(html, "html.parser")
        table = None

        # Priority selectors
        if selector:
            table = soup.select_one(selector)

        if not table:
            tables = soup.find_all("table", {"class": "dataTable"})
            for tbl in tables:
                if tbl.find("tbody"):
                    table = tbl
                    break

        if not table:
            for tbl in soup.find_all("table"):
                if tbl.find("tbody"):
                    table = tbl
                    break

        if not table:
            return [], []

        # Headers
        thead = table.find("thead")
        headers = []
        if thead:
            headers = [
                th.text.strip().replace("\n", " ").lower()
                for th in thead.find_all("th")
            ]
            headers = _deduplicate_headers(headers)

        # Rows
        rows = []
        tbody = table.find("tbody")
        if tbody:
            for tr in tbody.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                row = [td.text.strip().replace("\n", " ") for td in tds]
                if row:
                    rows.append(row)

        return headers, rows

    def parse_rankings_list_group(self, html: str) -> Tuple[List[str], List[List[str]]]:
        """
        Extract data from Spotrac's new div-based list-group structure for rankings.
        Returns generic headers ['rank', 'player', 'team', 'value'] and row data.
        """
        soup = self.bs(html, "html.parser")
        rows = []

        # Find all list-group-items that look like player rows
        # Structure: li.list-group-item > ... > div.link > a (Player)
        # Value is usually in a span.medium or span.bold

        items = soup.find_all("li", class_="list-group-item")
        if not items:
            return [], []

        for item in items:
            # Player Name
            link_div = item.find("div", class_="link")
            if not link_div:
                continue

            player_a = link_div.find("a")
            if not player_a:
                continue
            player_name = player_a.text.strip()

            # Team/Pos line often looks like: "KC, QB" inside a small tag or similar
            team_str = "Unknown"
            pos_str = "Unknown"
            small_tag = item.find("small")
            if small_tag:
                parts = small_tag.text.strip().split(",")
                if len(parts) >= 1:
                    team_str = parts[0].strip()
                if len(parts) >= 2:
                    pos_str = parts[1].strip()

            # Value (Cap Hit / salary)
            value_str = "0"
            val_span = item.find("span", class_="medium")
            if not val_span:
                val_span = item.find("span", class_="bold")
            if val_span:
                value_str = val_span.text.strip()

            # Rank
            rank_span = item.find("span", class_="rank-value")
            rank = rank_span.text.strip() if rank_span else str(len(rows) + 1)

            # Age is not present in the list-group structure
            age = ""

            # Construct row: [Rank, Player, Team, Pos, Age, Value]
            rows.append([rank, player_name, team_str, pos_str, age, value_str])

        headers = ["rank", "player", "team", "pos", "age", "value"]
        return headers, rows

    def parse_money(self, value) -> float:
        """Parse money string like '$255.4M' or '$60,985,272' to millions"""
        # Guard against Series/array values before any comparisons
        if isinstance(value, (pd.Series, pd.DataFrame)):
            if len(value) > 0:
                value = value.iloc[0]
            else:
                return 0.0

        try:
            if pd.isna(value):
                return 0.0
        except (ValueError, TypeError):
            pass
        if value is None or value == "-" or value == "":
            return 0.0

        # Clean the string
        clean_val = str(value).replace("$", "").replace(",", "").strip()

        try:
            if "M" in clean_val:
                return float(clean_val.replace("M", ""))
            elif "B" in clean_val:
                return float(clean_val.replace("B", "")) * 1000.0
            elif "K" in clean_val:
                return float(clean_val.replace("K", "")) / 1000.0
            else:
                # Assume raw dollars
                return float(clean_val) / 1_000_000.0
        except (ValueError, TypeError):
            return 0.0

    def normalize_player_contract_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Normalize contract columns from team contracts pages"""
        col_map = {}
        mapped_targets = set()

        for col in df.columns:
            col_lower = col.lower()
            target = None
            if (
                "player" in col_lower or "name" in col_lower
            ) and "player_name" not in mapped_targets:
                target = "player_name"
            elif (
                "team" in col_lower
                and "avg" not in col_lower
                and "team" not in mapped_targets
            ):
                target = "team"
            elif "pos" in col_lower and "position" not in mapped_targets:
                target = "position"
            elif (
                ("contract" in col_lower and "value" in col_lower)
                or col_lower == "value"
            ) and "total_contract_value" not in mapped_targets:
                target = "total_contract_value"
            elif (
                ("guaranteed" in col_lower or "guarantee" in col_lower)
                and "sign" not in col_lower
                and "guaranteed_money" not in mapped_targets
            ):
                target = "guaranteed_money"
            elif (
                "guaranteed" in col_lower
                and "sign" in col_lower
                and "guaranteed_salary" not in mapped_targets
            ):
                target = "guaranteed_salary"
            elif (
                "signing" in col_lower
                and "bonus" in col_lower
                and "signing_bonus" not in mapped_targets
            ):
                target = "signing_bonus"
            elif (
                "base" in col_lower
                and "salary" in col_lower
                and "base_salary" not in mapped_targets
            ):
                target = "base_salary"
            elif (
                "prorated" in col_lower
                and "bonus" in col_lower
                and "prorated_bonus" not in mapped_targets
            ):
                target = "prorated_bonus"
            elif (
                "roster" in col_lower
                and "bonus" in col_lower
                and "roster_bonus" not in mapped_targets
            ):
                target = "roster_bonus"
            elif (
                "contract" in col_lower
                and "year" in col_lower
                and "contract_length_years" not in mapped_targets
            ):
                target = "contract_length_years"
            elif (
                "years" in col_lower
                and "remaining" in col_lower
                and "years_remaining" not in mapped_targets
            ):
                target = "years_remaining"
            elif (
                "cap" in col_lower
                and "hit" in col_lower
                and "cap_hit" not in mapped_targets
            ):
                target = "cap_hit"
            elif (
                "dead" in col_lower
                and "cap" in col_lower
                and "dead_cap" not in mapped_targets
            ):
                target = "dead_cap"
            elif "age" in col_lower and "age" not in mapped_targets:
                target = "age"

            if target:
                col_map[col] = target
                mapped_targets.add(target)

        df = df.rename(columns=col_map).copy()

        # Parse money columns
        money_cols = [
            "total_contract_value",
            "guaranteed_money",
            "signing_bonus",
            "cap_hit",
            "dead_cap",
            "guaranteed_salary",
            "base_salary",
            "prorated_bonus",
            "roster_bonus",
        ]
        for col in money_cols:
            if col in df.columns:
                df[f"{col}_millions"] = df[col].apply(self.parse_money)

        # Parse Age (ensure numeric, handle missing)
        if "age" in df.columns:
            df["age"] = pd.to_numeric(df["age"], errors="coerce")

        df["year"] = year
        keep_cols = [
            "player_name",
            "team",
            "position",
            "age",
            "year",
            "total_contract_value_millions",
            "guaranteed_money_millions",
            "signing_bonus_millions",
            "contract_length_years",
            "years_remaining",
            "cap_hit_millions",
            "dead_cap_millions",
            "base_salary_millions",
            "prorated_bonus_millions",
            "roster_bonus_millions",
            "guaranteed_salary_millions",
        ]
        df = df[[c for c in keep_cols if c in df.columns]]

        if "player_name" in df.columns:
            df = df.dropna(subset=["player_name"])
            df = df[df["player_name"].str.strip() != ""]

        return df

    def validate_player_contract_data(self, df: pd.DataFrame, year: int):
        """Run data quality checks on player contract data"""
        if df.empty:
            raise DataQualityError(f"No contract data found for {year}")

        required = ["player_name", "team", "year"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing required columns: {missing}")

        if "player_name" in df.columns and df["player_name"].isnull().sum() > 0:
            logger.warning(
                f"⚠️ Detected {df['player_name'].isnull().sum()} null player names"
            )

        unique_teams = df["team"].nunique()
        if unique_teams < 1:
            raise DataQualityError(f"Expected at least one team, got {unique_teams}")

    def normalize_team_cap_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Normalize column names and parse monetary values"""
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if "team" in col_lower and "team" not in col_map.values():
                col_map[col] = "team"
            elif "active" in col_lower and "cap" in col_lower:
                col_map[col] = "active_cap"
            elif "dead" in col_lower and ("money" in col_lower or "cap" in col_lower):
                col_map[col] = "dead_money"
            elif "total" in col_lower and "cap" in col_lower:
                col_map[col] = "salary_cap"
            elif "space" in col_lower:
                col_map[col] = "cap_space"

        df = df.rename(columns=col_map)
        df["year"] = year

        money_cols = ["active_cap", "dead_money", "salary_cap", "cap_space"]
        for col in money_cols:
            if col in df.columns:
                df[f"{col}_millions"] = df[col].apply(self.parse_money)

        # Calculate dead cap %
        if "dead_money_millions" in df.columns and "salary_cap_millions" in df.columns:
            df["dead_cap_pct"] = (
                df["dead_money_millions"] / df["salary_cap_millions"]
            ) * 100

        # Keep only standardized columns
        keep_cols = [
            "team",
            "year",
            "salary_cap_millions",
            "active_cap_millions",
            "dead_money_millions",
            "cap_space_millions",
            "dead_cap_pct",
        ]
        df = df[[c for c in keep_cols if c in df.columns]]

        return df

    def validate_team_cap_data(self, df: pd.DataFrame, year: int):
        """Run data quality checks on team cap data"""
        if len(df) < 30:
            raise DataQualityError(f"Expected ≥30 team records, got {len(df)}")
        required = ["team", "year", "salary_cap_millions"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing required columns: {missing}")

    def normalize_player_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Generic normalization for any player-related table."""
        col_map = {}
        mapped_targets = set()

        for col in df.columns:
            col_lower = str(col).lower()
            target = None
            if (
                "player" in col_lower or "name" in col_lower
            ) and "player_name" not in mapped_targets:
                target = "player_name"
            elif (
                "team" in col_lower
                and "avg" not in col_lower
                and "team" not in mapped_targets
            ):
                target = "team"
            elif "pos" in col_lower and "position" not in mapped_targets:
                target = "position"
            elif (
                "salary" in col_lower or "compensation" in col_lower
            ) and "salary" not in mapped_targets:
                target = "salary"
            elif (
                "cap" in col_lower
                and "hit" in col_lower
                and "cap_hit" not in mapped_targets
            ):
                target = "cap_hit"
            elif (
                "dead" in col_lower
                and "money" in col_lower
                and "dead_money" not in mapped_targets
            ):
                target = "dead_money"
            elif (
                ("contract" in col_lower and "value" in col_lower)
                or col_lower == "value"
            ) and "total_contract_value" not in mapped_targets:
                target = "total_contract_value"
            elif (
                "guaranteed" in col_lower or "guarantee" in col_lower
            ) and "guaranteed_money" not in mapped_targets:
                target = "guaranteed_money"

            if target:
                col_map[col] = target
                mapped_targets.add(target)

        df = df.rename(columns=col_map).copy()

        # Parse money
        money_cols = [
            "salary",
            "cap_hit",
            "dead_money",
            "total_contract_value",
            "guaranteed_money",
        ]
        for col in money_cols:
            if col in df.columns:
                df[f"{col}_millions"] = df[col].apply(self.parse_money)

        df["year"] = year
        if "player_name" in df.columns:
            df = df.dropna(subset=["player_name"])
            df = df[df["player_name"].str.strip() != ""]

        return df

    def validate_player_data(self, df: pd.DataFrame, year: int, min_rows: int = 30):
        """Run data quality checks on player data"""
        # For historical years, the Dead Money page might be a team summary (32 teams)
        # or a full player list. We accept both if >= min_rows.
        if len(df) < min_rows:
            raise DataQualityError(f"Expected ≥{min_rows} records, got {len(df)}")
        required = ["player_name", "team", "year"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing columns: {missing}")

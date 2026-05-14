"""
Unit tests for pipeline/src/spotrac_parsers.py

Covers every parser, normalize, and validate method against the HTML fixtures in
pipeline/tests/fixtures/spotrac/.  Target: ≥80% line coverage on spotrac_parsers.py.

Run:
    make test
or:
    .venv/bin/pytest pipeline/tests/test_spotrac_parsers.py -v
"""

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.spotrac_parsers import (
    DataQualityError,
    SpotracParser,
    _build_run_tags,
    _deduplicate_headers,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "spotrac"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_fixture(name: str) -> str:
    path = FIXTURE_DIR / name
    assert path.exists(), f"Fixture missing: {path}"
    return path.read_text()


# ---------------------------------------------------------------------------
# _build_run_tags
# ---------------------------------------------------------------------------


class TestBuildRunTags:
    def test_returns_tuple_of_two_strings(self):
        tag, ts = _build_run_tags()
        assert isinstance(tag, str)
        assert isinstance(ts, str)

    def test_iso_week_format(self):
        dt = datetime(2024, 1, 15)  # Week 3 of 2024
        tag, _ = _build_run_tags(dt)
        assert tag.startswith("2024w")
        assert len(tag) == len("2024w03")

    def test_timestamp_format(self):
        dt = datetime(2024, 6, 1, 12, 30, 0)
        _, ts = _build_run_tags(dt)
        assert ts == "20240601_123000"

    def test_defaults_to_now(self):
        tag, ts = _build_run_tags()
        now = datetime.utcnow()
        assert str(now.year) in tag
        # timestamp starts with current year
        assert ts.startswith(str(now.year))


# ---------------------------------------------------------------------------
# _deduplicate_headers
# ---------------------------------------------------------------------------


class TestDeduplicateHeaders:
    def test_no_duplicates_unchanged(self):
        headers = ["player", "team", "cap_hit"]
        assert _deduplicate_headers(headers) == ["player", "team", "cap_hit"]

    def test_duplicate_gets_suffix(self):
        headers = ["player", "player"]
        result = _deduplicate_headers(headers)
        assert result[0] == "player"
        assert result[1] == "player_1"

    def test_triple_duplicate(self):
        headers = ["x", "x", "x"]
        result = _deduplicate_headers(headers)
        assert result == ["x", "x_1", "x_2"]

    def test_empty_header_becomes_unnamed(self):
        headers = [""]
        result = _deduplicate_headers(headers)
        assert result == ["unnamed"]

    def test_empty_duplicates(self):
        headers = ["", ""]
        result = _deduplicate_headers(headers)
        assert result[0] == "unnamed"
        assert result[1] == "unnamed_1"

    def test_empty_list(self):
        assert _deduplicate_headers([]) == []


# ---------------------------------------------------------------------------
# DataQualityError
# ---------------------------------------------------------------------------


class TestDataQualityError:
    def test_is_exception(self):
        assert issubclass(DataQualityError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(DataQualityError, match="something went wrong"):
            raise DataQualityError("something went wrong")


# ---------------------------------------------------------------------------
# SpotracParser.parse_money
# ---------------------------------------------------------------------------


class TestParseMoneyMethod:
    def setup_method(self):
        self.parser = SpotracParser()

    def test_millions_suffix(self):
        assert self.parser.parse_money("$45.5M") == 45.5

    def test_billions_suffix(self):
        assert self.parser.parse_money("$1.2B") == 1200.0

    def test_thousands_suffix(self):
        assert self.parser.parse_money("$500K") == pytest.approx(0.5)

    def test_raw_dollars(self):
        assert self.parser.parse_money("$60,985,272") == pytest.approx(60.985272)

    def test_zero_for_dash(self):
        assert self.parser.parse_money("-") == 0.0

    def test_zero_for_none(self):
        assert self.parser.parse_money(None) == 0.0

    def test_zero_for_empty_string(self):
        assert self.parser.parse_money("") == 0.0

    def test_zero_for_nan(self):
        import math

        assert math.isnan(self.parser.parse_money(float("nan"))) is False
        assert self.parser.parse_money(float("nan")) == 0.0

    def test_zero_for_garbage(self):
        assert self.parser.parse_money("N/A") == 0.0

    def test_pandas_series_uses_first_element(self):
        s = pd.Series(["$10.0M", "$20.0M"])
        assert self.parser.parse_money(s) == 10.0

    def test_empty_series_returns_zero(self):
        s = pd.Series([], dtype=str)
        assert self.parser.parse_money(s) == 0.0


# ---------------------------------------------------------------------------
# SpotracParser.parse_table — from HTML fixture
# ---------------------------------------------------------------------------


class TestParseTable:
    def setup_method(self):
        self.parser = SpotracParser()

    def test_team_cap_fixture_headers(self):
        html = _read_fixture("team_cap_2024.html")
        headers, rows = self.parser.parse_table(html)
        assert len(headers) >= 3
        # At least one header should mention "team" or "cap"
        combined = " ".join(headers).lower()
        assert "team" in combined or "cap" in combined

    def test_team_cap_fixture_rows(self):
        html = _read_fixture("team_cap_2024.html")
        headers, rows = self.parser.parse_table(html)
        assert len(rows) >= 30, f"Expected ≥30 rows, got {len(rows)}"

    def test_player_contracts_fixture_rows(self):
        html = _read_fixture("player_contracts_2024.html")
        headers, rows = self.parser.parse_table(html)
        assert len(rows) >= 3

    def test_player_salaries_fixture_rows(self):
        html = _read_fixture("player_salaries_2024.html")
        headers, rows = self.parser.parse_table(html)
        assert len(rows) >= 30

    def test_empty_html_returns_empty(self):
        headers, rows = self.parser.parse_table("<html></html>")
        assert headers == []
        assert rows == []

    def test_table_without_tbody_skipped(self):
        html = "<table><thead><tr><th>A</th></tr></thead></table>"
        headers, rows = self.parser.parse_table(html)
        assert rows == []

    def test_custom_selector_used(self):
        html = """
        <table id="other"><tbody><tr><td>X</td><td>Y</td></tr></tbody></table>
        <table id="target" class="dataTable">
          <thead><tr><th>col1</th><th>col2</th></tr></thead>
          <tbody><tr><td>a</td><td>b</td></tr></tbody>
        </table>"""
        headers, rows = self.parser.parse_table(html, selector="table#target")
        assert "col1" in headers
        assert rows[0] == ["a", "b"]

    def test_rows_with_only_one_cell_skipped(self):
        html = """
        <table class="dataTable">
          <thead><tr><th>A</th><th>B</th></tr></thead>
          <tbody>
            <tr><td>only one</td></tr>
            <tr><td>two</td><td>cells</td></tr>
          </tbody>
        </table>"""
        _, rows = self.parser.parse_table(html)
        assert len(rows) == 1
        assert rows[0] == ["two", "cells"]

    def test_deduplicated_headers_applied(self):
        html = """
        <table class="dataTable">
          <thead><tr><th>cap</th><th>cap</th></tr></thead>
          <tbody><tr><td>1</td><td>2</td></tr></tbody>
        </table>"""
        headers, _ = self.parser.parse_table(html)
        assert headers[0] == "cap"
        assert headers[1] == "cap_1"


# ---------------------------------------------------------------------------
# SpotracParser.parse_rankings_list_group
# ---------------------------------------------------------------------------


class TestParseRankingsListGroup:
    def setup_method(self):
        self.parser = SpotracParser()

    def test_rankings_fixture(self):
        html = _read_fixture("player_rankings_2024.html")
        headers, rows = self.parser.parse_rankings_list_group(html)
        assert headers == ["rank", "player", "team", "pos", "age", "value"]
        assert len(rows) >= 3

    def test_player_names_extracted(self):
        html = _read_fixture("player_rankings_2024.html")
        _, rows = self.parser.parse_rankings_list_group(html)
        players = [r[1] for r in rows]
        assert "Patrick Mahomes" in players

    def test_team_extracted(self):
        html = _read_fixture("player_rankings_2024.html")
        _, rows = self.parser.parse_rankings_list_group(html)
        teams = [r[2] for r in rows]
        assert "KC" in teams

    def test_value_extracted(self):
        html = _read_fixture("player_rankings_2024.html")
        _, rows = self.parser.parse_rankings_list_group(html)
        mahomes_row = next(r for r in rows if r[1] == "Patrick Mahomes")
        assert "$57.5M" in mahomes_row[5] or "57" in mahomes_row[5]

    def test_empty_html_returns_empty(self):
        headers, rows = self.parser.parse_rankings_list_group("<html></html>")
        assert headers == []
        assert rows == []

    def test_item_without_link_div_skipped(self):
        html = """
        <ul class="list-group">
          <li class="list-group-item">no link div here</li>
          <li class="list-group-item">
            <div class="link"><a href="#">Player</a></div>
            <span class="rank-value">1</span>
            <span class="medium">$10M</span>
          </li>
        </ul>"""
        _, rows = self.parser.parse_rankings_list_group(html)
        assert len(rows) == 1

    def test_rank_defaults_to_row_index_plus_one(self):
        html = """
        <ul class="list-group">
          <li class="list-group-item">
            <div class="link"><a href="#">Player A</a></div>
            <span class="medium">$5M</span>
          </li>
        </ul>"""
        _, rows = self.parser.parse_rankings_list_group(html)
        assert rows[0][0] == "1"

    def test_bold_span_used_when_medium_absent(self):
        html = """
        <ul class="list-group">
          <li class="list-group-item">
            <div class="link"><a href="#">Player B</a></div>
            <span class="bold">$20M</span>
          </li>
        </ul>"""
        _, rows = self.parser.parse_rankings_list_group(html)
        assert "$20M" in rows[0][5]


# ---------------------------------------------------------------------------
# SpotracParser.normalize_team_cap_df
# ---------------------------------------------------------------------------


class TestNormalizeTeamCapDf:
    def setup_method(self):
        self.parser = SpotracParser()

    def _make_df(self):
        return pd.DataFrame(
            {
                "Team": ["KC", "BUF"],
                "Active Cap": ["$220,000,000", "$215,000,000"],
                "Dead Money": ["$12,500,000", "$11,000,000"],
                "Total Cap": ["$232,500,000", "$226,000,000"],
                "Cap Space": ["$22,500,000", "$29,000,000"],
            }
        )

    def test_returns_dataframe(self):
        df = self.parser.normalize_team_cap_df(self._make_df(), 2024)
        assert isinstance(df, pd.DataFrame)

    def test_year_column_added(self):
        df = self.parser.normalize_team_cap_df(self._make_df(), 2024)
        assert "year" in df.columns
        assert (df["year"] == 2024).all()

    def test_money_columns_parsed_to_millions(self):
        df = self.parser.normalize_team_cap_df(self._make_df(), 2024)
        assert "active_cap_millions" in df.columns
        assert "dead_money_millions" in df.columns
        assert df["active_cap_millions"].iloc[0] == pytest.approx(220.0)
        assert df["dead_money_millions"].iloc[0] == pytest.approx(12.5)

    def test_dead_cap_pct_calculated(self):
        df = self.parser.normalize_team_cap_df(self._make_df(), 2024)
        assert "dead_cap_pct" in df.columns
        # 12.5 / 232.5 * 100 ≈ 5.38%
        assert df["dead_cap_pct"].iloc[0] == pytest.approx(12.5 / 232.5 * 100, rel=1e-3)

    def test_with_fixture_html(self):
        html = _read_fixture("team_cap_2024.html")
        headers, rows = self.parser.parse_table(html)
        raw_df = pd.DataFrame(rows, columns=headers[: len(rows[0])])
        df = self.parser.normalize_team_cap_df(raw_df, 2024)
        assert not df.empty
        assert "year" in df.columns


# ---------------------------------------------------------------------------
# SpotracParser.validate_team_cap_data
# ---------------------------------------------------------------------------


class TestValidateTeamCapData:
    def setup_method(self):
        self.parser = SpotracParser()

    def _make_valid_df(self, n=32):
        return pd.DataFrame(
            {
                "team": [f"Team{i}" for i in range(n)],
                "year": [2024] * n,
                "salary_cap_millions": [255.0] * n,
            }
        )

    def test_valid_df_does_not_raise(self):
        self.parser.validate_team_cap_data(self._make_valid_df(), 2024)

    def test_too_few_rows_raises(self):
        with pytest.raises(DataQualityError, match="30"):
            self.parser.validate_team_cap_data(self._make_valid_df(n=10), 2024)

    def test_missing_required_column_raises(self):
        df = self._make_valid_df().drop(columns=["salary_cap_millions"])
        with pytest.raises(DataQualityError, match="salary_cap_millions"):
            self.parser.validate_team_cap_data(df, 2024)


# ---------------------------------------------------------------------------
# SpotracParser.normalize_player_contract_df
# ---------------------------------------------------------------------------


class TestNormalizePlayerContractDf:
    def setup_method(self):
        self.parser = SpotracParser()

    def _make_df(self):
        return pd.DataFrame(
            {
                "Player": ["Patrick Mahomes", "Josh Allen", ""],
                "Team": ["KC", "BUF", "PHI"],
                "Pos.": ["QB", "QB", "QB"],
                "Age": ["28", "27", "25"],
                "Contract Value": ["$450,000,000", "$258,000,000", "$255,000,000"],
                "Guaranteed": ["$141,481,905", "$150,000,000", "$179,304,500"],
                "Signing Bonus": ["$26,640,000", "$20,000,000", "$27,000,000"],
                "Base Salary": ["$45,000,000", "$30,000,000", "$37,500,000"],
                "Contract Years": ["10", "6", "5"],
                "Years Remaining": ["8", "4", "4"],
                "Cap Hit": ["$57,500,000", "$43,000,000", "$51,000,000"],
                "Dead Cap": ["$100,000,000", "$120,000,000", "$179,304,500"],
            }
        )

    def test_player_name_column_mapped(self):
        df = self.parser.normalize_player_contract_df(self._make_df(), 2024)
        assert "player_name" in df.columns

    def test_empty_player_name_rows_dropped(self):
        df = self.parser.normalize_player_contract_df(self._make_df(), 2024)
        assert len(df) == 2

    def test_money_columns_parsed(self):
        df = self.parser.normalize_player_contract_df(self._make_df(), 2024)
        mahomes = df[df["player_name"] == "Patrick Mahomes"].iloc[0]
        assert mahomes["cap_hit_millions"] == pytest.approx(57.5)
        assert mahomes["base_salary_millions"] == pytest.approx(45.0)

    def test_year_column_added(self):
        df = self.parser.normalize_player_contract_df(self._make_df(), 2024)
        assert (df["year"] == 2024).all()

    def test_age_numeric(self):
        df = self.parser.normalize_player_contract_df(self._make_df(), 2024)
        assert pd.api.types.is_float_dtype(df["age"]) or pd.api.types.is_integer_dtype(
            df["age"]
        )

    def test_with_fixture_html(self):
        html = _read_fixture("player_contracts_2024.html")
        headers, rows = self.parser.parse_table(html)
        raw_df = pd.DataFrame(rows, columns=headers[: len(rows[0])])
        df = self.parser.normalize_player_contract_df(raw_df, 2024)
        assert "player_name" in df.columns
        assert not df.empty

    def test_prorated_bonus_column(self):
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
        df = self.parser.normalize_player_contract_df(pd.DataFrame(data), 2024)
        assert "prorated_bonus_millions" in df.columns
        assert "roster_bonus_millions" in df.columns
        mahomes = df[df["player_name"] == "Patrick Mahomes"].iloc[0]
        assert mahomes["prorated_bonus_millions"] == pytest.approx(10.5)
        assert mahomes["roster_bonus_millions"] == pytest.approx(2.0)
        assert mahomes["guaranteed_salary_millions"] == pytest.approx(141.481905)


# ---------------------------------------------------------------------------
# SpotracParser.validate_player_contract_data
# ---------------------------------------------------------------------------


class TestValidatePlayerContractData:
    def setup_method(self):
        self.parser = SpotracParser()

    def _make_valid_df(self):
        return pd.DataFrame(
            {
                "player_name": ["Patrick Mahomes", "Josh Allen"],
                "team": ["KC", "BUF"],
                "year": [2024, 2024],
            }
        )

    def test_valid_df_does_not_raise(self):
        self.parser.validate_player_contract_data(self._make_valid_df(), 2024)

    def test_empty_df_raises(self):
        with pytest.raises(DataQualityError, match="No contract data"):
            self.parser.validate_player_contract_data(pd.DataFrame(), 2024)

    def test_missing_column_raises(self):
        df = self._make_valid_df().drop(columns=["team"])
        with pytest.raises(DataQualityError, match="team"):
            self.parser.validate_player_contract_data(df, 2024)

    def test_zero_teams_raises(self):
        df = pd.DataFrame(
            {
                "player_name": ["A"],
                "team": [None],
                "year": [2024],
            }
        )
        with pytest.raises(DataQualityError, match="at least one team"):
            self.parser.validate_player_contract_data(df, 2024)


# ---------------------------------------------------------------------------
# SpotracParser.normalize_player_df
# ---------------------------------------------------------------------------


class TestNormalizePlayerDf:
    def setup_method(self):
        self.parser = SpotracParser()

    def _make_df(self):
        return pd.DataFrame(
            {
                "Player": ["Deshaun Watson", "Carson Wentz"],
                "Team": ["CLE", "WAS"],
                "Pos.": ["QB", "QB"],
                "Dead Money": ["$46,000,000", "$20,000,000"],
                "Cap Hit": ["$46,000,000", "$20,000,000"],
            }
        )

    def test_player_name_mapped(self):
        df = self.parser.normalize_player_df(self._make_df(), 2024)
        assert "player_name" in df.columns

    def test_money_parsed(self):
        df = self.parser.normalize_player_df(self._make_df(), 2024)
        watson = df[df["player_name"] == "Deshaun Watson"].iloc[0]
        assert watson["dead_money_millions"] == pytest.approx(46.0)

    def test_year_added(self):
        df = self.parser.normalize_player_df(self._make_df(), 2024)
        assert (df["year"] == 2024).all()

    def test_with_salary_column(self):
        df = pd.DataFrame(
            {
                "Player": ["Lamar Jackson"],
                "Team": ["BAL"],
                "Pos.": ["QB"],
                "Salary": ["$52,000,000"],
            }
        )
        result = self.parser.normalize_player_df(df, 2024)
        assert "salary_millions" in result.columns
        assert result["salary_millions"].iloc[0] == pytest.approx(52.0)

    def test_with_fixture_html(self):
        html = _read_fixture("player_salaries_2024.html")
        headers, rows = self.parser.parse_table(html)
        raw_df = pd.DataFrame(rows, columns=headers[: len(rows[0])])
        df = self.parser.normalize_player_df(raw_df, 2024)
        assert "player_name" in df.columns
        assert len(df) >= 30


# ---------------------------------------------------------------------------
# SpotracParser.validate_player_data
# ---------------------------------------------------------------------------


class TestValidatePlayerData:
    def setup_method(self):
        self.parser = SpotracParser()

    def _make_valid_df(self, n=50):
        return pd.DataFrame(
            {
                "player_name": [f"Player{i}" for i in range(n)],
                "team": [f"T{i % 32}" for i in range(n)],
                "year": [2024] * n,
            }
        )

    def test_valid_df_does_not_raise(self):
        self.parser.validate_player_data(self._make_valid_df(), 2024)

    def test_too_few_rows_raises(self):
        with pytest.raises(DataQualityError, match="30"):
            self.parser.validate_player_data(self._make_valid_df(n=5), 2024)

    def test_custom_min_rows(self):
        # min_rows=3 — a 5-row df should pass
        self.parser.validate_player_data(self._make_valid_df(n=5), 2024, min_rows=3)

    def test_missing_column_raises(self):
        df = self._make_valid_df().drop(columns=["team"])
        with pytest.raises(DataQualityError, match="team"):
            self.parser.validate_player_data(df, 2024)


# ---------------------------------------------------------------------------
# Backwards-compat: SpotracParser importable from spotrac_scraper_v2
# ---------------------------------------------------------------------------


class TestBackwardsCompatImport:
    def test_import_from_scraper_v2(self):
        from src.spotrac_scraper_v2 import DataQualityError as DQE
        from src.spotrac_scraper_v2 import SpotracParser as SP
        from src.spotrac_scraper_v2 import _build_run_tags as brt
        from src.spotrac_scraper_v2 import _deduplicate_headers as ddh

        assert SP is SpotracParser
        assert DQE is DataQualityError
        assert brt is _build_run_tags
        assert ddh is _deduplicate_headers

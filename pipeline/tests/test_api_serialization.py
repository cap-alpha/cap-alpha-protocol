"""
Tests for api.serialization.df_to_records — the JSON-safe DataFrame converter.

Regression coverage for the pundit-predictions 500: a nullable datetime column
(e.g. resolved_at) holding NaT slipped through df.where(df.notna(), None) and
crashed FastAPI/pydantic response serialization with
"'float' object cannot be interpreted as an integer".
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd
import pytest

import sys, pathlib

_API_DIR = pathlib.Path(__file__).parent.parent / "api"
if str(_API_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_API_DIR.parent))

from api.serialization import df_to_records  # noqa: E402


def _mixed_df() -> pd.DataFrame:
    """A frame shaped like the pundit-predictions result: mix of resolved and
    pending rows, so the nullable columns actually hold NaT / NA / NaN."""
    return pd.DataFrame(
        {
            # never-null datetime (like ingestion_timestamp)
            "ingestion_timestamp": pd.to_datetime(
                ["2026-04-28T13:12:10Z", "2026-05-03T13:22:16Z"], utc=True
            ),
            # nullable datetime with NaT (like resolved_at) — the crash trigger
            "resolved_at": pd.to_datetime(["2026-04-28T13:12:10Z", None], utc=True),
            # nullable int (like season_year)
            "season_year": pd.array([2026, None], dtype="Int64"),
            # nullable bool (like binary_correct)
            "binary_correct": pd.array([True, None], dtype="boolean"),
            # float with NaN (like weighted_score)
            "weighted_score": [1.0, float("nan")],
            "extracted_claim": ["A will happen", None],
        }
    )


class TestDfToRecords:
    def test_output_is_valid_json_serializable(self):
        """The whole point: the result must survive strict JSON serialization
        (no NaT, no bare NaN token). This is what FastAPI/pydantic does."""
        records = df_to_records(_mixed_df())
        # allow_nan=False rejects NaN/Infinity — proves no invalid tokens remain
        json.dumps(records, allow_nan=False)

    def test_nat_becomes_null(self):
        records = df_to_records(_mixed_df())
        assert records[0]["resolved_at"] is not None  # resolved row keeps a value
        assert records[1]["resolved_at"] is None  # pending row -> null, not NaT

    def test_timestamp_becomes_iso_string(self):
        records = df_to_records(_mixed_df())
        assert isinstance(records[0]["ingestion_timestamp"], str)
        assert records[0]["ingestion_timestamp"].startswith("2026-04-28")

    def test_nan_float_becomes_null(self):
        records = df_to_records(_mixed_df())
        assert records[0]["weighted_score"] == 1.0
        assert records[1]["weighted_score"] is None

    def test_nullable_int_and_bool(self):
        records = df_to_records(_mixed_df())
        assert records[0]["season_year"] == 2026
        assert records[1]["season_year"] is None
        assert records[0]["binary_correct"] is True
        assert records[1]["binary_correct"] is None

    def test_empty_and_none_frame(self):
        assert df_to_records(pd.DataFrame()) == []
        assert df_to_records(None) == []

    def test_reproduces_old_crash_and_confirms_fix(self):
        """Directly exercise the pydantic serialization path that used to 500."""
        pyd = pytest.importorskip("pydantic")
        ta = pyd.TypeAdapter(List[Dict[str, Any]])
        df = _mixed_df()

        # OLD behavior: NaT survives .where(notna, None) on datetime cols -> raises
        old_records = df.where(df.notna(), None).to_dict(orient="records")
        with pytest.raises(Exception):
            ta.dump_json(old_records)

        # NEW behavior: df_to_records is clean
        ta.dump_json(df_to_records(df))  # must not raise

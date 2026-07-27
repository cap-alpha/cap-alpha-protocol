"""
JSON-safe serialization helpers for API responses built from pandas DataFrames.

Why this exists
---------------
Several endpoints return `df.where(df.notna(), None).to_dict(orient="records")`.
That pattern is subtly broken for two common column shapes:

1. **Nullable datetime columns (e.g. `resolved_at`).** `df.where(df.notna(),
   None)` does NOT turn `NaT` into `None`: assigning `None` into a `datetime64`
   column coerces it straight back to `NaT`. The record therefore still holds a
   `pandas.NaT`, and FastAPI/pydantic v2 then raises, mid-response-serialization
   (outside the endpoint's own try/except):

       PydanticSerializationError: Error serializing to JSON:
       TypeError: 'float' object cannot be interpreted as an integer

   This 500s the whole endpoint for any row set containing an unresolved
   prediction — i.e. essentially every pundit. (Non-null datetime columns like
   `ingestion_timestamp` slip through only because they never hold NaT.)

2. **NaN in float columns.** `.to_dict()` leaves `float('nan')`, which pydantic
   emits as the bare token `NaN` — not valid JSON, and `JSON.parse` in the
   browser rejects it.

`df_to_records` routes through pandas' own JSON writer, which correctly maps
`NaT`/`NaN` -> `null`, `Timestamp` -> ISO-8601 string, and numpy/pandas scalar
types (`Int64`, `np.float64`, `np.bool_`) -> native `int`/`float`/`bool`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pandas as pd


def df_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Return a DataFrame as JSON-safe native-Python records.

    Handles NaT/NaN -> None, Timestamp -> ISO string, and numpy/pandas scalar
    types -> native Python scalars. Safe to hand straight to FastAPI. Returns
    an empty list for a None or empty frame.
    """
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", date_format="iso"))

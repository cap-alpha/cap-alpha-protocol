"""
Pundit Accountability Metrics Framework — Issue #338

Unified four-axis accountability profile for each pundit:

  1. Accuracy    — signed combined score (correctness × novelty × confidence × stakes)
  2. Volume      — claim count, coverage breadth, recency
  3. Integrity   — anti-gaming signals (spray-and-claim, post-miss behavior distribution)
  4. Epistemic virtue — mea-culpa rate, hedge calibration (placeholder axes for sub-issues)

This module is the framework backbone. Sub-issues (#339–#372) add flesh to each axis.
The public surface intentionally stays stable so callers don't break as sub-issues land.

Usage:
    from src.pundit_accountability_metrics import PunditProfile, build_profile_from_scores

    # Offline (unit tests, no BQ):
    profile = build_profile_from_scores(pundit_id="p1", pundit_name="Adam Schefter",
                                        claim_scores=[1.2, -0.8, 0.5],
                                        accountability_classes=["owns_it", "silent_burial"])

    # Online (BigQuery):
    python -m src.pundit_accountability_metrics --pundit-id p1
    python -m src.pundit_accountability_metrics --all
"""

import argparse
import logging
import math
import os
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from src.db_manager import DBManager
from src.scoring import (
    CLAIM_SCORES_TABLE,
    compute_pundit_aggregate,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCOUNTABILITY_TABLE = "gold_layer.accountability_ledger"
RESOLUTIONS_TABLE = "gold_layer.prediction_resolutions"
LEDGER_TABLE = "gold_layer.prediction_ledger"

# Claim volume below this threshold → mark as "low_volume"
LOW_VOLUME_THRESHOLD = 5


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class AccuracyAxis:
    """Axis 1 — was the pundit right?"""

    composite_score: float = 0.0  # mean signed combined score
    score_std: float = 0.0  # spread (high std = volatile)
    positive_rate: float = 0.0  # fraction of CORRECT / total resolved (non-VOID)
    total_scored: int = 0  # resolved predictions with a score


@dataclass
class VolumeAxis:
    """Axis 2 — how many calls, on how many topics?"""

    total_claims: int = 0  # lifetime resolved predictions
    unique_categories: int = 0  # domain breadth
    low_volume: bool = True  # True when total < LOW_VOLUME_THRESHOLD


@dataclass
class IntegrityAxis:
    """Axis 3 — did the pundit earn the score honestly?

    Populated by sub-issues #344–#361.  Stubs live here so callers can always
    reference the axis even before the sub-issues land.
    """

    owns_it_rate: float = 0.0  # fraction of misses where pundit owned the error
    silent_burial_rate: float = 0.0  # fraction buried silently
    revisionism_rate: float = 0.0
    doubling_down_rate: float = 0.0
    deflection_rate: float = 0.0
    accountability_sample: int = 0  # how many misses were classified

    # Placeholder flags for sub-issues; False until the detector is built
    spray_and_claim_flagged: bool = False  # #345
    quiet_revision_flagged: bool = False  # #346
    event_proximity_flagged: bool = False  # #348


@dataclass
class EpistemicVirtueAxis:
    """Axis 4 — does the pundit update, hedge calibratedly, own mistakes?

    Populated by sub-issues #350–#351.  Stubs here.
    """

    mea_culpa_rate: float = 0.0  # #350 — explicitly owns mistakes / total misses
    hedge_calibration_score: float = 0.0  # #351 — placeholder


@dataclass
class PunditProfile:
    """
    Unified accountability profile for a single pundit — the four-axis summary.

    All axes are computed from local data; callers pass in what they have.
    Sub-issues fill in richer values over time without changing this structure.
    """

    pundit_id: str
    pundit_name: str
    accuracy: AccuracyAxis = field(default_factory=AccuracyAxis)
    volume: VolumeAxis = field(default_factory=VolumeAxis)
    integrity: IntegrityAxis = field(default_factory=IntegrityAxis)
    epistemic_virtue: EpistemicVirtueAxis = field(default_factory=EpistemicVirtueAxis)

    def to_dict(self) -> dict:
        return {
            "pundit_id": self.pundit_id,
            "pundit_name": self.pundit_name,
            # accuracy
            "composite_score": self.accuracy.composite_score,
            "score_std": self.accuracy.score_std,
            "positive_rate": self.accuracy.positive_rate,
            "total_scored": self.accuracy.total_scored,
            # volume
            "total_claims": self.volume.total_claims,
            "unique_categories": self.volume.unique_categories,
            "low_volume": self.volume.low_volume,
            # integrity
            "owns_it_rate": self.integrity.owns_it_rate,
            "silent_burial_rate": self.integrity.silent_burial_rate,
            "revisionism_rate": self.integrity.revisionism_rate,
            "doubling_down_rate": self.integrity.doubling_down_rate,
            "deflection_rate": self.integrity.deflection_rate,
            "accountability_sample": self.integrity.accountability_sample,
            "spray_and_claim_flagged": self.integrity.spray_and_claim_flagged,
            "quiet_revision_flagged": self.integrity.quiet_revision_flagged,
            "event_proximity_flagged": self.integrity.event_proximity_flagged,
            # epistemic virtue
            "mea_culpa_rate": self.epistemic_virtue.mea_culpa_rate,
            "hedge_calibration_score": self.epistemic_virtue.hedge_calibration_score,
        }


# ---------------------------------------------------------------------------
# Offline (unit-testable) builder — no BQ required
# ---------------------------------------------------------------------------


def build_profile_from_scores(
    pundit_id: str,
    pundit_name: str,
    claim_scores: list[float],
    claim_categories: Optional[list[Optional[str]]] = None,
    accountability_classes: Optional[list[str]] = None,
) -> PunditProfile:
    """
    Build a PunditProfile from pre-fetched data lists (no BigQuery needed).

    Args:
        pundit_id:              Pundit identifier
        pundit_name:            Display name
        claim_scores:           List of raw_score floats from scoring.py
        claim_categories:       Parallel list of claim category strings (optional)
        accountability_classes: List of accountability class strings for INCORRECT
                                predictions (from accountability_engine.py)

    Returns:
        PunditProfile with all four axes populated to the extent possible.
    """
    # -- Axis 1: Accuracy -------------------------------------------------------
    agg = compute_pundit_aggregate(claim_scores)
    positive_rate = agg["positive_rate"]
    accuracy = AccuracyAxis(
        composite_score=agg["mean"],
        score_std=agg["std"],
        positive_rate=positive_rate,
        total_scored=agg["count"],
    )

    # -- Axis 2: Volume ---------------------------------------------------------
    unique_cats = len({c for c in claim_categories if c}) if claim_categories else 0
    total = len(claim_scores)
    volume = VolumeAxis(
        total_claims=total,
        unique_categories=unique_cats,
        low_volume=total < LOW_VOLUME_THRESHOLD,
    )

    # -- Axis 3: Integrity (accountability class distribution) ------------------
    integrity = _compute_integrity(accountability_classes or [])

    # -- Axis 4: Epistemic virtue — mea_culpa_rate from owns_it -----------------
    mea_culpa = integrity.owns_it_rate  # owns_it is the primary mea-culpa signal
    epistemic = EpistemicVirtueAxis(
        mea_culpa_rate=mea_culpa,
        hedge_calibration_score=0.0,  # #351 not yet implemented
    )

    return PunditProfile(
        pundit_id=pundit_id,
        pundit_name=pundit_name,
        accuracy=accuracy,
        volume=volume,
        integrity=integrity,
        epistemic_virtue=epistemic,
    )


def _compute_integrity(accountability_classes: list[str]) -> IntegrityAxis:
    """Compute integrity axis from a list of accountability class strings."""
    valid = [c for c in accountability_classes if c and c != "insufficient_data"]
    n = len(valid)
    if n == 0:
        return IntegrityAxis(accountability_sample=len(accountability_classes))

    def _rate(cls: str) -> float:
        return sum(1 for c in valid if c == cls) / n

    return IntegrityAxis(
        owns_it_rate=_rate("owns_it"),
        silent_burial_rate=_rate("silent_burial"),
        revisionism_rate=_rate("revisionism"),
        doubling_down_rate=_rate("doubling_down"),
        deflection_rate=_rate("deflection"),
        accountability_sample=n,
    )


# ---------------------------------------------------------------------------
# BigQuery builders
# ---------------------------------------------------------------------------


def _full(table: str, project_id: str) -> str:
    return f"`{project_id}.{table}`"


def fetch_pundit_scores(
    pundit_id: str, db: DBManager, project_id: str
) -> tuple[list[float], list[Optional[str]]]:
    """
    Returns (raw_scores, claim_categories) for all scored predictions of this pundit.
    """
    query = f"""
        SELECT raw_score, NULL AS claim_category
        FROM {_full(CLAIM_SCORES_TABLE, project_id)}
        WHERE pundit_id = '{pundit_id}'
    """
    df = db.fetch_df(query)
    if df.empty:
        return [], []
    scores = df["raw_score"].tolist()
    cats: list[Optional[str]] = (
        df["claim_category"].tolist()
        if "claim_category" in df.columns
        else [None] * len(scores)
    )
    return scores, cats


def fetch_accountability_classes(
    pundit_id: str, db: DBManager, project_id: str
) -> list[str]:
    """Returns list of accountability_class strings for this pundit's INCORRECT predictions."""
    query = f"""
        SELECT accountability_class
        FROM {_full(ACCOUNTABILITY_TABLE, project_id)}
        WHERE pundit_id = '{pundit_id}'
    """
    df = db.fetch_df(query)
    if df.empty:
        return []
    return df["accountability_class"].tolist()


def build_profile(
    pundit_id: str,
    pundit_name: str = "",
    db: Optional[DBManager] = None,
) -> PunditProfile:
    """
    Fetch data from BigQuery and build a PunditProfile for one pundit.
    """
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
        scores, cats = fetch_pundit_scores(pundit_id, db, project_id)
        acc_classes = fetch_accountability_classes(pundit_id, db, project_id)
        return build_profile_from_scores(
            pundit_id=pundit_id,
            pundit_name=pundit_name or pundit_id,
            claim_scores=scores,
            claim_categories=cats,
            accountability_classes=acc_classes,
        )
    finally:
        if close_db:
            db.close()


def get_all_pundit_ids(db: DBManager, project_id: str) -> list[tuple[str, str]]:
    """Returns list of (pundit_id, pundit_name) from claim_scores."""
    query = f"""
        SELECT DISTINCT pundit_id, pundit_name
        FROM {_full(CLAIM_SCORES_TABLE, project_id)}
        ORDER BY pundit_id
    """
    df = db.fetch_df(query)
    if df.empty:
        return []
    return list(zip(df["pundit_id"].tolist(), df["pundit_name"].tolist()))


def build_all_profiles(db: Optional[DBManager] = None) -> list[PunditProfile]:
    """Build PunditProfiles for every pundit with scored predictions."""
    close_db = db is None
    if db is None:
        db = DBManager()

    try:
        project_id = os.environ.get("GCP_PROJECT_ID", "cap-alpha-protocol")
        pairs = get_all_pundit_ids(db, project_id)
        profiles = []
        for pundit_id, pundit_name in pairs:
            try:
                p = build_profile(pundit_id, pundit_name, db=db)
                profiles.append(p)
            except Exception as e:
                logger.error("Failed to build profile for %s: %s", pundit_id, e)
        return profiles
    finally:
        if close_db:
            db.close()


def profiles_to_dataframe(profiles: list[PunditProfile]) -> pd.DataFrame:
    """Convert a list of PunditProfiles to a ranked DataFrame (composite_score desc)."""
    if not profiles:
        return pd.DataFrame()
    rows = [p.to_dict() for p in profiles]
    df = pd.DataFrame(rows)
    return df.sort_values("composite_score", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Pundit accountability metrics — per-pundit four-axis profile"
    )
    parser.add_argument("--pundit-id", type=str, help="Profile a single pundit")
    parser.add_argument(
        "--all", action="store_true", help="Build profiles for all pundits"
    )
    args = parser.parse_args()

    if args.pundit_id:
        profile = build_profile(args.pundit_id)
        for k, v in profile.to_dict().items():
            if isinstance(v, float):
                print(f"  {k:<35} {v:+.4f}")
            else:
                print(f"  {k:<35} {v}")
        return

    if args.all:
        profiles = build_all_profiles()
        if not profiles:
            print("No pundit profiles found.")
            return
        df = profiles_to_dataframe(profiles)
        print(
            df[
                [
                    "pundit_name",
                    "composite_score",
                    "positive_rate",
                    "total_scored",
                    "owns_it_rate",
                    "low_volume",
                ]
            ].to_string(index=False)
        )
        return

    parser.print_help()


if __name__ == "__main__":
    _cli()

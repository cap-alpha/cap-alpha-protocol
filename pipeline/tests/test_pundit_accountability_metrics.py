"""
Unit tests for pipeline/src/pundit_accountability_metrics.py — Issue #338

Tests the four-axis framework without BigQuery.
"""

import pytest
from src.pundit_accountability_metrics import (
    AccuracyAxis,
    EpistemicVirtueAxis,
    IntegrityAxis,
    LOW_VOLUME_THRESHOLD,
    PunditProfile,
    VolumeAxis,
    _compute_integrity,
    build_profile_from_scores,
    profiles_to_dataframe,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bold_correct_pundit():
    """Pundit who makes bold, correct calls and owns their few mistakes."""
    return build_profile_from_scores(
        pundit_id="p1",
        pundit_name="Bold Betty",
        claim_scores=[1.5, 1.2, 0.9, 1.1, 0.8, 1.3],
        claim_categories=[
            "draft_pick",
            "player_performance",
            "contract",
            "trade",
            "fa_signing",
            "game_outcome",
        ],
        accountability_classes=["owns_it", "owns_it"],
    )


@pytest.fixture
def loud_wrong_pundit():
    """Pundit who makes loud, wrong calls and never owns mistakes."""
    return build_profile_from_scores(
        pundit_id="p2",
        pundit_name="Loud Larry",
        claim_scores=[-1.5, -1.2, -0.8, -0.9, 0.3],
        claim_categories=[
            "draft_pick",
            "draft_pick",
            "player_performance",
            "contract",
            "trade",
        ],
        accountability_classes=["doubling_down", "deflection", "silent_burial"],
    )


@pytest.fixture
def empty_pundit():
    """Pundit with no scored predictions yet."""
    return build_profile_from_scores(
        pundit_id="p3",
        pundit_name="Nobody Nick",
        claim_scores=[],
    )


# ---------------------------------------------------------------------------
# PunditProfile structure
# ---------------------------------------------------------------------------


class TestPunditProfileStructure:
    def test_has_four_axes(self, bold_correct_pundit):
        p = bold_correct_pundit
        assert isinstance(p.accuracy, AccuracyAxis)
        assert isinstance(p.volume, VolumeAxis)
        assert isinstance(p.integrity, IntegrityAxis)
        assert isinstance(p.epistemic_virtue, EpistemicVirtueAxis)

    def test_to_dict_has_all_keys(self, bold_correct_pundit):
        d = bold_correct_pundit.to_dict()
        required = [
            "pundit_id",
            "pundit_name",
            "composite_score",
            "score_std",
            "positive_rate",
            "total_scored",
            "total_claims",
            "unique_categories",
            "low_volume",
            "owns_it_rate",
            "silent_burial_rate",
            "revisionism_rate",
            "doubling_down_rate",
            "deflection_rate",
            "accountability_sample",
            "spray_and_claim_flagged",
            "quiet_revision_flagged",
            "event_proximity_flagged",
            "mea_culpa_rate",
            "hedge_calibration_score",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_identity_fields(self, bold_correct_pundit):
        assert bold_correct_pundit.pundit_id == "p1"
        assert bold_correct_pundit.pundit_name == "Bold Betty"


# ---------------------------------------------------------------------------
# Axis 1 — Accuracy
# ---------------------------------------------------------------------------


class TestAccuracyAxis:
    def test_positive_composite_for_bold_correct(self, bold_correct_pundit):
        assert bold_correct_pundit.accuracy.composite_score > 0.0

    def test_negative_composite_for_loud_wrong(self, loud_wrong_pundit):
        assert loud_wrong_pundit.accuracy.composite_score < 0.0

    def test_zero_composite_for_empty(self, empty_pundit):
        assert empty_pundit.accuracy.composite_score == 0.0

    def test_positive_rate_range(self, bold_correct_pundit):
        pr = bold_correct_pundit.accuracy.positive_rate
        assert 0.0 <= pr <= 1.0

    def test_positive_rate_mostly_correct(self, bold_correct_pundit):
        assert bold_correct_pundit.accuracy.positive_rate > 0.8

    def test_positive_rate_mostly_wrong(self, loud_wrong_pundit):
        assert loud_wrong_pundit.accuracy.positive_rate < 0.5

    def test_total_scored_matches_input(self, bold_correct_pundit):
        assert bold_correct_pundit.accuracy.total_scored == 6

    def test_std_zero_for_uniform_scores(self):
        profile = build_profile_from_scores("x", "X", [1.0, 1.0, 1.0])
        assert profile.accuracy.score_std == pytest.approx(0.0)

    def test_std_positive_for_varied_scores(self, bold_correct_pundit):
        assert bold_correct_pundit.accuracy.score_std >= 0.0


# ---------------------------------------------------------------------------
# Axis 2 — Volume
# ---------------------------------------------------------------------------


class TestVolumeAxis:
    def test_total_claims_matches_input(self, bold_correct_pundit):
        assert bold_correct_pundit.volume.total_claims == 6

    def test_unique_categories_counted(self, bold_correct_pundit):
        assert bold_correct_pundit.volume.unique_categories == 6

    def test_low_volume_false_when_above_threshold(self, bold_correct_pundit):
        assert bold_correct_pundit.volume.low_volume is False

    def test_low_volume_true_when_below_threshold(self):
        profile = build_profile_from_scores("y", "Y", [0.5, -0.3])
        assert profile.volume.low_volume is True

    def test_low_volume_threshold_boundary(self):
        scores = [0.5] * LOW_VOLUME_THRESHOLD
        profile = build_profile_from_scores("z", "Z", scores)
        assert profile.volume.low_volume is False

    def test_zero_unique_categories_when_none_provided(self, empty_pundit):
        assert empty_pundit.volume.unique_categories == 0

    def test_duplicate_categories_deduplicated(self):
        profile = build_profile_from_scores(
            "a",
            "A",
            claim_scores=[1.0, -1.0, 0.5, -0.5, 0.8, -0.8],
            claim_categories=[
                "draft_pick",
                "draft_pick",
                "draft_pick",
                "contract",
                "contract",
                "contract",
            ],
        )
        assert profile.volume.unique_categories == 2


# ---------------------------------------------------------------------------
# Axis 3 — Integrity
# ---------------------------------------------------------------------------


class TestIntegrityAxis:
    def test_owns_it_rate_high_for_honest_pundit(self, bold_correct_pundit):
        assert bold_correct_pundit.integrity.owns_it_rate == pytest.approx(1.0)

    def test_doubling_down_rate_nonzero_for_loud_wrong(self, loud_wrong_pundit):
        assert loud_wrong_pundit.integrity.doubling_down_rate > 0.0

    def test_rates_sum_to_one(self, loud_wrong_pundit):
        i = loud_wrong_pundit.integrity
        total = (
            i.owns_it_rate
            + i.silent_burial_rate
            + i.revisionism_rate
            + i.doubling_down_rate
            + i.deflection_rate
        )
        assert total == pytest.approx(1.0, abs=1e-9)

    def test_empty_accountability_returns_zero_rates(self, empty_pundit):
        i = empty_pundit.integrity
        assert i.owns_it_rate == 0.0
        assert i.accountability_sample == 0

    def test_insufficient_data_excluded_from_rates(self):
        classes = ["owns_it", "insufficient_data", "insufficient_data"]
        i = _compute_integrity(classes)
        assert i.owns_it_rate == pytest.approx(1.0)
        assert i.accountability_sample == 1

    def test_placeholder_flags_default_false(self, bold_correct_pundit):
        i = bold_correct_pundit.integrity
        assert i.spray_and_claim_flagged is False
        assert i.quiet_revision_flagged is False
        assert i.event_proximity_flagged is False

    def test_all_classes_represented(self):
        classes = [
            "owns_it",
            "silent_burial",
            "revisionism",
            "doubling_down",
            "deflection",
        ]
        i = _compute_integrity(classes)
        assert i.owns_it_rate == pytest.approx(0.2)
        assert i.silent_burial_rate == pytest.approx(0.2)
        assert i.revisionism_rate == pytest.approx(0.2)
        assert i.doubling_down_rate == pytest.approx(0.2)
        assert i.deflection_rate == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Axis 4 — Epistemic virtue
# ---------------------------------------------------------------------------


class TestEpistemicVirtueAxis:
    def test_mea_culpa_rate_equals_owns_it_rate(self, bold_correct_pundit):
        assert bold_correct_pundit.epistemic_virtue.mea_culpa_rate == pytest.approx(
            bold_correct_pundit.integrity.owns_it_rate
        )

    def test_hedge_calibration_placeholder_zero(self, bold_correct_pundit):
        assert (
            bold_correct_pundit.epistemic_virtue.hedge_calibration_score
            == pytest.approx(0.0)
        )


# ---------------------------------------------------------------------------
# profiles_to_dataframe
# ---------------------------------------------------------------------------


class TestProfilesToDataframe:
    def test_returns_empty_dataframe_for_no_profiles(self):
        df = profiles_to_dataframe([])
        assert df.empty

    def test_rows_equal_profile_count(self, bold_correct_pundit, loud_wrong_pundit):
        df = profiles_to_dataframe([bold_correct_pundit, loud_wrong_pundit])
        assert len(df) == 2

    def test_sorted_by_composite_score_descending(
        self, bold_correct_pundit, loud_wrong_pundit
    ):
        df = profiles_to_dataframe([loud_wrong_pundit, bold_correct_pundit])
        scores = df["composite_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_all_dict_keys_present_as_columns(self, bold_correct_pundit):
        df = profiles_to_dataframe([bold_correct_pundit])
        for key in bold_correct_pundit.to_dict():
            assert key in df.columns


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_void_only_scores_give_zero_composite(self):
        profile = build_profile_from_scores("v", "V", [0.0, 0.0, 0.0, 0.0, 0.0])
        assert profile.accuracy.composite_score == pytest.approx(0.0)
        assert profile.accuracy.positive_rate == pytest.approx(0.0)

    def test_single_score_no_std(self):
        profile = build_profile_from_scores("s", "S", [1.25])
        assert profile.accuracy.composite_score == pytest.approx(1.25)
        assert profile.accuracy.score_std == pytest.approx(0.0)
        assert profile.volume.low_volume is True

    def test_mixed_categories_with_none(self):
        profile = build_profile_from_scores(
            "m",
            "M",
            claim_scores=[1.0, -1.0, 0.5, -0.5, 0.8, -0.8],
            claim_categories=["draft_pick", None, "contract", None, "trade", None],
        )
        assert profile.volume.unique_categories == 3

    def test_build_profile_from_scores_no_optional_args(self):
        profile = build_profile_from_scores("n", "N", [0.5, -0.5, 1.0, -1.0, 0.2])
        assert profile.volume.unique_categories == 0
        assert profile.integrity.accountability_sample == 0

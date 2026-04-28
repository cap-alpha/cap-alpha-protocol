"""
Unit tests for pipeline/src/scoring.py — Issue #340

Tests the 4 corners of the signed combined score formula:
  score = correctness_sign × (1 + λ_n·novelty) × (1 + λ_c·confidence) × stakes

No BigQuery required — pure unit tests.
"""

import pytest
from src.scoring import (
    LAMBDA_CONFIDENCE,
    LAMBDA_NOVELTY,
    STAKES_BY_CATEGORY,
    ClaimScore,
    category_stakes,
    compute_claim_score,
    compute_pundit_aggregate,
    correctness_sign,
)


# ---------------------------------------------------------------------------
# correctness_sign()
# ---------------------------------------------------------------------------


class TestCorrectnessSign:
    def test_correct_returns_plus_one(self):
        assert correctness_sign("CORRECT") == 1.0

    def test_incorrect_returns_minus_one(self):
        assert correctness_sign("INCORRECT") == -1.0

    def test_void_returns_zero(self):
        assert correctness_sign("VOID") == 0.0

    def test_unknown_returns_zero(self):
        assert correctness_sign("PENDING") == 0.0

    def test_case_insensitive(self):
        assert correctness_sign("correct") == 1.0
        assert correctness_sign("Incorrect") == -1.0


# ---------------------------------------------------------------------------
# category_stakes()
# ---------------------------------------------------------------------------


class TestCategoryStakes:
    def test_draft_pick_highest(self):
        assert category_stakes("draft_pick") == 1.5

    def test_fa_signing_lowest(self):
        assert category_stakes("fa_signing") == 0.7

    def test_unknown_category_defaults(self):
        assert category_stakes("unknown_type") == 1.0

    def test_none_category_defaults(self):
        assert category_stakes(None) == 1.0

    def test_all_known_categories_present(self):
        for cat, stake in STAKES_BY_CATEGORY.items():
            assert category_stakes(cat) == stake


# ---------------------------------------------------------------------------
# compute_claim_score() — the 4 corners
# ---------------------------------------------------------------------------


class TestComputeClaimScore:
    """
    Four canonical corners:
      A) right + bold + contrarian → large positive
      B) right + safe              → small positive
      C) wrong + safe              → small negative
      D) wrong + bold + contrarian → large negative (loud-and-wrong penalty)
    """

    def test_corner_a_right_bold_contrarian_large_positive(self):
        """CORRECT + high confidence + high novelty → largest positive score."""
        score = compute_claim_score(
            resolution_status="CORRECT",
            claim_category="draft_pick",  # stakes = 1.5
            quality_score=1.0,  # max confidence
            novelty=1.0,  # max contrarian
        )
        # sign=+1, novelty_factor=1.5, conf_factor=1.5, stakes=1.5
        expected = 1.0 * 1.5 * 1.5 * 1.5
        assert abs(score - expected) < 1e-9

    def test_corner_b_right_safe_small_positive(self):
        """CORRECT + low confidence + low novelty → small positive score."""
        score = compute_claim_score(
            resolution_status="CORRECT",
            claim_category="fa_signing",  # stakes = 0.7
            quality_score=0.0,  # min confidence
            novelty=0.0,  # consensus pick
        )
        # sign=+1, novelty_factor=1.0, conf_factor=1.0, stakes=0.7
        expected = 1.0 * 1.0 * 1.0 * 0.7
        assert abs(score - expected) < 1e-9
        assert score > 0

    def test_corner_c_wrong_safe_small_negative(self):
        """INCORRECT + low confidence + low novelty → small negative score."""
        score = compute_claim_score(
            resolution_status="INCORRECT",
            claim_category="fa_signing",  # stakes = 0.7
            quality_score=0.0,
            novelty=0.0,
        )
        expected = -1.0 * 1.0 * 1.0 * 0.7
        assert abs(score - expected) < 1e-9
        assert score < 0

    def test_corner_d_wrong_bold_contrarian_large_negative(self):
        """INCORRECT + high confidence + high novelty → largest negative (loud-and-wrong)."""
        score = compute_claim_score(
            resolution_status="INCORRECT",
            claim_category="draft_pick",  # stakes = 1.5
            quality_score=1.0,
            novelty=1.0,
        )
        expected = -1.0 * 1.5 * 1.5 * 1.5
        assert abs(score - expected) < 1e-9
        assert score < 0

    def test_corner_a_exceeds_corner_b(self):
        """Right+bold+contrarian should score higher than right+safe."""
        bold = compute_claim_score(
            "CORRECT", "draft_pick", quality_score=1.0, novelty=1.0
        )
        safe = compute_claim_score(
            "CORRECT", "fa_signing", quality_score=0.0, novelty=0.0
        )
        assert bold > safe

    def test_corner_d_less_than_corner_c(self):
        """Wrong+bold should score worse than wrong+safe."""
        loud = compute_claim_score(
            "INCORRECT", "draft_pick", quality_score=1.0, novelty=1.0
        )
        quiet = compute_claim_score(
            "INCORRECT", "fa_signing", quality_score=0.0, novelty=0.0
        )
        assert loud < quiet

    def test_void_always_zero(self):
        """VOID predictions must always score exactly 0."""
        for quality_score in [0.0, 0.5, 1.0]:
            for novelty in [0.0, 0.5, 1.0]:
                score = compute_claim_score(
                    "VOID",
                    claim_category="draft_pick",
                    quality_score=quality_score,
                    novelty=novelty,
                )
                assert score == 0.0

    def test_default_quality_and_novelty(self):
        """With defaults (0.5 / 0.5), CORRECT draft_pick produces expected value."""
        score = compute_claim_score("CORRECT", claim_category="draft_pick")
        # sign=1, novelty_factor=1+0.5*0.5=1.25, conf_factor=1+0.5*0.5=1.25, stakes=1.5
        expected = 1.0 * 1.25 * 1.25 * 1.5
        assert abs(score - expected) < 1e-9

    def test_custom_lambdas(self):
        """Custom λ_n / λ_c override the module-level defaults."""
        score = compute_claim_score(
            "CORRECT",
            claim_category="game_outcome",  # stakes=1.0
            quality_score=1.0,
            novelty=1.0,
            lambda_n=0.0,  # novelty bonus disabled
            lambda_c=0.0,  # confidence bonus disabled
        )
        assert abs(score - 1.0) < 1e-9

    def test_quality_score_clamped_above_one(self):
        """quality_score > 1.0 is clamped to 1.0."""
        score_clamped = compute_claim_score("CORRECT", quality_score=5.0)
        score_at_one = compute_claim_score("CORRECT", quality_score=1.0)
        assert abs(score_clamped - score_at_one) < 1e-9

    def test_quality_score_clamped_below_zero(self):
        """quality_score < 0.0 is clamped to 0.0."""
        score_clamped = compute_claim_score("CORRECT", quality_score=-1.0)
        score_at_zero = compute_claim_score("CORRECT", quality_score=0.0)
        assert abs(score_clamped - score_at_zero) < 1e-9


# ---------------------------------------------------------------------------
# compute_pundit_aggregate()
# ---------------------------------------------------------------------------


class TestComputePunditAggregate:
    def test_empty_list_returns_zeros(self):
        agg = compute_pundit_aggregate([])
        assert agg["mean"] == 0.0
        assert agg["std"] == 0.0
        assert agg["count"] == 0
        assert agg["positive_rate"] == 0.0

    def test_single_positive_score(self):
        agg = compute_pundit_aggregate([2.0])
        assert agg["mean"] == 2.0
        assert agg["std"] == 0.0
        assert agg["count"] == 1
        assert agg["positive_rate"] == 1.0

    def test_all_negative(self):
        agg = compute_pundit_aggregate([-1.0, -2.0, -0.5])
        assert agg["mean"] < 0
        assert agg["positive_rate"] == 0.0

    def test_mixed_scores(self):
        agg = compute_pundit_aggregate([1.0, -1.0, 0.5, -0.5])
        assert abs(agg["mean"] - 0.0) < 1e-9
        assert agg["count"] == 4
        # Only scores > 0 count as positive (0.0 is not positive)
        assert abs(agg["positive_rate"] - 0.5) < 1e-9

    def test_count_is_correct(self):
        scores = [0.1 * i for i in range(10)]
        agg = compute_pundit_aggregate(scores)
        assert agg["count"] == 10

    def test_std_is_population_std(self):
        """Verify population std (pstdev), not sample std."""
        import statistics

        scores = [1.0, 2.0, 3.0]
        agg = compute_pundit_aggregate(scores)
        assert abs(agg["std"] - statistics.pstdev(scores)) < 1e-9

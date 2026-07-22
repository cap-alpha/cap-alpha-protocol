"""
Unit tests for pipeline/src/scheduling/priority.py — Issue #1129 Phase 1
(IMPLEMENTATION SPEC v1, §2 "Scheduling math").

All functions under test are pure (no DB/network I/O, `now` always injected),
so this whole suite runs with no external dependencies.
"""

from datetime import datetime, timedelta, timezone

import pytest
from src.scheduling.priority import (
    BASE_INTERVALS,
    INTERVAL_FLOOR,
    V_MAX,
    V_MIN,
    WINDOW_RAMP_LEAD,
    ScheduleResult,
    clamp_attempt,
    compute_priority,
    compute_schedule,
    compute_urgency,
    next_check_at,
    next_interval,
    normalize_min_max,
    prominence,
    visibility,
    window_proximity,
)


def _t(offset_days: float = 0, offset_hours: float = 0) -> datetime:
    """Anchor datetime + offset, for readable window/ramp fixtures."""
    anchor = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return anchor + timedelta(days=offset_days, hours=offset_hours)


# ---------------------------------------------------------------------------
# normalize_min_max()
# ---------------------------------------------------------------------------


class TestNormalizeMinMax:
    def test_empty_pool_returns_zero(self):
        assert normalize_min_max(5.0, []) == 0.0

    def test_single_value_pool_returns_zero(self):
        # A lone active pundit has nobody to be "more prominent than" —
        # must not divide by zero.
        assert normalize_min_max(42.0, [42.0]) == 0.0

    def test_all_equal_pool_returns_zero(self):
        # Every pundit tied is degenerate the same way a single-pundit pool is.
        assert normalize_min_max(3.0, [3.0, 3.0, 3.0]) == 0.0

    def test_all_zero_pool_returns_zero_not_nan(self):
        # Zero posts across the board must not produce 0/0 = NaN.
        result = normalize_min_max(0.0, [0.0, 0.0, 0.0])
        assert result == 0.0
        assert result == result  # NaN != NaN; this asserts result is NOT NaN

    def test_value_at_pool_min(self):
        assert normalize_min_max(1.0, [1.0, 5.0, 10.0]) == 0.0

    def test_value_at_pool_max(self):
        assert normalize_min_max(10.0, [1.0, 5.0, 10.0]) == 1.0

    def test_value_at_pool_midpoint(self):
        assert normalize_min_max(5.5, [1.0, 10.0]) == pytest.approx(0.5)

    def test_value_outside_pool_range_not_clamped(self):
        # Spec doesn't say to clamp values that fall outside the pool
        # (e.g. a stale/inconsistent pool); min-max naturally extrapolates.
        assert normalize_min_max(15.0, [1.0, 10.0]) == pytest.approx(14.0 / 9.0)


# ---------------------------------------------------------------------------
# prominence()
# ---------------------------------------------------------------------------


class TestProminence:
    def test_published_true_contributes_point_six(self):
        # Zero posts/claims pool contribution isolates the published term.
        result = prominence(
            published=True,
            posts_per_month=0.0,
            claim_count=0.0,
            posts_per_month_pool=[0.0],
            claim_count_pool=[0.0],
        )
        assert result == pytest.approx(0.6)

    def test_published_false_contributes_zero(self):
        result = prominence(
            published=False,
            posts_per_month=0.0,
            claim_count=0.0,
            posts_per_month_pool=[0.0],
            claim_count_pool=[0.0],
        )
        assert result == 0.0

    def test_full_prominence_max_case(self):
        # published + top of both pools -> 0.6 + 0.3 + 0.1 = 1.0
        result = prominence(
            published=True,
            posts_per_month=100.0,
            claim_count=50.0,
            posts_per_month_pool=[0.0, 50.0, 100.0],
            claim_count_pool=[0.0, 25.0, 50.0],
        )
        assert result == pytest.approx(1.0)

    def test_single_pundit_pool_only_published_term_survives(self):
        # Single active pundit: posts/claims norm both degrade to 0 (no peer
        # to compare against), so prominence is driven entirely by `published`.
        result = prominence(
            published=True,
            posts_per_month=17.0,
            claim_count=9.0,
            posts_per_month_pool=[17.0],
            claim_count_pool=[9.0],
        )
        assert result == pytest.approx(0.6)

    def test_zero_posts_pundit_among_active_posters(self):
        # A quiet pundit (0 posts) among a pool that includes non-zero posters
        # normalizes to the pool minimum, not NaN.
        result = prominence(
            published=False,
            posts_per_month=0.0,
            claim_count=0.0,
            posts_per_month_pool=[0.0, 10.0, 20.0],
            claim_count_pool=[0.0, 5.0, 10.0],
        )
        assert result == 0.0

    def test_weights_sum_to_one_at_full_saturation(self):
        result = prominence(
            published=True,
            posts_per_month=1.0,
            claim_count=1.0,
            posts_per_month_pool=[0.0, 1.0],
            claim_count_pool=[0.0, 1.0],
        )
        assert result == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# visibility()
# ---------------------------------------------------------------------------


class TestVisibility:
    def test_zero_events(self):
        assert visibility(0) == 0.0

    def test_negative_events_clamped_to_zero(self):
        assert visibility(-3) == 0.0

    def test_below_saturation(self):
        assert visibility(2) == pytest.approx(0.4)

    def test_at_saturation_exactly(self):
        assert visibility(5) == 1.0

    def test_above_saturation_clamped_to_one(self):
        assert visibility(10) == 1.0

    def test_fractional_events(self):
        assert visibility(2.5) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# window_proximity()
# ---------------------------------------------------------------------------


class TestWindowProximity:
    def setup_method(self):
        self.ws = _t(20)  # window_start
        self.we = _t(25)  # window_end

    def test_before_ramp_start_is_zero(self):
        now = self.ws - WINDOW_RAMP_LEAD - timedelta(days=1)
        assert window_proximity(now, self.ws, self.we) == 0.0

    def test_exactly_at_ramp_start_is_zero(self):
        # ramp_start = ws - 14d is the inclusive lower bound of the ramp
        # branch; the ramp value there is 0/14d = 0.0.
        now = self.ws - WINDOW_RAMP_LEAD
        assert window_proximity(now, self.ws, self.we) == pytest.approx(0.0)

    def test_ramp_midpoint(self):
        now = self.ws - (WINDOW_RAMP_LEAD / 2)
        assert window_proximity(now, self.ws, self.we) == pytest.approx(0.5)

    def test_just_before_window_start_near_one(self):
        now = self.ws - timedelta(seconds=1)
        result = window_proximity(now, self.ws, self.we)
        assert result < 1.0
        assert result == pytest.approx(1.0, abs=1e-4)

    def test_exactly_at_window_start_is_one(self):
        assert window_proximity(self.ws, self.ws, self.we) == 1.0

    def test_inside_window_is_one(self):
        mid = self.ws + (self.we - self.ws) / 2
        assert window_proximity(mid, self.ws, self.we) == 1.0

    def test_exactly_at_window_end_is_one(self):
        # Inclusive per spec: "ws <= now <= we -> 1.0"
        assert window_proximity(self.we, self.ws, self.we) == 1.0

    def test_just_after_window_end_is_tail_sentinel(self):
        now = self.we + timedelta(seconds=1)
        assert window_proximity(now, self.ws, self.we) is None

    def test_far_after_window_end_is_tail_sentinel(self):
        now = self.we + timedelta(days=365)
        assert window_proximity(now, self.ws, self.we) is None

    def test_zero_length_window_at_instant_is_one(self):
        instant = _t(20)
        assert window_proximity(instant, instant, instant) == 1.0

    def test_zero_length_window_just_after_is_tail(self):
        instant = _t(20)
        after = instant + timedelta(seconds=1)
        assert window_proximity(after, instant, instant) is None


# ---------------------------------------------------------------------------
# compute_priority() — the max() soft-OR
# ---------------------------------------------------------------------------


class TestComputePriority:
    def test_window_proximity_dominates(self):
        p = compute_priority(
            window_proximity_value=0.9, visibility_value=0.1, prominence_value=0.1
        )
        assert p == pytest.approx(0.9)

    def test_visibility_dominates(self):
        p = compute_priority(
            window_proximity_value=0.0, visibility_value=0.8, prominence_value=0.1
        )
        assert p == pytest.approx(0.8)

    def test_prominence_dominates_scaled_by_point_seven(self):
        # prominence=1.0 contributes 0.7*1.0 = 0.7, which beats the other two.
        p = compute_priority(
            window_proximity_value=0.2, visibility_value=0.3, prominence_value=1.0
        )
        assert p == pytest.approx(0.7)

    def test_prominence_alone_caps_priority_at_point_seven(self):
        # Even a maximally prominent pundit (prominence=1.0) with zero
        # window/visibility signal never exceeds P=0.7.
        p = compute_priority(
            window_proximity_value=0.0, visibility_value=0.0, prominence_value=1.0
        )
        assert p == pytest.approx(0.7)

    def test_all_zero_is_zero(self):
        p = compute_priority(
            window_proximity_value=0.0, visibility_value=0.0, prominence_value=0.0
        )
        assert p == 0.0

    def test_all_one_is_one(self):
        p = compute_priority(
            window_proximity_value=1.0, visibility_value=1.0, prominence_value=1.0
        )
        assert p == 1.0

    def test_none_window_proximity_excluded_from_max(self):
        # TAIL regime sentinel: falls back to visibility/prominence only.
        p_with_tail = compute_priority(
            window_proximity_value=None, visibility_value=0.4, prominence_value=0.2
        )
        p_without_window_term = compute_priority(
            window_proximity_value=0.0, visibility_value=0.4, prominence_value=0.2
        )
        # None and an explicit 0.0 happen to agree here because 0.0 doesn't
        # win the max anyway — the important distinction is that None never
        # raises and never becomes the winning (implicitly negative) term.
        assert p_with_tail == p_without_window_term == pytest.approx(0.4)

    def test_none_window_proximity_does_not_suppress_high_visibility(self):
        p = compute_priority(
            window_proximity_value=None, visibility_value=1.0, prominence_value=0.0
        )
        assert p == 1.0


# ---------------------------------------------------------------------------
# compute_urgency() — V floor/ceiling
# ---------------------------------------------------------------------------


class TestComputeUrgency:
    def test_p_zero_gives_v_ceiling(self):
        assert compute_urgency(0.0) == pytest.approx(V_MAX)

    def test_p_one_gives_v_floor(self):
        assert compute_urgency(1.0) == pytest.approx(V_MIN)

    def test_p_half(self):
        assert compute_urgency(0.5) == pytest.approx(0.55)

    def test_malformed_p_above_one_clamped_to_floor(self):
        assert compute_urgency(2.0) == V_MIN

    def test_malformed_negative_p_clamped_to_ceiling(self):
        assert compute_urgency(-1.0) == V_MAX

    def test_v_always_within_bounds_across_p_range(self):
        for p_hundredth in range(0, 101):
            p = p_hundredth / 100.0
            v = compute_urgency(p)
            assert V_MIN <= v <= V_MAX


# ---------------------------------------------------------------------------
# clamp_attempt() + next_interval() — backoff progression, attempt clamp, floor
# ---------------------------------------------------------------------------


class TestClampAttempt:
    def test_in_range_attempts_unchanged(self):
        for i in range(len(BASE_INTERVALS)):
            assert clamp_attempt(i) == i

    def test_out_of_range_clamps_to_last_index(self):
        last = len(BASE_INTERVALS) - 1
        assert clamp_attempt(len(BASE_INTERVALS)) == last
        assert clamp_attempt(100) == last

    def test_negative_attempt_clamps_to_zero(self):
        assert clamp_attempt(-1) == 0
        assert clamp_attempt(-100) == 0


class TestNextInterval:
    def test_base_progression_at_v_ceiling(self):
        # At V=1.0 (P=0), next_interval should equal the raw base for each attempt.
        for attempt, base in enumerate(BASE_INTERVALS):
            assert next_interval(attempt, urgency=1.0) == base

    def test_attempt_zero_full_urgency_is_one_day(self):
        assert next_interval(0, urgency=1.0) == timedelta(days=1)

    def test_attempt_three_full_urgency_is_thirty_days(self):
        assert next_interval(3, urgency=1.0) == timedelta(days=30)

    def test_attempt_beyond_range_clamps_to_thirty_day_base(self):
        assert next_interval(4, urgency=1.0) == timedelta(days=30)
        assert next_interval(999, urgency=1.0) == timedelta(days=30)

    def test_negative_attempt_clamps_to_one_day_base(self):
        assert next_interval(-5, urgency=1.0) == timedelta(days=1)

    def test_low_urgency_scales_interval_down(self):
        # attempt=3 (30d base) at V_MIN=0.1 -> 3 days, well above the 6h floor.
        assert next_interval(3, urgency=V_MIN) == timedelta(days=3)

    def test_floor_triggers_for_short_base_and_low_urgency(self):
        # attempt=0 (1d base) at V_MIN=0.1 -> 2.4h, below the 6h floor.
        result = next_interval(0, urgency=V_MIN)
        assert result == INTERVAL_FLOOR
        assert result == timedelta(hours=6)

    def test_floor_never_undershot_even_at_extreme_urgency(self):
        # Defensive: even a (malformed) urgency of 0 must not go below the floor.
        result = next_interval(0, urgency=0.0)
        assert result == INTERVAL_FLOOR

    def test_interval_is_never_negative(self):
        for attempt in range(-2, 6):
            for hundredth in range(0, 101):
                urgency = hundredth / 100.0
                assert next_interval(attempt, urgency) >= timedelta(0)


class TestNextCheckAt:
    def test_adds_interval_to_now(self):
        now = _t(0)
        result = next_check_at(now, attempt=0, urgency=1.0)
        assert result == now + timedelta(days=1)

    def test_floored_interval_still_adds_correctly(self):
        now = _t(0)
        result = next_check_at(now, attempt=0, urgency=V_MIN)
        assert result == now + INTERVAL_FLOOR

    def test_result_is_always_after_now(self):
        now = _t(0)
        for attempt in range(len(BASE_INTERVALS)):
            for hundredth in (0, 25, 50, 75, 100):
                urgency = max(V_MIN, hundredth / 100.0)
                assert next_check_at(now, attempt, urgency) > now


# ---------------------------------------------------------------------------
# compute_schedule() — end-to-end composition
# ---------------------------------------------------------------------------


class TestComputeSchedule:
    def test_normal_regime_returns_next_check_at(self):
        ws = _t(20)
        we = _t(25)
        result = compute_schedule(
            now=_t(10),
            window_start=ws,
            window_end=we,
            published=True,
            posts_per_month=10.0,
            claim_count=5.0,
            posts_per_month_pool=[0.0, 10.0, 20.0],
            claim_count_pool=[0.0, 5.0, 10.0],
            matched_events_trailing_7d=0,
            attempt=0,
        )
        assert isinstance(result, ScheduleResult)
        assert result.in_tail is False
        assert result.next_check_at is not None
        assert result.next_check_at > _t(10)
        assert 0.0 <= result.priority_score <= 1.0
        assert V_MIN <= result.urgency <= V_MAX

    def test_tail_regime_returns_none_next_check_at(self):
        ws = _t(20)
        we = _t(25)
        result = compute_schedule(
            now=_t(30),  # past window_end
            window_start=ws,
            window_end=we,
            published=False,
            posts_per_month=0.0,
            claim_count=0.0,
            posts_per_month_pool=[0.0],
            claim_count_pool=[0.0],
            matched_events_trailing_7d=0,
            attempt=2,
        )
        assert result.in_tail is True
        assert result.next_check_at is None
        # priority_score is still a well-formed diagnostic value even in tail.
        assert 0.0 <= result.priority_score <= 1.0

    def test_single_pundit_pool_does_not_crash(self):
        # Regression guard: a single-active-pundit corpus must not raise
        # ZeroDivisionError inside the prominence normalization.
        now = _t(0)
        result = compute_schedule(
            now=now,
            window_start=_t(5),
            window_end=_t(10),
            published=True,
            posts_per_month=3.0,
            claim_count=1.0,
            posts_per_month_pool=[3.0],
            claim_count_pool=[1.0],
            matched_events_trailing_7d=0,
            attempt=0,
        )
        assert result.next_check_at is not None

    def test_high_visibility_pins_near_term_check_despite_far_window(self):
        # A claim with a far-off window but heavy news coverage should still
        # get a near-term next_check_at via the visibility term.
        now = _t(0)
        result = compute_schedule(
            now=now,
            window_start=_t(200),
            window_end=_t(210),
            published=False,
            posts_per_month=0.0,
            claim_count=0.0,
            posts_per_month_pool=[0.0],
            claim_count_pool=[0.0],
            matched_events_trailing_7d=5,  # saturates visibility to 1.0
            attempt=0,
        )
        assert result.priority_score == pytest.approx(1.0)
        assert result.urgency == pytest.approx(V_MIN)
        assert result.next_check_at == now + INTERVAL_FLOOR

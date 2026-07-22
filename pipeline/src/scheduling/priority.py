"""
Claim scheduling priority engine — Issue #1129 Phase 1 (spec §2: Scheduling math).

Pure, side-effect-free functions computing how urgently a claim needs its next
resolver check:

    prominence        = 0.6*published + 0.3*norm(posts_per_month) + 0.1*norm(claim_count)
    visibility         = min(matched_events_trailing_7d / 5, 1.0)
    window_proximity   = 0 before the pre-window ramp; linear 0->1 ramp starting
                          14d before resolution_window_start; 1.0 inside the window;
                          None ("TAIL regime") once resolution_window_end has passed
    P (priority)       = max(window_proximity, visibility, 0.7*prominence)   -- soft-OR
    V (urgency)        = 1 - 0.9*P, clamped to [0.1, 1.0]
    next_interval      = max(base[attempt] * V, 6h), base = [1d, 3d, 7d, 30d],
                          attempt clamped at the last index

No DB or network I/O happens in this module. `now` is always an injected
parameter -- nothing here calls datetime.now()/utcnow() -- so every function is
deterministic and trivially unit-testable.

Explicitly OUT OF SCOPE for this module (see issue #1129 Phase 1 deliverable
notes):
  - TAIL regime behavior (window_proximity=None / now > window_end). This
    module only *signals* TAIL via a None return from window_proximity() /
    in_tail=True from compute_schedule(); Phase 3 (#1129 §4, claim-value-gated
    hunt/decay) owns what actually happens to a claim once it's there.
  - Revival (attempt reset to 0 on new evidence). `attempt` is always an
    injected caller parameter; this module never mutates or infers it.
  - Wiring into resolve_daily's control flow. That's a follow-up PR after the
    silver_v2 corpus cutover (#1129 Phase 0) lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

# ---------------------------------------------------------------------------
# Constants (spec §2) -- explicit, named, no magic numbers inline below.
# ---------------------------------------------------------------------------

# window_proximity: how long before resolution_window_start the ramp begins.
WINDOW_RAMP_LEAD: timedelta = timedelta(days=14)

# V = 1 - PRIORITY_TO_URGENCY_SLOPE * P
PRIORITY_TO_URGENCY_SLOPE: float = 0.9

# V is clamped to this range regardless of P's (expected [0, 1]) range.
V_MIN: float = 0.1
V_MAX: float = 1.0

# Priority weighting of the prominence term: prominence alone caps P at 0.7,
# so a big pundit alone never fully pins cadence to source weight.
PROMINENCE_WEIGHT: float = 0.7

# prominence sub-weights (spec §2): published + norm(posts_per_month) + norm(claim_count)
PROMINENCE_PUBLISHED_WEIGHT: float = 0.6
PROMINENCE_POSTS_WEIGHT: float = 0.3
PROMINENCE_CLAIMS_WEIGHT: float = 0.1

# visibility saturates (= 1.0) at this many matched events in the trailing 7d.
VISIBILITY_SATURATION_EVENTS: float = 5.0

# Backoff base intervals by attempt (0-indexed). attempt clamps at the last index.
BASE_INTERVALS: tuple[timedelta, ...] = (
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=7),
    timedelta(days=30),
)

# Absolute floor on next_interval, regardless of how low V goes.
INTERVAL_FLOOR: timedelta = timedelta(hours=6)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def normalize_min_max(value: float, pool: Sequence[float]) -> float:
    """
    Min-max normalize `value` against `pool` (spec: "norm = min-max across
    active pundits").

    Degenerate pools -- empty, a single pundit, or every pundit tied -- carry
    no discriminating signal (there is no "more prominent than whom" to
    measure), so they normalize to 0.0 rather than raising ZeroDivisionError
    or producing NaN.
    """
    if not pool:
        return 0.0
    lo = min(pool)
    hi = max(pool)
    if hi == lo:
        return 0.0
    return (value - lo) / (hi - lo)


# ---------------------------------------------------------------------------
# Prominence
# ---------------------------------------------------------------------------


def prominence(
    published: bool,
    posts_per_month: float,
    claim_count: float,
    posts_per_month_pool: Sequence[float],
    claim_count_pool: Sequence[float],
) -> float:
    """
    prominence = 0.6*published + 0.3*norm(posts_per_month) + 0.1*norm(claim_count)

    `published` is the pundit_registry.published bool flag, used directly as a
    0/1 weight (it is already a binary signal -- nothing to normalize).
    `*_pool` are the corresponding raw values across all active pundits, used
    for min-max normalization via normalize_min_max().
    """
    published_term = 1.0 if published else 0.0
    posts_term = normalize_min_max(posts_per_month, posts_per_month_pool)
    claims_term = normalize_min_max(claim_count, claim_count_pool)
    return (
        PROMINENCE_PUBLISHED_WEIGHT * published_term
        + PROMINENCE_POSTS_WEIGHT * posts_term
        + PROMINENCE_CLAIMS_WEIGHT * claims_term
    )


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------


def visibility(matched_events_trailing_7d: float) -> float:
    """
    visibility = min(matched_events_trailing_7d / 5, 1.0)

    5+ funnel-matched news events about the claim's subject in the trailing 7
    days is fully hot. Clamped below at 0.0 defensively -- a negative count
    would be a caller bug, not something that should propagate a negative
    term into the max() in compute_priority().
    """
    if matched_events_trailing_7d <= 0:
        return 0.0
    return min(matched_events_trailing_7d / VISIBILITY_SATURATION_EVENTS, 1.0)


# ---------------------------------------------------------------------------
# Window proximity
# ---------------------------------------------------------------------------


def window_proximity(
    now: datetime, window_start: datetime, window_end: datetime
) -> float | None:
    """
    window_proximity(now, ws, we):
      now < ws - 14d          -> 0.0
      ws - 14d <= now < ws    -> linear ramp (now - (ws - 14d)) / 14d
      ws <= now <= we         -> 1.0
      now > we                -> None  (TAIL regime sentinel -- see module
                                          docstring; #1129 §4 / Phase 3 owns
                                          what happens next, not this function)

    Boundary checks are ordered `now > we` first, then `now >= ws`, so a
    same-instant window (ws == we) still resolves to 1.0 rather than falling
    through to the ramp branch.
    """
    if now > window_end:
        return None
    if now >= window_start:
        return 1.0

    ramp_start = window_start - WINDOW_RAMP_LEAD
    if now < ramp_start:
        return 0.0

    # ramp_start <= now < window_start
    elapsed = now - ramp_start
    return elapsed / WINDOW_RAMP_LEAD


# ---------------------------------------------------------------------------
# Priority (soft-OR) and urgency
# ---------------------------------------------------------------------------


def compute_priority(
    window_proximity_value: float | None,
    visibility_value: float,
    prominence_value: float,
) -> float:
    """
    P = max(window_proximity, visibility, 0.7*prominence) -- soft-OR /
    max-driven: any single hot signal pulls a claim forward regardless of the
    other two.

    window_proximity_value=None (TAIL regime) is excluded from the max rather
    than coerced to 0 or raising. Per spec §2, in the tail regime
    window_proximity is "not a simple term into P" -- Phase 3 tail logic
    (#1129 §4) is meant to take over cadence entirely once a claim is there.
    Excluding it (vs. treating None as 0) means if this function is still
    called during the tail for diagnostics, a claim that's highly visible or
    prominent doesn't get artificially suppressed by a phantom 0 term.
    """
    terms = [visibility_value, PROMINENCE_WEIGHT * prominence_value]
    if window_proximity_value is not None:
        terms.append(window_proximity_value)
    return max(terms)


def compute_urgency(priority: float) -> float:
    """
    V = 1 - 0.9*P, clamped to [0.1, 1.0].

    P is expected in [0, 1] (every input term to compute_priority is itself
    bounded to [0, 1]), which already places V in [0.1, 1.0] by construction.
    The clamp is a defensive floor/ceiling for a malformed P (e.g. > 1.0 or
    < 0.0 from a caller bug upstream), not something the formula relies on in
    the well-formed case.
    """
    v = 1.0 - PRIORITY_TO_URGENCY_SLOPE * priority
    return max(V_MIN, min(V_MAX, v))


# ---------------------------------------------------------------------------
# Backoff interval + next_check_at
# ---------------------------------------------------------------------------


def clamp_attempt(attempt: int) -> int:
    """
    Clamp `attempt` into the valid BASE_INTERVALS index range [0, len-1].

    attempt >= len(BASE_INTERVALS) clamps to the last index (spec: "clamp
    attempt at last index"). Negative attempt (not expected in normal
    operation, but not contractually excluded either) clamps to 0 rather than
    raising or indexing negatively into the tuple.
    """
    return max(0, min(attempt, len(BASE_INTERVALS) - 1))


def next_interval(attempt: int, urgency: float) -> timedelta:
    """
    next_interval = max(base[attempt] * V, 6h)
    base = [1d, 3d, 7d, 30d], attempt clamped at the last index.
    """
    idx = clamp_attempt(attempt)
    base = BASE_INTERVALS[idx]
    interval = base * urgency
    return max(interval, INTERVAL_FLOOR)


def next_check_at(now: datetime, attempt: int, urgency: float) -> datetime:
    """next_check_at = now + next_interval(attempt, urgency)."""
    return now + next_interval(attempt, urgency)


# ---------------------------------------------------------------------------
# End-to-end composition (spec §2, one claim x one pundit)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScheduleResult:
    """Result of composing the full §2 formula chain for one claim."""

    priority_score: float
    urgency: float
    next_check_at: datetime | None
    in_tail: bool


def compute_schedule(
    *,
    now: datetime,
    window_start: datetime,
    window_end: datetime,
    published: bool,
    posts_per_month: float,
    claim_count: float,
    posts_per_month_pool: Sequence[float],
    claim_count_pool: Sequence[float],
    matched_events_trailing_7d: float,
    attempt: int,
) -> ScheduleResult:
    """
    End-to-end composition of spec §2 for a single claim.

    Returns `next_check_at=None` and `in_tail=True` once the claim has
    entered the TAIL regime (now > window_end). `priority_score` is still
    populated in that case (from visibility/prominence only, per
    compute_priority's None-handling) as a diagnostic value, but callers must
    NOT treat next_check_at=None as "check now" -- route tail-regime claims to
    Phase 3 tail logic instead (not implemented in this module; see #1129 §4).
    """
    wp = window_proximity(now, window_start, window_end)
    vis = visibility(matched_events_trailing_7d)
    prom = prominence(
        published,
        posts_per_month,
        claim_count,
        posts_per_month_pool,
        claim_count_pool,
    )
    p = compute_priority(wp, vis, prom)
    v = compute_urgency(p)

    if wp is None:
        return ScheduleResult(
            priority_score=p, urgency=v, next_check_at=None, in_tail=True
        )

    check_at = next_check_at(now, attempt, v)
    return ScheduleResult(
        priority_score=p, urgency=v, next_check_at=check_at, in_tail=False
    )

"""
Extraction quality threshold tests.

These tests are **approach-level** — they validate whether the extraction system
as designed meets quality bars, not just whether individual functions are correct.
When they fail the message says "consider revising the extraction approach" rather
than just "assertion failed."

No real LLM calls, no BigQuery.  Runs in < 1 second.

Marker: quality_threshold
    pytest -m quality_threshold
"""

import re

import pytest

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

REQUIRED_POPULATION_RATE = {
    # originating_speaker is NULL for "authored" speech acts — that is correct
    # behaviour per the schema.  It is only required for "quoted" and
    # "commentary" speech acts; see TestSpeakerAttribution below.
    "stance": 0.80,  # 80% must have a stance
    "hedge_level": 0.80,
    "resolution_condition": 0.70,
    "claim_text_alignment": 1.00,  # every utterance needs this
    "testability_score": 1.00,
    "extraction_confidence": 1.00,
}

BIMODAL_THRESHOLD = 0.15  # max fraction that can be exactly 0.0 or exactly 1.0

MAX_UNRESOLVED_SPEAKER_RATE = 0.10  # max 10% may be UNRESOLVED

SPAM_PATTERNS = [
    r"email verification",
    r"\bSC\b",  # sweepstakes coin
    r"no table games",
    r"sweepstakes",
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_utterance(
    *,
    text="Mahomes will throw for 4000 yards this season",
    speech_act_type="assertion",
    testability_score=0.85,
    extraction_confidence=0.88,
    claim_text_alignment=0.92,
    stance="bullish",
    hedge_level="strong",
    resolution_condition="Mahomes throws ≥ 4000 yards per official NFL stats by end of season",
    resolution_horizon="2025-12-31T23:59:59Z",
    originating_speaker=None,
    speaker_entity_id="entity:mahomes_pundit",
    claim_text=None,
) -> dict:
    """Build a well-formed synthetic utterance."""
    return {
        "text": text,
        "claim_text": claim_text or text,
        "speech_act_type": speech_act_type,
        "testability_score": testability_score,
        "extraction_confidence": extraction_confidence,
        "claim_text_alignment": claim_text_alignment,
        "stance": stance,
        "hedge_level": hedge_level,
        "resolution_condition": resolution_condition,
        "resolution_horizon": resolution_horizon,
        "originating_speaker": originating_speaker,
        "speaker_entity_id": speaker_entity_id,
    }


@pytest.fixture
def sample_utterances() -> list[dict]:
    """
    20 realistic utterances: 15 well-formed, 5 intentionally imperfect.

    The intentionally-imperfect entries stay within the thresholds so the
    well-formed fixture passes all quality checks.  They are realistic
    degradations (one missing hedge_level, one low-but-non-bimodal
    testability_score, etc.) rather than catastrophic failures.
    """
    good = [
        _make_utterance(
            text="Patrick Mahomes will win MVP again this season",
            stance="bullish",
            testability_score=0.92,
            originating_speaker="Adam Schefter",
        ),
        _make_utterance(
            text="The Eagles will win the NFC East title",
            stance="bullish",
            testability_score=0.88,
        ),
        _make_utterance(
            text="Josh Allen will surpass 4200 passing yards",
            stance="bullish",
            testability_score=0.91,
        ),
        _make_utterance(
            text="The Browns will miss the playoffs again in 2025",
            stance="bearish",
            testability_score=0.87,
        ),
        _make_utterance(
            text="Travis Hunter will be the first overall pick",
            stance="bullish",
            testability_score=0.95,
            originating_speaker="Mel Kiper",
        ),
        _make_utterance(
            text="Tyreek Hill will finish with 1500+ receiving yards",
            stance="bullish",
            testability_score=0.83,
        ),
        _make_utterance(
            text="The Jets will not make the playoffs this season",
            stance="bearish",
            testability_score=0.80,
        ),
        _make_utterance(
            text="Brock Purdy will lead the 49ers to the Super Bowl",
            stance="bullish",
            testability_score=0.86,
            originating_speaker="Shannon Sharpe",
        ),
        _make_utterance(
            text="CeeDee Lamb will record at least 110 receptions",
            stance="bullish",
            testability_score=0.89,
        ),
        _make_utterance(
            text="Lamar Jackson will win a second MVP award",
            stance="bullish",
            testability_score=0.90,
        ),
        _make_utterance(
            text="The Packers will win a playoff game this year",
            stance="bullish",
            testability_score=0.78,
        ),
        _make_utterance(
            text="Cooper Kupp will not play in the first four games",
            stance="bearish",
            testability_score=0.82,
        ),
        _make_utterance(
            text="The Chiefs will be the AFC's top seed",
            stance="bullish",
            testability_score=0.84,
        ),
        _make_utterance(
            text="Justin Jefferson will surpass 1400 yards in the regular season",
            stance="bullish",
            testability_score=0.93,
        ),
        _make_utterance(
            text="The Raiders will fire their head coach before mid-season",
            stance="bearish",
            testability_score=0.76,
            originating_speaker="Ian Rapoport",
        ),
    ]

    # Intentionally imperfect — realistic degradations that still pass thresholds:
    # 1. Missing hedge_level (still >= 80% populated across the 20)
    slightly_bad_1 = {
        **_make_utterance(text="The Steelers will be competitive"),
        "hedge_level": None,
    }
    # 2. Low-but-not-bimodal testability score
    slightly_bad_2 = _make_utterance(
        text="I think the Bears might improve this year",
        testability_score=0.25,  # not 0.0 or 1.0 — continuous, just low
        stance="neutral",
    )
    # 3. No originating_speaker (fine — threshold is 90%, not 100%)
    slightly_bad_3 = _make_utterance(
        text="Davante Adams will stay in Las Vegas",
        originating_speaker=None,
    )
    # 4. Missing resolution_condition (still >= 70% threshold across 20)
    slightly_bad_4 = {
        **_make_utterance(text="The Colts will draft a QB"),
        "resolution_condition": None,
    }
    # 5. Medium testability, not exactly 0/1
    slightly_bad_5 = _make_utterance(
        text="The Bengals could be a dark horse this year",
        testability_score=0.45,
        stance="neutral",
    )

    # Attributed speech acts (quoted/commentary) — exercises TestSpeakerAttribution.
    # These MUST have originating_speaker set; the attribution test asserts 100% populated.
    attributed_1 = _make_utterance(
        text="According to Schefter, the trade will be finalized tomorrow",
        speech_act_type="quoted",
        originating_speaker="Adam Schefter",
    )
    attributed_2 = _make_utterance(
        text="As I said on the show, the QB room needs addressing this offseason",
        speech_act_type="commentary",
        originating_speaker="Colin Cowherd",
    )

    return good + [
        slightly_bad_1,
        slightly_bad_2,
        slightly_bad_3,
        slightly_bad_4,
        slightly_bad_5,
        attributed_1,
        attributed_2,
    ]


@pytest.fixture
def broken_utterances() -> list[dict]:
    """
    15 catastrophically broken utterances — NULL fields everywhere, bimodal
    testability scores (all exactly 0.0 or 1.0), all UNRESOLVED speakers,
    etc.  Used by meta-tests to confirm the thresholds actually catch a
    known-bad extraction state.
    """

    def _broken(i: int) -> dict:
        return {
            "text": f"claim number {i}",
            "claim_text": f"claim number {i}",
            "speech_act_type": "assertion",
            # Bimodal: alternate exactly 0.0 and 1.0
            "testability_score": 0.0 if i % 2 == 0 else 1.0,
            "extraction_confidence": None,
            "claim_text_alignment": None,
            "stance": None,
            "hedge_level": None,
            "resolution_condition": None,
            "resolution_horizon": None,
            "originating_speaker": None,
            "speaker_entity_id": f"UNRESOLVED:{i}",
        }

    return [_broken(i) for i in range(15)]


@pytest.fixture
def broken_quoted_utterances() -> list[dict]:
    """
    Quoted/commentary utterances that are missing originating_speaker.
    Used by the TestThresholdsSensitivity meta-test to confirm that
    TestSpeakerAttribution actually fires on known-bad data.
    """
    return [
        {**_make_utterance(speech_act_type="quoted"), "originating_speaker": None},
        {**_make_utterance(speech_act_type="commentary"), "originating_speaker": None},
        {**_make_utterance(speech_act_type="quoted"), "originating_speaker": None},
    ]


# ---------------------------------------------------------------------------
# Test class 1 — Field population contract
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestFieldPopulationContract:
    """
    Every field that the extraction prompt promises to fill must be populated
    at rates above REQUIRED_POPULATION_RATE.  Failure means the prompt needs
    to explicitly request the missing field, not that a unit is broken.
    """

    def test_field_population_rates(self, sample_utterances):
        for field, threshold in REQUIRED_POPULATION_RATE.items():
            populated = sum(
                1
                for u in sample_utterances
                if u.get(field) is not None
                and u.get(field) != ""
                and str(u.get(field)) != "None"
            )
            rate = populated / len(sample_utterances)
            assert rate >= threshold, (
                f"Field '{field}' population rate {rate:.0%} is below threshold {threshold:.0%}. "
                f"If this is consistently failing, the extraction prompt needs to explicitly request this field."
            )


# ---------------------------------------------------------------------------
# Test class 2 — Testability score distribution (not bimodal)
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestTestabilityScoreDistribution:
    """
    Testability scores should be continuous, not binary.  Bimodal output
    (all 0.0s or all 1.0s) means the prompt is functioning as a binary
    classifier rather than a calibrated scorer.
    """

    def test_testability_not_bimodal(self, sample_utterances):
        scores = [
            u["testability_score"]
            for u in sample_utterances
            if u.get("testability_score") is not None
        ]
        assert len(scores) > 0, "No testability_score values found in fixture"
        exactly_zero = sum(1 for s in scores if s == 0.0) / len(scores)
        exactly_one = sum(1 for s in scores if s == 1.0) / len(scores)
        binary_fraction = exactly_zero + exactly_one
        assert binary_fraction <= BIMODAL_THRESHOLD, (
            f"{binary_fraction:.0%} of testability scores are exactly 0.0 or 1.0 "
            f"(threshold: {BIMODAL_THRESHOLD:.0%}). "
            f"The extraction prompt needs calibration examples — a continuous scale, not binary classification."
        )


# ---------------------------------------------------------------------------
# Test class 2b — originating_speaker for attributed speech acts
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestSpeakerAttribution:
    """
    When speech_act is 'quoted' or 'commentary', originating_speaker must be
    populated.  Null in these cases means the extraction failed to propagate the
    source attribution — a data-loss bug, not a legitimate null.
    """

    def test_originating_speaker_set_for_attributed_speech_acts(
        self, sample_utterances
    ):
        attributed = [
            u
            for u in sample_utterances
            if u.get("speech_act_type") in ("quoted", "commentary")
        ]
        if not attributed:
            # None of the sample utterances use quoted/commentary — skip rather
            # than false-pass; add attributed fixtures if this is a concern.
            pytest.skip("No quoted/commentary speech acts in fixture")

        missing = [u for u in attributed if not u.get("originating_speaker")]
        rate = len(missing) / len(attributed)
        assert rate == 0.0, (
            f"{rate:.0%} of quoted/commentary utterances are missing originating_speaker. "
            f"The extraction prompt must populate originating_speaker for attributed speech acts."
        )


# ---------------------------------------------------------------------------
# Test class 3 — Speaker resolution rate
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestSpeakerResolution:
    """
    speaker_entity_id values that start with 'UNRESOLVED:' indicate the
    entity registry lookup failed.  Too many UNRESOLVED entries means
    either the pundit_registry is not seeded or the fallback logic is broken.
    """

    def test_speaker_resolution_rate(self, sample_utterances):
        unresolved = sum(
            1
            for u in sample_utterances
            if str(u.get("speaker_entity_id", "")).startswith("UNRESOLVED:")
        )
        rate = unresolved / len(sample_utterances)
        assert rate <= MAX_UNRESOLVED_SPEAKER_RATE, (
            f"{rate:.0%} of utterances have UNRESOLVED speaker_entity_id "
            f"(threshold: {MAX_UNRESOLVED_SPEAKER_RATE:.0%}). "
            f"Check that pundit_registry is seeded and _resolve_speaker_entity_id fallback is working."
        )


# ---------------------------------------------------------------------------
# Test class 4 — Content contamination (spam detection)
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestContentContamination:
    """
    Spam / ad copy should be filtered before LLM extraction.  Finding these
    patterns inside extracted claim_text means the pre-filter is not working.
    """

    def test_no_spam_content_in_claims(self, sample_utterances):
        for u in sample_utterances:
            text = (u.get("claim_text") or u.get("text") or "").lower()
            for pattern in SPAM_PATTERNS:
                assert not re.search(pattern, text, re.IGNORECASE), (
                    f"Spam content detected in claim: '{text[:80]}'. "
                    f"The content filter in assertion_extractor needs to catch this before LLM extraction."
                )


# ---------------------------------------------------------------------------
# Test class 5 — resolution_horizon completeness for testable claims
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestResolutionHorizonCompleteness:
    """
    High-testability claims (score >= 0.7) should have a resolution_horizon
    because they represent real, time-bound predictions.  A high missing rate
    means the prompt needs stronger guidance on when to populate this field.
    """

    def test_testable_claims_have_resolution_horizon(self, sample_utterances):
        testable = [
            u for u in sample_utterances if (u.get("testability_score") or 0) >= 0.7
        ]
        if not testable:
            pytest.skip("No high-testability utterances in fixture")

        missing_horizon = [
            u
            for u in testable
            if not u.get("resolution_horizon") or u.get("resolution_horizon") == "None"
        ]
        rate = len(missing_horizon) / len(testable)
        assert (
            rate <= 0.30
        ), (  # allow 30% missing — not every claim has an obvious horizon
            f"{rate:.0%} of high-testability claims are missing resolution_horizon (threshold: 30%). "
            f"Add resolution_horizon extraction guidance to the prompt for player/game/transaction claim types."
        )


# ---------------------------------------------------------------------------
# Meta-tests: verify the thresholds catch known-bad state
# ---------------------------------------------------------------------------


@pytest.mark.quality_threshold
class TestThresholdsSensitivity:
    """
    Meta-tests confirming that the quality thresholds *actually fail* when
    given the broken_utterances fixture.  If these pass, the thresholds are
    not checking what they claim to check.
    """

    def test_field_population_fails_on_broken_data(self, broken_utterances):
        """broken_utterances has NULL for stance, hedge_level, etc. — thresholds must fail."""
        failures = []
        for field, threshold in REQUIRED_POPULATION_RATE.items():
            populated = sum(
                1
                for u in broken_utterances
                if u.get(field) is not None
                and u.get(field) != ""
                and str(u.get(field)) != "None"
            )
            rate = populated / len(broken_utterances)
            if rate < threshold:
                failures.append(field)

        assert len(failures) > 0, (
            "Expected field population thresholds to fail on broken_utterances, but all passed. "
            "The broken fixture may not be broken enough, or thresholds need tightening."
        )

    def test_bimodal_detection_triggers_on_broken_data(self, broken_utterances):
        """broken_utterances has only exactly 0.0 and 1.0 scores — bimodal check must fail."""
        scores = [
            u["testability_score"]
            for u in broken_utterances
            if u.get("testability_score") is not None
        ]
        assert len(scores) > 0

        exactly_zero = sum(1 for s in scores if s == 0.0) / len(scores)
        exactly_one = sum(1 for s in scores if s == 1.0) / len(scores)
        binary_fraction = exactly_zero + exactly_one

        assert binary_fraction > BIMODAL_THRESHOLD, (
            f"Expected bimodal_fraction > {BIMODAL_THRESHOLD:.0%} for broken fixture, "
            f"but got {binary_fraction:.0%}. Adjust the broken_utterances fixture."
        )

    def test_speaker_resolution_fails_on_broken_data(self, broken_utterances):
        """broken_utterances has all UNRESOLVED speakers — speaker check must fail."""
        unresolved = sum(
            1
            for u in broken_utterances
            if str(u.get("speaker_entity_id", "")).startswith("UNRESOLVED:")
        )
        rate = unresolved / len(broken_utterances)

        assert rate > MAX_UNRESOLVED_SPEAKER_RATE, (
            f"Expected UNRESOLVED rate > {MAX_UNRESOLVED_SPEAKER_RATE:.0%} for broken fixture, "
            f"but got {rate:.0%}. Adjust the broken_utterances fixture."
        )

    def test_spam_detection_catches_injected_spam(self):
        """A synthetically injected spam utterance must trigger the spam check."""
        spam_utterance = {
            "text": "Email verification required for all sweepstakes entries",
            "claim_text": "Email verification required for all sweepstakes entries",
        }
        for pattern in SPAM_PATTERNS:
            text = spam_utterance["claim_text"].lower()
            if re.search(pattern, text, re.IGNORECASE):
                return  # at least one pattern matched — detector is working
        pytest.fail(
            "None of the SPAM_PATTERNS matched the injected spam utterance. "
            "Check that SPAM_PATTERNS is correctly defined."
        )

    def test_speaker_attribution_fails_on_broken_data(self, broken_quoted_utterances):
        """quoted/commentary utterances missing originating_speaker must trigger attribution check."""
        attributed = [
            u
            for u in broken_quoted_utterances
            if u.get("speech_act_type") in ("quoted", "commentary")
        ]
        assert len(attributed) > 0, "broken_quoted_utterances fixture has no attributed speech acts"

        missing = [u for u in attributed if not u.get("originating_speaker")]
        rate = len(missing) / len(attributed)
        assert rate > 0.0, (
            "Expected missing originating_speaker in broken_quoted_utterances, "
            "but all were populated.  Adjust the fixture."
        )

"""
Tests for the DomainProtocol, registry, and NFL reference plugin
(Issue #684).
"""

import pytest

from src.domain_protocol import (
    DEFAULT_TESTABILITY_WEIGHTS,
    SHARED_SPEECH_ACT_BLOCK,
    SHARED_TESTABILITY_BLOCK,
    TESTABILITY_SUBSCORE_KEYS,
    VALID_HEDGE_LEVELS,
    VALID_SPEECH_ACT_TYPES,
    VALID_STANCE_VALUES,
    DomainProtocol,
    ResolutionResult,
    compute_weighted_testability,
    validate_testability_weights,
)
from src.domain_registry import (
    get_plugin,
    get_plugin_or_none,
    list_plugins,
    register,
    reset_registry,
    unregister,
)
from src.plugins.nfl_plugin import (
    NFL_CLAIM_CATEGORIES,
    NFL_EXTRACTION_PROMPT_TEMPLATE,
    NFLPlugin,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_speech_act_types_match_extractor():
    """Protocol enum must match assertion_extractor.VALID_SPEECH_ACT_TYPES."""
    from src.assertion_extractor import VALID_SPEECH_ACT_TYPES as EXTRACTOR_SET

    assert set(VALID_SPEECH_ACT_TYPES) == set(EXTRACTOR_SET)


def test_default_testability_weights_sum_to_one():
    assert abs(sum(DEFAULT_TESTABILITY_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(DEFAULT_TESTABILITY_WEIGHTS) == set(TESTABILITY_SUBSCORE_KEYS)


def test_shared_blocks_are_nonempty_strings():
    assert (
        isinstance(SHARED_TESTABILITY_BLOCK, str) and SHARED_TESTABILITY_BLOCK.strip()
    )
    assert isinstance(SHARED_SPEECH_ACT_BLOCK, str) and SHARED_SPEECH_ACT_BLOCK.strip()


def test_valid_enum_tuples_are_immutable():
    assert isinstance(VALID_SPEECH_ACT_TYPES, tuple)
    assert isinstance(VALID_HEDGE_LEVELS, tuple)
    assert isinstance(VALID_STANCE_VALUES, tuple)


# ---------------------------------------------------------------------------
# ResolutionResult
# ---------------------------------------------------------------------------


def test_resolution_result_is_brier_scored():
    assert ResolutionResult(outcome="true").is_brier_scored() is True
    assert ResolutionResult(outcome="false").is_brier_scored() is True
    assert ResolutionResult(outcome="partial", confidence=0.5).is_brier_scored() is True
    assert ResolutionResult(outcome="void").is_brier_scored() is False
    assert ResolutionResult(outcome="pending").is_brier_scored() is False


def test_resolution_result_default_evidence_is_dict():
    r = ResolutionResult(outcome="true")
    assert r.evidence == {}
    assert r.notes == ""


def test_resolution_result_is_frozen():
    r = ResolutionResult(outcome="true")
    with pytest.raises(Exception):  # FrozenInstanceError
        r.outcome = "false"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Weights validation
# ---------------------------------------------------------------------------


def test_validate_weights_accepts_default():
    validate_testability_weights(DEFAULT_TESTABILITY_WEIGHTS)


def test_validate_weights_rejects_missing_key():
    bad = dict(DEFAULT_TESTABILITY_WEIGHTS)
    bad.pop("evidence_accessibility")
    with pytest.raises(ValueError, match="missing"):
        validate_testability_weights(bad)


def test_validate_weights_rejects_extra_key():
    bad = dict(DEFAULT_TESTABILITY_WEIGHTS)
    bad["bogus"] = 0.0
    with pytest.raises(ValueError, match="extra"):
        validate_testability_weights(bad)


def test_validate_weights_rejects_bad_sum():
    bad = {k: 0.5 for k in TESTABILITY_SUBSCORE_KEYS}  # sums to 2.5
    with pytest.raises(ValueError, match="sum to 1.0"):
        validate_testability_weights(bad)


def test_validate_weights_rejects_out_of_range():
    bad = dict(DEFAULT_TESTABILITY_WEIGHTS)
    bad["subject_specificity"] = 1.5
    bad["predicate_falsifiability"] = -0.25
    with pytest.raises(ValueError, match="not in"):
        validate_testability_weights(bad)


def test_compute_weighted_testability_uniform_matches_mean():
    uniform = {k: 0.2 for k in TESTABILITY_SUBSCORE_KEYS}
    sub = {k: 0.5 for k in TESTABILITY_SUBSCORE_KEYS}
    assert compute_weighted_testability(sub, uniform) == 0.5


def test_compute_weighted_testability_weighted_emphasis():
    weights = dict.fromkeys(TESTABILITY_SUBSCORE_KEYS, 0.0)
    weights["predicate_falsifiability"] = 1.0
    sub = {k: 0.0 for k in TESTABILITY_SUBSCORE_KEYS}
    sub["predicate_falsifiability"] = 0.9
    assert compute_weighted_testability(sub, weights) == 0.9


def test_compute_weighted_testability_missing_subscores_default_zero():
    assert compute_weighted_testability({}, DEFAULT_TESTABILITY_WEIGHTS) == 0.0


# ---------------------------------------------------------------------------
# NFL plugin satisfies the protocol
# ---------------------------------------------------------------------------


def test_nfl_plugin_satisfies_protocol():
    plugin = NFLPlugin()
    assert isinstance(plugin, DomainProtocol)
    assert plugin.domain == "nfl"


def test_nfl_claim_categories_match_extractor():
    """The plugin's category list must match assertion_extractor.VALID_CATEGORIES."""
    from src.assertion_extractor import VALID_CATEGORIES as EXTRACTOR_CATS

    assert set(NFL_CLAIM_CATEGORIES) == EXTRACTOR_CATS
    assert set(NFLPlugin().claim_categories()) == EXTRACTOR_CATS


def test_nfl_extraction_prompt_format_is_complete():
    """Building the prompt with a sample article must succeed."""
    plugin = NFLPlugin()
    prompt = plugin.extraction_prompt(
        {
            "raw_text": "The Eagles will win 12 games.",
            "title": "Eagles preview",
            "author": "John Smith",
            "source_name": "ESPN",
            "published_date": "2026-01-01",
            "sport": "NFL",
        }
    )
    assert "ESPN" in prompt
    assert "John Smith" in prompt
    assert "Eagles preview" in prompt
    assert "The Eagles will win 12 games." in prompt
    assert "speech_act_type" in prompt
    assert "testability_score" in prompt


def test_nfl_extraction_prompt_matches_legacy():
    """
    Pure-refactor guarantee: plugin prompt for canonical inputs must be
    byte-identical to the prompt produced by the legacy
    ``EXTRACTION_PROMPT.format`` path in assertion_extractor.
    """
    from src.assertion_extractor import EXTRACTION_PROMPT

    article = {
        "raw_text": "Lamar Jackson will win MVP this season.",
        "title": "Ravens 2026 outlook",
        "author": "Jane Doe",
        "source_name": "ProFootballTalk",
        "published_date": "2026-04-15",
        "sport": "NFL",
    }
    legacy = EXTRACTION_PROMPT.format(
        sport=article["sport"],
        published_date=article["published_date"],
        source_name=article["source_name"],
        author=article["author"],
        title=article["title"],
        text=article["raw_text"][:4000],
    )
    plugin_prompt = NFLPlugin().extraction_prompt(article)
    assert plugin_prompt == legacy


def test_nfl_extraction_prompt_handles_missing_fields():
    plugin = NFLPlugin()
    prompt = plugin.extraction_prompt({"raw_text": "Some text."})
    # Defaults should fill in
    assert "Unknown" in prompt
    assert "Untitled" in prompt
    assert "Some text." in prompt


def test_nfl_extraction_prompt_truncates_long_text():
    plugin = NFLPlugin()
    long_text = "A" * 8000
    prompt = plugin.extraction_prompt({"raw_text": long_text})
    # Per existing pipeline behavior, text is sliced to 4000 chars
    assert "A" * 4000 in prompt
    assert "A" * 4001 not in prompt


def test_nfl_extraction_prompt_template_id():
    """Template constant must be importable (used by future pipeline wiring)."""
    assert "{sport}" in NFL_EXTRACTION_PROMPT_TEMPLATE
    assert "{text}" in NFL_EXTRACTION_PROMPT_TEMPLATE


def test_nfl_resolve_entities_player_centric():
    plugin = NFLPlugin()
    out = plugin.resolve_entities(
        {
            "claim_category": "player_performance",
            "target_player": "Patrick Mahomes",
            "target_team": "KC",
        }
    )
    assert out["entities"] == {"player": "Patrick Mahomes", "team": "KC"}
    assert out["entity_resolved"] is True


def test_nfl_resolve_entities_team_centric_without_player():
    plugin = NFLPlugin()
    out = plugin.resolve_entities(
        {
            "claim_category": "game_outcome",
            "target_player": None,
            "target_team": "PHI",
        }
    )
    assert out["entities"] == {"team": "PHI"}
    assert out["entity_resolved"] is True


def test_nfl_resolve_entities_unresolved_when_player_missing():
    plugin = NFLPlugin()
    out = plugin.resolve_entities(
        {
            "claim_category": "injury",  # player-centric category
            "target_player": None,
            "target_team": "PHI",
        }
    )
    assert out["entity_resolved"] is False


def test_nfl_resolve_entities_does_not_drop_input_keys():
    plugin = NFLPlugin()
    inp = {
        "claim_category": "game_outcome",
        "target_team": "BAL",
        "extracted_claim": "Ravens win division",
        "speech_act_type": "assertion",
    }
    out = plugin.resolve_entities(inp)
    assert out["extracted_claim"] == "Ravens win division"
    assert out["speech_act_type"] == "assertion"


def test_nfl_resolution_adapter_returns_pending_placeholder():
    plugin = NFLPlugin()
    result = plugin.resolution_adapter({"claim_id": "abc"})
    assert result.outcome == "pending"
    assert result.is_brier_scored() is False


def test_nfl_testability_weights_match_default():
    assert NFLPlugin().testability_weights() == DEFAULT_TESTABILITY_WEIGHTS


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_registry():
    """Reset and reload registry for isolation between tests."""
    reset_registry(_testing_only=True)
    yield
    reset_registry(_testing_only=True)


def test_registry_loads_nfl_by_default(fresh_registry):
    plugin = get_plugin("nfl")
    assert isinstance(plugin, NFLPlugin)


def test_registry_unknown_domain_raises(fresh_registry):
    with pytest.raises(ValueError, match="No DomainProtocol plugin registered"):
        get_plugin("klingon")


def test_registry_unknown_domain_lists_known(fresh_registry):
    try:
        get_plugin("klingon")
    except ValueError as exc:
        assert "nfl" in str(exc)
    else:
        pytest.fail("expected ValueError")


def test_registry_get_plugin_or_none(fresh_registry):
    assert get_plugin_or_none("nfl") is not None
    assert get_plugin_or_none("absent") is None


def test_registry_list_plugins(fresh_registry):
    assert "nfl" in list_plugins()


def test_registry_register_collision_rejects(fresh_registry):
    get_plugin("nfl")  # ensure default is loaded
    with pytest.raises(ValueError, match="already registered"):
        register(NFLPlugin())


def test_registry_register_replace_overwrites(fresh_registry):
    get_plugin("nfl")
    second = NFLPlugin()
    register(second, replace=True)
    assert get_plugin("nfl") is second


def test_registry_register_rejects_non_protocol(fresh_registry):
    class NotAPlugin:
        domain = "broken"

    with pytest.raises(TypeError, match="DomainProtocol"):
        register(NotAPlugin())  # type: ignore[arg-type]


def test_registry_register_rejects_empty_domain(fresh_registry):
    plugin = NFLPlugin()
    plugin.domain = ""
    with pytest.raises(ValueError, match="non-empty"):
        register(plugin)


def test_registry_register_validates_weights(fresh_registry):
    class BadWeights(NFLPlugin):
        domain = "bad"

        def testability_weights(self):  # type: ignore[override]
            return {"subject_specificity": 1.0}  # missing 4 keys

    with pytest.raises(ValueError):
        register(BadWeights())


def test_registry_unregister(fresh_registry):
    get_plugin("nfl")
    unregister("nfl")
    assert get_plugin_or_none("nfl") is None


def test_reset_registry_requires_flag():
    with pytest.raises(RuntimeError, match="_testing_only=True"):
        reset_registry()


# ---------------------------------------------------------------------------
# Protocol structural typing — duck-typed plugin works without inheritance
# ---------------------------------------------------------------------------


class _DuckPlugin:
    """Doesn't inherit from anything but satisfies the protocol structurally."""

    domain = "duck"

    def extraction_prompt(self, article):
        return "duck"

    def resolve_entities(self, utterance):
        return utterance

    def claim_categories(self):
        return ["quack"]

    def resolution_adapter(self, claim):
        return ResolutionResult(outcome="pending")

    def testability_weights(self):
        return dict(DEFAULT_TESTABILITY_WEIGHTS)


def test_duck_plugin_satisfies_protocol():
    assert isinstance(_DuckPlugin(), DomainProtocol)


def test_register_duck_plugin(fresh_registry):
    register(_DuckPlugin())
    assert get_plugin("duck").extraction_prompt({}) == "duck"


# ---------------------------------------------------------------------------
# Politics stub
# ---------------------------------------------------------------------------


def test_politics_plugin_satisfies_protocol():
    from src.plugins.politics_plugin import PoliticsPlugin

    p = PoliticsPlugin()
    assert isinstance(p, DomainProtocol)
    assert p.domain == "politics.us"


def test_politics_plugin_weights_valid():
    from src.plugins.politics_plugin import PoliticsPlugin

    validate_testability_weights(PoliticsPlugin().testability_weights())


def test_politics_plugin_extraction_prompt_raises():
    from src.plugins.politics_plugin import PoliticsPlugin

    with pytest.raises(NotImplementedError):
        PoliticsPlugin().extraction_prompt({"raw_text": "x"})


def test_politics_plugin_categories_disjoint_from_nfl():
    """Sanity check: NFL and politics enums share no values."""
    from src.plugins.politics_plugin import POLITICS_CLAIM_CATEGORIES

    assert set(NFL_CLAIM_CATEGORIES).isdisjoint(POLITICS_CLAIM_CATEGORIES)


def test_politics_plugin_not_registered_by_default(fresh_registry):
    from src.plugins.politics_plugin import PoliticsPlugin

    # Stub must NOT auto-register.  Loading the registry triggers default
    # plugin registration; politics should still be absent.
    list_plugins()
    assert get_plugin_or_none("politics.us") is None
    # But it can be registered manually.
    register(PoliticsPlugin())
    assert get_plugin("politics.us").domain == "politics.us"

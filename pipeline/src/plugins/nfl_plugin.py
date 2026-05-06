"""
NFL DomainProtocol plugin (Issue #684).

A pure refactor: this plugin reproduces the exact extraction prompt and
behavior already implemented in ``pipeline/src/assertion_extractor.py``.
The orchestrator does not yet call into plugins; this file exists so the
``DomainProtocol`` (in ``pipeline/src/domain_protocol.py``) has a real,
behavior-preserving reference implementation that future PRs can wire
into the pipeline.

When the orchestrator is migrated to plugin dispatch:
    1. ``run_extraction`` looks up ``plugin = get_plugin(article.sport.lower())``.
    2. The hardcoded ``EXTRACTION_PROMPT`` is removed and
       ``plugin.extraction_prompt(article)`` is called instead.
    3. Per-utterance entity resolution moves to ``plugin.resolve_entities``.
    4. ``claim_categories`` validation replaces the hardcoded
       ``VALID_CATEGORIES`` set in ``assertion_extractor``.

This file does NOT change any behavior today.  It is the contract
implementation that makes the protocol non-vapor.
"""

from __future__ import annotations

from typing import Optional

from src.domain_protocol import (
    DEFAULT_TESTABILITY_WEIGHTS,
    ResolutionResult,
)

# ---------------------------------------------------------------------------
# Claim categories — mirrors assertion_extractor.VALID_CATEGORIES
# ---------------------------------------------------------------------------

NFL_CLAIM_CATEGORIES: list[str] = [
    "player_performance",
    "game_outcome",
    "trade",
    "draft_pick",
    "injury",
    "contract",
    "award_prediction",
    "fa_signing",
]


# ---------------------------------------------------------------------------
# Extraction prompt — verbatim copy of the prompt currently shipped in
# assertion_extractor.EXTRACTION_PROMPT.  Kept identical so we can swap
# the orchestrator over to plugin dispatch with zero diff in LLM input.
# ---------------------------------------------------------------------------

NFL_EXTRACTION_PROMPT_TEMPLATE = """You are a {sport} speech-act extraction system. Analyze the content below and extract ALL speech acts — including rhetorical questions, hedges, and opinions — not just testable predictions.

PUBLISHED: {published_date}

For EACH utterance, classify it and score its testability. Return a JSON array where each element has:
{{
  "text": "verbatim quote or close paraphrase",
  "speech_act_type": "assertion|conditional|recall|rhetorical_question|hedge|commentary|opinion|analogy|joke",
  "testability_subscores": {{
    "subject_specificity": 0.0,
    "predicate_falsifiability": 0.0,
    "threshold_concreteness": 0.0,
    "resolution_horizon_defined": 0.0,
    "evidence_accessibility": 0.0
  }},
  "testability_score": 0.0,
  "resolution_horizon": "ISO8601 datetime or null",
  "predicate": "will_win|will_be_below|will_retire|will_sign|will_miss_playoffs|...",
  "subject": "entity name string",
  "predicate_args": {{}},
  "extracted_claim": "concise testable statement for ledger (or empty string if not testable)",
  "claim_category": "player_performance|game_outcome|trade|draft_pick|injury|contract|award_prediction|fa_signing",
  "stance": "bullish|bearish|neutral",
  "season_year": null,
  "target_player": null,
  "target_team": null,
  "confidence_note": "how explicit/confident the prediction is",
  "prediction_horizon_days": -1,
  "speech_act": "authored|quoted|commentary",
  "originating_speaker": null,
  "resolution_condition": "plain-English statement of what makes this claim true, or empty string",
  "hedge_level": "strong|moderate|weak"
}}

speech_act_type definitions:
- assertion: declarative claim about a future outcome ("Mahomes will win MVP")
- conditional: claim contingent on a condition ("IF they stay healthy, Eagles win the Super Bowl")
- recall: speaker recalls a past prediction or fact as evidence ("I said three months ago that...")
- rhetorical_question: question used for emphasis, not an assertion ("Can anyone stop this offense?")
- hedge: statement explicitly marked as uncertain ("I think he might...", "wouldn't surprise me if")
- commentary: analysis/explanation without a testable outcome ("This offense runs through the slot")
- opinion: subjective evaluation without falsifiable outcome ("He's the best QB in the league")
- analogy: comparison to illustrate a point, not a direct claim
- joke: humor, sarcasm

testability_score = average of 5 sub-scores (each 0.0–1.0):
- subject_specificity: Is the subject a nameable entity? "The Eagles"=1.0, "young QBs these days"=0.0
- predicate_falsifiability: Can it be scored TRUE/FALSE? "will win the SB"=1.0, "will struggle"=0.4
- threshold_concreteness: "below 3%"=1.0, "low"=0.3, "some"=0.0
- resolution_horizon_defined: "by Q4 2025"=1.0, "soon"=0.3, "eventually"=0.0
- evidence_accessibility: Is there a data source that can answer this? "Eagles wins >= 11"=1.0, "most exciting team"=0.0

speech_act authorship classification (NEW — issue #366):
- authored: the speaker is directly making this claim themselves
- quoted: the speaker is transmitting someone else's claim ("Schefter just reported X") — set originating_speaker to the reported speaker's name
- commentary: the speaker is reacting to / agreeing or disagreeing with a claim they did not author — this IS itself an authored claim of agreement/disagreement. Set originating_speaker to the name of the speaker whose claim is being commented on.

originating_speaker: name of the entity whose claim is being transmitted (quoted) or commented on (commentary). Null for authored speech acts.

Stance rules (for promoted claims):
- bullish: prediction is positive/optimistic about the subject
- bearish: prediction is negative/pessimistic about the subject
- neutral: no clear directional bias (retirement, trade, factual future event)

--- FEW-SHOT EXAMPLES ---

Example 1 — Rhetorical question (NOT promoted to ledger):
Input: "Can anyone stop Patrick Mahomes at this point?"
Output:
{{
  "text": "Can anyone stop Patrick Mahomes at this point?",
  "speech_act_type": "rhetorical_question",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 0.1, "threshold_concreteness": 0.0, "resolution_horizon_defined": 0.0, "evidence_accessibility": 0.2}},
  "testability_score": 0.26,
  "resolution_horizon": null,
  "predicate": "",
  "subject": "Patrick Mahomes",
  "predicate_args": {{}},
  "extracted_claim": "",
  "claim_category": "player_performance",
  "stance": "bullish",
  "season_year": null,
  "target_player": "Patrick Mahomes",
  "target_team": "KC",
  "confidence_note": "rhetorical emphasis",
  "prediction_horizon_days": -1
}}

Example 2 — Genuine assertion (PROMOTED to ledger):
Input: "The Eagles will win at least 11 games this season."
Output:
{{
  "text": "The Eagles will win at least 11 games this season.",
  "speech_act_type": "assertion",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 1.0, "threshold_concreteness": 1.0, "resolution_horizon_defined": 0.8, "evidence_accessibility": 1.0}},
  "testability_score": 0.96,
  "resolution_horizon": "2025-12-31T23:59:59Z",
  "predicate": "will_win_at_least",
  "subject": "Philadelphia Eagles",
  "predicate_args": {{"threshold": 11, "stat": "wins", "unit": "games"}},
  "extracted_claim": "Eagles will win at least 11 games in the 2025 season",
  "claim_category": "game_outcome",
  "stance": "bullish",
  "season_year": 2025,
  "target_player": null,
  "target_team": "PHI",
  "confidence_note": "explicit numeric threshold",
  "prediction_horizon_days": 150
}}

Example 3 — Conditional (PROMOTED to ledger):
Input: "If their offensive line stays healthy, the Ravens will reach the AFC Championship."
Output:
{{
  "text": "If their offensive line stays healthy, the Ravens will reach the AFC Championship.",
  "speech_act_type": "conditional",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 0.9, "threshold_concreteness": 0.7, "resolution_horizon_defined": 0.8, "evidence_accessibility": 1.0}},
  "testability_score": 0.88,
  "resolution_horizon": "2025-12-31T23:59:59Z",
  "predicate": "will_reach",
  "subject": "Baltimore Ravens",
  "predicate_args": {{"milestone": "AFC Championship", "condition": "offensive line stays healthy"}},
  "extracted_claim": "Ravens will reach the AFC Championship (conditional on OL health)",
  "claim_category": "game_outcome",
  "stance": "bullish",
  "season_year": 2025,
  "target_player": null,
  "target_team": "BAL",
  "confidence_note": "conditional on OL health",
  "prediction_horizon_days": 120
}}

Example 4 — Quoted claim (speech_act=quoted, score routed to originating_speaker):
Input: "Adam Schefter is reporting that the Cowboys will cut Dak Prescott before the season."
Output:
{{
  "text": "Adam Schefter is reporting that the Cowboys will cut Dak Prescott before the season.",
  "speech_act_type": "assertion",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 1.0, "threshold_concreteness": 0.8, "resolution_horizon_defined": 0.7, "evidence_accessibility": 0.9}},
  "testability_score": 0.88,
  "resolution_horizon": "2026-09-01T00:00:00Z",
  "predicate": "will_cut",
  "subject": "Dallas Cowboys",
  "predicate_args": {{"player": "Dak Prescott", "timing": "before season"}},
  "extracted_claim": "Cowboys will cut Dak Prescott before the season (per Schefter)",
  "claim_category": "contract",
  "stance": "bearish",
  "season_year": 2026,
  "target_player": "Dak Prescott",
  "target_team": "DAL",
  "confidence_note": "attributed report from named insider",
  "prediction_horizon_days": 90,
  "speech_act": "quoted",
  "originating_speaker": "Adam Schefter"
}}

Example 5 — Commentary (speech_act=commentary, speaker authors an agree/disagree claim):
Input: "I completely agree with Cowherd — Mahomes will win a fourth Super Bowl before he retires."
Output:
{{
  "text": "I completely agree with Cowherd — Mahomes will win a fourth Super Bowl before he retires.",
  "speech_act_type": "assertion",
  "testability_subscores": {{"subject_specificity": 1.0, "predicate_falsifiability": 0.9, "threshold_concreteness": 0.8, "resolution_horizon_defined": 0.5, "evidence_accessibility": 0.9}},
  "testability_score": 0.82,
  "resolution_horizon": null,
  "predicate": "will_win",
  "subject": "Patrick Mahomes",
  "predicate_args": {{"milestone": "4th Super Bowl", "threshold": 4}},
  "extracted_claim": "agree: Mahomes will win a fourth Super Bowl before retiring",
  "claim_category": "game_outcome",
  "stance": "bullish",
  "season_year": null,
  "target_player": "Patrick Mahomes",
  "target_team": "KC",
  "confidence_note": "explicit agreement with named pundit's claim",
  "prediction_horizon_days": -1,
  "speech_act": "commentary",
  "originating_speaker": "Colin Cowherd"
}}

--- END EXAMPLES ---

SOURCE: {source_name}
AUTHOR: {author}
TITLE: {title}
TEXT:
{text}"""


# ---------------------------------------------------------------------------
# Plugin
# ---------------------------------------------------------------------------


class NFLPlugin:
    """
    NFL implementation of ``DomainProtocol``.

    Behavior is identical to the existing hardcoded extraction in
    ``assertion_extractor.py``.  This plugin is the "no-behavior-change"
    refactor target: every method here mirrors current behavior so the
    protocol can ship without disturbing the production pipeline.
    """

    domain: str = "nfl"

    def extraction_prompt(self, article: dict) -> str:
        """
        Reproduce the existing NFL extraction prompt.

        ``article`` keys consumed:
            raw_text, title, author, source_name, published_date, sport
        Defaults match the existing ``extract_assertions`` helper.
        """
        text = str(article.get("raw_text", ""))[:4000]
        return NFL_EXTRACTION_PROMPT_TEMPLATE.format(
            sport=str(article.get("sport") or "NFL"),
            published_date=str(article.get("published_date") or "Unknown"),
            source_name=str(article.get("source_name") or "Unknown"),
            author=str(article.get("author") or "Unknown"),
            title=str(article.get("title") or "Untitled"),
            text=text,
        )

    def resolve_entities(self, utterance: dict) -> dict:
        """
        Best-effort NFL entity resolution.

        Today the NFL pipeline relies on the LLM to populate
        ``target_player`` and ``target_team`` directly; downstream
        ``ingest_batch`` resolves player IDs lazily via the historical
        ``silver_v2_core.entity`` lookup.  This method preserves that
        behavior:

        - Pass through ``target_player`` / ``target_team`` from the
          LLM output.
        - Project them into the generic ``entities`` dict
          (``{"player": …, "team": …}``) so non-NFL consumers can read
          the resolved set without knowing about NFL's column names.
        - Mark ``entity_resolved=False`` if either target is missing
          where the claim category implies it should exist.

        No external API calls are made; this is in-memory bookkeeping.
        Heavy entity resolution (player_id → ESPN/SportsDataIO) is
        handled by ``_resolve_speaker_entity_id`` and the async
        re-enrichment pass, not here.
        """
        out = dict(utterance)
        target_player: Optional[str] = out.get("target_player")
        target_team: Optional[str] = out.get("target_team")

        entities: dict[str, str] = {}
        if target_player:
            entities["player"] = target_player
        if target_team:
            entities["team"] = target_team
        out["entities"] = entities

        # An NFL utterance is "fully resolved" if it has at least one of
        # player / team for player-centric claim categories, or just team
        # for team-centric ones.  We keep this loose so silent drops are
        # impossible.
        category = out.get("claim_category", "")
        if category in {
            "player_performance",
            "injury",
            "trade",
            "fa_signing",
            "contract",
        }:
            out["entity_resolved"] = bool(target_player)
        elif category in {"game_outcome", "draft_pick", "award_prediction"}:
            out["entity_resolved"] = bool(target_team or target_player)
        else:
            out["entity_resolved"] = bool(entities)
        return out

    def claim_categories(self) -> list[str]:
        """Return the closed enum of NFL claim categories."""
        return list(NFL_CLAIM_CATEGORIES)

    def resolution_adapter(self, claim: dict) -> ResolutionResult:
        """
        NFL resolution adapter — placeholder.

        Today, NFL resolution is performed by ``historical_resolver`` and
        related scripts, not by a plugin method.  This implementation
        returns ``pending`` so the plugin satisfies the protocol; a
        follow-up PR will route the existing resolvers through this
        method without changing their underlying logic.
        """
        return ResolutionResult(
            outcome="pending",
            confidence=0.0,
            notes="NFL plugin resolution_adapter not yet wired; "
            "use pipeline.scripts.historical_resolver for now.",
        )

    def testability_weights(self) -> dict[str, float]:
        """
        NFL uses the default empirical weights.

        These were calibrated against the existing NFL corpus; politics
        and finance plugins should override with their own weights.
        """
        return dict(DEFAULT_TESTABILITY_WEIGHTS)


__all__ = [
    "NFLPlugin",
    "NFL_CLAIM_CATEGORIES",
    "NFL_EXTRACTION_PROMPT_TEMPLATE",
]

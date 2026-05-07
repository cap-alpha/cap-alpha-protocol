"""
DomainProtocol — full multi-domain extraction interface (Issue #684).

This module defines the *complete* contract every domain plugin (NFL,
politics, finance, …) must satisfy at the **pipeline orchestration
layer**.  It is intentionally broader than ``domain_plugin.DomainPlugin``
(the ABC introduced by #685, which is narrowly scoped to entity
resolution).  The two compose:

* ``DomainPlugin`` (ABC, ``domain_plugin.py``) — entity-resolution
  contract: ``domain_key``, ``matches``, ``resolve_entities``.  Choose
  this when you only need cached-inline entity ID resolution.
* ``DomainProtocol`` (Protocol, this file) — pipeline-orchestration
  contract: ``extraction_prompt``, ``resolve_entities``,
  ``claim_categories``, ``resolution_adapter``,
  ``testability_weights``.  Choose this when you need the full
  prompt + scoring pipeline behind a plugin boundary.

A plugin author is free to implement either or both; the registry below
treats ``DomainProtocol`` as the canonical multi-method contract for
the assertion-extractor orchestrator.

Design decisions captured here (see issue #684 for full rationale):

Q1. **Entity resolution timing.**
    ``resolve_entities`` runs *synchronously and best-effort* during the
    pipeline's per-utterance loop.  Plugins that need slow / network-bound
    lookups MUST cache aggressively or short-circuit to "unresolved"; an
    optional async re-enrichment job (``pipeline.scripts.reresolve_entities``)
    is the right place for cross-domain batch resolution and is fed by
    rows where ``entity_resolved == False``.  Default for any new domain:
    return what is cheap to resolve in-memory; never block extraction on a
    third-party API.

Q2. **Void outcome semantics.**
    ``ResolutionResult.outcome`` is the closed enum
    ``Literal["true", "false", "partial", "void", "pending"]``.  ``void``
    means "the claim's resolution condition can no longer be evaluated,
    through no fault of the claim's truth value" — e.g. candidate
    withdraws before the election, game is cancelled, company is
    delisted, player retires before the prediction window resolves.
    Voided claims are *excluded* from Brier and accuracy aggregates and
    are *not* counted as wrong predictions.  ``partial`` means "claim was
    partly true" (scored fractionally).  ``pending`` means "evidence does
    not yet exist."  This matches the ``outcome`` column already shipped
    in migration 016 (``true|false|partial|unresolvable|vacuous|pending``)
    where ``vacuous → void`` and ``unresolvable → void`` map to the same
    Brier-excluded bucket.

Q3. **Prompt composition.**
    Plain Python string composition.  Each plugin's ``extraction_prompt``
    method returns the fully-formed prompt string.  Shared scaffolding
    (the testability subscores block, the speech_act_type enum, the
    hedge_level / stance / resolution_condition fields) is exposed as
    module-level constants on this file (``SHARED_TESTABILITY_BLOCK``
    etc.) and the plugin concatenates them around its own
    domain-specific sections (claim categories enum, few-shot examples,
    entity vocabulary).  Jinja2 was rejected: it adds a runtime
    dependency and a templating mental model for what is, today, a
    trivial join of three or four string blocks.  Revisit when there are
    ≥3 plugins sharing ≥80% of their prompt structure.

Q4. **BigQuery entity schema (hybrid).**
    The plugin returns ``entities: dict[str, str]`` from
    ``resolve_entities``; plugin-specific adapters then map that dict to
    the BQ row.  NFL preserves the existing ``target_player`` /
    ``target_team`` columns (every existing query depends on them);
    non-sports domains leave them NULL and serialise their entity dict
    into the ``target_entity`` JSON column (added by a forthcoming
    migration).  The canonical resolved-entity FK already exists on
    ``silver_v2_claims.claim.subject_entity_ids ARRAY<STRING>`` and
    points at ``silver_v2_core.entity.entity_id`` — that is the join key
    long-term.  No backward-incompatible migrations.

Q5. **Protocol vs ABC + resolution adapter timing.**
    ``Protocol`` with ``@runtime_checkable`` (structural subtyping).
    Plugins are not required to inherit from anything; the registry
    verifies compliance with ``isinstance(plugin, DomainProtocol)``.
    This composes cleanly with later optional capability protocols
    (``AsyncResolver``, ``EntityCache``, …).  The
    ``resolution_adapter`` runs in a *separate scheduled job*
    (``pipeline.scripts.resolve_claims``), not inline with extraction:
    extraction throughput must not be coupled to resolver latency or
    external API quotas, and many claims only resolve weeks/months
    after assertion (election day, season end, earnings call).  The
    append-only ``silver_v2_claims.resolution`` table is already shaped
    for this — keyed by ``claim_id`` and tolerant of multiple
    re-resolutions per claim as evidence accumulates.

The protocol is intentionally narrow.  Anything that is *not* in this
file is domain-private and may be implemented however the plugin author
prefers.  When you find yourself wanting to add a sixth method, ask
first whether it belongs to a *capability* protocol (e.g. an
``AsyncResolver`` protocol that some plugins implement and others don't)
rather than the core ``DomainProtocol`` shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Shared prompt scaffolding (Q3)
#
# Plugins concatenate these constants with their domain-specific sections.
# Keeping them here makes "shared schema across all domains" a single source
# of truth — drift is a code review issue, not a hidden YAML divergence.
# ---------------------------------------------------------------------------

#: Closed enum of speech_act_type values.  Mirrors
#: ``assertion_extractor.VALID_SPEECH_ACT_TYPES``.  Promoted-to-ledger types
#: are ``assertion``, ``conditional``, ``recall``.
VALID_SPEECH_ACT_TYPES: tuple[str, ...] = (
    "assertion",
    "conditional",
    "recall",
    "rhetorical_question",
    "hedge",
    "commentary",
    "opinion",
    "analogy",
    "joke",
)

#: Closed enum of hedge_level values used in the testability extraction.
VALID_HEDGE_LEVELS: tuple[str, ...] = ("strong", "moderate", "weak")

#: Closed enum of stance values used to capture directional sentiment.
VALID_STANCE_VALUES: tuple[str, ...] = ("bullish", "bearish", "neutral")

#: Names of the five testability subscores.  Order matters — many downstream
#: aggregates iterate this tuple.
TESTABILITY_SUBSCORE_KEYS: tuple[str, ...] = (
    "subject_specificity",
    "predicate_falsifiability",
    "threshold_concreteness",
    "resolution_horizon_defined",
    "evidence_accessibility",
)

#: Default per-subscore weighting (sum to 1.0).  NFL-empirical baseline.
#: A plugin's ``testability_weights()`` may override this.
DEFAULT_TESTABILITY_WEIGHTS: dict[str, float] = {
    "subject_specificity": 0.25,
    "predicate_falsifiability": 0.30,
    "threshold_concreteness": 0.20,
    "resolution_horizon_defined": 0.15,
    "evidence_accessibility": 0.10,
}

#: Shared block describing the five testability subscores.  Plugins paste
#: this verbatim into their extraction prompt so the schema is identical
#: across domains.
SHARED_TESTABILITY_BLOCK: str = """testability_score = average of 5 sub-scores (each 0.0–1.0):
- subject_specificity: Is the subject a nameable entity?
- predicate_falsifiability: Can it be scored TRUE/FALSE?
- threshold_concreteness: Is the threshold concrete vs vague?
- resolution_horizon_defined: Is the resolution window specific?
- evidence_accessibility: Is there a data source that can answer this?
"""

#: Shared block describing speech_act_type.  Plugins may extend with examples
#: but must not redefine the enum.
SHARED_SPEECH_ACT_BLOCK: str = """speech_act_type definitions:
- assertion: declarative claim about a future outcome
- conditional: claim contingent on a condition ("IF X, then Y")
- recall: speaker recalls a past prediction or fact as evidence
- rhetorical_question: question used for emphasis, not an assertion
- hedge: explicitly uncertain ("I think he might…")
- commentary: analysis/explanation without a testable outcome
- opinion: subjective evaluation without falsifiable outcome
- analogy: comparison to illustrate a point, not a direct claim
- joke: humor, sarcasm
"""


# ---------------------------------------------------------------------------
# ResolutionResult (Q2)
# ---------------------------------------------------------------------------


#: Closed set of outcomes a resolution adapter may return.
#:
#: - ``true``     : claim came true.
#: - ``false``    : claim was wrong.
#: - ``partial``  : claim was partly correct; scored fractionally
#:                  (use ``confidence`` field as the scored fraction).
#: - ``void``     : claim's resolution condition can no longer be evaluated
#:                  (cancelled election, game cancelled, player retired
#:                  before window).  *Excluded from Brier/accuracy aggregates.*
#: - ``pending``  : not yet resolvable; evidence has not arrived.
ResolutionOutcome = Literal["true", "false", "partial", "void", "pending"]


@dataclass(frozen=True)
class ResolutionResult:
    """
    Outcome of attempting to resolve a single claim.

    A plugin's ``resolution_adapter`` returns one of these per claim.  The
    pipeline writes the result to ``silver_v2_claims.resolution`` (the
    append-only, cryptographically chained outcomes table).  Multiple
    ``ResolutionResult`` rows per claim are allowed — a claim may be
    ``pending`` for weeks before resolving ``true``, or be re-resolved from
    ``partial`` to ``true`` once more evidence accrues.

    Fields
    ------
    outcome:
        One of ``true | false | partial | void | pending``.  See
        ``ResolutionOutcome``.

    confidence:
        0.0–1.0 confidence in this outcome.  For ``partial`` outcomes this
        doubles as the partial-credit fraction (0.5 = "half right").  For
        ``void`` and ``pending`` the value is informational only — those
        outcomes are not Brier-scored.

    source_url:
        Citation URL for the evidence supporting this resolution.  May be
        ``None`` for ``pending`` results.  Strongly encouraged for
        ``true``/``false``/``partial`` so resolution is auditable.

    resolved_at:
        UTC timestamp of when the resolution was computed.  ``None`` for
        ``pending``.

    evidence:
        Structured evidence payload, e.g.
        ``{"source": "sportradar.nfl", "stat": "wins", "value": 14}``.
        Written verbatim to the ``evidence JSON`` column of
        ``silver_v2_claims.resolution``.  Empty dict if no structured
        evidence is available.

    notes:
        Free-text explanation of the verdict.  Useful for edge cases
        and partial-credit reasoning.
    """

    outcome: ResolutionOutcome
    confidence: float = 1.0
    source_url: Optional[str] = None
    resolved_at: Optional[datetime] = None
    evidence: dict = field(default_factory=dict)
    notes: str = ""

    def is_brier_scored(self) -> bool:
        """Return True if this outcome contributes to Brier/accuracy aggregates.

        ``void`` and ``pending`` outcomes are *excluded* from scoring.  Every
        other outcome is included.  Plugins should never roll their own
        scoring filter — call this so the policy stays in one place.
        """
        return self.outcome not in ("void", "pending")


# ---------------------------------------------------------------------------
# DomainProtocol (Q5)
# ---------------------------------------------------------------------------


@runtime_checkable
class DomainProtocol(Protocol):
    """
    Pipeline-orchestration contract every domain plugin must satisfy.

    This is a ``typing.Protocol`` (structural subtyping).  Plugins do *not*
    need to inherit from this class — the registry verifies compliance via
    ``isinstance(plugin, DomainProtocol)``.  Any object that has these
    five methods and the ``domain`` attribute is a valid plugin.

    Distinct from the entity-resolution ABC ``DomainPlugin`` introduced
    by issue #685 (in ``pipeline/src/domain_plugin.py``).  The ABC is
    narrowly scoped to entity resolution; ``DomainProtocol`` is the
    broader contract used by ``assertion_extractor`` for prompt building,
    claim-category validation, weighted testability, and resolution
    adapters.  A plugin may satisfy either or both.

    Why Protocol over ABC for the orchestration contract:
        - Plugins can live in third-party packages without importing this
          module at type-definition time (only at runtime registration).
        - Future capability protocols (``AsyncResolver``, ``EntityCache``)
          compose by mix-and-match rather than inheritance.
        - Tests can pass a ``MagicMock(spec=DomainProtocol)`` without any
          ABC ceremony.

    Lifecycle:
        1. Pipeline picks up a raw article from ``raw_pundit_media``.
        2. Calls ``plugin.extraction_prompt(article_dict)`` to build the
           LLM prompt; sends to qwen2.5:32b (or whatever provider is
           configured).
        3. Receives a list of utterance dicts back from the LLM.
        4. For each utterance, calls ``plugin.resolve_entities(utterance)``
           to enrich entity references in-place.
        5. Validates each utterance's ``claim_category`` against
           ``plugin.claim_categories()``.
        6. Computes the weighted testability score using
           ``plugin.testability_weights()``.
        7. Writes utterances to ``silver_v2_claims.raw_utterance`` and
           promotes qualifying ones to the ledger.
        8. (Separate scheduled job)
           ``plugin.resolution_adapter(claim)`` is called for each
           pending claim by ``pipeline.scripts.resolve_claims``.

    Threading / async model:
        Methods on this protocol are synchronous and may be called from
        any thread.  Plugins MUST be safe to share across the pipeline's
        per-article loop (no mutable per-call state on the plugin
        instance).  Network-bound work belongs in the async re-enrichment
        and resolver jobs, not here.
    """

    #: Stable domain identifier matching ``silver_v2_core.domain_taxonomy``.
    #: Examples: ``"nfl"``, ``"politics.us"``, ``"finance.equities"``.
    #: Lowercase, dotted notation for sub-domains.  Used as the key in
    #: ``domain_registry``.
    domain: str

    def extraction_prompt(self, article: dict) -> str:
        """
        Build the LLM extraction prompt for a single article.

        Parameters
        ----------
        article : dict
            Mandatory keys: ``raw_text`` (str), ``title`` (str),
            ``author`` (str), ``source_name`` (str),
            ``published_date`` (str, ISO date or empty).
            Plugins may consume additional optional keys but must
            tolerate them being missing.

        Returns
        -------
        str
            A fully-formed prompt ready to be passed to
            ``LLMProvider.extract_predictions``.  The prompt MUST request
            the standard speech_act_type / testability_subscores /
            stance / hedge_level / resolution_condition fields (see
            ``SHARED_TESTABILITY_BLOCK`` and ``SHARED_SPEECH_ACT_BLOCK``)
            so the orchestrator can interpret the response without
            knowing which plugin produced it.

        The plugin owns:
            - claim_category enum (domain-specific)
            - few-shot examples (domain-specific)
            - entity vocabulary hints
            - any domain-specific guardrails
        """
        ...

    def resolve_entities(self, utterance: dict) -> dict:
        """
        Enrich an LLM-extracted utterance with resolved entity identifiers.

        Called *synchronously* during extraction (see Q1).  Implementations
        MUST be fast: in-memory lookup, cached HTTP, or short-circuit to
        unresolved.  Network calls are tolerated only behind a cache with
        TTL ≥ 1 day.

        Parameters
        ----------
        utterance : dict
            The utterance dict as returned by the LLM (already validated
            for shape).  Plugin may mutate or copy.

        Returns
        -------
        dict
            The (possibly enriched) utterance.  Plugins SHOULD set:
              - ``entities``: dict[str, str]
                  Generic mapping of role → resolved entity_id.
                  Example NFL: ``{"player": "uuid…", "team": "uuid…"}``.
                  Example politics: ``{"candidate": "uuid…",
                  "office": "uuid…"}``.
              - ``entity_resolved``: bool
                  True if every named entity in the utterance was
                  resolved; False if any required entity is unknown
                  (the row is still written — silent drops are forbidden).

            Backward-compatibility for NFL: the NFL plugin additionally
            populates ``target_player`` / ``target_team`` so existing
            queries continue to work.  Other domains leave those NULL.
        """
        ...

    def claim_categories(self) -> list[str]:
        """
        Return the closed enum of valid claim_category values for this domain.

        Used both as a prompt hint (interpolated into ``extraction_prompt``)
        and as a runtime validator (utterances with unknown categories
        are coerced to a fallback or dropped according to plugin policy).

        Categories are domain-specific:
            NFL:      trade, draft_pick, fa_signing, injury, contract,
                      game_outcome, player_performance, award_prediction
            Politics: election_outcome, polling_prediction, appointment,
                      legislation, policy_prediction
            Finance:  earnings, rate_decision, merger, bankruptcy,
                      price_target, regulatory
        """
        ...

    def resolution_adapter(self, claim: dict) -> ResolutionResult:
        """
        Attempt to resolve whether a claim came true.

        Called by the periodic ``resolve_claims`` scheduled job, NOT
        inline with extraction (see Q5).  May make external API calls,
        consult BigQuery historical tables, or short-circuit to
        ``ResolutionResult(outcome="pending", …)`` when no evidence yet
        exists.

        Parameters
        ----------
        claim : dict
            A row from ``silver_v2_claims.claim`` plus its denormalized
            predicate / predicate_args.  The exact shape is
            domain-specific; the resolver job hydrates the row before
            passing it in.

        Returns
        -------
        ResolutionResult
            See ``ResolutionResult`` for outcome semantics.  Use
            ``outcome="void"`` for claims that have become unresolvable
            through no fault of their truth value (e.g. cancelled event)
            so they are excluded from accuracy aggregates.
        """
        ...

    def testability_weights(self) -> dict[str, float]:
        """
        Per-subscore weighting for the composite testability score.

        Must contain exactly the five keys in ``TESTABILITY_SUBSCORE_KEYS``
        and the values must sum to 1.0 ± 1e-6.  Returning
        ``DEFAULT_TESTABILITY_WEIGHTS`` is fine for any plugin that has
        not yet calibrated its own weights.

        Rationale for per-domain weights:
            Politics — elections have fixed dates so
            ``resolution_horizon_defined`` matters less; political
            language is deliberately vague so
            ``predicate_falsifiability`` matters more.

            Finance — ``threshold_concreteness`` dominates: "EPS will
            beat estimates by 10%" is far more testable than "earnings
            will be strong".

            Sports (NFL default) — balanced, with slight emphasis on
            ``predicate_falsifiability`` because pundit hot-takes love
            unfalsifiable adjectives ("explosive offense", "elite
            defense").
        """
        ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_testability_weights(weights: dict[str, float]) -> None:
    """
    Raise ``ValueError`` if ``weights`` is not a valid testability-weight dict.

    Used by ``domain_registry.register`` and recommended in plugin unit
    tests.  Validates:
      - exactly the five keys in ``TESTABILITY_SUBSCORE_KEYS`` are present;
      - all values are floats in [0.0, 1.0];
      - values sum to 1.0 ± 1e-6.
    """
    if set(weights.keys()) != set(TESTABILITY_SUBSCORE_KEYS):
        missing = set(TESTABILITY_SUBSCORE_KEYS) - set(weights.keys())
        extra = set(weights.keys()) - set(TESTABILITY_SUBSCORE_KEYS)
        raise ValueError(
            f"testability_weights keys mismatch — missing={sorted(missing)}, "
            f"extra={sorted(extra)}"
        )
    for k, v in weights.items():
        if not isinstance(v, (int, float)):
            raise ValueError(
                f"testability_weights[{k!r}] must be numeric, got {type(v).__name__}"
            )
        if not (0.0 <= float(v) <= 1.0):
            raise ValueError(f"testability_weights[{k!r}]={v} not in [0.0, 1.0]")
    total = float(sum(weights.values()))
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"testability_weights must sum to 1.0 ± 1e-6; got {total!r}")


def compute_weighted_testability(
    subscores: dict, weights: Optional[dict[str, float]] = None
) -> float:
    """
    Compute a weighted composite testability score.

    Differs from ``assertion_extractor.compute_testability_score`` (which
    is a uniform mean) — this is used when a plugin's
    ``testability_weights()`` returns non-uniform weights.

    Missing subscores default to 0.0 so the score is penalized
    appropriately rather than silently boosted.
    """
    w = weights or DEFAULT_TESTABILITY_WEIGHTS
    validate_testability_weights(w)
    if not subscores:
        return 0.0
    total = 0.0
    for k in TESTABILITY_SUBSCORE_KEYS:
        try:
            v = float(subscores.get(k, 0.0))
        except (TypeError, ValueError):
            v = 0.0
        v = max(0.0, min(1.0, v))
        total += v * w[k]
    return round(total, 4)


__all__ = [
    "DomainProtocol",
    "ResolutionResult",
    "ResolutionOutcome",
    "VALID_SPEECH_ACT_TYPES",
    "VALID_HEDGE_LEVELS",
    "VALID_STANCE_VALUES",
    "TESTABILITY_SUBSCORE_KEYS",
    "DEFAULT_TESTABILITY_WEIGHTS",
    "SHARED_TESTABILITY_BLOCK",
    "SHARED_SPEECH_ACT_BLOCK",
    "validate_testability_weights",
    "compute_weighted_testability",
]

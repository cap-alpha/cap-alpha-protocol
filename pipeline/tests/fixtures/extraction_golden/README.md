# Extraction Golden Fixtures

Golden fixture set for regression-testing the assertion extractor (Issue #600).
Each `.txt` file contains a short transcript snippet from a sports pundit. The
corresponding `.expected.json` files contain hand-labeled expected extraction results.

## Labeling protocol

- **Labeler:** Claude Code (agent), initial pass 2026-05-03
- **Review status:** No inter-rater check on initial creation. See Issue #600 for future review cycles.
- **Disagreements noted:** adversarial_03 (hedged assertion) — boundary between "hedge" and
  "assertion"; labeled "assertion" because speaker expresses explicit numeric confidence (70%)
  and syntactically commits to the claim. adversarial_01 (sarcasm) — boundary between
  "rhetorical_question" and "joke"; labeled "rhetorical_question" because the sarcastic
  tone is conveyed through the rhetorical structure ("just like every year, right?").

## Fixture inventory

| Prefix | Count | Speech act type | Expected testability range |
|---|---|---|---|
| `assertion_0*.txt` | 5 | `assertion` | 0.78–0.90 |
| `conditional_0*.txt` | 5 | `conditional` | 0.68–0.75 |
| `recall_0*.txt` | 5 | `recall` | 0.60–0.68 |
| `rhetorical_0*.txt` | 5 | `rhetorical_question` | 0.10–0.16 |
| `hedge_0*.txt` | 5 | `hedge` | 0.28–0.35 |
| `adversarial_0*.txt` | 5 | mixed (see notes) | varies |
| **Total** | **30** | — | — |

## Expected JSON schema

```json
{
  "speech_act_type": "assertion",
  "testability_score_expected": 0.80,
  "claim_count_expected": 1,
  "adversarial_type": "...",
  "notes": "..."
}
```

| Field | Meaning |
|---|---|
| `speech_act_type` | Expected `speech_act_type` of the **first** utterance returned |
| `testability_score_expected` | Expected score; test passes if actual is within ±0.15 |
| `claim_count_expected` | Total utterance count the extractor should return |
| `adversarial_type` | (adversarial fixtures only) Category of adversarial pattern |
| `notes` | Labeling rationale and any inter-rater comments |

## Adversarial fixtures

| Fixture | Pattern | Expected label | Trap |
|---|---|---|---|
| `adversarial_01` | Sarcasm | `rhetorical_question` | Literal reading = assertion; sarcasm must be detected |
| `adversarial_02` | Double-negation | `assertion` | "won't say X won't" = "X will" — negation must be resolved |
| `adversarial_03` | Hedged assertion | `assertion` | Hedge markers present but explicit numeric confidence signals a real prediction |
| `adversarial_04` | Attribution | `commentary` | Speaker relays sources and explicitly disclaims personal ownership |
| `adversarial_05` | Compound | first=`assertion`, count=2 | Two speech acts in one text; claim_count=2 |

## Pass threshold

Tests fail if the pass rate drops below `GOLDEN_PASS_THRESHOLD` env var (default 0.80).
80–90% pass rate emits a warning instead of a hard failure.
See `pipeline/tests/test_extractor_golden.py` for the full regression logic.

## Extending the fixture set

When adding fixtures:
1. Create `{name}.txt` with a short (1–4 sentence) pundit transcript snippet
2. Create `{name}.expected.json` with the schema above
3. Run the golden tests locally to validate your expected labels against the current extractor
4. Document any inter-rater disagreements or boundary cases in this README under a dated entry
5. If the fixture count changes, update the assertion in `TestExtractorGolden.test_fixture_count`

## Change log

| Date | Author | Change |
|---|---|---|
| 2026-05-03 | Claude Code (agent) | Initial set of 30 fixtures across 5 speech act types + 5 adversarial |

-- CI Assertion: silver_v2_claim_must_be_testable
-- Issue: #555 — General-purpose truth ledger (Phase B-0)
--
-- Returns rows that VIOLATE the constraint:
--   Every claim must be backed by an utterance with a testable speech_act_type.
--
-- Qualifying speech_act_types: assertion, conditional, recall
-- Non-qualifying: rhetorical_question, hedge, commentary, opinion, analogy, joke
--
-- CI usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/sql/assertions/silver_v2_claim_must_be_testable.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID --format=json | \
--     python3 -c "import sys,json; rows=json.load(sys.stdin); sys.exit(1 if rows else 0)"
--
-- The CI step fails (exit 1) if this query returns ANY rows.

SELECT
  c.claim_id,
  c.utterance_id,
  c.speaker_entity_id,
  c.domain,
  c.predicate,
  c.asserted_at,
  u.speech_act_type,
  u.testability_score,
  u.text AS utterance_text
FROM `{project_id}.silver_v2_claims.claim` AS c
INNER JOIN `{project_id}.silver_v2_claims.raw_utterance` AS u
  ON u.utterance_id = c.utterance_id
WHERE
  u.speech_act_type NOT IN ('assertion', 'conditional', 'recall')
ORDER BY
  c.asserted_at DESC;

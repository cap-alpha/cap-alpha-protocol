-- Migration 021: speech-act authorship classification (Issue #366)
-- Adds speech_act (authored|quoted|commentary) and originating_speaker columns
-- to silver_v2_claims.raw_utterance.
--
-- speech_act distinguishes who *owns* the claim (authorship dimension) from
-- speech_act_type (utterance-shape dimension already present).
--
-- When speech_act=quoted, originating_speaker names the entity whose claim is
-- being transmitted; the resolution score routes there instead of the speaker.
-- When speech_act=commentary, the utterance is an authored agree/disagree claim
-- by the speaker about a claim they did not originate.
--
-- Usage:
--   export PROJECT_ID=cap-alpha-protocol
--   envsubst < pipeline/migrations/021_add_speech_act_classification.sql | \
--     bq query --use_legacy_sql=false --project_id=$PROJECT_ID

ALTER TABLE `{project_id}.silver_v2_claims.raw_utterance`
  ADD COLUMN IF NOT EXISTS speech_act STRING
    OPTIONS(description="authored|quoted|commentary — authorship classification. authored=speaker owns the claim; quoted=speaker is transmitting another person's claim; commentary=speaker is reacting to a claim, themselves authoring an agree/disagree assertion. NULL for legacy rows extracted before migration 021."),
  ADD COLUMN IF NOT EXISTS originating_speaker STRING
    OPTIONS(description="Name of the entity whose claim is being transmitted (speech_act=quoted) or commented on (speech_act=commentary). NULL for authored speech acts.");

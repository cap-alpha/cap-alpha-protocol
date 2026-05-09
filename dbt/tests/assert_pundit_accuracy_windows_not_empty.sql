-- Singular test: assert gold_layer.pundit_accuracy_windows is not empty.
--
-- This table will be created by migration 026 (PR #855, queued). If this query
-- returns any rows the test FAILS, alerting that the table exists but the rolling
-- accuracy computation pipeline has not populated it.
--
-- Catches: migration 026 lands → accuracy window backfill never runs → rolling
-- accuracy stats missing from pundit leaderboards and comparison views.

select count(*) as row_count
from {{ source('gold_layer', 'pundit_accuracy_windows') }}
having count(*) = 0

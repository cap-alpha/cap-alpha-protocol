-- Singular test: assert gold_layer.entities is not empty.
--
-- This table is created by migration 022 (target_entity column) and extended by
-- the PR #856 schema. If this query returns any rows the test FAILS, alerting that
-- the table was created by a migration but never backfilled with data.
--
-- Catches: schema migration creates table → backfill job never runs → table silently
-- stays empty while downstream dashboards show zero results.

select count(*) as row_count
from {{ source('gold_layer', 'entities') }}
having count(*) = 0

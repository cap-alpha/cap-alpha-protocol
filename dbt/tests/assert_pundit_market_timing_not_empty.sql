-- Singular test: assert gold_layer.pundit_market_timing is not empty.
--
-- This table will be created by migration 025 (PR #854, queued). If this query
-- returns any rows the test FAILS, alerting that the table exists but the market
-- timing scoring pipeline has not populated it.
--
-- Catches: migration 025 lands → market timing backfill never runs → timing scores
-- silently absent from pundit profile pages and ranking dashboards.

select count(*) as row_count
from {{ source('gold_layer', 'pundit_market_timing') }}
having count(*) = 0

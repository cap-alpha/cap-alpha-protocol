-- Singular test: assert gold_layer.pundit_calibration is not empty.
--
-- This table is created by migration 024. If this query returns any rows the test
-- FAILS, alerting that the table was created by a migration but the calibration
-- scoring pipeline has not yet populated it.
--
-- Catches: migration 024 lands → calibration scoring job never runs → calibration
-- scores silently missing from pundit profile pages.

select count(*) as row_count
from {{ source('gold_layer', 'pundit_calibration') }}
having count(*) = 0

-- [TODO: PRODUCTIONIZATION - PHASE 2]
-- Staging model: Clean and standardize team dead money data

{{ config(
    materialized='table',
    schema='staging',
    tags=['staging', 'team_data']
) }}

SELECT
    team,
    CAST(year AS INT64) as year,
    CAST(active_cap AS NUMERIC) as active_cap_million,
    CAST(dead_money AS NUMERIC) as dead_money_million,
    CAST(total_cap AS NUMERIC) as total_cap_million,
    CAST(dead_cap_pct AS NUMERIC) as dead_cap_percentage,
    CURRENT_TIMESTAMP() as dbt_loaded_at
    
FROM {{ source('raw', 'team_dead_money_raw') }}

WHERE team IS NOT NULL
  AND year BETWEEN 2015 AND EXTRACT(YEAR FROM CURRENT_DATE())

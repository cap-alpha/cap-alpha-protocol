-- Staging model: Normalize and validate player contract data
-- Source: Spotrac team contracts pages
-- Purpose: Clean contract financial data for downstream feature engineering

{{ config(
    materialized='table',
    schema='staging',
    tags=['staging', 'contracts'],
    description='Normalized player contract data from Spotrac'
) }}

WITH source_contracts AS (
    SELECT
        player_name,
        team,
        position,
        year,
        total_contract_value_millions,
        guaranteed_money_millions,
        signing_bonus_millions,
        contract_length_years,
        years_remaining,
        cap_hit_millions,
        dead_cap_millions,
        CURRENT_TIMESTAMP() as dbt_loaded_at
    FROM {{ source('raw', 'player_contracts_raw') }}
    WHERE year IS NOT NULL
      AND player_name IS NOT NULL
      AND team IS NOT NULL
)

SELECT
    DISTINCT
    player_name,
    team,
    position,
    CAST(year AS INT64) as year,
    COALESCE(CAST(total_contract_value_millions AS NUMERIC), 0) as total_contract_value_millions,
    COALESCE(CAST(guaranteed_money_millions AS NUMERIC), 0) as guaranteed_money_millions,
    COALESCE(CAST(signing_bonus_millions AS NUMERIC), 0) as signing_bonus_millions,
    CAST(contract_length_years AS INT64) as contract_length_years,
    CAST(years_remaining AS INT64) as years_remaining,
    COALESCE(CAST(cap_hit_millions AS NUMERIC), 0) as cap_hit_millions,
    COALESCE(CAST(dead_cap_millions AS NUMERIC), 0) as dead_cap_millions,
    -- Derived features
    CASE 
        WHEN guaranteed_money_millions > 0 AND total_contract_value_millions > 0
        THEN ROUND(guaranteed_money_millions / total_contract_value_millions * 100, 2)
        ELSE 0
    END as guaranteed_pct,
    dbt_loaded_at
    
FROM source_contracts

WHERE total_contract_value_millions IS NOT NULL
  AND guaranteed_money_millions IS NOT NULL

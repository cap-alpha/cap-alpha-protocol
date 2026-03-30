-- Prediction Feature Mart: Player Dead Money Risk Features
-- Combines contract data + roster performance + historical dead money
-- Purpose: Training dataset for dead money prediction models

{{ config(
    materialized='table',
    schema='marts',
    tags=['mart', 'prediction', 'features'],
    description='Player features for dead money prediction modeling'
) }}

WITH contracts AS (
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
        guaranteed_pct,
        cap_hit_millions
    FROM {{ ref('stg_player_contracts') }}
),

rosters AS (
    -- PFR roster data for player age, performance metrics
    SELECT DISTINCT
        player_name,
        team,
        year,
        CAST(age AS INT64) as age_at_year,
        CAST(games_played AS INT64) as games_played,
        CAST(approximate_value AS NUMERIC) as performance_av,
        CAST(years_experience AS INT64) as years_experience
    FROM {{ ref('stg_player_rosters') }}  -- Will be created as companion model
    WHERE age IS NOT NULL
),

dead_money AS (
    SELECT
        player_name,
        team,
        year,
        dead_cap_hit as dead_money_millions,
        1 as became_dead_money_flag
    FROM {{ ref('stg_player_dead_money') }}
),

joined_features AS (
    SELECT
        c.player_name,
        c.team,
        c.position,
        c.year,
        -- Contract financial features
        c.total_contract_value_millions,
        c.guaranteed_money_millions,
        c.signing_bonus_millions,
        c.contract_length_years,
        c.years_remaining,
        c.guaranteed_pct,
        c.cap_hit_millions,
        -- Roster performance features
        COALESCE(r.age_at_year, 0) as age_at_signing,
        COALESCE(r.games_played, 0) as games_played_prior_year,
        COALESCE(r.performance_av, 0) as performance_av,
        COALESCE(r.years_experience, 0) as years_experience,
        -- Target variable
        COALESCE(dm.became_dead_money_flag, 0) as became_dead_money_next_year,
        COALESCE(dm.dead_money_millions, 0) as dead_money_amount,
        -- Derived risk features
        CASE 
            WHEN c.guaranteed_pct > 80 THEN 'high_guarantee'
            WHEN c.guaranteed_pct > 50 THEN 'moderate_guarantee'
            ELSE 'low_guarantee'
        END as guarantee_category,
        CASE 
            WHEN c.contract_length_years > 3 THEN 'long_term'
            WHEN c.contract_length_years > 1 THEN 'medium_term'
            ELSE 'short_term'
        END as contract_length_category,
        CASE 
            WHEN COALESCE(r.age_at_year, 0) >= 32 THEN 'veteran'
            WHEN COALESCE(r.age_at_year, 0) >= 27 THEN 'prime'
            ELSE 'young'
        END as age_category,
        CASE 
            WHEN COALESCE(r.performance_av, 0) > 10 THEN 'elite'
            WHEN COALESCE(r.performance_av, 0) > 5 THEN 'good'
            WHEN COALESCE(r.performance_av, 0) > 2 THEN 'average'
            ELSE 'below_average'
        END as performance_category,
        CURRENT_TIMESTAMP() as dbt_loaded_at
        
    FROM contracts c
    LEFT JOIN rosters r
        ON c.player_name = r.player_name
        AND c.team = r.team
        AND c.year = r.year
    LEFT JOIN dead_money dm
        ON c.player_name = dm.player_name
        AND c.team = dm.team
        AND c.year = dm.year
)

SELECT *
FROM joined_features
WHERE total_contract_value_millions > 0  -- Only contracts with financial data
  AND guaranteed_money_millions > 0       -- Only contracts with guaranteed money

-- Staging model: Pro Football Reference roster data
-- Source: PFR combined rosters CSV
-- Purpose: Player performance metrics, age, experience for enrichment

{{ config(
    materialized='table',
    schema='staging',
    tags=['staging', 'rosters'],
    description='Normalized PFR roster data with player performance metrics'
) }}

WITH source_rosters AS (
    SELECT
        "Player" as player_name,
        team,
        "Pos" as position,
        year,
        CAST("Age" AS INT64) as age,
        CAST("G" AS INT64) as games_played,
        CAST("GS" AS INT64) as games_started,
        CAST("AV" AS NUMERIC) as approximate_value,
        CAST("Yrs" AS INT64) as years_experience,
        College as college,
        "Drafted (tm/rnd/yr)" as draft_info,
        CURRENT_TIMESTAMP() as dbt_loaded_at
    FROM {{ source('raw', 'pfr_rosters_raw') }}
    WHERE "Player" IS NOT NULL
      AND team IS NOT NULL
      AND year IS NOT NULL
)

SELECT DISTINCT
    player_name,
    team,
    position,
    CAST(year AS INT64) as year,
    age,
    games_played,
    games_started,
    approximate_value,
    years_experience,
    college,
    draft_info,
    dbt_loaded_at
    
FROM source_rosters

WHERE age IS NOT NULL
  AND age > 0
  AND age < 50
  AND games_played >= 0
  AND approximate_value >= 0

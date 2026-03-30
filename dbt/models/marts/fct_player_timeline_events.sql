{{ config(
    materialized='table',
    schema='marts',
    tags=['mart', 'timeline']
) }}

WITH contracts AS (
    SELECT
        player_name,
        team,
        DATE(year, 3, 1) as event_date, -- Start of league year
        'Contract' as event_type,
        CONCAT('Signed ', CAST(contract_length_years AS STRING), ' yr / $', CAST(total_contract_value_millions AS STRING), 'M contract') as event_description,
        CAST(total_contract_value_millions AS NUMERIC) as financial_impact_millions
    FROM {{ ref('stg_player_contracts') }}
    WHERE total_contract_value_millions > 0
),

cap_hits AS (
    SELECT
        player_name,
        team,
        DATE(year, 9, 1) as event_date, -- Start of season
        'Dead Money' as event_type,
        CONCAT('Dead Cap Hit: $', CAST(dead_cap_millions AS STRING), 'M') as event_description,
        CAST(dead_cap_millions AS NUMERIC) as financial_impact_millions
    FROM {{ ref('stg_spotrac_dead_money') }}
    WHERE dead_cap_millions > 0
),

news AS (
    SELECT
        player_name,
        CAST(NULL AS STRING) as team,
        CAST(ingested_at AS DATE) as event_date,
        CASE
            WHEN LOWER(raw_text) LIKE '%injur%' OR LOWER(raw_text) LIKE '%surgery%' OR LOWER(raw_text) LIKE '%torn%' THEN 'Injury'
            WHEN LOWER(raw_text) LIKE '%trade%' THEN 'Trade'
            WHEN LOWER(raw_text) LIKE '%restructure%' THEN 'Restructure'
            WHEN LOWER(raw_text) LIKE '%release%' OR LOWER(raw_text) LIKE '%cut%' THEN 'Release'
            ELSE 'News Intel'
        END as event_type,
        raw_text as event_description,
        CAST(0.0 AS NUMERIC) as financial_impact_millions
    FROM {{ source('raw', 'raw_media_sentiment') }}
),

combined AS (
    SELECT * FROM contracts
    UNION ALL
    SELECT * FROM cap_hits
    UNION ALL
    SELECT * FROM news
)

SELECT
    {{ dbt_utils.generate_surrogate_key(['player_name', 'event_date', 'event_type', 'event_description']) }} as timeline_event_id,
    player_name,
    team,
    event_date,
    event_type,
    event_description,
    financial_impact_millions,
    CURRENT_TIMESTAMP() as dbt_created_at
FROM combined
ORDER BY event_date DESC

{{ config(
    materialized='table',
    schema='marts',
    tags=['mart', 'timeline']
) }}

WITH contracts AS (
    SELECT
        player_name,
        team,
        MAKE_DATE(year, 3, 1) as event_date, -- Start of league year
        'Contract' as event_type,
        'Signed ' || CAST(contract_length_years AS VARCHAR) || ' yr / $' || CAST(total_contract_value_millions AS VARCHAR) || 'M contract' as event_description,
        CAST(total_contract_value_millions AS DECIMAL(10,2)) as financial_impact_millions
    FROM {{ ref('stg_player_contracts') }}
    WHERE total_contract_value_millions > 0
),

cap_hits AS (
    SELECT
        player_name,
        team,
        MAKE_DATE(year, 9, 1) as event_date, -- Start of season
        'Dead Money' as event_type,
        'Dead Cap Hit: $' || CAST(dead_cap_millions AS VARCHAR) || 'M' as event_description,
        CAST(dead_cap_millions AS DECIMAL(10,2)) as financial_impact_millions
    FROM {{ ref('stg_spotrac_dead_money') }}
    WHERE dead_cap_millions > 0
),

news AS (
    SELECT
        player_name,
        NULL::VARCHAR as team,
        CAST(ingested_at AS DATE) as event_date,
        CASE
            WHEN LOWER(raw_text) LIKE '%injur%' OR LOWER(raw_text) LIKE '%surgery%' OR LOWER(raw_text) LIKE '%torn%' THEN 'Injury'
            WHEN LOWER(raw_text) LIKE '%trade%' THEN 'Trade'
            WHEN LOWER(raw_text) LIKE '%restructure%' THEN 'Restructure'
            WHEN LOWER(raw_text) LIKE '%release%' OR LOWER(raw_text) LIKE '%cut%' THEN 'Release'
            ELSE 'News Intel'
        END as event_type,
        raw_text as event_description,
        0.0::DECIMAL(10,2) as financial_impact_millions
    FROM bronze_layer.raw_media_sentiment
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

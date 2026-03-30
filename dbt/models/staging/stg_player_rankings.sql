-- Staging model for player rankings
-- Source: player_rankings table loaded via dbt seed or external ingestion

{{ config(materialized='table', schema='staging') }}

with src as (
    select *
    from {{ source('raw', 'player_rankings_raw') }}
)

select
  CAST(Player AS STRING) as player,
  CAST(Team AS STRING) as team,
  CAST(Position AS STRING) as position,
  SAFE_CAST(CapValue AS FLOAT64) as cap_value,
  SAFE_CAST(Year AS INT64) as year
from src
where Player is not null and Player <> ''

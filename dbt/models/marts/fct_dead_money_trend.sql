{{ config(materialized='table', schema='marts') }}

-- Dead money trend over time: total NFL dead money by year
with team_cap as (
  select
    year,
    team,
    dead_money_millions,
    salary_cap_millions
  from {{ ref('stg_spotrac_team_cap') }}
)

select
  year,
  round(CAST(sum(dead_money_millions) AS NUMERIC), 2) as total_dead_money_millions,
  round(CAST(avg(dead_money_millions) AS NUMERIC), 2) as avg_dead_money_per_team,
  round(CAST(max(dead_money_millions) AS NUMERIC), 2) as max_dead_money_millions,
  count(distinct team) as teams_with_data
from team_cap
group by year
order by year

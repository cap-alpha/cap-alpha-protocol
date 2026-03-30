{{ config(materialized='table', schema='marts') }}

-- Dead money by player: for player-level analysis with percentile ranks
-- Filter: only include players with > $1M dead cap (avoid noise from minor charges)
with player_dm as (
  select
    player_name,
    team,
    year,
    dead_cap_millions
  from {{ ref('stg_spotrac_dead_money') }}
  where dead_cap_millions > 1.0
),

team_totals as (
  select
    team,
    year,
    sum(dead_cap_millions) as team_total_dead_money_millions
  from player_dm
  group by team, year
),

nfl_stats as (
  select
    year,
    sum(dead_cap_millions) as nfl_total_dead_money_millions,
    avg(dead_cap_millions) as nfl_avg_dead_cap,
    stddev_pop(dead_cap_millions) as nfl_stddev_dead_cap
  from player_dm
  group by year
),

nfl_percentiles as (
  select
    year,
    dead_cap_millions,
    PERCENTILE_CONT(dead_cap_millions, 0.75) OVER (PARTITION BY year) as p75_dead_cap,
    PERCENTILE_CONT(dead_cap_millions, 0.90) OVER (PARTITION BY year) as p90_dead_cap,
    PERCENTILE_CONT(dead_cap_millions, 0.95) OVER (PARTITION BY year) as p95_dead_cap
  from player_dm
),

player_with_percentile as (
  select
    p.player_name,
    p.team,
    p.year,
    p.dead_cap_millions,
    t.team_total_dead_money_millions,
    round(CAST(p.dead_cap_millions / t.team_total_dead_money_millions * 100 AS NUMERIC), 2) as pct_of_team_dead_money,
    n.nfl_total_dead_money_millions,
    round(CAST(p.dead_cap_millions / n.nfl_total_dead_money_millions * 100 AS NUMERIC), 4) as pct_of_nfl_dead_money,
    percent_rank() over (partition by p.year order by p.dead_cap_millions) as percentile_rank,
    round(CAST(percent_rank() over (partition by p.year order by p.dead_cap_millions) * 100 AS NUMERIC), 1) as nfl_percentile
  from player_dm p
  join team_totals t on p.team = t.team and p.year = t.year
  join nfl_stats n on p.year = n.year
)

select
  player_name,
  team,
  year,
  round(CAST(dead_cap_millions AS NUMERIC), 2) as dead_cap_millions,
  round(CAST(team_total_dead_money_millions AS NUMERIC), 2) as team_total_dead_money_millions,
  pct_of_team_dead_money,
  round(CAST(nfl_total_dead_money_millions AS NUMERIC), 2) as nfl_total_dead_money_millions,
  pct_of_nfl_dead_money,
  nfl_percentile,
  row_number() over (partition by year order by dead_cap_millions desc) as rank_in_year
from player_with_percentile
order by year, dead_cap_millions desc

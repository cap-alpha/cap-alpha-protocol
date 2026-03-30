-- Union player rankings and team cap data for comprehensive view
-- Exposes: player-level cap hits, team aggregates, year-over-year trends

with player_rankings as (
  select
    player,
    team,
    position,
    cap_value,
    year,
    'player' as level
  from {{ ref('stg_player_rankings') }}
  where player is not null
),

team_cap_totals as (
  select
    null as player,
    team,
    'TEAM' as position,
    dead_money_million as cap_value,
    year,
    'team' as level
  from {{ ref('stg_team_dead_money') }}
  where team is not null
)

select * from player_rankings
union all
select * from team_cap_totals
order by year desc, cap_value desc

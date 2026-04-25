# API Vendor Payload Guide

NFL Dead Money / Pundit Prediction Ledger — B2B integration reference.

Interactive docs: `GET /docs` (Swagger UI) or `GET /redoc` (ReDoc).
Machine-readable spec: `GET /openapi.json` or [`docs/api/openapi.json`](openapi.json).

---

## Authentication

B2B endpoints (`/v1/cap/*`) require an `X-API-Key` header:

```
X-API-Key: your-key-here
```

Keys are provisioned by setting the `B2B_API_KEYS` environment variable
(comma-separated list).  When the variable is absent the API runs in dev mode
(auth disabled).

Rate limit: **1 000 requests / hour** per key (override with `B2B_RATE_LIMIT_RPH`).
Exceeded quota → HTTP 429 + `Retry-After` header.

---

## Vendor Payload 1 — Pundit Index

**Endpoints**

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/leaderboard` | Pundits ranked by weighted accuracy score |
| `GET` | `/v1/pundits/` | All pundits with aggregate stats |
| `GET` | `/v1/pundits/{pundit_id}` | Single pundit breakdown by claim category |

**Key fields**

| Field | Type | Description |
|---|---|---|
| `avg_brier_score` | float [0, 1] | Probabilistic calibration score. 0 = perfect, 1 = perfectly wrong. Primary Pundit Index metric. |
| `avg_weighted_score` | float | Recency- and difficulty-adjusted score. Drives leaderboard ranking. |
| `accuracy_rate` | float [0, 1] | `correct_count / resolved_count` |
| `total_predictions` | int | All-time prediction count |
| `resolved_count` | int | Predictions with a final CORRECT / INCORRECT verdict |

**Example response — `/v1/leaderboard`**

```json
{
  "leaderboard": [
    {
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "sport": "NFL",
      "total_predictions": 847,
      "resolved_count": 631,
      "correct_count": 384,
      "accuracy_rate": 0.608,
      "avg_brier_score": 0.24,
      "avg_weighted_score": 0.71
    }
  ],
  "total": 42
}
```

**Integrity guarantee**

Every prediction is stored in an append-only BigQuery ledger with a tamper-evident
SHA-256 hash chain.  Verify with `GET /v1/integrity/verify`.

---

## Vendor Payload 2 — FMV Trajectory

**Endpoint**

```
GET /v1/cap/fmv/{player_name}
X-API-Key: required
```

Returns the year-over-year Fair Market Value (FMV) trajectory for a player.
The `trajectory` field is the primary vendor signal.

**`trajectory` values**

| Value | Meaning |
|---|---|
| `improving` | FMV increased YoY — player value rising faster than cap hit |
| `declining` | FMV decreased YoY — player value falling; contract at risk |
| `flat` | No meaningful change |
| `unknown` | Fewer than 2 seasons of data |

**Key fields per season**

| Field | Type | Description |
|---|---|---|
| `fair_market_value` | float (millions USD) | Model-derived fair value. Divergence from `cap_hit_millions` is the core FMV signal. |
| `cap_hit_millions` | float | Actual cap charge |
| `efficiency_ratio` | float | `fair_market_value / cap_hit_millions`. Values > 1.0 = surplus value. |
| `edce_risk` | float | Expected Dead Cap Exposure composite score |
| `ml_risk_score` | float [0, 1] | XGBoost dead-cap risk probability |

**Example response**

```json
{
  "player_name": "Patrick Mahomes",
  "trajectory": "improving",
  "seasons": [
    {
      "year": 2023,
      "team": "KAN",
      "position": "QB",
      "cap_hit_millions": 40.0,
      "fair_market_value": 42.0,
      "efficiency_ratio": 1.05,
      "ml_risk_score": 0.12
    },
    {
      "year": 2024,
      "team": "KAN",
      "position": "QB",
      "cap_hit_millions": 45.0,
      "fair_market_value": 48.0,
      "efficiency_ratio": 1.07,
      "ml_risk_score": 0.15
    }
  ]
}
```

---

## Vendor Payload 3 — Injury Lag

**Endpoint**

```
GET /v1/cap/players/{player_name}
X-API-Key: required
```

Returns the full cap profile for a player across all available seasons.
Cross-reference `availability_rating` with `ml_risk_score` to identify contracts
where availability decline has not yet been priced into the dead-cap exposure.

**Key fields**

| Field | Type | Description |
|---|---|---|
| `availability_rating` | float [0, 1] | `games_played / max_games`. Values below 0.75 with high `cap_hit_millions` signal an availability-repricing lag. |
| `ml_risk_score` | float [0, 1] | XGBoost dead-cap risk probability. Combined with low `availability_rating`, flags Injury Lag candidates. |
| `games_played` | int | Actual games played in the season |
| `dead_cap_millions` | float | Dead cap obligation if released — the financial cost of the lag |
| `guaranteed_money_millions` | float | Total guaranteed money remaining — magnifies lag risk |

**Injury Lag signal logic**

A contract shows Injury Lag when:
- `availability_rating < 0.75` (missed 4+ games in a 17-game season), AND
- `ml_risk_score > 0.30` (model flags elevated dead-cap risk), AND
- `dead_cap_millions` remains high relative to `fair_market_value`

**Example response**

```json
{
  "player_name": "Saquon Barkley",
  "season_count": 6,
  "seasons": [
    {
      "year": 2022,
      "team": "NYG",
      "position": "RB",
      "cap_hit_millions": 7.2,
      "dead_cap_millions": 3.6,
      "guaranteed_money_millions": 7.2,
      "fair_market_value": 5.8,
      "ml_risk_score": 0.41,
      "availability_rating": 0.71,
      "games_played": 12
    }
  ]
}
```

---

## Additional Endpoints

### Paginated player list

```
GET /v1/cap/players?year=2024&position=QB&team=KAN&limit=50&page=1
X-API-Key: required
```

Query parameters: `year`, `position`, `team`, `limit` (1–500), `page`.

### Team cap summary

```
GET /v1/cap/teams?year=2024&conference=AFC
X-API-Key: required
```

Returns pre-computed positional spending breakdowns and cap space per team.

### Prediction search

```
GET /v1/predictions/?category=injury&status=CORRECT&player=mahomes&limit=50
```

No API key required.  Full-text substring match on `player` and `pundit_name`.

---

## Error responses

| Status | Meaning |
|---|---|
| 401 | Invalid or missing `X-API-Key` |
| 404 | Player / pundit not found |
| 422 | Validation error (missing required header or invalid query param) |
| 429 | Rate limit exceeded — check `Retry-After` header |
| 500 | Internal error — retry with exponential backoff |

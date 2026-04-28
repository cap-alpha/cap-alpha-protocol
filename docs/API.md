# Pundit Prediction Ledger — REST API Reference

**Base URL:** `https://pundit-ledger-api-wvhvx2muna-uc.a.run.app`

All endpoints are versioned under `/v1`. Responses are JSON throughout.

---

## Authentication

Every endpoint (except the health check `GET /`) requires an API key passed as an HTTP header:

```
x-api-key: capk_live_...
```

Keys are provisioned via the Cap Alpha dashboard. The key format is `capk_live_<random>`.

**Error — missing or invalid key:**
```json
HTTP 401
{ "detail": "Invalid or missing API key" }
```

---

## Rate Limits

Rate limits depend on your subscription tier:

| Tier | Keys Allowed | Notes |
|---|---|---|
| Free | 1 | Public leaderboard access |
| Pro | 3 | Full prediction history |
| API Starter | 10 | Suitable for small apps |
| Enterprise | 25 | High-volume integrations |

If you exceed your rate limit the API returns `HTTP 429`. Contact `support@cap-alpha.co` to upgrade.

---

## Endpoints

### `GET /` — Health check

No auth required. Returns service status.

**Response:**
```json
{
  "status": "ok",
  "service": "pundit-prediction-ledger",
  "version": "1.0.0"
}
```

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/
```

---

### `GET /v1/me` — API key info

Returns the tier, rate limit, scopes, and last-used info for the authenticated key. Useful for SDK clients to surface quota state.

**Auth required:** yes

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/me \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "key_id": "capk_live_abc123",
  "tier": "api_starter",
  "scopes": ["read"],
  "last_used_at": "2025-04-27T12:00:00Z"
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 422 | Validation error |

---

### `GET /v1/leaderboard` — Ranked pundits by accuracy

Returns pundits ranked by weighted accuracy score (accuracy × timeliness). Cached for 5 minutes.

**Auth required:** yes

**Query parameters:**

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `limit` | integer | no | Number of pundits to return (1–100, default 25) | `?limit=10` |

**curl:**
```bash
curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/leaderboard?limit=10" \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "leaderboard": [
    {
      "pundit_id": "mcafee_pat",        // unique slug for the pundit
      "pundit_name": "Pat McAfee",      // display name
      "total": 142,                     // total predictions tracked
      "resolved": 118,                  // predictions with a final verdict
      "correct": 71,                    // correct predictions
      "accuracy_rate": 0.601,           // correct / resolved (0–1)
      "avg_weighted_score": 0.72        // accuracy × timeliness composite
    }
  ],
  "total": 48                           // total pundits in the full dataset
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 500 | Backend / BigQuery error |

---

### `GET /v1/pundits/` — List all tracked pundits

Returns all pundits with aggregate accuracy stats (same shape as leaderboard but unranked and unfiltered).

**Auth required:** yes

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/pundits/ \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "pundits": [
    {
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "total": 142,
      "resolved": 118,
      "correct": 71,
      "accuracy_rate": 0.601,
      "avg_weighted_score": 0.72
    }
  ],
  "total": 48
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 500 | Backend / BigQuery error |

---

### `GET /v1/pundits/{pundit_id}` — Pundit detail

Returns a single pundit's overall accuracy summary plus a breakdown by claim category (e.g. draft picks, spreads, season props).

**Auth required:** yes

**Path parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `pundit_id` | string | yes | Pundit slug (e.g. `mcafee_pat`) |

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/pundits/mcafee_pat \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "pundit": {
    "pundit_id": "mcafee_pat",
    "pundit_name": "Pat McAfee",
    "total": 142,
    "resolved": 118,
    "correct": 71,
    "accuracy_rate": 0.601,
    "avg_weighted_score": 0.72
  },
  "accuracy_by_category": [
    {
      "claim_category": "draft_pick",    // category of prediction
      "total": 38,                       // predictions in this category
      "resolved": 32,                    // resolved predictions
      "correct": 21,                     // correct predictions
      "accuracy_rate": 0.656,            // accuracy within this category
      "avg_weighted_score": 0.78         // weighted score within this category
    },
    {
      "claim_category": "season_prop",
      "total": 55,
      "resolved": 49,
      "correct": 27,
      "accuracy_rate": 0.551,
      "avg_weighted_score": 0.66
    }
  ]
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 404 | Pundit not found |
| 422 | Validation error |
| 500 | Backend / BigQuery error |

---

### `GET /v1/pundits/{pundit_id}/predictions` — Pundit prediction history

Returns a paginated list of all predictions for a pundit, with resolution status.

**Auth required:** yes

**Path parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `pundit_id` | string | yes | Pundit slug |

**Query parameters:**

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `page` | integer | no | Page number (default 1) | `?page=2` |
| `page_size` | integer | no | Records per page (1–100, default 20) | `?page_size=50` |
| `status` | string | no | Filter by resolution status: `CORRECT`, `INCORRECT`, or `PENDING` | `?status=CORRECT` |

**curl:**
```bash
curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/pundits/mcafee_pat/predictions?page=1&page_size=20&status=CORRECT" \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "pundit_id": "mcafee_pat",
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",    // cryptographic record identifier
      "ingestion_timestamp": "2025-04-10T08:30:00Z",
      "source_url": "https://x.com/PatMcAfeeShow/status/...",
      "raw_assertion_text": "Chase Young goes top 5",
      "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
      "claim_category": "draft_pick",
      "season_year": 2025,
      "target_player_id": "chase_young_2025",
      "target_team": null,
      "resolution_status": "CORRECT",           // CORRECT | INCORRECT | PENDING
      "resolved_at": "2025-04-25T22:00:00Z",
      "binary_correct": true,
      "brier_score": 0.09,                      // probability calibration score (lower is better)
      "weighted_score": 0.91,
      "outcome_notes": "Selected 3rd overall by the Giants"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 142,
  "pages": 8
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 422 | Invalid query parameter |
| 500 | Backend / BigQuery error |

---

### `GET /v1/predictions/` — Search predictions

Filterable search across all predictions from all pundits, joined with resolution data.

**Auth required:** yes

**Query parameters:**

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `category` | string | no | Filter by `claim_category` (exact match) | `?category=draft_pick` |
| `status` | string | no | Filter by resolution status: `CORRECT`, `INCORRECT`, `PENDING` | `?status=PENDING` |
| `player` | string | no | Substring match on `target_player_name` (case-insensitive) | `?player=mahomes` |
| `pundit_name` | string | no | Substring match on `pundit_name` (case-insensitive) | `?pundit_name=schefter` |
| `limit` | integer | no | Records per page (1–200, default 50) | `?limit=100` |
| `page` | integer | no | Page number (default 1) | `?page=3` |

**curl:**
```bash
curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/predictions/?category=draft_pick&status=CORRECT&limit=25" \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "ingestion_timestamp": "2025-04-10T08:30:00Z",
      "source_url": "https://x.com/PatMcAfeeShow/status/...",
      "raw_assertion_text": "Chase Young goes top 5",
      "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
      "claim_category": "draft_pick",
      "season_year": 2025,
      "target_player_id": "chase_young_2025",
      "target_player_name": "Chase Young",
      "target_team": null,
      "resolution_status": "CORRECT",
      "resolved_at": "2025-04-25T22:00:00Z",
      "binary_correct": true,
      "brier_score": 0.09,
      "weighted_score": 0.91,
      "outcome_notes": "Selected 3rd overall by the Giants"
    }
  ],
  "page": 1,
  "limit": 25,
  "total": 412,
  "pages": 17
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 422 | Invalid query parameter |
| 500 | Backend / BigQuery error |

---

### `GET /v1/predictions/recent` — Latest resolved predictions

Returns the most recently resolved predictions across all pundits, ordered by resolution date descending.

**Auth required:** yes

**Query parameters:**

| Name | Type | Required | Description | Example |
|---|---|---|---|---|
| `limit` | integer | no | Number of predictions to return (1–100, default 20) | `?limit=50` |

**curl:**
```bash
curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/predictions/recent?limit=10" \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "pundit_id": "schefter_adam",
      "pundit_name": "Adam Schefter",
      "ingestion_timestamp": "2025-04-12T14:00:00Z",
      "extracted_claim": "Eagles will trade their first-round pick",
      "claim_category": "trade",
      "season_year": 2025,
      "target_player_id": null,
      "target_team": "PHI",
      "resolution_status": "INCORRECT",
      "resolved_at": "2025-04-25T23:59:00Z",
      "binary_correct": false,
      "brier_score": 0.81,
      "weighted_score": 0.19,
      "outcome_notes": "Eagles did not trade their first-round pick"
    }
  ],
  "count": 10
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 500 | Backend / BigQuery error |

---

### `GET /v1/draft/{year}` — Draft prediction summary

Returns all draft pick predictions for a given season year, with an aggregate count of pending vs. resolved.

**Auth required:** yes

**Path parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `year` | integer | yes | NFL draft year (e.g. `2025`) |

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/draft/2025 \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "year": 2025,
  "total": 89,                  // total draft predictions tracked
  "resolved": 72,               // predictions with CORRECT or INCORRECT verdict
  "pending": 17,                // awaiting resolution
  "predictions": [
    {
      "prediction_hash": "sha256:abc123...",
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "ingestion_timestamp": "2025-04-10T08:30:00Z",
      "source_url": "https://x.com/PatMcAfeeShow/status/...",
      "raw_assertion_text": "Chase Young goes top 5",
      "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
      "season_year": 2025,
      "target_player_name": "Chase Young",
      "target_team": null,
      "resolution_status": "CORRECT",
      "resolved_at": "2025-04-25T22:00:00Z",
      "binary_correct": true,
      "weighted_score": 0.91,
      "outcome_notes": "Selected 3rd overall by the Giants"
    }
  ]
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 422 | Validation error (e.g. non-integer year) |
| 500 | Backend / BigQuery error |

---

### `GET /v1/draft/{year}/results` — Draft resolution scoreboard

Returns draft predictions grouped by resolution status, plus per-pundit accuracy stats for the draft class. Useful for building a "who called the draft best" scoreboard.

**Auth required:** yes

**Path parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `year` | integer | yes | NFL draft year (e.g. `2025`) |

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/draft/2025/results \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "year": 2025,
  "total": 89,
  "by_status": {
    "CORRECT": [
      {
        "prediction_hash": "sha256:abc123...",
        "pundit_id": "mcafee_pat",
        "pundit_name": "Pat McAfee",
        "extracted_claim": "Chase Young will be selected in the top 5 of the 2025 NFL Draft",
        "target_player_name": "Chase Young",
        "target_team": null,
        "resolution_status": "CORRECT",
        "resolved_at": "2025-04-25T22:00:00Z",
        "binary_correct": true,
        "weighted_score": 0.91,
        "outcome_notes": "Selected 3rd overall by the Giants"
      }
    ],
    "INCORRECT": [ /* ... */ ],
    "PENDING": [ /* ... */ ]
  },
  "pundit_accuracy": [
    {
      "pundit_id": "mcafee_pat",
      "pundit_name": "Pat McAfee",
      "total_predictions": 12,
      "resolved_count": 10,
      "correct_count": 7,
      "accuracy_rate": 0.7,
      "avg_weighted_score": 0.81
    }
  ]
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 422 | Validation error |
| 500 | Backend / BigQuery error |

---

### `GET /v1/integrity/verify` — Hash chain integrity check

Walks the full prediction ledger and verifies the cryptographic hash chain is intact. Returns `verified: true` if no records have been tampered with.

Each prediction is SHA-256 hashed including the previous record's hash, forming a tamper-evident chain. Any modification to a historical record breaks all subsequent hashes.

**Auth required:** yes

**curl:**
```bash
curl https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/integrity/verify \
  -H "x-api-key: capk_live_your_key"
```

**Response:**
```json
{
  "verified": true,
  "records_checked": 4821,
  "broken_at": null               // null when chain is intact; hash ID if tampered
}
```

**Errors:**

| Code | Meaning |
|---|---|
| 401 | Missing or invalid API key |
| 500 | Integrity check failed to run |

---

## Common error shapes

All errors follow FastAPI's standard response format:

```json
{
  "detail": "Human-readable error message"
}
```

Validation errors (422) include field-level context:
```json
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is less than or equal to 100",
      "type": "value_error.number.not_le"
    }
  ]
}
```

---

## Quick start

1. Sign in at [cap-alpha.co](https://cap-alpha.co) and create an API key from your account dashboard.
2. Make your first request:

```bash
curl "https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/v1/leaderboard?limit=5" \
  -H "x-api-key: capk_live_your_key"
```

3. Explore endpoints with the interactive schema at:
   `https://pundit-ledger-api-wvhvx2muna-uc.a.run.app/docs`

---

*Questions? Email `support@cap-alpha.co`.*

import logging
import os
import sys
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from api.pundit_router import router as pundit_router
    from api.cap_router import router as cap_router
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from api.pundit_router import router as pundit_router
    from api.cap_router import router as cap_router

try:
    from src.adversarial_engine import AdversarialEngine
    from src.trade_partner_finder import TradePartnerFinder
    from src.win_probability import WinProbabilityModel

    _TRADE_AVAILABLE = True
except Exception:
    _TRADE_AVAILABLE = False

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_DESCRIPTION = """
## NFL Dead Money — Pundit Prediction Ledger API

Cryptographically-verified NFL analytics platform.  All prediction records are stored
in an append-only BigQuery ledger with a tamper-evident SHA-256 hash chain.

### Vendor Payloads

| Payload | Endpoints | Description |
|---|---|---|
| **Pundit Index** | `GET /v1/leaderboard`, `GET /v1/pundits/` | Brier-scored accuracy rankings for tracked NFL media personalities |
| **FMV Trajectory** | `GET /v1/cap/fmv/{player_name}` | Year-over-year Fair Market Value direction signal (improving / declining / flat) |
| **Injury Lag** | `GET /v1/cap/players/{player_name}` | `availability_rating` × `ml_risk_score` overlay identifying contracts not yet repriced for injury-adjusted market value |

### Authentication

B2B endpoints (`/v1/cap/*`) require an `X-API-Key` header.
Contact us to obtain a key.  Keys not set in `B2B_API_KEYS` env var → dev mode (auth disabled).

### Rate Limits

Default: **1 000 requests / hour** per API key (configurable via `B2B_RATE_LIMIT_RPH`).
Exceeded quota returns HTTP 429 with a `Retry-After` header.
"""

_TAGS_METADATA = [
    {
        "name": "pundit-ledger",
        "description": (
            "Public prediction ledger endpoints.  No API key required.  "
            "Surfaces the **Pundit Index** and **FMV Trajectory** vendor payloads."
        ),
        "externalDocs": {
            "description": "Vendor payload guide",
            "url": "https://github.com/ucalegon206/cap-alpha-protocol/blob/main/docs/api/VENDOR_PAYLOADS.md",
        },
    },
    {
        "name": "b2b-cap-intelligence",
        "description": (
            "B2B Cap Intelligence API.  All endpoints require `X-API-Key` header.  "
            "Surfaces the **FMV Trajectory** and **Injury Lag** vendor payloads."
        ),
        "externalDocs": {
            "description": "Vendor payload guide",
            "url": "https://github.com/ucalegon206/cap-alpha-protocol/blob/main/docs/api/VENDOR_PAYLOADS.md",
        },
    },
]

app = FastAPI(
    title="NFL Dead Money — Pundit Prediction Ledger API",
    description=_DESCRIPTION,
    version="1.0.0",
    openapi_tags=_TAGS_METADATA,
    contact={
        "name": "Cap Alpha Protocol",
        "url": "https://github.com/ucalegon206/cap-alpha-protocol",
    },
    license_info={
        "name": "Proprietary",
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(pundit_router)
app.include_router(cap_router)  # SP30-1: B2B Cap Intelligence API (requires X-API-Key)

# Initialize Engine (only if trade modules loaded successfully)
if _TRADE_AVAILABLE:
    engine = AdversarialEngine()
    win_model = WinProbabilityModel()
    partner_finder = TradePartnerFinder()


class TradeProposal(BaseModel):
    team_a: str
    team_b: str
    team_a_assets: List[Dict[str, Any]]
    team_b_assets: List[Dict[str, Any]]
    config: Optional[Dict[str, Any]] = None


@app.get("/")
def health_check():
    return {"status": "ok", "service": "pundit-prediction-ledger", "version": "1.0.0"}


@app.post("/api/trade/evaluate")
def evaluate_trade(proposal: TradeProposal):
    if not _TRADE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trade engine not available")
    try:
        logger.info(
            f"Received trade evaluation request: {proposal.team_a} <-> {proposal.team_b}"
        )
        result = engine.evaluate_trade(proposal.dict())
        return result
    except Exception as e:
        logger.error(f"Error evaluating trade: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/trade/counter")
def generate_counter(proposal: TradeProposal):
    if not _TRADE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trade engine not available")
    try:
        logger.info(
            f"Generating counter-offer for: {proposal.team_a} <-> {proposal.team_b}"
        )
        counter = engine.generate_counter_offer(proposal.dict())
        return counter
    except Exception as e:
        logger.error(f"Error generating counter: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/vegas")
def analyze_vegas(proposal: TradeProposal):
    if not _TRADE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trade engine not available")
    try:
        logger.info(
            f"Analyzing Vegas impact for: {proposal.team_a} <-> {proposal.team_b}"
        )
        impact = win_model.calculate_win_impact(proposal.dict())
        return impact
    except Exception as e:
        logger.error(f"Error analyzing Vegas impact: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trade/find_partner/{player_id}")
def find_partner(player_id: str, cap_hit: float, position: str = "QB"):
    if not _TRADE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Trade engine not available")
    try:
        logger.info(f"Finding partners for {player_id} ({position}, ${cap_hit}M)")
        partners = partner_finder.find_buyers(
            player_id, position=position, cap_hit=cap_hit
        )
        return {"player": player_id, "top_partners": partners}
    except Exception as e:
        logger.error(f"Error finding partners: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

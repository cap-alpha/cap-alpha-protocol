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

app = FastAPI(
    title="Cap Alpha Protocol API",
    description="""
## Cap Alpha Protocol — B2B Intelligence API

Cryptographically verified NFL contract analytics and pundit prediction tracking.

### Authentication

`/v1/cap/` endpoints require a **B2B API key** passed as the `X-API-Key` request header.
Contact [api@capalphaprotocol.com](mailto:api@capalphaprotocol.com) to request credentials.

### Vendor Payloads

| Payload | Description | Endpoint |
|---------|-------------|----------|
| **Pundit Index** | Per-pundit accuracy scores, Brier scores, weighted rankings | `GET /v1/leaderboard`, `GET /v1/pundits/` |
| **FMV Trajectory** | Fair-market value + risk tier + dead-cap exposure per player | `GET /v1/cap/players` |
| **Cap Intelligence** | Team-level cap totals, risk cap, surplus value | `GET /v1/cap/teams` |
| **Integrity Proof** | Cryptographic hash chain verification | `GET /v1/integrity/verify` |

### Rate Limits

| Tier | Requests/day |
|------|-------------|
| free | 100 |
| standard | 1,000 |
| premium | 10,000 |
""",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "pundit-ledger",
            "description": "Pundit prediction tracking and accuracy leaderboards",
        },
        {
            "name": "cap-intelligence",
            "description": "NFL player and team cap data (requires X-API-Key)",
        },
    ],
    contact={
        "name": "Cap Alpha Protocol",
        "email": "api@capalphaprotocol.com",
    },
    license_info={
        "name": "Proprietary — B2B License Required",
    },
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(pundit_router)
app.include_router(cap_router)

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

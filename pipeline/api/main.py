import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException

_SENTRY_DSN = os.environ.get("SENTRY_DSN")
if _SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        sentry_sdk.init(
            dsn=_SENTRY_DSN,
            traces_sample_rate=0.1,
            integrations=[StarletteIntegration(), FastApiIntegration()],
            environment=os.environ.get("ENVIRONMENT", "production"),
            send_default_pii=False,
        )
    except ImportError:
        pass  # sentry-sdk not installed; error reporting disabled
from pydantic import BaseModel

try:
    from api.entity_router import router as entity_router
    from api.integrity_router import router as integrity_router
    from api.pundit_router import router as pundit_router
    from api.quality_router import router as quality_router
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
    from api.entity_router import router as entity_router
    from api.integrity_router import router as integrity_router
    from api.pundit_router import router as pundit_router
    from api.quality_router import router as quality_router

# MCP server (issue #814).  Import is lazy-tolerant: if the optional
# ``fastmcp`` package is unavailable (older deploys, minimal dev installs)
# the REST API still works — only the /mcp mount is skipped.
try:
    from api.mcp_middleware import APIKeyContextMiddleware
    from api.mcp_server import get_mcp_asgi_app, get_mcp_server

    _MCP_AVAILABLE = True
except Exception as _mcp_err:  # pragma: no cover — import-only failure path
    logging.getLogger(__name__).warning(
        "MCP server unavailable, /mcp will not be mounted: %s", _mcp_err
    )
    _MCP_AVAILABLE = False

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


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Forward lifespan events to the MCP ASGI app so its session manager
    # starts/stops cleanly.  Without this, FastMCP raises
    # "Task group is not initialized" on the first request.
    if _MCP_AVAILABLE and getattr(app.state, "_mcp_app", None) is not None:
        async with app.state._mcp_app.router.lifespan_context(app):
            yield
    else:
        yield


app = FastAPI(
    title="Pundit Prediction Ledger API",
    description="Cryptographically verified NFL pundit prediction tracking",
    version="1.0.0",
    lifespan=_lifespan,
)

from fastapi.middleware.cors import CORSMiddleware

origins = os.getenv("ALLOWED_ORIGINS", "https://cap-alpha.co").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(pundit_router)
app.include_router(quality_router)
app.include_router(integrity_router)
app.include_router(entity_router)

# -----------------------------------------------------------------------------
# Mount the MCP server at /mcp (issue #814 Phase 1).
# -----------------------------------------------------------------------------
if _MCP_AVAILABLE:
    try:
        mcp_app = get_mcp_asgi_app(path="/")
        # Wrap with auth middleware that extracts X-API-Key + sets the
        # mcp_current_key_info ContextVar before any tool handler runs.
        wrapped_mcp = APIKeyContextMiddleware(mcp_app)
        app.state._mcp_app = mcp_app
        app.mount("/mcp", wrapped_mcp)

        @app.get("/.well-known/mcp.json")
        def mcp_discovery() -> Dict[str, Any]:
            server = get_mcp_server()
            return {
                "name": server.name,
                "version": "1.0.0",
                "transport": "http+sse",
                "endpoint": "/mcp",
                "minimum_tier": "agent_growth",
                "phase": 1,
                "tools": list(
                    getattr(server, "_tool_manager", {}).get("_tools", {}).keys()
                )
                if hasattr(server, "_tool_manager")
                else [],
            }

        logger.info("MCP server mounted at /mcp (Phase 1, 6 tools)")
    except Exception as exc:  # pragma: no cover — mount failure
        logger.error("Failed to mount /mcp: %s", exc)
        app.state._mcp_app = None
else:
    app.state._mcp_app = None

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

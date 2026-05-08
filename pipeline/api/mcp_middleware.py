"""
ASGI middleware: extracts ``X-API-Key`` from incoming MCP HTTP requests,
resolves the key via BigQuery, binds the resulting key_info dict to the
``mcp_current_key_info`` ContextVar so tool handlers can read it.

When ``MCP_AUTH_DISABLED`` is set (test/dev only) the middleware injects a
synthetic ``agent_growth`` key so tool calls bypass BigQuery entirely.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from api.mcp_auth import (
    is_mcp_auth_disabled,
    resolve_api_key,
    set_current_key_info,
    reset_current_key_info,
)

logger = logging.getLogger(__name__)


def _synthetic_key_info() -> Dict[str, Any]:
    return {
        "key_id": "test-key",
        "user_id": "test-user",
        "tier": os.environ.get("MCP_AUTH_DISABLED_TIER", "agent_growth"),
        "status": "active",
        "scopes": [],
        "name": "MCP_AUTH_DISABLED",
    }


class APIKeyContextMiddleware:
    """Pure ASGI middleware — works with FastMCP's Starlette app."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Allow unauthenticated discovery on /mcp/.well-known/*.  Everything
        # else (tools/list, tools/call) must carry an API key.
        path: str = scope.get("path", "")
        if path.endswith("/.well-known/mcp.json") or path.endswith("/health"):
            await self.app(scope, receive, send)
            return

        api_key: Optional[str] = self._extract_key(scope)
        key_info: Optional[Dict[str, Any]]
        if is_mcp_auth_disabled():
            key_info = _synthetic_key_info()
        elif not api_key:
            response = JSONResponse(
                {
                    "error": "MISSING_API_KEY",
                    "code": -32001,
                    "detail": "X-API-Key header required for MCP requests",
                },
                status_code=401,
            )
            await response(scope, receive, send)
            return
        else:
            key_info = resolve_api_key(api_key)
            if key_info is None:
                response = JSONResponse(
                    {
                        "error": "INVALID_API_KEY",
                        "code": -32001,
                        "detail": "API key was not recognized or has been revoked",
                    },
                    status_code=401,
                )
                await response(scope, receive, send)
                return

        token = set_current_key_info(key_info)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_current_key_info(token)

    @staticmethod
    def _extract_key(scope: Scope) -> Optional[str]:
        for name, value in scope.get("headers", []):
            try:
                if name.decode("latin-1").lower() == "x-api-key":
                    return value.decode("latin-1").strip()
            except Exception:
                continue
        return None

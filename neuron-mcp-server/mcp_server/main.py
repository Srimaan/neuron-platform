"""
FastMCP entry point (Chapter 3 — Neuron guide).

- ``TRANSPORT`` or ``MCP_TRANSPORT``: set either to ``stdio`` for Claude Desktop; otherwise HTTP.
- ``GET /health`` → ``{"status":"ok","tools_registered":5}``.
- Optional ``MCP_AUTH_TOKEN``: Bearer required for MCP routes; ``/health`` stays public.

Run: ``uv run python -m mcp_server.main``

See https://srimaan.github.io/neuron-guide/03-first-mcp-server.html
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server.config import get_settings
from mcp_server.tools import register_all_tools

mcp = FastMCP("neuron-mcp-server")

register_all_tools(mcp)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    """Liveness probe and tool registry count (used by Chapter 3 verification)."""
    tools = await mcp._tool_manager.get_tools()
    return JSONResponse({"status": "ok", "tools_registered": len(tools)})


class _BearerAuthMiddleware:
    """Require ``Authorization: Bearer <token>`` for HTTP MCP traffic; exempt ``GET /health``."""

    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path == "/health" or path.rstrip("/") == "/health":
            await self.app(scope, receive, send)
            return
        raw_headers = scope.get("headers") or []
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw_headers}
        auth = headers.get("authorization", "")
        if auth != f"Bearer {self.token}":
            resp = JSONResponse({"error": "unauthorized"}, status_code=401)
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _http_middleware() -> list[Middleware]:
    s = get_settings()
    tok = s.mcp_auth_token.strip()
    if not tok:
        return []
    return [Middleware(_BearerAuthMiddleware, token=tok)]


async def _tool_count() -> int:
    tools = await mcp._tool_manager.get_tools()
    return len(tools)


def main() -> None:
    """Console script / ``python -m mcp_server.main`` entrypoint."""
    s = get_settings()
    logging.basicConfig(
        level=getattr(logging, s.log_level.upper(), logging.INFO),
        format="%(levelname)s %(message)s",
    )
    log = logging.getLogger("neuron-mcp-server")
    n_tools = asyncio.run(_tool_count())
    auth_on = bool(s.mcp_auth_token.strip())
    transport_raw = os.environ.get("TRANSPORT", "").strip().lower()
    if not transport_raw:
        transport_raw = os.environ.get("MCP_TRANSPORT", "").strip().lower()

    log.info("neuron-mcp-server starting...")
    log.info("Tools registered: %s", n_tools)
    log.info("Auth: %s", "enabled" if auth_on else "disabled")

    if transport_raw == "stdio":
        log.info("Transport: stdio")
        mcp.run(transport="stdio", log_level=s.log_level.lower())
    else:
        log.info("Transport: SSE HTTP (streamable-http)")
        log.info("Listening on http://%s:%s/mcp", s.mcp_host, s.mcp_port)
        log.info("Health: http://127.0.0.1:%s/health", s.mcp_port)
        mcp.run(
            transport="http",
            host=s.mcp_host,
            port=s.mcp_port,
            middleware=_http_middleware(),
            log_level=s.log_level.lower(),
        )


if __name__ == "__main__":
    main()

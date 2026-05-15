"""HTTP /health endpoint (Neuron guide checkpoint)."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_health_returns_five_tools() -> None:
    from mcp_server.main import mcp

    app = mcp.http_app(transport="http")
    with TestClient(app, raise_server_exceptions=True) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "tools_registered": 5}

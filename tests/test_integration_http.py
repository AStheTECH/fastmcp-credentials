"""
End-to-end tests over a real FastMCP ASGI app, driven via in-memory HTTP.

Unlike the rest of the suite (which exercises CredentialMiddleware and the
backends directly, with FastMCP mocked out), these tests spin up an actual
``FastMCP`` instance, mount it as a stateless Streamable HTTP app (the
``2026-07-28`` protocol — no ``initialize`` handshake, no
``Mcp-Session-Id``), and drive it with real HTTP requests. They exist to
prove the whole stack — FastMCP's middleware dispatch, the ASGI app, and
this package's ``ContextVar``-based credential injection — still holds
together end to end on the modern, stateless protocol, for both the
``static`` and ``oauth`` credential paths.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastmcp import FastMCP

from fastmcp_credentials import (
    CredentialMiddleware,
    HeaderCredentialBackend,
    get_credentials,
)

_HEADERS = {"Accept": "application/json, text/event-stream"}


def _tool_call_payload(request_id: int, name: str = "whoami") -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": {}},
    }


async def _client_for(app) -> tuple[LifespanManager, httpx.AsyncClient]:
    manager = LifespanManager(app)
    await manager.__aenter__()
    transport = httpx.ASGITransport(app=manager.app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")
    return manager, client


@pytest.fixture
async def static_app():
    backend = HeaderCredentialBackend()
    mcp = FastMCP("static-test", middleware=[CredentialMiddleware(backend, "static")])

    @mcp.tool
    def whoami() -> str:
        return json.dumps(get_credentials().fields)

    app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True)
    manager, client = await _client_for(app)
    try:
        yield client
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


@pytest.fixture
async def oauth_app():
    backend = HeaderCredentialBackend()
    mcp = FastMCP("oauth-test", middleware=[CredentialMiddleware(backend, "oauth")])

    @mcp.tool
    def whoami() -> str:
        cred = get_credentials()
        return json.dumps(
            {
                "access_token": cred.access_token,
                "scopes": cred.scopes,
                "extra": cred.extra,
                "expires_at": cred.expires_at.isoformat() if cred.expires_at else None,
            }
        )

    app = mcp.http_app(path="/mcp", transport="streamable-http", stateless_http=True)
    manager, client = await _client_for(app)
    try:
        yield client
    finally:
        await client.aclose()
        await manager.__aexit__(None, None, None)


# ---------------------------------------------------------------------------
# Stateless protocol shape — no session id, no initialize handshake
# ---------------------------------------------------------------------------

async def test_static_tool_call_requires_no_initialize_handshake(static_app):
    r = await static_app.post(
        "/mcp",
        json=_tool_call_payload(1),
        headers={**_HEADERS, "X-Mcp-Cred-Fields": json.dumps({"apiKey": "sk-abc"})},
    )
    assert r.status_code == 200
    assert "sk-abc" in r.text


async def test_static_tool_call_gets_no_session_id_header(static_app):
    r = await static_app.post(
        "/mcp",
        json=_tool_call_payload(1),
        headers={**_HEADERS, "X-Mcp-Cred-Fields": json.dumps({"apiKey": "sk-abc"})},
    )
    assert "mcp-session-id" not in {h.lower() for h in r.headers}


async def test_oauth_tool_call_requires_no_initialize_handshake(oauth_app):
    r = await oauth_app.post(
        "/mcp",
        json=_tool_call_payload(1),
        headers={**_HEADERS, "X-Mcp-Cred-Access-Token": "test-token-abc"},
    )
    assert r.status_code == 200
    assert "test-token-abc" in r.text


async def test_oauth_tool_call_gets_no_session_id_header(oauth_app):
    r = await oauth_app.post(
        "/mcp",
        json=_tool_call_payload(1),
        headers={**_HEADERS, "X-Mcp-Cred-Access-Token": "test-token-abc"},
    )
    assert "mcp-session-id" not in {h.lower() for h in r.headers}


# ---------------------------------------------------------------------------
# OAuth field resolution over real HTTP (the gap the empirical pass left)
# ---------------------------------------------------------------------------

async def test_oauth_scopes_and_extra_resolved_over_http(oauth_app):
    r = await oauth_app.post(
        "/mcp",
        json=_tool_call_payload(1),
        headers={
            **_HEADERS,
            "X-Mcp-Cred-Access-Token": "test-token-abc",
            "X-Mcp-Cred-Scopes": "read write",
            "X-Mcp-Cred-Extra": json.dumps({"dc": "us10"}),
            "X-Mcp-Cred-Expires-At": "2026-05-04T12:00:00+00:00",
        },
    )
    assert r.status_code == 200
    body = r.text
    assert "test-token-abc" in body
    assert "read" in body and "write" in body
    assert "us10" in body
    assert "2026-05-04" in body


async def test_oauth_missing_access_token_header_raises_over_http(oauth_app):
    r = await oauth_app.post("/mcp", json=_tool_call_payload(1), headers=_HEADERS)
    assert r.status_code == 200  # JSON-RPC error, not an HTTP error
    assert "error" in r.text
    assert "X-MCP-Cred-Access-Token" in r.text


# ---------------------------------------------------------------------------
# ContextVar isolation under real concurrent stateless requests
# ---------------------------------------------------------------------------

def _tool_text(resp: httpx.Response) -> str:
    """Extract the tool's returned JSON string from the SSE-wrapped response body."""
    line = next(line for line in resp.text.splitlines() if line.startswith("data: "))
    envelope = json.loads(line[len("data: "):])
    return envelope["result"]["structuredContent"]["result"]


async def test_concurrent_oauth_requests_do_not_leak_credentials(oauth_app):
    async def call(i: int) -> httpx.Response:
        return await oauth_app.post(
            "/mcp",
            json=_tool_call_payload(i),
            headers={**_HEADERS, "X-Mcp-Cred-Access-Token": f"tok-{i}"},
        )

    responses = await asyncio.gather(*[call(i) for i in range(25)])
    for i, resp in enumerate(responses):
        assert resp.status_code == 200
        assert json.loads(_tool_text(resp))["access_token"] == f"tok-{i}"


async def test_concurrent_static_requests_do_not_leak_credentials(static_app):
    async def call(i: int) -> httpx.Response:
        return await static_app.post(
            "/mcp",
            json=_tool_call_payload(i),
            headers={**_HEADERS, "X-Mcp-Cred-Fields": json.dumps({"apiKey": f"key-{i}"})},
        )

    responses = await asyncio.gather(*[call(i) for i in range(25)])
    for i, resp in enumerate(responses):
        assert resp.status_code == 200
        assert json.loads(_tool_text(resp))["apiKey"] == f"key-{i}"

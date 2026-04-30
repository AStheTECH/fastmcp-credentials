from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp_credentials.middleware import CredentialMiddleware, _current_credential
from fastmcp_credentials.backends.base import CredentialBackend
from fastmcp_credentials.types import ResolvedCredential, CredentialError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StaticBackend(CredentialBackend):
    """Minimal backend that always returns the same credential."""

    def __init__(self, cred: ResolvedCredential) -> None:
        self._cred = cred
        self.resolved_ids: list[str] = []

    async def resolve(self, credential_id: str) -> ResolvedCredential:
        self.resolved_ids.append(credential_id)
        return self._cred


def _mock_request(credential_id: str | None = None, header: str = "X-Credential-ID"):
    """Build a minimal mock Starlette Request with the given header value."""
    headers: dict[str, str] = {}
    if credential_id is not None:
        headers[header] = credential_id
    req = MagicMock()
    req.headers.get = lambda h, default=None: headers.get(h, default)
    return req


def _make_middleware(cred: ResolvedCredential, header: str = "X-Credential-ID"):
    backend = _StaticBackend(cred)
    return CredentialMiddleware(backend, header=header), backend


# ---------------------------------------------------------------------------
# Tests — header absent
# ---------------------------------------------------------------------------

async def test_no_header_skips_resolve_and_calls_next():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, backend = _make_middleware(cred)
    call_next = AsyncMock(return_value="result")

    with patch("fastmcp_credentials.middleware.get_http_request", return_value=_mock_request()):
        result = await middleware.on_call_tool(MagicMock(), call_next)

    assert result == "result"
    assert backend.resolved_ids == []
    call_next.assert_called_once()


async def test_none_request_skips_resolve_and_calls_next():
    """get_http_request() can return None outside an HTTP context."""
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, backend = _make_middleware(cred)
    call_next = AsyncMock(return_value="ok")

    with patch("fastmcp_credentials.middleware.get_http_request", return_value=None):
        result = await middleware.on_call_tool(MagicMock(), call_next)

    assert result == "ok"
    assert backend.resolved_ids == []


# ---------------------------------------------------------------------------
# Tests — header present
# ---------------------------------------------------------------------------

async def test_header_present_resolves_correct_id():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, backend = _make_middleware(cred)

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request("cred_abc123")):
        await middleware.on_call_tool(MagicMock(), AsyncMock())

    assert backend.resolved_ids == ["cred_abc123"]


async def test_header_present_injects_credential_into_contextvar():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, _ = _make_middleware(cred)
    captured: dict = {}

    async def capturing_next(ctx):
        captured["cred"] = _current_credential.get()

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request("cred_abc")):
        await middleware.on_call_tool(MagicMock(), capturing_next)

    assert captured["cred"] is cred


async def test_custom_header_name_is_read():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, backend = _make_middleware(cred, header="X-My-Auth")
    captured: dict = {}

    async def capturing_next(ctx):
        captured["cred"] = _current_credential.get()

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request("cred_xyz", header="X-My-Auth")):
        await middleware.on_call_tool(MagicMock(), capturing_next)

    assert backend.resolved_ids == ["cred_xyz"]
    assert captured["cred"] is cred


# ---------------------------------------------------------------------------
# Tests — ContextVar lifecycle
# ---------------------------------------------------------------------------

async def test_contextvar_is_none_before_call():
    assert _current_credential.get() is None


async def test_contextvar_reset_to_none_after_successful_call():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, _ = _make_middleware(cred)

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request("cred_1")):
        await middleware.on_call_tool(MagicMock(), AsyncMock(return_value=None))

    assert _current_credential.get() is None


async def test_contextvar_reset_to_none_even_when_tool_raises():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, _ = _make_middleware(cred)

    async def raising_next(ctx):
        raise RuntimeError("tool exploded")

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request("cred_1")):
        with pytest.raises(RuntimeError, match="tool exploded"):
            await middleware.on_call_tool(MagicMock(), raising_next)

    assert _current_credential.get() is None


async def test_contextvar_not_visible_outside_tool_scope():
    """Credential set during a call must not bleed into subsequent calls without a header."""
    cred = ResolvedCredential(type="static", api_key="sk-test")
    middleware, _ = _make_middleware(cred)

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request("cred_1")):
        await middleware.on_call_tool(MagicMock(), AsyncMock())

    # Second call — no header → no credential injected
    seen: dict = {}

    async def check_next(ctx):
        seen["cred"] = _current_credential.get()

    with patch("fastmcp_credentials.middleware.get_http_request",
               return_value=_mock_request()):
        await middleware.on_call_tool(MagicMock(), check_next)

    assert seen["cred"] is None

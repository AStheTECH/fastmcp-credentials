from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp_credentials.middleware import CredentialMiddleware, _current_credential
from fastmcp_credentials.backends.base import CredentialBackend
from fastmcp_credentials.types import ResolvedCredential, CredentialError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _StubBackend(CredentialBackend):
    """Backend stub that returns a fixed credential or raises on demand."""

    def __init__(self, cred: ResolvedCredential | None = None, raises: Exception | None = None):
        self._cred = cred
        self._raises = raises
        self.call_count = 0

    async def resolve(self) -> ResolvedCredential:
        self.call_count += 1
        if self._raises:
            raise self._raises
        return self._cred


def _middleware(cred: ResolvedCredential | None = None, raises: Exception | None = None):
    backend = _StubBackend(cred=cred, raises=raises)
    return CredentialMiddleware(backend), backend


# ---------------------------------------------------------------------------
# Credential resolution and injection
# ---------------------------------------------------------------------------

async def test_backend_resolve_is_called_on_every_tool_call():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    mw, backend = _middleware(cred)
    await mw.on_call_tool(MagicMock(), AsyncMock())
    await mw.on_call_tool(MagicMock(), AsyncMock())
    assert backend.call_count == 2


async def test_credential_is_in_contextvar_during_call():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    mw, _ = _middleware(cred)
    captured: dict = {}

    async def capturing_next(ctx):
        captured["cred"] = _current_credential.get()

    await mw.on_call_tool(MagicMock(), capturing_next)
    assert captured["cred"] is cred


async def test_call_next_return_value_is_propagated():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    mw, _ = _middleware(cred)
    result = await mw.on_call_tool(MagicMock(), AsyncMock(return_value="tool-result"))
    assert result == "tool-result"


# ---------------------------------------------------------------------------
# ContextVar lifecycle
# ---------------------------------------------------------------------------

async def test_contextvar_is_none_before_any_call():
    assert _current_credential.get() is None


async def test_contextvar_reset_to_none_after_successful_call():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    mw, _ = _middleware(cred)
    await mw.on_call_tool(MagicMock(), AsyncMock())
    assert _current_credential.get() is None


async def test_contextvar_reset_to_none_when_tool_raises():
    cred = ResolvedCredential(type="static", api_key="sk-test")
    mw, _ = _middleware(cred)

    async def raising_next(ctx):
        raise RuntimeError("tool exploded")

    with pytest.raises(RuntimeError, match="tool exploded"):
        await mw.on_call_tool(MagicMock(), raising_next)

    assert _current_credential.get() is None


async def test_contextvar_not_set_when_backend_raises():
    mw, _ = _middleware(raises=CredentialError("backend down"))

    with pytest.raises(CredentialError):
        await mw.on_call_tool(MagicMock(), AsyncMock())

    assert _current_credential.get() is None


async def test_credential_does_not_leak_between_sequential_calls():
    cred_a = ResolvedCredential(type="static", api_key="sk-a")
    cred_b = ResolvedCredential(type="oauth", access_token="tok-b")

    backend_a = _StubBackend(cred=cred_a)
    backend_b = _StubBackend(cred=cred_b)
    mw_a = CredentialMiddleware(backend_a)
    mw_b = CredentialMiddleware(backend_b)

    seen: list = []

    async def capture(ctx):
        seen.append(_current_credential.get())

    await mw_a.on_call_tool(MagicMock(), capture)
    await mw_b.on_call_tool(MagicMock(), capture)

    assert seen[0] is cred_a
    assert seen[1] is cred_b
    assert _current_credential.get() is None


# ---------------------------------------------------------------------------
# Backend exception propagation
# ---------------------------------------------------------------------------

async def test_backend_exception_propagates():
    mw, _ = _middleware(raises=CredentialError("vault unreachable"))
    with pytest.raises(CredentialError, match="vault unreachable"):
        await mw.on_call_tool(MagicMock(), AsyncMock())


async def test_non_credential_backend_exception_also_propagates():
    mw, _ = _middleware(raises=ValueError("unexpected"))
    with pytest.raises(ValueError, match="unexpected"):
        await mw.on_call_tool(MagicMock(), AsyncMock())

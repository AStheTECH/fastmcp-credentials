from __future__ import annotations
import base64
import json
import pytest
from datetime import timezone
from unittest.mock import MagicMock, patch

from fastmcp_credentials.backends.headers import HeaderCredentialBackend
from fastmcp_credentials.types import MissingCredentialHeaderError

_PATCH = "fastmcp_credentials.backends.headers.get_http_request"


def _make_request(headers: dict[str, str]) -> MagicMock:
    req = MagicMock()
    req.headers.get = lambda key, default=None: headers.get(key, default)
    return req


# ---------------------------------------------------------------------------
# Missing headers / no request
# ---------------------------------------------------------------------------

async def test_raises_when_request_is_none():
    with patch(_PATCH, return_value=None):
        with pytest.raises(MissingCredentialHeaderError):
            await HeaderCredentialBackend().resolve()


async def test_raises_when_neither_token_header_is_present():
    with patch(_PATCH, return_value=_make_request({})):
        with pytest.raises(MissingCredentialHeaderError) as exc_info:
            await HeaderCredentialBackend().resolve()
    assert "X-MCP-Cred-Access-Token" in str(exc_info.value)
    assert "X-MCP-Cred-Api-Key" in str(exc_info.value)


async def test_missing_header_error_lists_missing_headers():
    with patch(_PATCH, return_value=_make_request({})):
        with pytest.raises(MissingCredentialHeaderError) as exc_info:
            await HeaderCredentialBackend().resolve()
    assert exc_info.value.missing_headers == [
        "X-MCP-Cred-Access-Token",
        "X-MCP-Cred-Api-Key",
    ]


# ---------------------------------------------------------------------------
# OAuth credential (access token present)
# ---------------------------------------------------------------------------

async def test_resolves_oauth_type_from_access_token_header():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "ya29.tok"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.type == "oauth"


async def test_resolves_access_token_value():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "ya29.tok"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.access_token == "ya29.tok"


async def test_access_token_takes_priority_over_api_key():
    headers = {
        "X-MCP-Cred-Access-Token": "ya29.tok",
        "X-MCP-Cred-Api-Key": "sk-also-present",
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.type == "oauth"
    assert cred.access_token == "ya29.tok"


# ---------------------------------------------------------------------------
# Static credential (API key present, no access token)
# ---------------------------------------------------------------------------

async def test_resolves_static_type_from_api_key_header():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Api-Key": "sk-abc"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.type == "static"


async def test_resolves_api_key_value():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Api-Key": "sk-abc"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.api_key == "sk-abc"


# ---------------------------------------------------------------------------
# Scopes header
# ---------------------------------------------------------------------------

async def test_scopes_parsed_from_csv():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Scopes": "read, write, admin",
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.scopes == ["read", "write", "admin"]


async def test_scopes_parsed_from_json_array():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Scopes": '["read", "write"]',
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.scopes == ["read", "write"]


async def test_scopes_absent_gives_none():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "tok"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.scopes is None


# ---------------------------------------------------------------------------
# Extra header
# ---------------------------------------------------------------------------

async def test_extra_parsed_from_plain_json():
    payload = json.dumps({"tenant_id": "t-123", "region": "us-east-1"})
    headers = {"X-MCP-Cred-Access-Token": "tok", "X-MCP-Cred-Extra": payload}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.extra["tenant_id"] == "t-123"
    assert cred.extra["region"] == "us-east-1"


async def test_extra_parsed_from_base64_encoded_json():
    payload = base64.b64encode(json.dumps({"account": "acct-42"}).encode()).decode()
    headers = {"X-MCP-Cred-Access-Token": "tok", "X-MCP-Cred-Extra": payload}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.extra["account"] == "acct-42"


async def test_extra_absent_gives_empty_dict():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "tok"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.extra == {}


async def test_malformed_extra_is_ignored(caplog):
    headers = {"X-MCP-Cred-Access-Token": "tok", "X-MCP-Cred-Extra": "!!!not-json-or-b64!!!"}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.extra == {}
    assert "X-MCP-Cred-Extra" in caplog.text


# ---------------------------------------------------------------------------
# Expires-At header
# ---------------------------------------------------------------------------

async def test_expires_at_parsed_from_iso_8601():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Expires-At": "2026-05-04T12:00:00+00:00",
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.expires_at is not None
    assert cred.expires_at.tzinfo is not None


async def test_naive_expires_at_normalized_to_utc():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Expires-At": "2026-05-04T12:00:00",  # no tz
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.expires_at.tzinfo == timezone.utc


async def test_expires_at_absent_gives_none():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "tok"})):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.expires_at is None


async def test_malformed_expires_at_is_ignored(caplog):
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Expires-At": "not-a-date",
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve()
    assert cred.expires_at is None
    assert "X-MCP-Cred-Expires-At" in caplog.text

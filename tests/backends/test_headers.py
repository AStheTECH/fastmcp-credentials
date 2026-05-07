from __future__ import annotations
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

async def test_oauth_raises_when_request_is_none():
    with patch(_PATCH, return_value=None):
        with pytest.raises(MissingCredentialHeaderError):
            await HeaderCredentialBackend().resolve("oauth")


async def test_static_raises_when_request_is_none():
    with patch(_PATCH, return_value=None):
        with pytest.raises(MissingCredentialHeaderError):
            await HeaderCredentialBackend().resolve("static")


async def test_oauth_raises_when_access_token_header_missing():
    with patch(_PATCH, return_value=_make_request({})):
        with pytest.raises(MissingCredentialHeaderError) as exc_info:
            await HeaderCredentialBackend().resolve("oauth")
    assert "X-MCP-Cred-Access-Token" in str(exc_info.value)
    assert exc_info.value.missing_headers == ["X-MCP-Cred-Access-Token"]


async def test_static_raises_when_fields_header_missing():
    with patch(_PATCH, return_value=_make_request({})):
        with pytest.raises(MissingCredentialHeaderError) as exc_info:
            await HeaderCredentialBackend().resolve("static")
    assert "X-MCP-Cred-Fields" in str(exc_info.value)
    assert exc_info.value.missing_headers == ["X-MCP-Cred-Fields"]


# ---------------------------------------------------------------------------
# OAuth credential
# ---------------------------------------------------------------------------

async def test_resolves_oauth_type():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "ya29.tok"})):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.type == "oauth"


async def test_resolves_access_token_value():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "ya29.tok"})):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.access_token == "ya29.tok"


# ---------------------------------------------------------------------------
# Static credential
# ---------------------------------------------------------------------------

async def test_resolves_static_type():
    headers = {"X-MCP-Cred-Fields": json.dumps({"apiKey": "sk-abc"})}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.type == "static"


async def test_resolves_single_field():
    headers = {"X-MCP-Cred-Fields": json.dumps({"secretKey": "sk_live_abc"})}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.fields["secretKey"] == "sk_live_abc"


async def test_resolves_multiple_fields():
    payload = {"keyId": "rz_live_xxx", "keySecret": "secret123"}
    headers = {"X-MCP-Cred-Fields": json.dumps(payload)}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.fields["keyId"] == "rz_live_xxx"
    assert cred.fields["keySecret"] == "secret123"


async def test_static_fields_are_all_strings():
    headers = {"X-MCP-Cred-Fields": json.dumps({"count": 42, "flag": True})}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.fields["count"] == "42"
    assert cred.fields["flag"] == "True"


async def test_malformed_fields_header_gives_empty_dict(caplog):
    headers = {"X-MCP-Cred-Fields": "!!!not-json!!!"}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.fields == {}
    assert "X-MCP-Cred-Fields" in caplog.text


async def test_static_credential_has_no_access_token():
    headers = {"X-MCP-Cred-Fields": json.dumps({"apiKey": "sk-abc"})}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.access_token is None


async def test_static_credential_has_empty_extra():
    headers = {"X-MCP-Cred-Fields": json.dumps({"apiKey": "sk-abc"})}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("static")
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# Scopes header (OAuth only)
# ---------------------------------------------------------------------------

async def test_scopes_parsed_from_space_separated():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Scopes": "read write admin",
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.scopes == ["read", "write", "admin"]


async def test_scopes_parsed_from_json_array():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Scopes": '["read", "write"]',
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.scopes == ["read", "write"]


async def test_scopes_absent_gives_none():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "tok"})):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.scopes is None


# ---------------------------------------------------------------------------
# Extra header (OAuth metadata only)
# ---------------------------------------------------------------------------

async def test_extra_parsed_from_plain_json():
    payload = json.dumps({"dc": "us10", "workspace": "my-ws"})
    headers = {"X-MCP-Cred-Access-Token": "tok", "X-MCP-Cred-Extra": payload}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.extra["dc"] == "us10"
    assert cred.extra["workspace"] == "my-ws"


async def test_extra_absent_gives_empty_dict():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "tok"})):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.extra == {}


async def test_malformed_extra_is_ignored(caplog):
    headers = {"X-MCP-Cred-Access-Token": "tok", "X-MCP-Cred-Extra": "!!!not-json!!!"}
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("oauth")
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
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.expires_at is not None
    assert cred.expires_at.tzinfo is not None


async def test_naive_expires_at_normalized_to_utc():
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Expires-At": "2026-05-04T12:00:00",  # no tz
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.expires_at.tzinfo == timezone.utc


async def test_expires_at_absent_gives_none():
    with patch(_PATCH, return_value=_make_request({"X-MCP-Cred-Access-Token": "tok"})):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.expires_at is None


async def test_malformed_expires_at_is_ignored(caplog):
    headers = {
        "X-MCP-Cred-Access-Token": "tok",
        "X-MCP-Cred-Expires-At": "not-a-date",
    }
    with patch(_PATCH, return_value=_make_request(headers)):
        cred = await HeaderCredentialBackend().resolve("oauth")
    assert cred.expires_at is None
    assert "X-MCP-Cred-Expires-At" in caplog.text

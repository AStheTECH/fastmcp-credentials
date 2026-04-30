from __future__ import annotations
import json
import pytest
from pathlib import Path
from datetime import timezone

from fastmcp_credentials.backends.file import FileCredentialBackend
from fastmcp_credentials.types import CredentialNotFoundError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(tmp_path: Path, data: dict) -> Path:
    p = tmp_path / "creds.json"
    p.write_text(json.dumps(data))
    return p


# ---------------------------------------------------------------------------
# Flat format — credential_id is ignored
# ---------------------------------------------------------------------------

async def test_flat_static(tmp_path):
    path = _write(tmp_path, {"type": "static", "api_key": "sk-abc"})
    cred = await FileCredentialBackend(path).resolve("any-id")
    assert cred.type == "static"
    assert cred.api_key == "sk-abc"


async def test_flat_oauth(tmp_path):
    path = _write(tmp_path, {
        "type": "oauth",
        "access_token": "tok-access",
        "refresh_token": "tok-refresh",
        "client_id": "client-id",
        "client_secret": "client-secret",
        "token_uri": "https://auth.example.com/token",
    })
    cred = await FileCredentialBackend(path).resolve("any-id")
    assert cred.type == "oauth"
    assert cred.access_token == "tok-access"
    assert cred.refresh_token == "tok-refresh"
    assert cred.client_id == "client-id"
    assert cred.client_secret == "client-secret"
    assert cred.token_uri == "https://auth.example.com/token"


async def test_flat_credential_id_is_ignored(tmp_path):
    path = _write(tmp_path, {"type": "static", "api_key": "sk-abc"})
    backend = FileCredentialBackend(path)
    assert (await backend.resolve("foo")).api_key == (await backend.resolve("bar")).api_key


async def test_flat_with_extra_dict(tmp_path):
    path = _write(tmp_path, {
        "type": "static",
        "api_key": "sk-abc",
        "extra": {"account_id": "acct-42", "region": "us-east-1"},
    })
    cred = await FileCredentialBackend(path).resolve("any")
    assert cred.extra["account_id"] == "acct-42"
    assert cred.extra["region"] == "us-east-1"


async def test_flat_missing_extra_gives_empty_dict(tmp_path):
    path = _write(tmp_path, {"type": "static", "api_key": "sk-abc"})
    cred = await FileCredentialBackend(path).resolve("any")
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# Keyed format — credential_id selects the entry
# ---------------------------------------------------------------------------

async def test_keyed_resolves_correct_entry(tmp_path):
    path = _write(tmp_path, {
        "cred_user1": {"type": "static", "api_key": "sk-user1"},
        "cred_user2": {"type": "static", "api_key": "sk-user2"},
    })
    cred = await FileCredentialBackend(path).resolve("cred_user1")
    assert cred.api_key == "sk-user1"


async def test_keyed_different_ids_return_different_creds(tmp_path):
    path = _write(tmp_path, {
        "cred_a": {"type": "static", "api_key": "sk-aaa"},
        "cred_b": {"type": "static", "api_key": "sk-bbb"},
    })
    backend = FileCredentialBackend(path)
    assert (await backend.resolve("cred_a")).api_key == "sk-aaa"
    assert (await backend.resolve("cred_b")).api_key == "sk-bbb"


async def test_keyed_unknown_id_raises_not_found(tmp_path):
    path = _write(tmp_path, {
        "cred_user1": {"type": "static", "api_key": "sk-user1"},
    })
    with pytest.raises(CredentialNotFoundError) as exc_info:
        await FileCredentialBackend(path).resolve("cred_missing")
    assert "cred_missing" in str(exc_info.value)


async def test_keyed_oauth_entry(tmp_path):
    path = _write(tmp_path, {
        "cred_oauth": {
            "type": "oauth",
            "access_token": "tok",
            "scopes": ["read"],
        }
    })
    cred = await FileCredentialBackend(path).resolve("cred_oauth")
    assert cred.type == "oauth"
    assert cred.access_token == "tok"


# ---------------------------------------------------------------------------
# Field parsing
# ---------------------------------------------------------------------------

async def test_expires_at_parsed_with_timezone(tmp_path):
    path = _write(tmp_path, {
        "type": "oauth",
        "expires_at": "2026-04-24T12:00:00+00:00",
    })
    cred = await FileCredentialBackend(path).resolve("any")
    assert cred.expires_at is not None
    assert cred.expires_at.tzinfo is not None


async def test_naive_expires_at_normalized_to_utc(tmp_path):
    path = _write(tmp_path, {
        "type": "oauth",
        "expires_at": "2026-04-24T12:00:00",  # no tz
    })
    cred = await FileCredentialBackend(path).resolve("any")
    assert cred.expires_at.tzinfo == timezone.utc


async def test_scopes_as_list_preserved(tmp_path):
    path = _write(tmp_path, {
        "type": "oauth",
        "scopes": ["read", "write", "admin"],
    })
    cred = await FileCredentialBackend(path).resolve("any")
    assert cred.scopes == ["read", "write", "admin"]


async def test_scopes_as_comma_string_parsed_to_list(tmp_path):
    path = _write(tmp_path, {
        "type": "oauth",
        "scopes": "read, write, admin",
    })
    cred = await FileCredentialBackend(path).resolve("any")
    assert cred.scopes == ["read", "write", "admin"]


async def test_path_accepted_as_string(tmp_path):
    path = _write(tmp_path, {"type": "static", "api_key": "sk-abc"})
    cred = await FileCredentialBackend(str(path)).resolve("any")
    assert cred.api_key == "sk-abc"

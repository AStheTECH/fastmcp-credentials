from __future__ import annotations
import pytest
from datetime import timezone
from fastmcp_credentials.backends.env import EnvCredentialBackend
from fastmcp_credentials.types import CredentialError

# Use a short, collision-resistant prefix for all tests.
PREFIX = "FCTEST_"


# ---------------------------------------------------------------------------
# Static auth
# ---------------------------------------------------------------------------

async def test_static_is_default_type(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}API_KEY", "sk-abc")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.type == "static"


async def test_static_api_key_resolved(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}API_KEY", "sk-abc")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.api_key == "sk-abc"


async def test_static_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv(f"{PREFIX}API_KEY", raising=False)
    with pytest.raises(CredentialError, match=f"{PREFIX}API_KEY"):
        await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")


async def test_static_extra_fields_collected(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}API_KEY", "pk-live")
    monkeypatch.setenv(f"{PREFIX}EXTRA_API_SECRET", "sk-secret")
    monkeypatch.setenv(f"{PREFIX}EXTRA_ACCOUNT_ID", "acct-42")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.extra["api_secret"] == "sk-secret"
    assert cred.extra["account_id"] == "acct-42"


async def test_static_extra_keys_are_lowercased(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}API_KEY", "pk-live")
    monkeypatch.setenv(f"{PREFIX}EXTRA_MY_FIELD", "val")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert "my_field" in cred.extra
    assert "MY_FIELD" not in cred.extra


async def test_static_no_extra_vars_gives_empty_dict(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}API_KEY", "sk-abc")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# OAuth auth
# ---------------------------------------------------------------------------

async def test_oauth_type_set_via_cred_type_var(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.type == "oauth"


async def test_oauth_all_standard_fields_resolved(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    monkeypatch.setenv(f"{PREFIX}ACCESS_TOKEN", "tok-access")
    monkeypatch.setenv(f"{PREFIX}REFRESH_TOKEN", "tok-refresh")
    monkeypatch.setenv(f"{PREFIX}CLIENT_ID", "client-id")
    monkeypatch.setenv(f"{PREFIX}CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(f"{PREFIX}TOKEN_URI", "https://auth.example.com/token")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.access_token == "tok-access"
    assert cred.refresh_token == "tok-refresh"
    assert cred.client_id == "client-id"
    assert cred.client_secret == "client-secret"
    assert cred.token_uri == "https://auth.example.com/token"


async def test_oauth_scopes_split_on_comma(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    monkeypatch.setenv(f"{PREFIX}SCOPES", "read, write, admin")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.scopes == ["read", "write", "admin"]


async def test_oauth_no_scopes_var_gives_none(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    monkeypatch.delenv(f"{PREFIX}SCOPES", raising=False)
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.scopes is None


async def test_oauth_expires_at_parsed_with_timezone(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    monkeypatch.setenv(f"{PREFIX}EXPIRES_AT", "2026-04-24T12:00:00+00:00")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.expires_at is not None
    assert cred.expires_at.tzinfo is not None


async def test_oauth_naive_expires_at_normalized_to_utc(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    monkeypatch.setenv(f"{PREFIX}EXPIRES_AT", "2026-04-24T12:00:00")  # no tz
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.expires_at.tzinfo == timezone.utc


async def test_oauth_extra_fields_collected(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    monkeypatch.setenv(f"{PREFIX}EXTRA_TENANT_ID", "tenant-xyz")
    monkeypatch.setenv(f"{PREFIX}EXTRA_WORKSPACE", "ws-prod")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.extra["tenant_id"] == "tenant-xyz"
    assert cred.extra["workspace"] == "ws-prod"


async def test_oauth_no_extra_vars_gives_empty_dict(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}CRED_TYPE", "oauth")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("ignored")
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# General behaviour
# ---------------------------------------------------------------------------

async def test_credential_id_is_ignored(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}API_KEY", "sk-abc")
    backend = EnvCredentialBackend(prefix=PREFIX)
    cred_a = await backend.resolve("anything")
    cred_b = await backend.resolve("something-else")
    assert cred_a.api_key == cred_b.api_key


def test_prefix_is_uppercased_on_init():
    backend = EnvCredentialBackend(prefix="myservice_")
    assert backend.prefix == "MYSERVICE_"


def test_empty_prefix_is_allowed():
    backend = EnvCredentialBackend()
    assert backend.prefix == ""

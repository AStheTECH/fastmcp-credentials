from __future__ import annotations
import json
import pytest
from datetime import timezone
from fastmcp_credentials.backends.env import EnvCredentialBackend
from fastmcp_credentials.types import CredentialError

PREFIX = "FCTEST_"


# ---------------------------------------------------------------------------
# Static auth — FIELDS JSON (primary pattern)
# ---------------------------------------------------------------------------

async def test_static_is_default_type(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}FIELDS", json.dumps({"apiKey": "sk-abc"}))
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert cred.type == "static"


async def test_static_fields_json_single_field(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}FIELDS", json.dumps({"secretKey": "sk_live_xxx"}))
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert cred.fields["secretKey"] == "sk_live_xxx"


async def test_static_fields_json_multiple_fields(monkeypatch):
    payload = {"keyId": "rz_live_xxx", "keySecret": "secret123"}
    monkeypatch.setenv(f"{PREFIX}FIELDS", json.dumps(payload))
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert cred.fields["keyId"] == "rz_live_xxx"
    assert cred.fields["keySecret"] == "secret123"


async def test_static_fields_json_invalid_raises(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}FIELDS", "not-json")
    with pytest.raises(CredentialError, match=f"{PREFIX}FIELDS"):
        await EnvCredentialBackend(prefix=PREFIX).resolve("static")


# ---------------------------------------------------------------------------
# Static auth — FIELD_* individual vars
# ---------------------------------------------------------------------------

async def test_static_individual_field_vars(monkeypatch):
    # Use uppercase suffixes — Windows env vars are case-insensitive and always
    # stored uppercase, so FIELD_* key names are uppercased on Windows.
    # Use the FIELDS JSON blob when camelCase field names are required.
    monkeypatch.setenv(f"{PREFIX}FIELD_API_KEY", "sk-abc")
    monkeypatch.setenv(f"{PREFIX}FIELD_SECRET_KEY", "secret-xyz")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert cred.fields["API_KEY"] == "sk-abc"
    assert cred.fields["SECRET_KEY"] == "secret-xyz"


async def test_static_field_vars_key_suffix_is_the_field_name(monkeypatch):
    # The field name is taken verbatim from the env var suffix after FIELD_.
    # On case-sensitive platforms (Linux/Mac) the case is preserved; on Windows
    # env vars are always uppercased by the OS, so use all-caps suffixes.
    monkeypatch.setenv(f"{PREFIX}FIELD_PHONE_NUMBER_ID", "1234567890")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert "PHONE_NUMBER_ID" in cred.fields
    assert cred.fields["PHONE_NUMBER_ID"] == "1234567890"


async def test_static_fields_json_takes_priority_over_field_vars(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}FIELDS", json.dumps({"apiKey": "from-json"}))
    monkeypatch.setenv(f"{PREFIX}FIELD_apiKey", "from-individual")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert cred.fields["apiKey"] == "from-json"


# ---------------------------------------------------------------------------
# Static auth — nothing set raises
# ---------------------------------------------------------------------------

async def test_static_no_credentials_raises(monkeypatch):
    monkeypatch.delenv(f"{PREFIX}FIELDS", raising=False)
    with pytest.raises(CredentialError):
        await EnvCredentialBackend(prefix=PREFIX).resolve("static")


async def test_static_has_empty_extra(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}FIELDS", json.dumps({"apiKey": "sk-abc"}))
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("static")
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# OAuth auth
# ---------------------------------------------------------------------------

async def test_oauth_type_resolved(monkeypatch):
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.type == "oauth"


async def test_oauth_all_standard_fields_resolved(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}ACCESS_TOKEN", "tok-access")
    monkeypatch.setenv(f"{PREFIX}REFRESH_TOKEN", "tok-refresh")
    monkeypatch.setenv(f"{PREFIX}CLIENT_ID", "client-id")
    monkeypatch.setenv(f"{PREFIX}CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(f"{PREFIX}TOKEN_URI", "https://auth.example.com/token")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.access_token == "tok-access"
    assert cred.refresh_token == "tok-refresh"
    assert cred.client_id == "client-id"
    assert cred.client_secret == "client-secret"
    assert cred.token_uri == "https://auth.example.com/token"


async def test_oauth_scopes_split_on_whitespace(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}SCOPES", "read write admin")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.scopes == ["read", "write", "admin"]


async def test_oauth_no_scopes_var_gives_none(monkeypatch):
    monkeypatch.delenv(f"{PREFIX}SCOPES", raising=False)
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.scopes is None


async def test_oauth_expires_at_parsed_with_timezone(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}EXPIRES_AT", "2026-04-24T12:00:00+00:00")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.expires_at is not None
    assert cred.expires_at.tzinfo is not None


async def test_oauth_naive_expires_at_normalized_to_utc(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}EXPIRES_AT", "2026-04-24T12:00:00")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.expires_at.tzinfo == timezone.utc


async def test_oauth_extra_fields_collected(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}EXTRA_DC", "us10")
    monkeypatch.setenv(f"{PREFIX}EXTRA_WORKSPACE", "ws-prod")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.extra["dc"] == "us10"
    assert cred.extra["workspace"] == "ws-prod"


async def test_oauth_extra_keys_are_lowercased(monkeypatch):
    monkeypatch.setenv(f"{PREFIX}EXTRA_MY_FIELD", "val")
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert "my_field" in cred.extra
    assert "MY_FIELD" not in cred.extra


async def test_oauth_no_extra_vars_gives_empty_dict(monkeypatch):
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.extra == {}


async def test_oauth_has_empty_fields(monkeypatch):
    cred = await EnvCredentialBackend(prefix=PREFIX).resolve("oauth")
    assert cred.fields == {}


# ---------------------------------------------------------------------------
# General behaviour
# ---------------------------------------------------------------------------

def test_prefix_is_uppercased_on_init():
    backend = EnvCredentialBackend(prefix="myservice_")
    assert backend.prefix == "MYSERVICE_"


def test_empty_prefix_is_allowed():
    backend = EnvCredentialBackend()
    assert backend.prefix == ""

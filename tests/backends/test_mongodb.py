from __future__ import annotations
import base64
import json
import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp_credentials.backends.mongodb import MongoDBCredentialBackend
from fastmcp_credentials.types import ResolvedCredential, CredentialError, CredentialNotFoundError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_key() -> bytes:
    return os.urandom(32)


@pytest.fixture
def key_b64(raw_key: bytes) -> str:
    return base64.b64encode(raw_key).decode()


@pytest.fixture
def backend(raw_key: bytes) -> MongoDBCredentialBackend:
    """Fully constructed backend with a mocked collection — no motor needed."""
    b = MongoDBCredentialBackend.__new__(MongoDBCredentialBackend)
    b._key = raw_key
    b._col = AsyncMock()
    return b


def _enc(key: bytes, value: str) -> str:
    """Encrypt a value the same way the backend does (used to build fake DB docs)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, value.encode(), None)
    return base64.b64encode(nonce + ct).decode()


def _future(hours: int = 1) -> str:
    return (datetime.now(tz=timezone.utc) + timedelta(hours=hours)).isoformat()


def _past(hours: int = 1) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=hours)).isoformat()


# ---------------------------------------------------------------------------
# Key loading
# ---------------------------------------------------------------------------

def test_load_key_returns_raw_bytes(key_b64, raw_key):
    assert MongoDBCredentialBackend._load_key(key_b64) == raw_key


def test_load_key_reads_from_env_when_arg_is_none(monkeypatch, key_b64, raw_key):
    monkeypatch.setenv("CRED_ENCRYPTION_KEY", key_b64)
    assert MongoDBCredentialBackend._load_key(None) == raw_key


def test_load_key_missing_raises_credential_error(monkeypatch):
    monkeypatch.delenv("CRED_ENCRYPTION_KEY", raising=False)
    with pytest.raises(CredentialError, match="Encryption key is required"):
        MongoDBCredentialBackend._load_key(None)


def test_load_key_wrong_length_raises_credential_error():
    short = base64.b64encode(os.urandom(16)).decode()  # 16 bytes, not 32
    with pytest.raises(CredentialError, match="32 bytes"):
        MongoDBCredentialBackend._load_key(short)


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip(backend):
    for plaintext in ["sk-abc123", "ya29.token-value", "1//refresh-token", ""]:
        assert backend._decrypt(backend._encrypt(plaintext)) == plaintext


def test_encrypt_is_nondeterministic(backend):
    # Different nonce each call → different ciphertext for the same plaintext
    a = backend._encrypt("same-value")
    b = backend._encrypt("same-value")
    assert a != b


def test_decrypt_reverses_encrypt(backend):
    plaintext = "super-secret"
    assert backend._decrypt(backend._encrypt(plaintext)) == plaintext


# ---------------------------------------------------------------------------
# resolve — not found
# ---------------------------------------------------------------------------

async def test_resolve_not_found_raises_credential_not_found_error(backend):
    backend._col.find_one.return_value = None
    with pytest.raises(CredentialNotFoundError) as exc_info:
        await backend.resolve("cred_missing")
    assert "cred_missing" in str(exc_info.value)


# ---------------------------------------------------------------------------
# resolve — static credential
# ---------------------------------------------------------------------------

async def test_resolve_static_decrypts_api_key(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "static",
        "api_key": _enc(raw_key, "sk-live-abc"),
    }
    cred = await backend.resolve("cred_1")
    assert cred.type == "static"
    assert cred.api_key == "sk-live-abc"


async def test_resolve_missing_optional_fields_are_none(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "static",
        "api_key": _enc(raw_key, "sk-live"),
    }
    cred = await backend.resolve("cred_1")
    assert cred.access_token is None
    assert cred.refresh_token is None
    assert cred.client_id is None
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# resolve — OAuth credential
# ---------------------------------------------------------------------------

async def test_resolve_oauth_decrypts_all_encrypted_fields(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "access_token": _enc(raw_key, "tok-access"),
        "refresh_token": _enc(raw_key, "tok-refresh"),
        "client_secret": _enc(raw_key, "client-secret"),
        "client_id": "client-id",
        "token_uri": "https://auth.example.com/token",
        "scopes": ["read", "write"],
        "expires_at": _future(),
    }
    cred = await backend.resolve("cred_1")
    assert cred.access_token == "tok-access"
    assert cred.refresh_token == "tok-refresh"
    assert cred.client_secret == "client-secret"
    assert cred.client_id == "client-id"  # plaintext — passed through unchanged
    assert cred.token_uri == "https://auth.example.com/token"
    assert cred.scopes == ["read", "write"]


async def test_resolve_scopes_as_comma_string_parsed(backend):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "scopes": "read, write, admin",
        "expires_at": _future(),
    }
    cred = await backend.resolve("cred_1")
    assert cred.scopes == ["read", "write", "admin"]


async def test_resolve_naive_expires_at_normalized_to_utc(backend):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "expires_at": "2026-04-24T12:00:00",  # no tz
    }
    cred = await backend.resolve("cred_1")
    assert cred.expires_at.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# resolve — extras
# ---------------------------------------------------------------------------

async def test_resolve_encrypted_extra_decrypted_into_extra_dict(backend, raw_key):
    extra_data = {"api_secret": "sk-secret", "account_id": "acct-42"}
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "static",
        "api_key": _enc(raw_key, "pk-live"),
        "encrypted_extra": _enc(raw_key, json.dumps(extra_data)),
    }
    cred = await backend.resolve("cred_1")
    assert cred.extra["api_secret"] == "sk-secret"
    assert cred.extra["account_id"] == "acct-42"


async def test_resolve_plaintext_extra_merged_into_extra_dict(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "static",
        "api_key": _enc(raw_key, "pk-live"),
        "extra": {"region": "us-east-1"},
    }
    cred = await backend.resolve("cred_1")
    assert cred.extra["region"] == "us-east-1"


async def test_resolve_plaintext_extra_wins_on_key_collision(backend, raw_key):
    """extra (plaintext) is merged on top of encrypted_extra, so it takes priority."""
    encrypted_data = {"shared": "from-encrypted", "only_enc": "yes"}
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "static",
        "api_key": _enc(raw_key, "pk-live"),
        "encrypted_extra": _enc(raw_key, json.dumps(encrypted_data)),
        "extra": {"shared": "from-plaintext"},
    }
    cred = await backend.resolve("cred_1")
    assert cred.extra["shared"] == "from-plaintext"
    assert cred.extra["only_enc"] == "yes"


async def test_resolve_no_extras_gives_empty_dict(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "static",
        "api_key": _enc(raw_key, "pk-live"),
    }
    cred = await backend.resolve("cred_1")
    assert cred.extra == {}


# ---------------------------------------------------------------------------
# resolve — token refresh
# ---------------------------------------------------------------------------

async def test_resolve_does_not_refresh_when_not_expired(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "access_token": _enc(raw_key, "tok-valid"),
        "refresh_token": _enc(raw_key, "tok-refresh"),
        "expires_at": _future(hours=2),
    }
    cred = await backend.resolve("cred_1")
    backend._col.update_one.assert_not_called()
    assert cred.access_token == "tok-valid"


async def test_resolve_does_not_refresh_when_no_refresh_token(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "access_token": _enc(raw_key, "tok-expired"),
        "expires_at": _past(),
        # no refresh_token field
    }
    cred = await backend.resolve("cred_1")
    backend._col.update_one.assert_not_called()


async def test_resolve_triggers_refresh_when_expired_and_refresh_token_present(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "access_token": _enc(raw_key, "tok-old"),
        "refresh_token": _enc(raw_key, "tok-refresh"),
        "client_id": "client-id",
        "client_secret": _enc(raw_key, "client-secret"),
        "token_uri": "https://auth.example.com/token",
        "expires_at": _past(),
    }

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "tok-new", "expires_in": 3600}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", MockClient):
        cred = await backend.resolve("cred_1")

    assert cred.access_token == "tok-new"
    assert cred.expires_at is not None


async def test_resolve_refresh_updates_mongodb_with_encrypted_token(backend, raw_key):
    backend._col.find_one.return_value = {
        "credential_id": "cred_1",
        "type": "oauth",
        "access_token": _enc(raw_key, "tok-old"),
        "refresh_token": _enc(raw_key, "tok-refresh"),
        "client_id": "client-id",
        "client_secret": _enc(raw_key, "client-secret"),
        "token_uri": "https://auth.example.com/token",
        "expires_at": _past(),
    }

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"access_token": "tok-new", "expires_in": 3600}

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_response

    MockClient = MagicMock()
    MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", MockClient):
        await backend.resolve("cred_1")

    backend._col.update_one.assert_called_once()
    filter_doc, update_doc = backend._col.update_one.call_args[0]
    assert filter_doc == {"credential_id": "cred_1"}
    assert "access_token" in update_doc["$set"]
    assert "expires_at" in update_doc["$set"]
    # The stored access_token must be ciphertext, not plaintext
    assert update_doc["$set"]["access_token"] != "tok-new"


# ---------------------------------------------------------------------------
# _refresh_token — edge cases
# ---------------------------------------------------------------------------

async def test_refresh_token_missing_token_uri_raises(backend):
    cred = ResolvedCredential(
        type="oauth",
        refresh_token="tok-refresh",
        token_uri=None,
    )
    with pytest.raises(CredentialError, match="missing token_uri"):
        await backend._refresh_token("cred_1", cred)


# ---------------------------------------------------------------------------
# Constructor — motor import error
# ---------------------------------------------------------------------------

def test_constructor_raises_import_error_when_motor_missing(monkeypatch, key_b64):
    with patch.dict(sys.modules, {"motor.motor_asyncio": None}):
        with pytest.raises(ImportError, match="motor"):
            MongoDBCredentialBackend(db_url="mongodb://localhost", encryption_key=key_b64)

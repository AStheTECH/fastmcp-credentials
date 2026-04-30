from __future__ import annotations
import base64
import json
import os
from datetime import datetime, timedelta, timezone
from .base import CredentialBackend
from ..types import ResolvedCredential, CredentialNotFoundError, CredentialError

# Individual fields encrypted as AES-256-GCM values at rest.
# Provider-specific additional fields go in the document's `encrypted_extra` JSON blob.
_ENCRYPTED_FIELDS = frozenset({"access_token", "refresh_token", "client_secret", "api_key"})


class MongoDBCredentialBackend(CredentialBackend):
    """
    MongoDB-backed credential store with AES-256-GCM encryption at rest.

    Stores credential data in a single MongoDB collection. Standard sensitive
    fields are encrypted individually; any provider-specific additional fields
    are stored as an encrypted JSON blob in ``encrypted_extra``.

    Requires the ``hosted`` extra::

        pip install 'fastmcp-credentials[hosted]'

    Required:
        Pass ``encryption_key`` directly, or set the ``CRED_ENCRYPTION_KEY`` env var.
        Generate a key with::

            python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"

    Args:
        db_url:         MongoDB connection string.
        db_name:        Database name. Falls back to ``CRED_DB_NAME`` env var,
                        then ``"credentials"``.
        encryption_key: AES-256 key (32 bytes, base64-encoded). Falls back to
                        ``CRED_ENCRYPTION_KEY`` env var.
        collection:     Collection name (default: ``"credentials"``).

    Document schema::

        {
            "credential_id": "cred_abc123",     # unique index
            "type":          "oauth" | "static",

            # OAuth fields — field names follow RFC 6749 standard names.
            # Providers that use non-standard names should store those in encrypted_extra.
            "access_token":  "<encrypted>",     # AES-256-GCM
            "refresh_token": "<encrypted>",     # AES-256-GCM
            "client_id":     "...",             # plaintext — OAuth client identifier
            "client_secret": "<encrypted>",     # AES-256-GCM
            "token_uri":     "https://...",     # plaintext — token endpoint URL
            "scopes":        ["read", "write"], # plaintext list of granted scopes
            "expires_at":    "2026-04-24T12:00:00+00:00",  # plaintext ISO 8601 UTC

            # Static credentials — primary key
            "api_key":       "<encrypted>",     # AES-256-GCM

            # Provider-specific extras (any auth type):
            # A JSON object encrypted as a single blob. Decrypted values are merged
            # into ResolvedCredential.extra and accessible via cred.extra["field_name"].
            "encrypted_extra": "<encrypted>",  # e.g. {"api_secret": "...", "account_id": "..."}

            # Non-sensitive extras — merged into ResolvedCredential.extra after encrypted_extra.
            # Useful for region, workspace slug, or other non-secret routing data.
            "extra": { "region": "us-east-1" },
        }
    """

    def __init__(
        self,
        db_url: str,
        db_name: str | None = None,
        encryption_key: str | None = None,
        collection: str = "credentials",
    ) -> None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as exc:
            raise ImportError(
                "motor is required for MongoDBCredentialBackend. "
                "Install it with: pip install 'fastmcp-credentials[hosted]'"
            ) from exc

        self._col = AsyncIOMotorClient(db_url)[
            db_name or os.environ.get("CRED_DB_NAME", "credentials")
        ][collection]
        self._key = self._load_key(encryption_key)

    # -- Encryption helpers -----------------------------------------------

    @staticmethod
    def _load_key(key: str | None) -> bytes:
        raw_b64 = key or os.environ.get("CRED_ENCRYPTION_KEY")
        if not raw_b64:
            raise CredentialError(
                "Encryption key is required. Pass encryption_key= or set CRED_ENCRYPTION_KEY env var. "
                'Generate one with: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
            )
        decoded = base64.b64decode(raw_b64)
        if len(decoded) != 32:
            raise CredentialError("Encryption key must be exactly 32 bytes (256 bits), base64-encoded.")
        return decoded

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt with AES-256-GCM. Returns base64(nonce || ciphertext || tag)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = os.urandom(12)
        ct = AESGCM(self._key).encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()

    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt AES-256-GCM value produced by _encrypt."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.b64decode(ciphertext)
        nonce, ct = raw[:12], raw[12:]
        return AESGCM(self._key).decrypt(nonce, ct, None).decode()

    # -- Public interface -------------------------------------------------

    async def resolve(self, credential_id: str) -> ResolvedCredential:
        doc = await self._col.find_one({"credential_id": credential_id})
        if not doc:
            raise CredentialNotFoundError(credential_id)

        doc = dict(doc)
        for f in _ENCRYPTED_FIELDS:
            if doc.get(f):
                doc[f] = self._decrypt(doc[f])

        # Decrypt the extras blob, then merge plaintext extras on top
        extra: dict = {}
        if raw_extra := doc.get("encrypted_extra"):
            extra = json.loads(self._decrypt(raw_extra))
        if plaintext_extra := doc.get("extra"):
            if isinstance(plaintext_extra, dict):
                extra = {**extra, **plaintext_extra}

        expires_at: datetime | None = None
        if raw := doc.get("expires_at"):
            expires_at = datetime.fromisoformat(raw) if isinstance(raw, str) else raw
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

        scopes = doc.get("scopes")
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split(",") if s.strip()]

        cred = ResolvedCredential(
            type=doc.get("type", "oauth"),
            access_token=doc.get("access_token"),
            refresh_token=doc.get("refresh_token"),
            client_id=doc.get("client_id"),
            client_secret=doc.get("client_secret"),
            token_uri=doc.get("token_uri"),
            scopes=scopes,
            expires_at=expires_at,
            api_key=doc.get("api_key"),
            extra=extra,
        )

        if cred.type == "oauth" and cred.is_expired() and cred.refresh_token:
            cred = await self._refresh_token(credential_id, cred)

        return cred

    async def _refresh_token(self, credential_id: str, cred: ResolvedCredential) -> ResolvedCredential:
        """Call the OAuth token endpoint and persist the new encrypted access token."""
        try:
            import httpx
        except ImportError as exc:
            raise ImportError(
                "httpx is required for token refresh. "
                "Install it with: pip install 'fastmcp-credentials[hosted]'"
            ) from exc

        if not cred.token_uri:
            raise CredentialError(f"Cannot refresh token for credential_id={credential_id}: missing token_uri")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                cred.token_uri,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": cred.refresh_token,
                    "client_id": cred.client_id,
                    "client_secret": cred.client_secret,
                },
            )
            resp.raise_for_status()
            token_data = resp.json()

        new_access_token: str = token_data["access_token"]
        expires_in: int = token_data.get("expires_in", 3600)
        new_expires_at = datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in)

        await self._col.update_one(
            {"credential_id": credential_id},
            {"$set": {
                "access_token": self._encrypt(new_access_token),
                "expires_at": new_expires_at.isoformat(),
            }},
        )

        cred.access_token = new_access_token
        cred.expires_at = new_expires_at
        return cred

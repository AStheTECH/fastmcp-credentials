from __future__ import annotations
import os
from datetime import datetime, timezone
from .base import CredentialBackend
from ..types import ResolvedCredential, CredentialError


class EnvCredentialBackend(CredentialBackend):
    """
    Reads credentials from environment variables.

    Intended for open-source / local development use — no database or
    cloud dependency required. Set a prefix to namespace your env vars:

        backend = EnvCredentialBackend(prefix="MYSERVICE_")

    Then set env vars like:

    For static auth — default:
        MYSERVICE_API_KEY=sk-...
        # MYSERVICE_CRED_TYPE=static  (this is the default, no need to set)

    For OAuth:
        MYSERVICE_CRED_TYPE=oauth
        MYSERVICE_ACCESS_TOKEN=...
        MYSERVICE_REFRESH_TOKEN=...
        MYSERVICE_CLIENT_ID=...
        MYSERVICE_CLIENT_SECRET=...
        MYSERVICE_TOKEN_URI=https://auth.example.com/token
        MYSERVICE_SCOPES=read,write

    For any auth type, provider-specific extra fields can be added with
    the EXTRA_ prefix — they are collected into cred.extra:
        MYSERVICE_EXTRA_ACCOUNT_ID=acct_42
        MYSERVICE_EXTRA_WORKSPACE=my-workspace
        # → cred.extra["account_id"], cred.extra["workspace"]

    """

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix.upper()

    def _get(self, key: str) -> str | None:
        return os.environ.get(f"{self.prefix}{key}")

    def _collect_extra(self) -> dict[str, str]:
        """Collect all {PREFIX}EXTRA_{NAME} vars into a lowercased dict."""
        extra_prefix = f"{self.prefix}EXTRA_"
        return {
            k[len(extra_prefix):].lower(): v
            for k, v in os.environ.items()
            if k.startswith(extra_prefix)
        }

    async def resolve(self) -> ResolvedCredential:
        # ``async def`` satisfies the CredentialBackend ABC contract shared with
        # network-based backends. All reads here are synchronous os.environ
        # lookups — effectively instant, no I/O — so awaiting is not needed.
        p = self.prefix
        cred_type = (os.environ.get(f"{p}CRED_TYPE") or "static").lower()
        extra = self._collect_extra()

        if cred_type == "static":
            api_key = os.environ.get(f"{p}API_KEY")
            if not api_key:
                raise CredentialError(f"Missing env var: {p}API_KEY")
            return ResolvedCredential(type="static", api_key=api_key, extra=extra)

        # OAuth
        scopes_raw = os.environ.get(f"{p}SCOPES", "")
        scopes = [s.strip() for s in scopes_raw.split(",") if s.strip()] or None

        expires_at: datetime | None = None
        if raw := os.environ.get(f"{p}EXPIRES_AT"):
            expires_at = datetime.fromisoformat(raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

        return ResolvedCredential(
            type="oauth",
            access_token=os.environ.get(f"{p}ACCESS_TOKEN"),
            refresh_token=os.environ.get(f"{p}REFRESH_TOKEN"),
            client_id=os.environ.get(f"{p}CLIENT_ID"),
            client_secret=os.environ.get(f"{p}CLIENT_SECRET"),
            token_uri=os.environ.get(f"{p}TOKEN_URI"),
            scopes=scopes,
            expires_at=expires_at,
            extra=extra,
        )

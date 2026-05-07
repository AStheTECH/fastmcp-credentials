from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from typing import Literal
from .base import CredentialBackend
from ..types import ResolvedCredential, CredentialError


class EnvCredentialBackend(CredentialBackend):
    """
    Reads credentials from environment variables.

    Intended for open-source / local development use — no database or
    cloud dependency required. Set a prefix to namespace your env vars:

        backend = EnvCredentialBackend(prefix="MYSERVICE_")

    The auth type is declared in code via CredentialMiddleware, not read from env vars.

    For static auth:
        # Option 1 — JSON object (recommended for multi-field providers):
        MYSERVICE_FIELDS={"keyId":"rz_live_...","keySecret":"..."}

        # Option 2 — individual FIELD_<name> vars (useful when values come
        # from a secrets manager that injects one env var per secret):
        MYSERVICE_FIELD_keyId=rz_live_...
        MYSERVICE_FIELD_keySecret=...

    For OAuth:
        MYSERVICE_ACCESS_TOKEN=...
        MYSERVICE_REFRESH_TOKEN=...
        MYSERVICE_CLIENT_ID=...
        MYSERVICE_CLIENT_SECRET=...
        MYSERVICE_TOKEN_URI=https://auth.example.com/token
        MYSERVICE_SCOPES=read write

    OAuth provider metadata can be added with the EXTRA_ prefix:
        MYSERVICE_EXTRA_DC=us10
        MYSERVICE_EXTRA_WORKSPACE=my-workspace
        # → cred.extra["dc"], cred.extra["workspace"]
    """

    def __init__(self, prefix: str = "") -> None:
        self.prefix = prefix.upper()

    def _get(self, key: str) -> str | None:
        return os.environ.get(f"{self.prefix}{key}")

    def _collect_oauth_extra(self) -> dict[str, str]:
        """Collect {PREFIX}EXTRA_{NAME} vars into a lowercased dict (OAuth metadata)."""
        extra_prefix = f"{self.prefix}EXTRA_"
        return {
            k[len(extra_prefix):].lower(): v
            for k, v in os.environ.items()
            if k.startswith(extra_prefix)
        }

    def _collect_static_fields(self) -> dict[str, str]:
        """
        Collect static credential fields in priority order:
        1. PREFIX_FIELDS (JSON object)
        2. PREFIX_FIELD_<name> individual vars (key name preserved as-is)
        """
        p = self.prefix

        # 1. JSON blob
        fields_json = os.environ.get(f"{p}FIELDS")
        if fields_json:
            try:
                parsed = json.loads(fields_json)
                if isinstance(parsed, dict):
                    return {str(k): str(v) for k, v in parsed.items()}
            except json.JSONDecodeError:
                raise CredentialError(
                    f"Invalid JSON in {p}FIELDS. "
                    "Value must be a JSON object, e.g. "
                    '\'{"keyId":"...","keySecret":"..."}\'.'
                )

        # 2. Individual FIELD_* vars
        field_prefix = f"{p}FIELD_"
        individual = {
            k[len(field_prefix):]: v
            for k, v in os.environ.items()
            if k.startswith(field_prefix)
        }
        if individual:
            return individual

        return {}

    async def resolve(self, credential_type: Literal["static", "oauth"]) -> ResolvedCredential:
        p = self.prefix

        if credential_type == "static":
            fields = self._collect_static_fields()
            if not fields:
                raise CredentialError(
                    f"No static credentials found. "
                    f"Set {p}FIELDS (JSON object) or individual {p}FIELD_<name> env vars."
                )
            return ResolvedCredential(type="static", fields=fields)

        # OAuth
        scopes_raw = os.environ.get(f"{p}SCOPES", "")
        scopes = [s.strip() for s in scopes_raw.split() if s.strip()] or None

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
            extra=self._collect_oauth_extra(),
        )

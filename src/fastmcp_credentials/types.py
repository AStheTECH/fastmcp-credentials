from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal


@dataclass
class ResolvedCredential:
    """Fully resolved, decrypted credential ready for use in a tool."""

    type: Literal["static", "oauth"]

    # OAuth fields
    access_token: str | None = None
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    token_uri: str | None = None
    scopes: list[str] | None = None
    expires_at: datetime | None = None

    # Static (API key / PAT) fields
    api_key: str | None = None

    # Escape hatch for provider-specific extras
    extra: dict = field(default_factory=dict)

    def is_expired(self) -> bool:
        """True if the access token has expired (or expires within 60 s)."""
        if not self.expires_at:
            return False
        now = datetime.now(tz=timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return now >= exp - timedelta(seconds=60)


class CredentialError(Exception):
    """Raised when credentials cannot be resolved or are invalid."""


class CredentialNotFoundError(CredentialError):
    def __init__(self, credential_id: str) -> None:
        super().__init__(f"Credential not found: {credential_id!r}")
        self.credential_id = credential_id

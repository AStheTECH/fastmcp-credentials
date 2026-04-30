from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from .base import CredentialBackend
from ..types import ResolvedCredential, CredentialNotFoundError


class FileCredentialBackend(CredentialBackend):
    """
    Reads credentials from a local JSON file.

    Supports two formats:

    1. Flat (single credential):
       { "type": "oauth", "access_token": "...", ... }

    2. Keyed (multiple credentials):
       { "cred_abc123": { "type": "oauth", "access_token": "..." }, ... }
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def resolve(self, credential_id: str) -> ResolvedCredential:
        with self.path.open() as fh:
            data: dict = json.load(fh)

        # Keyed format — look up by credential_id
        if credential_id in data and isinstance(data[credential_id], dict):
            cred_data = data[credential_id]
        # Flat format — use the whole file
        elif "type" in data:
            cred_data = data
        else:
            raise CredentialNotFoundError(credential_id)

        return self._from_dict(cred_data)

    @staticmethod
    def _from_dict(d: dict) -> ResolvedCredential:
        expires_at: datetime | None = None
        if raw := d.get("expires_at"):
            expires_at = datetime.fromisoformat(raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

        scopes = d.get("scopes")
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split(",") if s.strip()]

        return ResolvedCredential(
            type=d.get("type", "oauth"),
            access_token=d.get("access_token"),
            refresh_token=d.get("refresh_token"),
            client_id=d.get("client_id"),
            client_secret=d.get("client_secret"),
            token_uri=d.get("token_uri"),
            scopes=scopes,
            expires_at=expires_at,
            api_key=d.get("api_key"),
            extra=d.get("extra", {}),
        )

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from typing import Any, Literal, cast

from fastmcp.server.dependencies import get_http_request

from .base import CredentialBackend
from ..types import ResolvedCredential, MissingCredentialHeaderError

logger = logging.getLogger(__name__)

_HEADER_ACCESS_TOKEN = "X-MCP-Cred-Access-Token"
_HEADER_FIELDS = "X-MCP-Cred-Fields"
_HEADER_SCOPES = "X-MCP-Cred-Scopes"
_HEADER_EXTRA = "X-MCP-Cred-Extra"
_HEADER_EXPIRES_AT = "X-MCP-Cred-Expires-At"


class HeaderCredentialBackend(CredentialBackend):
    """
    Reads credentials from HTTP request headers injected by the gateway (hosted mode).

    No database, no encryption, no token refresh — the gateway is the authority.
    The gateway decrypts, refreshes if needed, then injects only the resolved
    fields into outbound headers before forwarding the request to this MCP server.

    The credential type is declared by the developer in CredentialMiddleware, not
    inferred from headers at runtime.

    For ``credential_type="oauth"``:
        X-MCP-Cred-Access-Token  — required; OAuth access token
        X-MCP-Cred-Scopes        — optional; space-separated or JSON-array
        X-MCP-Cred-Extra         — optional; JSON object of OAuth provider metadata
        X-MCP-Cred-Expires-At    — optional; ISO 8601 UTC expiration timestamp

    For ``credential_type="static"``:
        X-MCP-Cred-Fields        — required; JSON object of all static fields
                                   e.g. {"keyId":"rz_live_...","keySecret":"..."}
    """

    async def resolve(self, credential_type: Literal["static", "oauth"]) -> ResolvedCredential:
        request = get_http_request()

        if credential_type == "static":
            if request is None:
                raise MissingCredentialHeaderError([_HEADER_FIELDS])
            fields_raw = request.headers.get(_HEADER_FIELDS)
            if not fields_raw:
                raise MissingCredentialHeaderError([_HEADER_FIELDS])
            logger.debug("HeaderCredentialBackend: resolved static credential from headers")
            return ResolvedCredential(
                type="static",
                fields=_parse_fields(fields_raw),
            )

        # oauth
        if request is None:
            raise MissingCredentialHeaderError([_HEADER_ACCESS_TOKEN])
        headers = request.headers
        access_token = headers.get(_HEADER_ACCESS_TOKEN)
        if not access_token:
            raise MissingCredentialHeaderError([_HEADER_ACCESS_TOKEN])
        logger.debug("HeaderCredentialBackend: resolved oauth credential from headers")
        return ResolvedCredential(
            type="oauth",
            access_token=access_token,
            scopes=_parse_scopes(headers.get(_HEADER_SCOPES)),
            expires_at=_parse_expires_at(headers.get(_HEADER_EXPIRES_AT)),
            extra=_parse_json_header(_HEADER_EXTRA, headers.get(_HEADER_EXTRA)),
        )


def _parse_fields(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except json.JSONDecodeError:
        pass
    logger.warning(
        "HeaderCredentialBackend: could not parse %s as JSON object, ignoring",
        _HEADER_FIELDS,
    )
    return {}


def _parse_scopes(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            return [s for s in parsed if s]
        except json.JSONDecodeError:
            pass
    return [s.strip() for s in raw.split(" ") if s.strip()] or None


def _parse_json_header(name: str, raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return cast(dict[str, Any], parsed)
    except json.JSONDecodeError:
        logger.warning(
            "HeaderCredentialBackend: could not parse %s as JSON, ignoring", name
        )
        return {}


def _parse_expires_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        logger.warning(
            "HeaderCredentialBackend: invalid %s %r, ignoring", _HEADER_EXPIRES_AT, raw
        )
        return None

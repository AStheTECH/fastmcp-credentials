from __future__ import annotations
import base64
import json
import logging
from datetime import datetime, timezone

from fastmcp.server.dependencies import get_http_request

from .base import CredentialBackend
from ..types import ResolvedCredential, MissingCredentialHeaderError

logger = logging.getLogger(__name__)

_HEADER_ACCESS_TOKEN = "X-MCP-Cred-Access-Token"
_HEADER_API_KEY = "X-MCP-Cred-Api-Key"
_HEADER_SCOPES = "X-MCP-Cred-Scopes"
_HEADER_EXTRA = "X-MCP-Cred-Extra"
_HEADER_EXPIRES_AT = "X-MCP-Cred-Expires-At"


class HeaderCredentialBackend(CredentialBackend):
    """
    Reads credentials from HTTP request headers injected by the gateway (hosted mode).

    No database, no encryption, no token refresh — the gateway is the authority.
    The gateway decrypts, refreshes if needed, then injects only the resolved
    fields into outbound headers before forwarding the request to this MCP server.

    Required headers (at least one must be present):
        X-MCP-Cred-Access-Token  — OAuth access token
        X-MCP-Cred-Api-Key       — Static API key / PAT

    Optional headers:
        X-MCP-Cred-Scopes      — CSV ("read,write") or JSON array ("["read","write"]")
        X-MCP-Cred-Extra       — JSON object or base64-encoded JSON with provider-specific fields
        X-MCP-Cred-Expires-At  — ISO 8601 UTC expiration timestamp

    Raises MissingCredentialHeaderError if neither token header is present.
    """

    async def resolve(self) -> ResolvedCredential:
        request = get_http_request()
        if request is None:
            raise MissingCredentialHeaderError([_HEADER_ACCESS_TOKEN, _HEADER_API_KEY])

        headers = request.headers

        access_token = headers.get(_HEADER_ACCESS_TOKEN)
        api_key = headers.get(_HEADER_API_KEY)

        if not access_token and not api_key:
            raise MissingCredentialHeaderError([_HEADER_ACCESS_TOKEN, _HEADER_API_KEY])

        scopes = _parse_scopes(headers.get(_HEADER_SCOPES))
        extra = _parse_extra(headers.get(_HEADER_EXTRA))
        expires_at = _parse_expires_at(headers.get(_HEADER_EXPIRES_AT))

        if access_token:
            logger.debug(
                "HeaderCredentialBackend: resolved oauth credential from headers"
            )
            return ResolvedCredential(
                type="oauth",
                access_token=access_token,
                scopes=scopes,
                expires_at=expires_at,
                extra=extra,
            )

        logger.debug("HeaderCredentialBackend: resolved static credential from headers")
        return ResolvedCredential(
            type="static",
            api_key=api_key,
            extra=extra,
        )


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
    return [s.strip() for s in raw.split(",") if s.strip()] or None


def _parse_extra(raw: str | None) -> dict:
    if not raw:
        return {}
    raw = raw.strip()
    # Try plain JSON first
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    # Try base64-encoded JSON
    try:
        decoded = base64.b64decode(raw + "==").decode("utf-8")
        return json.loads(decoded)
    except Exception:
        logger.warning(
            "HeaderCredentialBackend: could not parse X-MCP-Cred-Extra, ignoring"
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
            "HeaderCredentialBackend: invalid X-MCP-Cred-Expires-At %r, ignoring", raw
        )
        return None

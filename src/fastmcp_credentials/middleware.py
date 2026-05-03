from __future__ import annotations
import logging
from contextvars import ContextVar
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.dependencies import get_http_request

from .backends.base import CredentialBackend
from .backends.headers import HeaderCredentialBackend
from .types import ResolvedCredential

logger = logging.getLogger(__name__)

# Request-scoped store. Set by CredentialMiddleware before each tool call,
# read by get_credentials(). Never touches tool parameters or LLM context.
_current_credential: ContextVar[ResolvedCredential | None] = ContextVar(
    "_fastmcp_credential", default=None
)


class CredentialMiddleware(Middleware):
    """
    FastMCP middleware that resolves credentials before every tool call.

    Reads the credential ID from an HTTP header (default: ``X-Credential-ID``),
    resolves it via the configured backend, and stores the result in a
    ``ContextVar`` scoped to the current tool invocation. After the tool
    returns (or raises), the ``ContextVar`` is always reset in a ``finally``
    block so credentials never leak between concurrent requests.

    Tools retrieve the credential with :func:`get_credentials` — a plain
    synchronous function, no ``await``, no ``ctx`` parameter required.
    The LLM never sees any credential data; it is invisible to the MCP schema.

    Example (env-based, local / self-hosted)::

        backend = EnvCredentialBackend(prefix="MYSERVICE_")
        mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend)])

    Example (MongoDB-backed, hosted deployments)::

        backend = MongoDBCredentialBackend(db_url=os.environ["DB_URL"])
        mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend)])

    Args:
        backend: Any :class:`CredentialBackend` implementation.
        header:  HTTP header name carrying the credential ID
                 (default: ``"X-Credential-ID"``).
    """

    def __init__(
        self,
        backend: CredentialBackend,
        header: str = "X-Credential-ID",
    ) -> None:
        self.backend = backend
        self.header = header

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        request = get_http_request()
        credential_id: str | None = request.headers.get(self.header) if request else None

        # HeaderCredentialBackend doesn't need X-Credential-ID — it reads from request headers directly
        if isinstance(self.backend, HeaderCredentialBackend):
            logger.debug("Resolving credentials from request headers (HeaderCredentialBackend)")
            try:
                creds = await self.backend.resolve()
                token = _current_credential.set(creds)
                try:
                    return await call_next(context)
                finally:
                    _current_credential.reset(token)
            except Exception:
                # If credential resolution fails, let the error propagate
                raise

        # For other backends, require X-Credential-ID header
        if not credential_id:
            logger.debug(
                "No %s header present — proceeding without credential injection. "
                "Calls to get_credentials() will raise CredentialError.",
                self.header,
            )
            return await call_next(context)

        logger.debug("Resolving credential_id=%r via %s", credential_id, type(self.backend).__name__)
        creds = await self.backend.resolve(credential_id)

        token = _current_credential.set(creds)
        try:
            return await call_next(context)
        finally:
            _current_credential.reset(token)

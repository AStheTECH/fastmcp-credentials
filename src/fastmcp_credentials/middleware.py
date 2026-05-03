from __future__ import annotations
import logging
from contextvars import ContextVar
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext

from .backends.base import CredentialBackend
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

    Resolves credentials via the configured backend and stores the result in a
    ``ContextVar`` scoped to the current tool invocation. After the tool
    returns (or raises), the ``ContextVar`` is always reset in a ``finally``
    block so credentials never leak between concurrent requests.

    Tools retrieve the credential with :func:`get_credentials` — a plain
    synchronous function, no ``await``, no ``ctx`` parameter required.
    The LLM never sees any credential data; it is invisible to the MCP schema.

    Example (env-based, local / self-hosted)::

        backend = EnvCredentialBackend(prefix="MYSERVICE_")
        mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend)])

    Example (header-based, gateway-injected credentials)::

        backend = HeaderCredentialBackend()
        mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend)])

    Args:
        backend: Either :class:`EnvCredentialBackend` or :class:`HeaderCredentialBackend`.
    """

    def __init__(self, backend: CredentialBackend) -> None:
        self.backend = backend

    async def on_call_tool(self, context: MiddlewareContext, call_next: Any) -> Any:
        logger.debug("Resolving credentials via %s", type(self.backend).__name__)
        try:
            creds = await self.backend.resolve()
            token = _current_credential.set(creds)
            try:
                return await call_next(context)
            finally:
                _current_credential.reset(token)
        except Exception:
            logger.error("Credential resolution failed", exc_info=True)
            raise

"""
fastmcp-credentials
===================
Secure credential injection middleware for FastMCP servers.

Keeps secrets completely out of the LLM — credentials travel in HTTP headers,
are resolved server-side, and are injected into tools via a ContextVar.

OSS / local mode (env vars, no gateway):

    from fastmcp_credentials import CredentialMiddleware, EnvCredentialBackend, get_credentials

    backend = EnvCredentialBackend(prefix="MY_SERVICE_")
    mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend, "static")])

Hosted mode (gateway injects credentials as headers):

    from fastmcp_credentials import CredentialMiddleware, HeaderCredentialBackend, get_credentials

    backend = HeaderCredentialBackend()
    mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend, "oauth")])

In both modes, tools retrieve credentials identically:

    @mcp.tool()
    def call_api(query: str) -> str:
        creds = get_credentials()
        return requests.get(url, headers={"Authorization": f"Bearer {creds.access_token}"}).text
"""

from .types import (
    ResolvedCredential,
    CredentialError,
    CredentialNotFoundError,
    MissingCredentialHeaderError,
)
from .middleware import CredentialMiddleware
from .helpers import get_credentials
from .config import CredentialMode, get_mode
from .backends import (
    CredentialBackend,
    EnvCredentialBackend,
    HeaderCredentialBackend,
)

__all__ = [
    "ResolvedCredential",
    "CredentialError",
    "CredentialNotFoundError",
    "MissingCredentialHeaderError",
    "CredentialMiddleware",
    "get_credentials",
    "CredentialMode",
    "get_mode",
    "CredentialBackend",
    "EnvCredentialBackend",
    "HeaderCredentialBackend",
]

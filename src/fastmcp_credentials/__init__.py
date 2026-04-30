"""
fastmcp-credentials
===================
Secure credential injection middleware for FastMCP servers.

Keeps secrets completely out of the LLM — credentials travel in HTTP headers,
are resolved server-side, and are injected into tools via a ContextVar.

Quick start:

    from fastmcp import FastMCP
    from fastmcp_credentials import CredentialMiddleware, EnvCredentialBackend, get_credentials

    backend = EnvCredentialBackend(prefix="MY_SERVICE_")
    mcp = FastMCP("My Server", middleware=[CredentialMiddleware(backend)])

    @mcp.tool()
    def call_api(query: str) -> str:
        creds = get_credentials()           # resolved from X-Credential-ID header
        return requests.get(url, headers={"Authorization": f"Bearer {creds.access_token}"}).text
"""

from .types import ResolvedCredential, CredentialError, CredentialNotFoundError
from .middleware import CredentialMiddleware
from .helpers import get_credentials
from .backends import (
    CredentialBackend,
    EnvCredentialBackend,
    FileCredentialBackend,
    MongoDBCredentialBackend,
)

__all__ = [
    "ResolvedCredential",
    "CredentialError",
    "CredentialNotFoundError",
    "CredentialMiddleware",
    "get_credentials",
    "CredentialBackend",
    "EnvCredentialBackend",
    "FileCredentialBackend",
    "MongoDBCredentialBackend",
]

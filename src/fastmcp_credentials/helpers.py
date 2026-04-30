from __future__ import annotations
from .middleware import _current_credential
from .types import ResolvedCredential, CredentialError


def get_credentials() -> ResolvedCredential:
    """
    Return the credential resolved for the current tool call.

    This is a plain synchronous function — no await, no ctx parameter.
    Call it at the top of any tool that needs to authenticate:

        @mcp.tool()
        def list_files(folder_id: str) -> list:
            creds = get_credentials()
            service = build_drive_service(creds)
            ...

    Raises CredentialError if called outside a tool context or when no
    X-Credential-ID header was present in the request.
    """
    creds = _current_credential.get()
    if creds is None:
        raise CredentialError(
            "No credential has been resolved for this request. "
            "Ensure CredentialMiddleware is registered on your FastMCP server "
            "and that the request includes the X-Credential-ID header."
        )
    return creds

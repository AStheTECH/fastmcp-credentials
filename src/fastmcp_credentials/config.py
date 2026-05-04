from __future__ import annotations
import os
from enum import Enum


class CredentialMode(Enum):
    HOSTED = "hosted"  # Header-only
    OSS = "oss"  # Env  for local and self-hosted deployments


def get_mode() -> CredentialMode:
    """
    Read credential mode from FASTMCP_CREDENTIAL_MODE env var.

    Defaults to "oss" so existing deployments are unaffected.
    Set FASTMCP_CREDENTIAL_MODE=hosted in production MCP servers running behind the gateway.
    """
    raw = os.environ.get("FASTMCP_CREDENTIAL_MODE", "oss").strip().lower()
    try:
        return CredentialMode(raw)
    except ValueError:
        raise ValueError(
            f"Invalid FASTMCP_CREDENTIAL_MODE={raw!r}. "
            f"Valid values: {[m.value for m in CredentialMode]}"
        )

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Literal
from ..types import ResolvedCredential


class CredentialBackend(ABC):
    """
    Abstract interface for credential resolution.

    Implement this to plug in any credential source:
    environment variables (``EnvCredentialBackend``) or gateway-injected HTTP headers
    (``HeaderCredentialBackend``).
    """

    @abstractmethod
    async def resolve(self, credential_type: Literal["static", "oauth"]) -> ResolvedCredential:
        """Return fully resolved (decrypted) credentials for the declared auth type."""
        ...

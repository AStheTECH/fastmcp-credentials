from __future__ import annotations
from abc import ABC, abstractmethod
from ..types import ResolvedCredential


class CredentialBackend(ABC):
    """
    Abstract interface for credential resolution.

    Implement this to plug in any credential source:
    environment variables (``EnvCredentialBackend``) or gateway-injected HTTP headers
    (``HeaderCredentialBackend``).
    """

    @abstractmethod
    async def resolve(self) -> ResolvedCredential:
        """Return fully resolved (decrypted) credentials."""
        ...

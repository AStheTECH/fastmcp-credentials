from __future__ import annotations
from abc import ABC, abstractmethod
from ..types import ResolvedCredential


class CredentialBackend(ABC):
    """
    Abstract interface for credential resolution.

    Implement this to plug in any secret store:
    environment variables, local files, MongoDB, AWS Secrets Manager, etc.
    """

    @abstractmethod
    async def resolve(self) -> ResolvedCredential:
        """Return fully resolved (decrypted) credentials."""
        ...

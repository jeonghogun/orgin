"""
Core module for secrets management.

This provides an abstraction layer for retrieving secrets, allowing the application
to be agnostic about the secret's source (e.g., environment variables, file, cloud secret manager).
"""
from typing import Protocol, Optional
from app.config.settings import settings

class SecretProvider(Protocol):
    """A protocol for any class that provides secrets."""
    def get(self, key: str) -> Optional[str]:
        ...

class EnvSecrets(SecretProvider):
    """
    A SecretProvider that retrieves secrets from the application's Pydantic settings,
    which are loaded from environment variables or a .env file.
    """
    def get(self, key: str) -> Optional[str]:
        """Gets a secret from the application settings."""
        return getattr(settings, key, None)

# Default provider instance
env_secrets_provider = EnvSecrets()

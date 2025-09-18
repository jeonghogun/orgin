"""Core module for secrets management."""

import os
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
        """Gets a secret from the application settings with environment fallback."""

        value = getattr(settings, key, None)
        if value is not None:
            return value
        return os.getenv(key)

# Default provider instance
env_secrets_provider = EnvSecrets()


def get_secret_provider() -> SecretProvider:
    """Return the global secret provider instance."""
    return env_secrets_provider

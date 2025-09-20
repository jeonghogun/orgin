"""Runtime checks executed during FastAPI startup."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List

from app.config.settings import settings
from app.core.errors import LLMError
from app.services.database_service import get_database_service
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)


async def run_startup_checks() -> None:
    """Run a suite of lightweight health checks before the app starts serving."""

    errors: List[str] = []

    await _verify_database(errors)
    _verify_llm_provider(errors)

    if not errors:
        logger.info("Startup configuration verified successfully.")
        return

    for message in errors:
        logger.error("Startup check failed: %s", message)

    raise RuntimeError(
        "Startup validation failed; see log messages above for detailed diagnostics."
    )


async def _verify_database(errors: List[str]) -> None:
    """Ensure the configured database is reachable and responsive."""

    if settings.TESTING or os.getenv("PYTEST_CURRENT_TEST"):
        logger.info("Startup check skipping database validation in testing mode.")
        return

    def _check() -> None:
        try:
            database_service = get_database_service()
            with database_service.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        except Exception as exc:  # pragma: no cover - defensive logging
            errors.append(
                "Database connectivity check failed: "
                f"{exc}. Confirm DATABASE_URL and DB_ENCRYPTION_KEY are configured."
            )

    await asyncio.to_thread(_check)


def _verify_llm_provider(errors: List[str]) -> None:
    """Ensure at least one LLM provider is available when mocks are disabled."""

    if settings.MOCK_LLM:
        logger.info("Startup check skipping LLM provider validation because MOCK_LLM is enabled.")
        return

    try:
        llm_service = get_llm_service()
        provider_name = settings.LLM_PROVIDER
        llm_service.get_provider(provider_name)
    except LLMError as exc:
        errors.append(
            "LLM provider check failed: "
            f"{exc.error_message}"
        )
    except Exception as exc:  # pragma: no cover - defensive logging
        errors.append(
            "Unexpected error while verifying LLM provider configuration: "
            f"{exc}"
        )

"""Application configuration powered by Pydantic settings."""

import logging
import os
from typing import Optional, Dict, Any
from urllib.parse import urlparse, urlunparse

from pydantic import model_validator, PostgresDsn, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)

DEFAULT_TEST_DB_ENCRYPTION_KEY = "test-encryption-key-32-bytes-long"


_ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
_ENV_FILE = ".env" if _ENVIRONMENT not in {"production", "prod"} else None


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, case_sensitive=True)

    # --- Database Configuration ---
    # Allow DATABASE_URL to be optional now
    DATABASE_URL: Optional[PostgresDsn] = None
    # Add individual Postgres variables
    POSTGRES_HOST: str = "localhost"  # Default for local development
    POSTGRES_PORT: int = 6432  # pgbouncer port
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[str] = None
    POSTGRES_DB: Optional[str] = None
    DB_ENCRYPTION_KEY: str  # No default, must be loaded from env

    @model_validator(mode='before')
    @classmethod
    def assemble_db_connection(cls, v: Any) -> Any:
        if isinstance(v, dict) and 'DATABASE_URL' not in v:
            # If DATABASE_URL is not provided, build it from components
            user = v.get("POSTGRES_USER")
            password = v.get("POSTGRES_PASSWORD")
            host = v.get("POSTGRES_HOST", "localhost")
            port = v.get("POSTGRES_PORT", 6432)
            db = v.get("POSTGRES_DB")
            if all([user, password, host, port, db]):
                v['DATABASE_URL'] = str(PostgresDsn.build(
                    scheme="postgresql",
                    username=user,
                    password=password,
                    host=host,
                    port=int(port),
                    path=f"{db}",
                ))
        return v

    # --- General API Configuration ---
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    DEBUG: bool = False
    EXPOSE_DEBUG_ENDPOINTS: bool = False
    TESTING: bool = False
    CORS_ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173,http://127.0.0.1:5173"

    # --- Authentication ---
    # Defaulting to True is a security risk. Should be False by default.
    AUTH_OPTIONAL: bool = False
    WS_CLIENT_ID_OPTIONAL: bool = True  # Added this field

    # --- LLM Configuration ---
    MOCK_LLM: bool = False
    LLM_MODEL: str = "gpt-4o"
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    FORCE_DEFAULT_PROVIDER: bool = False
    LLM_TIMEOUT: float = 30.0
    LLM_MAX_RETRIES: int = 3
    LLM_BASE_DELAY: float = 1.0
    LLM_MAX_DELAY: float = 60.0
    LLM_CIRCUIT_BREAKER_THRESHOLD: int = 5
    LLM_CIRCUIT_BREAKER_TIMEOUT: float = 60.0
    LLM_EXPONENTIAL_BASE: float = 2.0
    LLM_JITTER_FACTOR: float = 0.25

    # --- Conversation Feature Flag ---
    ENABLE_CONVERSATION: bool = True

    # --- Hybrid Retrieval Configuration ---
    RAG_BM25_WEIGHT: float = 0.55
    RAG_VEC_WEIGHT: float = 0.45
    RAG_TIME_DECAY: float = 0.03
    HYBRID_TOPK_BM25: int = 50
    HYBRID_TOPK_VEC: int = 50
    HYBRID_RETURN_TOPN: int = 20
    TIME_DECAY_ENABLED: bool = True # This seems redundant now, but we'll keep for compatibility
    TIME_DECAY_LAMBDA: float = 0.03 # This seems redundant now

    # --- Re-ranker Configuration ---
    RERANK_ENABLED: bool = False
    RERANK_PROVIDER: str = "cohere"  # "openai" or "cohere"
    RERANK_TOP: int = 20

    # --- Frontend Configuration ---
    VITE_API_BASE_URL: Optional[str] = None
    VITE_WS_BASE_URL: Optional[str] = None

    # --- Redis & Celery ---
    REDIS_URL: Optional[str] = None  # Will be set from environment
    CELERY_BROKER_URL: Optional[str] = None  # Will be set from environment
    CELERY_RESULT_BACKEND: Optional[str] = None  # Will be set from environment

    # --- External APIs ---
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # --- Firebase Configuration ---
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None

    # --- APM / Observability Configuration ---
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = None # e.g., http://localhost:4318
    NEW_RELIC_LICENSE_KEY: Optional[str] = None
    NEW_RELIC_APP_NAME: str = "origin-api"
    DATADOG_API_KEY: Optional[str] = None
    DATADOG_APP_KEY: Optional[str] = None
    DATADOG_SERVICE: str = "origin-api"

    # --- Security Configuration ---
    ENCRYPTION_KEY: Optional[str] = None
    API_KEY_ROTATION_INTERVAL: int = 86400  # 24 hours in seconds
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_DURATION: int = 900  # 15 minutes in seconds

    # --- Monitoring Configuration ---
    ENABLE_METRICS: bool = True
    ENABLE_TRACING: bool = True
    ENABLE_ALERTS: bool = True
    ALERT_WEBHOOK_URL: Optional[str] = None

    # --- Storage Configuration ---
    DATA_DIR: str = "data"
    LOGS_DIR: str = "logs"
    MEMORY_DB_PATH: str = "data/memory.db"
    CLOUD_STORAGE_BUCKET_NAME: Optional[str] = None
    CLOUD_STORAGE_SIGNED_URL_TTL: int = 3600  # 1 hour by default
    GCP_PROJECT_ID: Optional[str] = None

    # --- Upload Validation ---
    UPLOAD_STORAGE_DIR: str = "uploads"
    UPLOAD_TEMP_DIR: Optional[str] = None
    UPLOAD_ALLOWED_EXTENSIONS: list[str] = [
        "txt",
        "md",
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "csv",
        "json",
        "docx",
        "pptx",
    ]
    UPLOAD_MAX_SIZE_MB: int = 25
    UPLOAD_CHUNK_SIZE_BYTES: int = 1024 * 1024  # 1 MB
    UPLOAD_SCAN_COMMAND: Optional[str] = None
    UPLOAD_SCAN_TIMEOUT_SECONDS: int = 30

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- Real-time Delivery Guardrails ---
    REALTIME_MAX_CONNECTIONS_PER_ROOM: int = 64
    REALTIME_MAX_SSE_QUEUE_SIZE: int = 256
    REALTIME_SEND_TIMEOUT_SECONDS: float = 3.0
    REALTIME_SEND_MAX_RETRIES: int = 1
    REALTIME_SEND_RETRY_BACKOFF_SECONDS: float = 0.5
    REALTIME_DISCONNECT_ON_SLOW_CONSUMER: bool = True

    # --- Metrics and Alerting Configuration ---
    METRICS_ENABLED: bool = True
    ALERT_TOKEN_THRESHOLD: int = 10000  # Alert if a single review uses more than 10k tokens
    ALERT_PROVIDER_FAILURE_RATE_THRESHOLD: float = 0.5  # Alert if a specific provider's failure rate exceeds 50%

    # --- Cost Guardrails ---
    PER_REVIEW_TOKEN_BUDGET: Optional[int] = None  # e.g., 20000
    DAILY_TOKEN_BUDGET: Optional[int] = 200000
    DAILY_COST_BUDGET: float = 50.0
    DAILY_ORG_TOKEN_BUDGET: Optional[int] = None  # e.g., 100000
    ALERT_LATENCY_SECONDS_THRESHOLD: int = 300  # Alert if a single review takes more than 5 minutes
    ALERT_FAILURE_RATE_THRESHOLD: float = 0.2  # Alert if overall failure rate exceeds 20%

    # --- Memory Archive Configuration ---
    MEMORY_ARCHIVE_AFTER_DAYS: int = 14  # Archive conversations after 14 days
    MEMORY_ARCHIVE_BATCH_SIZE: int = 300  # Process 300 conversations per batch (balanced between 200-500)
    MEMORY_ARCHIVE_MIN_MESSAGES: int = 10  # Minimum messages required for archival

    # --- Test Configuration ---
    ALLOW_TEST_DB_ENCRYPTION_KEY: bool = False
    AUTO_LAUNCH_TEST_SERVICES: bool = True
    ALLOW_MISSING_TEST_SERVICES: bool = True
    RUN_HEAVY_TESTS: bool = False

TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _rewrite_url_with_overrides(url: str, host: Optional[str], port: Optional[str]) -> str:
    """Rewrite a URL's host/port components while preserving credentials and paths."""

    parsed = urlparse(url)
    userinfo, at, hostport = parsed.netloc.rpartition("@")
    current_host, _, current_port = hostport.partition(":")

    new_host = host or current_host
    new_port = port or current_port

    host_segment = new_host or current_host
    if new_port:
        host_segment = f"{host_segment}:{new_port}"

    if at:
        netloc = f"{userinfo}{at}{host_segment}"
    else:
        netloc = host_segment

    return urlunparse(parsed._replace(netloc=netloc))


def _apply_test_overrides(settings: Settings) -> None:
    """Apply test-specific overrides for services that rely on network URLs."""

    redis_host = os.getenv("TEST_REDIS_HOST")
    redis_port = os.getenv("TEST_REDIS_PORT")

    if redis_host or redis_port:
        if settings.REDIS_URL:
            settings.REDIS_URL = _rewrite_url_with_overrides(
                settings.REDIS_URL,
                redis_host,
                redis_port,
            )
        else:
            host = redis_host or "localhost"
            port = redis_port or "6379"
            settings.REDIS_URL = f"redis://{host}:{port}/0"

        if not settings.CELERY_BROKER_URL:
            settings.CELERY_BROKER_URL = settings.REDIS_URL
        if not settings.CELERY_RESULT_BACKEND:
            settings.CELERY_RESULT_BACKEND = settings.REDIS_URL


def _base_redis_url() -> Optional[str]:
    """Determine the baseline Redis URL before any test overrides are applied."""

    if settings.REDIS_URL:
        return settings.REDIS_URL

    env_url = os.getenv("REDIS_URL")
    if env_url:
        return env_url

    host = os.getenv("REDIS_HOST")
    port = os.getenv("REDIS_PORT")
    if host or port:
        host = host or "localhost"
        port = port or "6379"
        return f"redis://{host}:{port}/0"

    return None


def get_effective_redis_url() -> Optional[str]:
    """Return the Redis URL after applying any runtime test overrides."""

    redis_host = os.getenv("TEST_REDIS_HOST")
    redis_port = os.getenv("TEST_REDIS_PORT")

    base_url = _base_redis_url()

    if redis_host or redis_port:
        if base_url:
            return _rewrite_url_with_overrides(base_url, redis_host, redis_port)

        host = redis_host or "localhost"
        port = redis_port or "6379"
        return f"redis://{host}:{port}/0"

    return base_url


def get_effective_celery_url() -> Optional[str]:
    """Return the Celery broker/backend URL honoring Redis overrides."""

    celery_url = settings.CELERY_BROKER_URL or os.getenv("CELERY_BROKER_URL")
    if celery_url:
        return celery_url

    return get_effective_redis_url()


def _is_truthy(value: Optional[str]) -> bool:
    return bool(value) and value.lower() in TRUTHY_VALUES


def _should_allow_test_fallback() -> bool:
    """Return True when it's explicitly safe to use the bundled test DB key."""

    if os.getenv("PYTEST_CURRENT_TEST"):
        return True

    if _is_truthy(os.getenv("TESTING")):
        return True

    if _is_truthy(os.getenv("ALLOW_TEST_DB_ENCRYPTION_KEY")):
        return True

    env_name = os.getenv("ENVIRONMENT", "").lower()
    if env_name in {"local", "development", "dev", "test"}:
        return True

    return False


def _load_settings() -> Settings:
    """Instantiate :class:`Settings`, providing a guarded fallback for tests."""

    try:
        return Settings()
    except ValidationError as exc:
        missing_encryption_key = any(
            error.get("loc") == ("DB_ENCRYPTION_KEY",)
            for error in exc.errors()
        )
        if not missing_encryption_key:
            raise

        if not _should_allow_test_fallback():
            logger.error(
                "DB_ENCRYPTION_KEY validation failed. Set DB_ENCRYPTION_KEY or explicitly "
                "opt-in via ALLOW_TEST_DB_ENCRYPTION_KEY for local development runs.",
                exc_info=True,
            )
            raise RuntimeError(
                "DB_ENCRYPTION_KEY must be configured. Provide a secure key or set "
                "ALLOW_TEST_DB_ENCRYPTION_KEY=1 for local/test usage."
            ) from exc

        fallback_key = os.getenv("DB_ENCRYPTION_KEY") or DEFAULT_TEST_DB_ENCRYPTION_KEY
        logger.warning(
            "Using built-in test DB encryption key. Do not use this fallback in production environments.",
        )

        return Settings(DB_ENCRYPTION_KEY=fallback_key)


# Global settings instance
settings = _load_settings()
_apply_test_overrides(settings)

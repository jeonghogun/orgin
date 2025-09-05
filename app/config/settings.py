"""
Application Configuration Settings
"""

from typing import Optional, Dict, Any
from pydantic_settings import BaseSettings
from pydantic import model_validator, PostgresDsn


class Settings(BaseSettings):
    """Application settings with environment variable support"""

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
                    port=port,
                    path=f"{db}",
                ))
        return v

    # --- General API Configuration ---
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    DEBUG: bool = True
    TESTING: bool = False

    # --- Authentication ---
    AUTH_OPTIONAL: bool = True
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

    # --- Hybrid Retrieval Configuration ---
    HYBRID_BM25_WEIGHT: float = 0.55
    HYBRID_VEC_WEIGHT: float = 0.45
    HYBRID_TOPK_BM25: int = 50
    HYBRID_TOPK_VEC: int = 50
    HYBRID_RETURN_TOPN: int = 20
    TIME_DECAY_ENABLED: bool = True
    TIME_DECAY_LAMBDA: float = 0.03

    # --- Re-ranker Configuration ---
    RERANK_ENABLED: bool = False
    RERANK_PROVIDER: str = "cohere"  # "openai" or "cohere"
    RERANK_TOP: int = 20

    # --- Frontend Configuration ---
    VITE_API_BASE_URL: Optional[str] = None
    VITE_WS_BASE_URL: Optional[str] = None

    # --- Redis & Celery ---
    REDIS_URL: str = "redis://redis:6379"  # Docker environment default
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # --- External APIs ---
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # --- Firebase Configuration ---
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None

    # --- APM Configuration ---
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

    # --- Rate Limiting ---
    RATE_LIMIT_PER_MINUTE: int = 60

    # --- Metrics and Alerting Configuration ---
    METRICS_ENABLED: bool = True
    ALERT_TOKEN_THRESHOLD: int = 10000  # Alert if a single review uses more than 10k tokens
    ALERT_PROVIDER_FAILURE_RATE_THRESHOLD: float = 0.5  # Alert if a specific provider's failure rate exceeds 50%

    # --- Cost Guardrails ---
    PER_REVIEW_TOKEN_BUDGET: Optional[int] = None  # e.g., 20000
    DAILY_ORG_TOKEN_BUDGET: Optional[int] = None  # e.g., 100000
    ALERT_LATENCY_SECONDS_THRESHOLD: int = 300  # Alert if a single review takes more than 5 minutes
    ALERT_FAILURE_RATE_THRESHOLD: float = 0.2  # Alert if overall failure rate exceeds 20%

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()

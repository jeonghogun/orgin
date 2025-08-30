"""
Application Configuration Settings
"""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    # API Configuration
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    DEBUG: bool = True
    TESTING: bool = False

    # Authentication
    AUTH_OPTIONAL: bool = True

    # LLM Configuration
    MOCK_LLM: bool = False
    LLM_MODEL: str = "gpt-4o"

    # Hybrid Retrieval Configuration
    HYBRID_BM25_WEIGHT: float = 0.55
    HYBRID_VEC_WEIGHT: float = 0.45
    HYBRID_TOPK_BM25: int = 50
    HYBRID_TOPK_VEC: int = 50
    HYBRID_RETURN_TOPN: int = 20
    TIME_DECAY_ENABLED: bool = True
    TIME_DECAY_LAMBDA: float = 0.03

    # Re-ranker Configuration
    RERANK_ENABLED: bool = False
    RERANK_PROVIDER: str = "cohere" # "openai" or "cohere"
    RERANK_TOP: int = 20

    # Frontend-specific, but present in the same .env file
    VITE_API_BASE_URL: Optional[str] = None
    VITE_WS_BASE_URL: Optional[str] = None
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str  # No default, must be loaded from env
    GEMINI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    FORCE_DEFAULT_PROVIDER: bool = False
    LLM_TIMEOUT: float = 30.0
    LLM_MAX_RETRIES: int = 2

    # Firebase Configuration
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None
    FIREBASE_PROJECT_ID: Optional[str] = None

    # External APIs
    GOOGLE_API_KEY: Optional[str] = None
    GOOGLE_CSE_ID: Optional[str] = None

    # Redis Configuration
    REDIS_URL: str = "redis://localhost:6379"

    # Celery Configuration
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Database Configuration
    DATABASE_URL: str  # No default, must be loaded from env
    DB_ENCRYPTION_KEY: str # No default, must be loaded from env

    # Storage Configuration
    DATA_DIR: str = "data"
    LOGS_DIR: str = "logs"
    MEMORY_DB_PATH: str = "data/memory.db"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Metrics and Alerting Configuration
    METRICS_ENABLED: bool = True
    ALERT_TOKEN_THRESHOLD: int = 10000  # Alert if a single review uses more than 10k tokens

    # Cost Guardrails
    PER_REVIEW_TOKEN_BUDGET: Optional[int] = None # e.g., 20000
    DAILY_ORG_TOKEN_BUDGET: Optional[int] = None # e.g., 100000
    ALERT_LATENCY_SECONDS_THRESHOLD: int = 300  # Alert if a single review takes more than 5 minutes
    ALERT_FAILURE_RATE_THRESHOLD: float = 0.2  # Alert if overall failure rate exceeds 20%
    ALERT_PROVIDER_FAILURE_RATE_THRESHOLD: float = 0.5 # Alert if a specific provider's failure rate exceeds 50%

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()

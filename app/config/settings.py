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

    # Authentication
    AUTH_OPTIONAL: bool = True

    # LLM Configuration
    LLM_MODEL: str = "gpt-4o"
    LLM_PROVIDER: str = "openai"
    OPENAI_API_KEY: str = ""
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

    # Database Configuration
    DATABASE_URL: str = "postgresql://user:password@localhost/origin_db"

    # Storage Configuration
    DATA_DIR: str = "data"
    LOGS_DIR: str = "logs"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()

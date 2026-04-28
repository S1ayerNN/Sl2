from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MyAstro"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://myastro:myastro_secret@db:5432/myastro"
    DATABASE_URL_SYNC: str = "postgresql://myastro:myastro_secret@db:5432/myastro"

    # Redis
    REDIS_URL: str = "redis://:myastro_redis_secret@redis:6379/0"

    # JWT - MUST be overridden in .env, app will refuse to start with default
    JWT_SECRET_KEY: str = "change-me-to-a-random-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # OpenAI
    OPENAI_API_KEY: str = ""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # PII Encryption - MUST be overridden in .env
    ENCRYPTION_KEY: str = "change-me-to-a-random-encryption-key"

    # Ad verification
    AD_VIEW_TOKEN_TTL_SECONDS: int = 300  # 5 min validity for ad completion token

    # Family members
    FAMILY_MEMBERS_LIMIT_FREE: int = 0  # Free users: only self
    FAMILY_MEMBERS_LIMIT_PREMIUM: int = 5  # Premium users: up to 5 members

    # Rate limiting
    HOROSCOPE_DAILY_LIMIT_FREE: int = 3
    HOROSCOPE_DAILY_LIMIT_PREMIUM: int = 20
    HOROSCOPE_HISTORY_SIZE: int = 5

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()

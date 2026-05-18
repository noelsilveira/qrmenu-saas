from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "QRMenu SaaS"
    APP_VERSION: str = "2.0.0"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "change-me-in-production"

    # JWT
    JWT_SECRET_KEY: str = "change-me-jwt-secret-key-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database
    POSTGRES_URI: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/saas_db"
    POSTGRES_POOL_SIZE: int = 20
    POSTGRES_MAX_OVERFLOW: int = 40

    # Redis
    REDIS_URI: str = "redis://localhost:6379/0"
    REDIS_CELERY_URI: str = "redis://localhost:6379/1"

    # WhatsApp
    META_WA_API_VERSION: str = "v18.0"
    META_WA_ACCESS_TOKEN: str = ""
    META_WA_PHONE_NUMBER_ID: str = ""
    META_WA_BUSINESS_ACCOUNT_ID: str = ""
    META_WA_WEBHOOK_VERIFY_TOKEN: str = ""

    # Delivery
    OSRM_BASE_URL: str = "http://localhost:5000"
    GOOGLE_MAPS_API_KEY: str = ""

    # 3rd Party
    TALABAT_API_BASE: str = "https://api.talabat.com/v2"
    TALABAT_CLIENT_ID: str = ""
    TALABAT_CLIENT_SECRET: str = ""

    # Payments
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Files
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = "qrmenu-assets"

    CORS_ORIGINS: List[str] = ["*"]

    class Config:
        env_file = ".env"

settings = Settings()

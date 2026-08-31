# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    DATABASE_URL: str
    ENCRYPTION_KEY: str
    FRONTEND_URL: str = "http://localhost:3000"

    # Web Push
    VAPID_PUBLIC_KEY: str
    VAPID_PRIVATE_KEY: str
    VAPID_CLAIM_EMAIL: str = "mailto:admin@loansoft.com"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
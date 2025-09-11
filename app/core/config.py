from pydantic_settings import BaseSettings
import os
from dotenv import load_dotenv

env = os.getenv("ENV", "dev")
if env == "dev":
    dotenv_path = ".env"
else:
    dotenv_path = f".env.{env}"
load_dotenv(dotenv_path=dotenv_path, override=True)


class Settings(BaseSettings):
    PROJECT_NAME: str = "SandwichScan API"
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@db:5432/sandwichscan_dev",
    )
    FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://127.0.0.1:5173")
    BACKEND_API_V1_URL: str = os.getenv(
        "BACKEND_API_V1_URL", "http://127.0.0.1:8000/app/v1"
    )
    RESET_PASSWORD_TOKEN_SECRET: str = "SECRET"
    VERIFICATION_TOKEN_SECRET: str = "SECRET"
    JWT_SECRET: str = "SECRET"
    HASHIDS_MIN_LENGTH: int = 12
    HASHIDS_SALT: str = os.getenv("HASHIDS_SALT", "SECRET")
    ACCESS_TOKEN_EXPIRED_SECONDS: int = 3600 * 24 * 7  # 1 week

    USE_CREDENTIALS: bool = env == "prod"
    VALIDATE_CERTS: bool = env == "prod"
    SECURE_COOKIES: bool = env == "prod"
    ENV: str = env

    ALCHEMY_API_KEY: str = os.getenv("ALCHEMY_API_KEY", "")
    GOOGLE_CLOUD_PROJECT: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    )

settings = Settings()

print("Loading environment variables...")
print(f"DATABASE_URL: {settings.DATABASE_URL}")

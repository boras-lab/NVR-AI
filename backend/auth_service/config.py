from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    JWT_SECRET_KEY: str = "super_secret_key_change_in_production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "postgresql+asyncpg://nvr_admin:nvr_password_secure@localhost:5433/ai_nvr"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

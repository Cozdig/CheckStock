from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения и параметры окружения"""

    PROJECT_NAME: str = "CheckStock"
    DATABASE_URL: str = "sqlite+aiosqlite:///./checkstock.db"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

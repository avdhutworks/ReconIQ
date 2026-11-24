
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "ReconIQ"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "local"

    DATABASE_URL: str = (
        "postgresql+psycopg://reconiq:local_dev_password"
        "@localhost:5432/reconiq"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
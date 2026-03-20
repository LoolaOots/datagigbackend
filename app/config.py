from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    secret_key: str = "changeme"

    # Supabase
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str

    # Database
    database_url: str

    # Resend
    resend_api_key: str

    # Internal auth
    internal_api_secret: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()

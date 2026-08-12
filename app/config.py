from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Ramal CRM"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/ramal_crm"
    secret_key: str = "dev-secret"
    debug: bool = False
    google_places_api_key: str | None = None
    tavily_api_key: str | None = None
    timezone: str = "America/Santiago"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

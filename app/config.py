from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_publishable_key: str = ""

    public_base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./be_late.db"
    currency: str = "jpy"

    doubt_phase_minutes_before: int = 120

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

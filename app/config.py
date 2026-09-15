from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    database_url: str = "sqlite:///./be_late.db"

    doubt_phase_minutes_before: int = 120

    # LIFF (LINE Front-end Framework) app used by the companion PWA to log
    # users in and mint an ID token this backend can verify.
    liff_channel_id: str = ""
    cors_allow_origins: str = "*"  # comma-separated list, or "*"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

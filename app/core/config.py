"""Application settings loaded from environment / .env file."""

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    DATABASE_URL: str
    APP_ENV: str = "dev"
    GEMINI_API_KEY: str | None = None

    # Auth (used from Week 2 onwards)
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60

    SESSION_COOKIE_SECURE: bool | None = None
    # Only honor X-Forwarded-For for rate-limit keying when running behind a
    # trusted reverse proxy. Leave False in dev and in any environment where
    # the app is reachable directly — otherwise clients can trivially spoof
    # their rate-limit bucket by sending their own X-Forwarded-For header.
    TRUST_FORWARDED_HEADERS: bool = False

    MAX_FORM_BYTES: int = 100_000
    MAX_FORM_FIELDS: int = 200
    MAX_INGEST_CHARS: int = 5_000
    MATCHER_CANDIDATE_LIMIT: int = 500
    COORDINATOR_TASK_LIMIT: int = 200
    COORDINATOR_PENDING_LIMIT: int = 200
    APPLICANTS_LIMIT: int = 200
    ADMIN_LIST_LIMIT: int = 200
    VOLUNTEER_TASK_SCAN_LIMIT: int = 500
    VOLUNTEER_ASSIGNMENTS_LIMIT: int = 300
    TASK_TITLE_MAX_CHARS: int = 255
    AUTH_LOGIN_RATE_LIMIT: str = "10/minute"
    AUTH_REGISTER_RATE_LIMIT: str = "5/minute"
    INGEST_RATE_LIMIT: str = "30/minute"

    @property
    def session_cookie_secure(self) -> bool:
        if self.SESSION_COOKIE_SECURE is not None:
            return self.SESSION_COOKIE_SECURE
        return self.APP_ENV.lower() in {"prod", "production", "staging"}

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.JWT_EXPIRE_MINUTES <= 0:
            raise ValueError("JWT_EXPIRE_MINUTES must be greater than zero.")

        is_deployed = self.APP_ENV.lower() in {"prod", "production", "staging"}
        if not is_deployed:
            return self

        if self.SESSION_COOKIE_SECURE is False:
            raise ValueError("SESSION_COOKIE_SECURE must not be false in deployed environments.")

        secret = self.JWT_SECRET.strip()
        if secret == "change-me-use-a-long-random-string" or len(secret) < 32:
            raise ValueError("JWT_SECRET must be replaced with a strong production secret.")
        return self


settings = Settings()

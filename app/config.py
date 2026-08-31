"""Application settings, loaded from environment or .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # No LinkedIn credentials here. Callers supply their own cookies per
    # request, which keeps the deployment credential-free and means the user
    # agent always matches the browser the cookies came from.
    request_timeout: float = 15.0
    log_level: str = "INFO"


def parse_cookie_header(header: str) -> dict[str, str]:
    """Split a raw Cookie header into name -> value.

    Values are kept exactly as sent, quotes included: JSESSIONID arrives quoted
    and must stay that way in the jar, while the csrf-token header drops them.
    Only the first `=` separates name from value — `lidc=b=VB1` is a real shape.
    """
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.strip():
            cookies[name.strip()] = value.strip()
    return cookies


def csrf_token_for(cookies: dict[str, str]) -> str:
    """The csrf-token header value: JSESSIONID *without* its quotes.

    The asymmetry is real and load-bearing — the cookie keeps its quotes while
    the header drops them. Four independent implementations have converged on
    it.
    """
    return cookies.get("JSESSIONID", "").strip('"')


@lru_cache
def get_settings() -> Settings:
    return Settings()

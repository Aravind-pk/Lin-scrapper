"""Application settings, loaded from environment or .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.errors import SessionExpired


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # The whole Cookie header, pasted verbatim. Only li_at and JSESSIONID are
    # load-bearing for a request to succeed; bcookie, bscookie, lidc and _pxvid
    # are device-continuity identifiers and cost nothing to carry.
    li_cookie_header: str = ""

    request_timeout: float = 15.0
    log_level: str = "INFO"

    @property
    def cookies(self) -> dict[str, str]:
        return parse_cookie_header(self.li_cookie_header)

    @property
    def csrf_token(self) -> str:
        return csrf_token_for(self.cookies)

    def require_session(self) -> dict[str, str]:
        """Cookies for an outbound call, or a clear failure if unconfigured."""
        cookies = self.cookies
        if not cookies.get("li_at") or not cookies.get("JSESSIONID"):
            raise SessionExpired(
                "No LinkedIn session configured.",
                detail="Paste the whole Cookie header into LI_COOKIE_HEADER.",
            )
        return cookies


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

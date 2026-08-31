"""Application settings, loaded from environment or .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.errors import SessionExpired


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # The whole Cookie header, pasted verbatim.
    #
    # Two cookies (li_at + JSESSIONID) are enough for a single request to
    # succeed, and an earlier version supported supplying just those. Measured
    # across a sequence, they are not enough: the session is revoked on the
    # second request, where the full jar served three. bcookie, bscookie, lidc
    # and _pxvid (PerimeterX) are device-continuity identifiers — invisible in
    # one response, decisive across several.
    li_cookie_header: str = ""

    api_key: str = ""

    request_timeout: float = 15.0
    log_level: str = "INFO"

    @property
    def cookies(self) -> dict[str, str]:
        """The cookie jar to seed, as name -> value.

        Values are kept exactly as sent, quotes included: JSESSIONID arrives
        quoted and must stay that way, while the csrf-token header drops them.
        """
        cookies: dict[str, str] = {}
        for part in self.li_cookie_header.split(";"):
            name, sep, value = part.strip().partition("=")
            if sep and name.strip():
                cookies[name.strip()] = value.strip()
        return cookies

    @property
    def csrf_token(self) -> str:
        """The csrf-token header value: JSESSIONID *without* its quotes.

        The asymmetry is real and load-bearing — the cookie keeps its quotes
        while the header drops them. Four independent implementations have now
        converged on it.
        """
        return self.cookies.get("JSESSIONID", "").strip('"')

    def require_session(self) -> dict[str, str]:
        """Cookies for an outbound call, or a clear failure if unconfigured."""
        cookies = self.cookies
        if not cookies.get("li_at") or not cookies.get("JSESSIONID"):
            raise SessionExpired(
                "No LinkedIn session configured.",
                detail="Paste the whole Cookie header into LI_COOKIE_HEADER.",
            )
        return cookies


@lru_cache
def get_settings() -> Settings:
    return Settings()

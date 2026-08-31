"""HTTP client for LinkedIn's Voyager API.

Plain httpx. TLS impersonation was measured against this exact endpoint, both
while blocked and while succeeding, and changed nothing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import csrf_token_for, parse_cookie_header
from app.errors import (
    ProfileNotFound,
    SessionExpired,
    UpstreamError,
    UpstreamTimeout,
)
from app.linkedin.constants import (
    ACCEPT,
    FORBIDDEN_HEADERS,
    PROFILE_UNREACHABLE_MARKER,
    REFERER,
    RESTLI_VERSION,
    build_profile_url,
)

log = logging.getLogger(__name__)


class LinkedInClient:
    def __init__(
        self,
        cookies: dict[str, str],
        csrf_token: str,
        user_agent: str,
        timeout: float = 15.0,
    ):
        self._csrf_token = csrf_token
        # Required, not defaulted. LinkedIn binds a session to the browser it
        # was issued to, so a stand-in value invalidates the session instead of
        # failing — the worst way for a default to be wrong.
        self._user_agent = user_agent
        # Seed the jar once. Never pass cookies= per request: httpx merges the
        # two sources and sends every cookie twice, which LinkedIn reads as a
        # hijacked session and responds to by invalidating it everywhere.
        self._client = httpx.AsyncClient(
            cookies=cookies,
            timeout=httpx.Timeout(timeout),
            # A 3xx is the answer, not a detour. Following them loops 30 times.
            follow_redirects=False,
        )
        log.info("Seeded %d cookies: %s", len(cookies), ", ".join(sorted(cookies)))

    @classmethod
    def from_cookie_header(
        cls, header: str, user_agent: str, timeout: float = 15.0
    ) -> LinkedInClient:
        cookies = parse_cookie_header(header)
        return cls(
            cookies=cookies,
            csrf_token=csrf_token_for(cookies),
            user_agent=user_agent,
            timeout=timeout,
        )

    def _headers(self) -> dict[str, str]:
        headers = {
            # Must equal the JSESSIONID cookie, minus its quotes. Voyager
            # checks only that the two match — not that it issued the value.
            "csrf-token": self._csrf_token,
            "accept": ACCEPT,
            "x-restli-protocol-version": RESTLI_VERSION,
            "user-agent": self._user_agent,
            "accept-language": "en-US,en;q=0.9",
            # The SPA shell, not the profile being read.
            "referer": REFERER,
        }
        assert not FORBIDDEN_HEADERS & set(headers), "fabricated x-li-* header"
        return headers

    async def get_profile(self, slug: str) -> dict[str, Any]:
        url = build_profile_url(slug)
        response = await self._get(url)
        if 300 <= response.status_code < 400:
            _log_redirect(response, url)

        _raise_for_status(
            response.status_code,
            response.text,
            response.headers.get("location"),
            requested_url=url,
            clear_site_data=response.headers.get("clear-site-data"),
        )
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("LinkedIn returned a non-JSON body.") from exc

    async def _get(self, url: str) -> httpx.Response:
        try:
            return await self._client.get(url, headers=self._headers())
        except httpx.TimeoutException as exc:
            raise UpstreamTimeout() from exc
        except httpx.HTTPError as exc:
            raise UpstreamError(detail=str(exc)) from exc

    async def aclose(self) -> None:
        await self._client.aclose()


def _log_redirect(response: httpx.Response, url: str) -> None:
    """Why a 3xx happened, in names only so the log stays safe to paste."""
    set_cookie = response.headers.get_list("set-cookie")
    names = sorted({c.split("=", 1)[0].strip() for c in set_cookie})
    log.warning(
        "Upstream %s: to-self=%s, clear-site-data=%s, set-cookie=%s, headers=%s",
        response.status_code,
        response.headers.get("location") == url,
        response.headers.get("clear-site-data") or "none",
        names or "none",
        sorted(response.headers.keys()),
    )


def _raise_for_status(
    status: int,
    body: str,
    location: str | None,
    *,
    requested_url: str | None = None,
    clear_site_data: str | None = None,
) -> None:
    """Map an upstream response to our error vocabulary.

    Ordering matters: the 3xx branch must come before the >= 400 branch.
    """
    if 300 <= status < 400:
        # A redirect back to the same URL, or one carrying clear-site-data, is
        # LinkedIn actively revoking the session rather than letting it expire.
        # Worth naming separately: it means the cookies were valid and have now
        # been spent, so the fix is to re-copy them, not to wait.
        revoked = bool(clear_site_data) or (
            location is not None and location == requested_url
        )
        if revoked:
            cleared = (
                f" with clear-site-data: {clear_site_data}" if clear_site_data else ""
            )
            raise SessionExpired(
                "LinkedIn revoked this session.",
                detail=(
                    f"Redirected to the requested URL{cleared}. Re-copy the "
                    "Cookie header from a logged-in browser."
                ),
            )
        raise SessionExpired(detail=f"Redirected to {location or 'unknown'}.")

    if status >= 400:
        # Only the body separates "profile unreachable" from "session dead" —
        # both arrive as 403. Reading the status alone sends operators off
        # re-copying cookies that were fine.
        if status == 403 and PROFILE_UNREACHABLE_MARKER in body:
            raise ProfileNotFound()
        if status in (401, 403):
            raise SessionExpired()
        if status == 404:
            raise ProfileNotFound()
        if status == 410:
            raise UpstreamError(
                "LinkedIn retired this endpoint.",
                detail="The decoration has likely rotated; re-verify with "
                "tools/browser_console_probe.js.",
            )
        raise UpstreamError(detail=f"HTTP {status}")

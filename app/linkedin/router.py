"""Route for the LinkedIn integration.

The route lives with the provider rather than in main.py, so a second
integration is a new package plus one include_router line.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from time import perf_counter
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.deps import get_client
from app.errors import InvalidProfileURL, SessionExpired
from app.linkedin.client import LinkedInClient
from app.linkedin.profile import Meta, ProfileResponse, extract_profile

router = APIRouter(prefix="/api/integrations/linkedin", tags=["linkedin"])

_ALLOWED_HOST_SUFFIX = "linkedin.com"


class ProfileRequest(BaseModel):
    url: str
    cookie_header: str | None = Field(
        default=None,
        description=(
            "Your LinkedIn Cookie header, verbatim. Omit to use the server's "
            "own session. Sent in the body, never the query string, so it "
            "stays out of logs and browser history."
        ),
    )
    user_agent: str | None = Field(
        default=None,
        description=(
            "The user agent of the browser these cookies came from. LinkedIn "
            "binds a session to the browser it issued it to, so a mismatch is "
            "something it can score against."
        ),
    )


def parse_profile_url(url: str) -> str:
    """Extract the member slug from a LinkedIn profile URL."""
    candidate = url.strip()
    if not candidate:
        raise InvalidProfileURL()
    if "//" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    host = parsed.netloc.split(":")[0].lower()
    if not (host == _ALLOWED_HOST_SUFFIX or host.endswith(f".{_ALLOWED_HOST_SUFFIX}")):
        raise InvalidProfileURL(detail=f"Host {host or '(none)'} is not LinkedIn.")

    segments = [s for s in parsed.path.split("/") if s]
    if len(segments) < 2 or segments[0] != "in":
        raise InvalidProfileURL(
            detail="Expected a /in/<slug> path; company and school URLs are "
            "not profiles."
        )
    return segments[1]


@asynccontextmanager
async def _client_for(
    cookie_header: str | None,
    user_agent: str | None,
    shared: LinkedInClient,
    settings: Settings,
):
    """A caller's own session if they supplied one, else the server's.

    A caller-supplied client is short-lived and closed after the request; the
    shared one outlives it and must not be.
    """
    if not cookie_header:
        if not settings.li_cookie_header:
            raise SessionExpired(
                "No LinkedIn session available.",
                detail="Send cookie_header with the request, or configure "
                "LI_COOKIE_HEADER on the server.",
            )
        yield shared
        return

    client = LinkedInClient.from_cookie_header(
        cookie_header,
        timeout=settings.request_timeout,
        user_agent=user_agent,
    )
    try:
        yield client
    finally:
        await client.aclose()


@router.post("/profile", response_model=ProfileResponse)
async def fetch_profile(
    body: ProfileRequest,
    shared: LinkedInClient = Depends(get_client),
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    slug = parse_profile_url(body.url)
    started = perf_counter()
    async with _client_for(
        body.cookie_header, body.user_agent, shared, settings
    ) as client:
        payload = await client.get_profile(slug)
    elapsed_ms = int((perf_counter() - started) * 1000)
    return ProfileResponse(
        profile=extract_profile(payload),
        meta=Meta(duration_ms=elapsed_ms),
    )

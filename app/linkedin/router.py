"""Route for the LinkedIn integration.

The route lives with the provider rather than in main.py, so a second
integration is a new package plus one include_router line.
"""

from __future__ import annotations

from time import perf_counter
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.errors import InvalidProfileURL
from app.linkedin.client import LinkedInClient
from app.linkedin.profile import Meta, ProfileResponse, extract_profile

router = APIRouter(prefix="/api/integrations/linkedin", tags=["linkedin"])

_ALLOWED_HOST_SUFFIX = "linkedin.com"


class ProfileRequest(BaseModel):
    url: str
    cookie_header: str = Field(
        min_length=1,
        description=(
            "Your LinkedIn Cookie header, verbatim. Required — the service "
            "holds no session of its own. Sent in the body, never the query "
            "string, so it stays out of logs and browser history."
        ),
    )
    user_agent: str = Field(
        min_length=1,
        description=(
            "The user agent of the browser these cookies came from. Required: "
            "LinkedIn binds a session to the browser it issued it to, and a "
            "mismatch invalidates the session rather than failing the request."
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


@router.post("/profile", response_model=ProfileResponse)
async def fetch_profile(
    body: ProfileRequest,
    settings: Settings = Depends(get_settings),
) -> ProfileResponse:
    slug = parse_profile_url(body.url)
    started = perf_counter()
    client = LinkedInClient.from_cookie_header(
        body.cookie_header,
        timeout=settings.request_timeout,
        user_agent=body.user_agent,
    )
    try:
        payload = await client.get_profile(slug)
    finally:
        await client.aclose()
    elapsed_ms = int((perf_counter() - started) * 1000)
    return ProfileResponse(
        profile=extract_profile(payload),
        meta=Meta(duration_ms=elapsed_ms),
    )

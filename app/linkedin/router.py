"""Route for the LinkedIn integration.

The route lives with the provider rather than in main.py, so a second
integration is a new package plus one include_router line.
"""

from __future__ import annotations

from time import perf_counter
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.deps import get_client, require_api_key
from app.errors import InvalidProfileURL
from app.linkedin.client import LinkedInClient
from app.linkedin.profile import Meta, ProfileResponse, extract_profile

router = APIRouter(prefix="/api/integrations/linkedin", tags=["linkedin"])

_ALLOWED_HOST_SUFFIX = "linkedin.com"


class ProfileRequest(BaseModel):
    url: str


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


@router.post(
    "/profile",
    response_model=ProfileResponse,
    dependencies=[Depends(require_api_key)],
)
async def fetch_profile(
    body: ProfileRequest,
    client: LinkedInClient = Depends(get_client),
) -> ProfileResponse:
    slug = parse_profile_url(body.url)
    started = perf_counter()
    payload = await client.get_profile(slug)
    elapsed_ms = int((perf_counter() - started) * 1000)
    return ProfileResponse(
        profile=extract_profile(payload),
        meta=Meta(duration_ms=elapsed_ms),
    )

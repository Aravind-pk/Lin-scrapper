"""Shared FastAPI dependencies.

Provider packages import from here, so adding a second integration needs no
change to application code.
"""

from __future__ import annotations

from fastapi import Depends, Header, Request

from app.config import Settings, get_settings
from app.errors import Unauthorized
from app.linkedin.client import LinkedInClient


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_key:
        raise Unauthorized(
            "Service has no API key configured.",
            detail="Set API_KEY in the environment.",
        )
    if x_api_key != settings.api_key:
        raise Unauthorized()


def get_client(request: Request) -> LinkedInClient:
    """The process-wide client, built once during startup."""
    return request.app.state.linkedin_client

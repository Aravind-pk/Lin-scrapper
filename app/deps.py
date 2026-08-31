"""Shared FastAPI dependencies.

Provider packages import from here, so adding a second integration needs no
change to application code.
"""

from __future__ import annotations

from fastapi import Request

from app.linkedin.client import LinkedInClient


def get_client(request: Request) -> LinkedInClient:
    """The process-wide client, built from the server's own cookie header.

    Used when a caller supplies no cookies of their own.
    """
    return request.app.state.linkedin_client

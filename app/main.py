"""Application wiring. Nothing surprising should live here."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.errors import LinkedInAPIError
from app.linkedin.client import LinkedInClient
from app.linkedin.constants import DECORATION_ID
from app.linkedin.router import router as linkedin_router


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.linkedin_client = LinkedInClient(
        cookies=settings.cookies,
        csrf_token=settings.csrf_token,
        timeout=settings.request_timeout,
    )
    try:
        yield
    finally:
        await app.state.linkedin_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="LinkedIn Profile API",
        description="Accepts a LinkedIn profile URL, returns structured JSON.",
        version="1.0.0",
        lifespan=lifespan,
    )

    @app.exception_handler(LinkedInAPIError)
    async def _handle_known(_: Request, exc: LinkedInAPIError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "invalid_request",
                    "message": "Request body is malformed.",
                    "detail": str(exc.errors()),
                }
            },
        )

    @app.get("/health")
    async def health(settings: Settings = Depends(get_settings)) -> dict:
        # Names only, never values — so this response and the logs are safe
        # to paste into an issue.
        return {
            "status": "ok",
            "decoration_id": DECORATION_ID,
            "cookies_configured": sorted(settings.cookies),
            "api_key_configured": bool(settings.api_key),
        }

    app.include_router(linkedin_router)
    return app


app = create_app()

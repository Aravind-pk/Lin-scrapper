"""Application wiring. Nothing surprising should live here."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings, get_settings
from app.errors import LinkedInAPIError
from app.linkedin.client import LinkedInClient
from app.linkedin.constants import DECORATION_ID
from app.linkedin.router import router as linkedin_router

_PLAYGROUND = Path(__file__).parent / "static" / "playground.html"


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

    @app.api_route(
        "/",
        methods=["GET", "HEAD"],
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def playground() -> str:
        return _PLAYGROUND.read_text(encoding="utf-8")

    @app.api_route("/health", methods=["GET", "HEAD"])
    async def health(settings: Settings = Depends(get_settings)) -> dict:
        # A count and two booleans — enough to diagnose a misconfigured
        # server without enumerating the jar or exposing a single value.
        cookies = settings.cookies
        return {
            "status": "ok",
            "decoration_id": DECORATION_ID,
            "server_session": {
                "configured": bool(cookies),
                "cookie_count": len(cookies),
                "has_li_at": "li_at" in cookies,
                "has_jsessionid": "JSESSIONID" in cookies,
            },
        }

    app.include_router(linkedin_router)
    return app


app = create_app()

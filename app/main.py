"""Application wiring. Nothing surprising should live here."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import get_settings
from app.errors import LinkedInAPIError
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
    configure_logging(get_settings().log_level)
    yield


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
    async def health() -> dict:
        # Nothing credential-shaped to report: the service holds no session.
        return {"status": "ok", "decoration_id": DECORATION_ID}

    app.include_router(linkedin_router)
    return app


app = create_app()

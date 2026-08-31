from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
COOKIE_HEADER = 'li_at=AQEDATEST; JSESSIONID="ajax:1234567890123456789"'

_ENV_KEYS = ("REQUEST_TIMEOUT", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    """Keep the developer's .env out of the tests.

    Settings reads .env by default, so a populated local file silently
    overrides what a test constructs — results would depend on whose machine
    they run on.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def normalized_payload() -> dict:
    return json.loads((FIXTURES / "profile_normalized.json").read_text())


@pytest.fixture
def settings() -> Settings:
    return Settings()


class FakeClient:
    """Stands in for LinkedInClient in router tests."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls: list[str] = []
        self.closed = False
        self.header: str | None = None
        self.user_agent: str | None = None

    async def get_profile(self, slug: str) -> dict:
        self.calls.append(slug)
        if self.error:
            raise self.error
        return self.payload or {}

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def make_app(settings, monkeypatch):
    """A TestClient whose requests build `fake` instead of a real client.

    Every request constructs its own client now, so the factory is the seam.
    """

    def _make(fake: FakeClient) -> TestClient:
        def factory(header, user_agent, timeout=15.0):
            fake.header = header
            fake.user_agent = user_agent
            return fake

        monkeypatch.setattr(
            "app.linkedin.router.LinkedInClient.from_cookie_header",
            staticmethod(factory),
        )
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: settings
        # No context manager: lifespan only configures logging.
        return TestClient(app)

    return _make

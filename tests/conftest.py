from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import get_client
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"

_ENV_KEYS = ("LI_COOKIE_HEADER", "API_KEY", "REQUEST_TIMEOUT", "LOG_LEVEL")


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch):
    """Keep the developer's .env out of the tests.

    Settings reads .env by default, so a populated local file silently
    overrides what a test constructs — tests would pass or fail depending on
    whose machine they run on.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

API_KEY = "test-api-key"
COOKIE_HEADER = 'li_at=AQEDATEST; JSESSIONID="ajax:1234567890123456789"'


@pytest.fixture
def normalized_payload() -> dict:
    return json.loads((FIXTURES / "profile_normalized.json").read_text())


@pytest.fixture
def settings() -> Settings:
    return Settings(api_key=API_KEY, li_cookie_header=COOKIE_HEADER)


class FakeClient:
    """Stands in for LinkedInClient in router tests."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.payload = payload
        self.error = error
        self.calls: list[str] = []

    async def get_profile(self, slug: str) -> dict:
        self.calls.append(slug)
        if self.error:
            raise self.error
        return self.payload or {}


@pytest.fixture
def make_app(settings):
    def _make(fake: FakeClient) -> TestClient:
        app = create_app()
        app.dependency_overrides[get_client] = lambda: fake
        app.dependency_overrides[get_settings] = lambda: settings
        # No context manager: lifespan would build a real outbound client,
        # and every test overrides it anyway.
        return TestClient(app)

    return _make


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"X-API-Key": API_KEY}

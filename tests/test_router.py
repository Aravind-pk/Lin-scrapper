"""End-to-end through the app, against a stubbed upstream client."""

from app.errors import (
    ProfileNotFound,
    SessionExpired,
    UpstreamError,
    UpstreamTimeout,
)
from app.linkedin.constants import DECORATION_ID
from tests.conftest import FakeClient

URL = "https://www.linkedin.com/in/ada-lovelace"
PATH = "/api/integrations/linkedin/profile"


def test_happy_path_returns_the_profile_envelope(
    make_app, auth_headers, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    r = make_app(fake).post(PATH, json={"url": URL}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["name"] == "Ada Lovelace"
    assert body["meta"]["decoration_id"] == DECORATION_ID
    assert body["meta"]["source"] == "voyager-dash-profiles"
    assert isinstance(body["meta"]["duration_ms"], int)


def test_response_carries_every_field_the_brief_names(
    make_app, auth_headers, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    p = make_app(fake).post(
        PATH, json={"url": URL}, headers=auth_headers
    ).json()["profile"]
    for field in (
        "name", "headline", "location", "about", "experience", "education",
        "skills", "certifications", "languages", "profile_picture",
        "background_image",
    ):
        assert p[field], f"{field} is empty"


def test_slug_is_extracted_from_the_url(
    make_app, auth_headers, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(
        PATH, json={"url": f"{URL}/?trk=nav"}, headers=auth_headers
    )
    assert fake.calls == ["ada-lovelace"]


def test_missing_api_key_is_401(make_app, normalized_payload):
    fake = FakeClient(payload=normalized_payload)
    r = make_app(fake).post(PATH, json={"url": URL})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


def test_wrong_api_key_is_401(make_app, normalized_payload):
    fake = FakeClient(payload=normalized_payload)
    r = make_app(fake).post(
        PATH, json={"url": URL}, headers={"X-API-Key": "wrong"}
    )
    assert r.status_code == 401


def test_non_linkedin_url_is_400(make_app, auth_headers):
    r = make_app(FakeClient()).post(
        PATH, json={"url": "https://example.com/in/ada"}, headers=auth_headers
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_profile_url"


def test_company_url_is_400(make_app, auth_headers):
    r = make_app(FakeClient()).post(
        PATH,
        json={"url": "https://www.linkedin.com/company/tross"},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_malformed_body_is_422(make_app, auth_headers):
    r = make_app(FakeClient()).post(
        PATH, json={"profile": URL}, headers=auth_headers
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_url_is_not_looked_up_when_the_api_key_is_missing(make_app):
    """Auth runs before any upstream call."""
    fake = FakeClient()
    make_app(fake).post(PATH, json={"url": URL})
    assert fake.calls == []


def test_profile_not_found_is_404(make_app, auth_headers):
    r = make_app(FakeClient(error=ProfileNotFound())).post(
        PATH, json={"url": URL}, headers=auth_headers
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "profile_not_found"


def test_session_expired_is_503_not_404(make_app, auth_headers):
    """Conflating these two sends operators off re-copying good cookies."""
    r = make_app(FakeClient(error=SessionExpired())).post(
        PATH, json={"url": URL}, headers=auth_headers
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "session_expired"


def test_upstream_error_is_502(make_app, auth_headers):
    r = make_app(FakeClient(error=UpstreamError())).post(
        PATH, json={"url": URL}, headers=auth_headers
    )
    assert r.status_code == 502


def test_upstream_timeout_is_504(make_app, auth_headers):
    r = make_app(FakeClient(error=UpstreamTimeout())).post(
        PATH, json={"url": URL}, headers=auth_headers
    )
    assert r.status_code == 504


def test_error_detail_is_surfaced_when_present(make_app, auth_headers):
    r = make_app(FakeClient(error=ProfileNotFound(detail="gone"))).post(
        PATH, json={"url": URL}, headers=auth_headers
    )
    assert r.json()["error"]["detail"] == "gone"


def test_health_reports_cookie_names_never_values(make_app):
    r = make_app(FakeClient()).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body["cookies_configured"]) == {"li_at", "JSESSIONID"}
    assert "AQEDATEST" not in r.text
    assert "ajax:" not in r.text


def test_health_reports_the_decoration_in_use(make_app):
    assert make_app(FakeClient()).get("/health").json()["decoration_id"] == (
        DECORATION_ID
    )

"""End-to-end through the app, against a stubbed upstream client."""

from app.errors import (
    ProfileNotFound,
    SessionExpired,
    UpstreamError,
    UpstreamTimeout,
)
from app.linkedin.constants import DECORATION_ID
from tests.conftest import COOKIE_HEADER, FakeClient

URL = "https://www.linkedin.com/in/ada-lovelace"
PATH = "/api/integrations/linkedin/profile"
UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/151.0.0.0"


def body(**over) -> dict:
    return {
        "url": URL,
        "cookie_header": COOKIE_HEADER,
        "user_agent": UA,
        **over,
    }


# --- happy path ---


def test_happy_path_returns_the_profile_envelope(make_app, normalized_payload):
    fake = FakeClient(payload=normalized_payload)
    r = make_app(fake).post(PATH, json=body())
    assert r.status_code == 200
    out = r.json()
    assert out["profile"]["name"] == "Ada Lovelace"
    assert out["meta"]["decoration_id"] == DECORATION_ID
    assert out["meta"]["source"] == "voyager-dash-profiles"
    assert isinstance(out["meta"]["duration_ms"], int)


def test_response_carries_every_field_the_brief_names(make_app, normalized_payload):
    p = make_app(FakeClient(payload=normalized_payload)).post(
        PATH, json=body()
    ).json()["profile"]
    for field in (
        "name", "headline", "location", "about", "experience", "education",
        "skills", "certifications", "languages", "profile_picture",
        "background_image",
    ):
        assert p[field], f"{field} is empty"


def test_slug_is_extracted_from_the_url(make_app, normalized_payload):
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(PATH, json=body(url=f"{URL}/?trk=nav"))
    assert fake.calls == ["ada-lovelace"]


# --- the caller's session is the only session ---


def test_cookies_reach_the_client_verbatim(make_app, normalized_payload):
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(PATH, json=body())
    assert fake.header == COOKIE_HEADER


def test_user_agent_reaches_the_client(make_app, normalized_payload):
    """LinkedIn binds a session to the browser it issued it to, so the UA has
    to travel with the cookies."""
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(PATH, json=body())
    assert fake.user_agent == UA


def test_missing_user_agent_is_422(make_app):
    """Required, not defaulted: a stand-in user agent invalidates the caller's
    session rather than failing the request."""
    r = make_app(FakeClient()).post(
        PATH, json={"url": URL, "cookie_header": COOKIE_HEADER}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_empty_user_agent_is_422(make_app):
    r = make_app(FakeClient()).post(PATH, json=body(user_agent=""))
    assert r.status_code == 422


def test_client_is_closed_after_every_request(make_app, normalized_payload):
    """Per-request clients leak connections if they are not closed."""
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(PATH, json=body())
    assert fake.closed is True


def test_client_is_closed_even_when_the_fetch_fails(make_app):
    fake = FakeClient(error=UpstreamError())
    make_app(fake).post(PATH, json=body())
    assert fake.closed is True


def test_missing_cookies_is_422_not_a_session_error(make_app):
    """The service holds no session, so absent cookies are a malformed
    request — not an expired one, which would send callers off re-copying
    cookies they never sent."""
    r = make_app(FakeClient()).post(PATH, json={"url": URL})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_empty_cookie_string_is_also_422(make_app):
    r = make_app(FakeClient()).post(PATH, json=body(cookie_header=""))
    assert r.status_code == 422


# --- request validation ---


def test_non_linkedin_url_is_400(make_app):
    r = make_app(FakeClient()).post(
        PATH, json=body(url="https://example.com/in/ada")
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_profile_url"


def test_company_url_is_400(make_app):
    r = make_app(FakeClient()).post(
        PATH, json=body(url="https://www.linkedin.com/company/tross")
    )
    assert r.status_code == 400


def test_malformed_body_is_422(make_app):
    r = make_app(FakeClient()).post(PATH, json={"nope": 1})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_bad_url_is_rejected_before_any_upstream_call(make_app):
    fake = FakeClient()
    make_app(fake).post(PATH, json=body(url="https://example.com/in/a"))
    assert fake.calls == []


# --- upstream failures ---


def test_profile_not_found_is_404(make_app):
    r = make_app(FakeClient(error=ProfileNotFound())).post(PATH, json=body())
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "profile_not_found"


def test_session_expired_is_503_not_404(make_app):
    """Conflating these two sends operators off re-copying good cookies."""
    r = make_app(FakeClient(error=SessionExpired())).post(PATH, json=body())
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "session_expired"


def test_upstream_error_is_502(make_app):
    r = make_app(FakeClient(error=UpstreamError())).post(PATH, json=body())
    assert r.status_code == 502


def test_upstream_timeout_is_504(make_app):
    r = make_app(FakeClient(error=UpstreamTimeout())).post(PATH, json=body())
    assert r.status_code == 504


def test_error_detail_is_surfaced_when_present(make_app):
    r = make_app(FakeClient(error=ProfileNotFound(detail="gone"))).post(
        PATH, json=body()
    )
    assert r.json()["error"]["detail"] == "gone"


# --- health ---


def test_health_reports_no_credential_state(make_app):
    """There is no session to report on, and nothing cookie-shaped to leak."""
    out = make_app(FakeClient()).get("/health").json()
    assert out == {"status": "ok", "decoration_id": DECORATION_ID}


def test_root_and_health_answer_head(make_app):
    """Platform health checks probe with HEAD. FastAPI's @app.get registers
    GET alone, and a 405 there reads as an unhealthy instance."""
    client = make_app(FakeClient())
    assert client.head("/").status_code == 200
    assert client.head("/health").status_code == 200

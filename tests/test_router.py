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
    make_app, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    r = make_app(fake).post(PATH, json={"url": URL})
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["name"] == "Ada Lovelace"
    assert body["meta"]["decoration_id"] == DECORATION_ID
    assert body["meta"]["source"] == "voyager-dash-profiles"
    assert isinstance(body["meta"]["duration_ms"], int)


def test_response_carries_every_field_the_brief_names(
    make_app, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    p = make_app(fake).post(
        PATH, json={"url": URL}
    ).json()["profile"]
    for field in (
        "name", "headline", "location", "about", "experience", "education",
        "skills", "certifications", "languages", "profile_picture",
        "background_image",
    ):
        assert p[field], f"{field} is empty"


def test_slug_is_extracted_from_the_url(
    make_app, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(
        PATH, json={"url": f"{URL}/?trk=nav"}
    )
    assert fake.calls == ["ada-lovelace"]


def test_no_api_key_is_required(make_app, normalized_payload):
    """The endpoint is open; the LinkedIn cookies are the only credential."""
    fake = FakeClient(payload=normalized_payload)
    assert make_app(fake).post(PATH, json={"url": URL}).status_code == 200


def test_server_session_is_used_when_no_cookies_supplied(
    make_app, normalized_payload
):
    fake = FakeClient(payload=normalized_payload)
    make_app(fake).post(PATH, json={"url": URL})
    assert fake.calls == ["ada-lovelace"]


def test_caller_cookies_build_a_separate_client(
    make_app, normalized_payload, monkeypatch
):
    """A caller's session must not touch the shared client."""
    shared = FakeClient(payload=normalized_payload)
    caller = FakeClient(payload=normalized_payload)
    seen = {}

    def fake_factory(header, timeout=15.0, user_agent=None):
        seen["header"] = header
        seen["user_agent"] = user_agent
        return caller

    monkeypatch.setattr(
        "app.linkedin.router.LinkedInClient.from_cookie_header", fake_factory
    )
    r = make_app(shared).post(
        PATH, json={"url": URL, "cookie_header": "li_at=CALLER; JSESSIONID=x"}
    )
    assert r.status_code == 200
    assert seen["header"] == "li_at=CALLER; JSESSIONID=x"
    assert seen["user_agent"] is None
    assert caller.calls == ["ada-lovelace"]
    assert shared.calls == []


def test_caller_client_is_closed_after_the_request(
    make_app, normalized_payload, monkeypatch
):
    """Short-lived clients leak connections if they are not closed."""
    caller = FakeClient(payload=normalized_payload)
    monkeypatch.setattr(
        "app.linkedin.router.LinkedInClient.from_cookie_header",
        lambda header, timeout=15.0, user_agent=None: caller,
    )
    make_app(FakeClient()).post(
        PATH, json={"url": URL, "cookie_header": "li_at=CALLER"}
    )
    assert caller.closed is True


def test_caller_user_agent_reaches_the_client(
    make_app, normalized_payload, monkeypatch
):
    """The playground sends navigator.userAgent so the request matches the
    browser the cookies came from."""
    caller = FakeClient(payload=normalized_payload)
    seen = {}

    def factory(header, timeout=15.0, user_agent=None):
        seen["ua"] = user_agent
        return caller

    monkeypatch.setattr(
        "app.linkedin.router.LinkedInClient.from_cookie_header", factory
    )
    make_app(FakeClient()).post(
        PATH,
        json={
            "url": URL,
            "cookie_header": "li_at=X",
            "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/151",
        },
    )
    assert seen["ua"] == "Mozilla/5.0 (X11; Linux x86_64) Chrome/151"


def test_shared_client_is_never_closed(make_app, normalized_payload):
    """It outlives the request; closing it would break every later call."""
    shared = FakeClient(payload=normalized_payload)
    make_app(shared).post(PATH, json={"url": URL})
    assert shared.closed is False


def test_no_session_anywhere_is_503(make_app, no_server_session):
    r = make_app(FakeClient()).post(PATH, json={"url": URL})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "session_expired"


def test_non_linkedin_url_is_400(make_app):
    r = make_app(FakeClient()).post(
        PATH, json={"url": "https://example.com/in/ada"}
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_profile_url"


def test_company_url_is_400(make_app):
    r = make_app(FakeClient()).post(
        PATH,
        json={"url": "https://www.linkedin.com/company/tross"},
    )
    assert r.status_code == 400


def test_malformed_body_is_422(make_app):
    r = make_app(FakeClient()).post(
        PATH, json={"profile": URL}
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request"


def test_bad_url_is_rejected_before_any_upstream_call(make_app):
    fake = FakeClient()
    make_app(fake).post(PATH, json={"url": "https://example.com/in/a"})
    assert fake.calls == []


def test_profile_not_found_is_404(make_app):
    r = make_app(FakeClient(error=ProfileNotFound())).post(
        PATH, json={"url": URL}
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "profile_not_found"


def test_session_expired_is_503_not_404(make_app):
    """Conflating these two sends operators off re-copying good cookies."""
    r = make_app(FakeClient(error=SessionExpired())).post(
        PATH, json={"url": URL}
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "session_expired"


def test_upstream_error_is_502(make_app):
    r = make_app(FakeClient(error=UpstreamError())).post(
        PATH, json={"url": URL}
    )
    assert r.status_code == 502


def test_upstream_timeout_is_504(make_app):
    r = make_app(FakeClient(error=UpstreamTimeout())).post(
        PATH, json={"url": URL}
    )
    assert r.status_code == 504


def test_error_detail_is_surfaced_when_present(make_app):
    r = make_app(FakeClient(error=ProfileNotFound(detail="gone"))).post(
        PATH, json={"url": URL}
    )
    assert r.json()["error"]["detail"] == "gone"


def test_health_never_exposes_a_cookie_value_or_name(make_app):
    """A count and two booleans is enough to diagnose a misconfigured server."""
    r = make_app(FakeClient()).get("/health")
    assert r.status_code == 200
    session = r.json()["server_session"]
    assert session == {
        "configured": True,
        "cookie_count": 2,
        "has_li_at": True,
        "has_jsessionid": True,
    }
    assert "AQEDATEST" not in r.text
    assert "ajax:" not in r.text


def test_health_reports_an_unconfigured_server(make_app, no_server_session):
    session = make_app(FakeClient()).get("/health").json()["server_session"]
    assert session["configured"] is False and session["cookie_count"] == 0


def test_health_reports_the_decoration_in_use(make_app):
    assert make_app(FakeClient()).get("/health").json()["decoration_id"] == (
        DECORATION_ID
    )


def test_root_and_health_answer_head(make_app):
    """Platform health checks probe with HEAD. FastAPI's @app.get registers
    GET alone, and a 405 there reads as an unhealthy instance."""
    client = make_app(FakeClient())
    assert client.head("/").status_code == 200
    assert client.head("/health").status_code == 200

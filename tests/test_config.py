"""The cookie helpers. Settings itself holds no credentials any more."""

from app.config import Settings, csrf_token_for, parse_cookie_header

HEADER = 'bcookie="v=2&a"; li_at=AQEDTEST; JSESSIONID="ajax:99"; lidc=b=VB1'


def test_header_is_parsed_whole():
    assert sorted(parse_cookie_header(HEADER)) == [
        "JSESSIONID",
        "bcookie",
        "li_at",
        "lidc",
    ]


def test_values_containing_equals_survive():
    """lidc=b=VB1 is a real shape; splitting on every = would corrupt it."""
    assert parse_cookie_header(HEADER)["lidc"] == "b=VB1"


def test_jsessionid_keeps_its_quotes():
    assert parse_cookie_header(HEADER)["JSESSIONID"] == '"ajax:99"'


def test_csrf_token_strips_the_quotes():
    """The asymmetry: cookie keeps quotes, header drops them."""
    cookies = parse_cookie_header(HEADER)
    assert cookies["JSESSIONID"] == '"ajax:99"'
    assert csrf_token_for(cookies) == "ajax:99"


def test_stray_whitespace_is_tolerated():
    cookies = parse_cookie_header('  li_at=AQED ;  JSESSIONID="ajax:9" ; ')
    assert cookies["li_at"] == "AQED"
    assert cookies["JSESSIONID"] == '"ajax:9"'


def test_empty_header_yields_an_empty_jar():
    assert parse_cookie_header("") == {}


def test_csrf_token_is_empty_without_a_jsessionid():
    assert csrf_token_for({"li_at": "AQED"}) == ""


def test_settings_hold_no_credentials():
    """Callers supply cookies per request; the service stores none."""
    fields = set(Settings.model_fields)
    assert fields == {"request_timeout", "log_level"}

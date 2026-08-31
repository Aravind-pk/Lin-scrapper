import pytest

from app.config import Settings
from app.errors import SessionExpired

HEADER = 'bcookie="v=2&a"; li_at=AQEDTEST; JSESSIONID="ajax:99"; lidc=b=VB1'


def test_cookie_header_is_parsed_whole():
    assert sorted(Settings(li_cookie_header=HEADER).cookies) == [
        "JSESSIONID",
        "bcookie",
        "li_at",
        "lidc",
    ]


def test_values_containing_equals_survive():
    """lidc=b=VB1 is a real shape; splitting on every = would corrupt it."""
    assert Settings(li_cookie_header=HEADER).cookies["lidc"] == "b=VB1"


def test_jsessionid_keeps_its_quotes_in_the_jar():
    assert Settings(li_cookie_header=HEADER).cookies["JSESSIONID"] == '"ajax:99"'


def test_csrf_token_strips_the_quotes():
    """The asymmetry: cookie keeps quotes, header drops them."""
    s = Settings(li_cookie_header=HEADER)
    assert s.cookies["JSESSIONID"] == '"ajax:99"'
    assert s.csrf_token == "ajax:99"


def test_stray_whitespace_is_tolerated():
    s = Settings(li_cookie_header='  li_at=AQED ;  JSESSIONID="ajax:9" ; ')
    assert s.cookies["li_at"] == "AQED"
    assert s.cookies["JSESSIONID"] == '"ajax:9"'


def test_empty_header_yields_an_empty_jar():
    assert Settings(li_cookie_header="").cookies == {}


def test_csrf_token_is_empty_without_a_session():
    assert Settings(li_cookie_header="").csrf_token == ""


def test_require_session_raises_when_unconfigured():
    with pytest.raises(SessionExpired):
        Settings(li_cookie_header="").require_session()


def test_require_session_raises_without_li_at():
    with pytest.raises(SessionExpired):
        Settings(li_cookie_header='JSESSIONID="ajax:99"').require_session()


def test_require_session_raises_without_jsessionid():
    with pytest.raises(SessionExpired):
        Settings(li_cookie_header="li_at=AQED").require_session()


def test_require_session_returns_the_jar():
    assert Settings(li_cookie_header=HEADER).require_session()["li_at"] == "AQEDTEST"

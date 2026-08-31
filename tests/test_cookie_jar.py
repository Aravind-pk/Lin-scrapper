"""Cookie duplication is a silent session-killer.

A competing implementation passes cookies= per request while also holding a
session jar; httpx merges the two and sends every cookie twice, which LinkedIn
reads as a hijacked session. Our design seeds once and passes nothing — but
that is invisible convention, so it is a test.
"""

import inspect

from app.linkedin.client import LinkedInClient

COOKIES = {"li_at": "AQED", "JSESSIONID": '"ajax:99"', "lidc": "b=VB1"}


async def test_jar_is_seeded_at_construction():
    c = LinkedInClient(cookies=COOKIES, csrf_token="ajax:99")
    try:
        assert c._client.cookies.get("li_at") == "AQED"
    finally:
        await c.aclose()


async def test_jar_holds_no_duplicates():
    c = LinkedInClient(cookies=COOKIES, csrf_token="ajax:99")
    try:
        names = list(c._client.cookies)
        assert len(names) == len(set(names)) == len(COOKIES)
    finally:
        await c.aclose()


def test_get_profile_never_passes_cookies_per_request():
    """The failure is invisible at runtime — no error, just dead sessions."""
    source = inspect.getsource(LinkedInClient.get_profile)
    assert "cookies=" not in source

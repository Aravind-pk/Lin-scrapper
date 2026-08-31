"""The header set is the whole fix.

Sending thirteen headers, three of them invented, produced a 302-to-self with
clear-site-data — LinkedIn revoking the session. Sending the honest set gets
200. These tests pin both halves of that.
"""

import pytest

from app.linkedin.client import LinkedInClient
from app.linkedin.constants import (
    ACCEPT,
    BROWSER_USER_AGENT,
    FORBIDDEN_HEADERS,
    REFERER,
    RESTLI_VERSION,
)

COOKIES = {"li_at": "AQED", "JSESSIONID": '"ajax:99"'}


@pytest.fixture
async def client():
    c = LinkedInClient(cookies=COOKIES, csrf_token="ajax:99")
    yield c
    await c.aclose()


async def test_no_fabricated_x_li_header_is_ever_sent(client):
    """The regression guard for the mistake that cost three sessions."""
    sent = {k.lower() for k in client._headers()}
    assert not (sent & FORBIDDEN_HEADERS)


async def test_csrf_token_is_unquoted_while_cookie_keeps_quotes(client):
    assert client._headers()["csrf-token"] == "ajax:99"
    assert COOKIES["JSESSIONID"] == '"ajax:99"'


async def test_accept_is_the_normalized_json_variant(client):
    assert client._headers()["accept"] == ACCEPT


async def test_restli_protocol_version_is_present(client):
    assert client._headers()["x-restli-protocol-version"] == RESTLI_VERSION


async def test_referer_is_the_feed_not_the_profile(client):
    """The request comes from the SPA shell, not the page being read."""
    assert client._headers()["referer"] == REFERER
    assert "/in/" not in client._headers()["referer"]


async def test_user_agent_is_a_browser_string(client):
    assert client._headers()["user-agent"] == BROWSER_USER_AGENT


async def test_no_trace_context_headers_are_sent(client):
    """These were once argued to be honest because a browser randomises them
    per request. Wrong: a page-forest id names a page-load tree the server
    issued, and the tracestate format is vendor-defined. Sending invented
    values reproduced the request-1-succeeds-request-2-dead revocation."""
    sent = {k.lower() for k in client._headers()}
    assert "x-li-pageforestid" not in sent
    assert "x-li-traceparent" not in sent
    assert "x-li-tracestate" not in sent


async def test_client_sends_no_x_li_header_at_all(client):
    """The in-browser probe that succeeds sends none. Neither do we."""
    assert not [k for k in client._headers() if k.lower().startswith("x-li-")]


async def test_headers_match_the_proven_browser_set(client):
    """The three the probe sends, plus what any HTTP client legitimately adds.

    No sec-ch-ua or priority: those are client hints a browser generates, and
    ours would claim Chromium while the TLS stack underneath is Python.
    """
    assert {k.lower() for k in client._headers()} == {
        "csrf-token",
        "accept",
        "x-restli-protocol-version",
        "user-agent",
        "accept-language",
        "referer",
    }


async def test_redirects_are_not_followed(client):
    """A 3xx is the answer, not a detour. Following them loops 30 times."""
    assert client._client.follow_redirects is False

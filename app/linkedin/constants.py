"""Everything specific to LinkedIn's Voyager API lives here, not in app config."""

from __future__ import annotations

from urllib.parse import urlencode

VOYAGER_BASE = "https://www.linkedin.com/voyager/api"
DASH_PROFILES_PATH = "/identity/dash/profiles"

# The legacy /identity/profiles/{slug}/profileView endpoint returns 410 Gone.
# Every popular library and tutorial still points at it, which is why they are
# all broken. This decoration is the live replacement: 200, ~113 entities.
DECORATION_ID = (
    "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-103"
)

ACCEPT = "application/vnd.linkedin.normalized+json+2.1"
RESTLI_VERSION = "2.0.0"

# Fallback only. LinkedIn binds a session to the browser it was issued to, so
# presenting that session under a different platform string is a mismatch it
# can score against — an earlier version claimed Windows while the cookies came
# from Linux. Callers should send their real user agent; the playground reads
# navigator.userAgent and does.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)

# The SPA shell issues this request, not the profile page being read.
REFERER = "https://www.linkedin.com/feed/"

# Fabricating any of these produced a 302-to-self carrying
# clear-site-data: "storage" — LinkedIn actively revoking the session. They
# describe page loads and telemetry that never happened, so there is no honest
# value to send. Asserted against in tests; never add to this request.
#
# The trace-context three were once argued to be different, on the grounds that
# a browser generates them randomly per request. That reasoning is wrong: a
# page-forest id names a page-load tree the server issued, and the tracestate
# format is vendor-defined, so both are invented values wearing a real header's
# name. Sending them reproduced the exact "request 1 -> 200, request 2 -> dead"
# pattern that fabricated telemetry produced before. The in-browser probe that
# succeeds sends none of them.
FORBIDDEN_HEADERS = frozenset(
    {
        "x-li-track",
        "x-li-page-instance",
        "x-li-pem-metadata",
        "x-li-pageforestid",
        "x-li-traceparent",
        "x-li-tracestate",
    }
)

# LinkedIn's own wording when a profile is unreachable. A 403 carrying this is
# a profile problem; a bare 403 is a session problem.
PROFILE_UNREACHABLE_MARKER = "VoyagerUserVisibleException"


def build_profile_url(slug: str) -> str:
    query = urlencode(
        {
            "q": "memberIdentity",
            "memberIdentity": slug,
            "decorationId": DECORATION_ID,
        }
    )
    return f"{VOYAGER_BASE}{DASH_PROFILES_PATH}?{query}"

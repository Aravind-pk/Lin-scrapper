"""_raise_for_status is the most branch-heavy function in the codebase and has
an ordering dependency, so every branch is pinned."""

import pytest

from app.errors import ProfileNotFound, SessionExpired, UpstreamError
from app.linkedin.client import _raise_for_status
from app.linkedin.constants import PROFILE_UNREACHABLE_MARKER

UNREACHABLE_BODY = (
    '{"status":403,"code":"","message":"",'
    f'"$type":"com.linkedin.voyager.common.{PROFILE_UNREACHABLE_MARKER}"}}'
)


def test_200_raises_nothing():
    assert _raise_for_status(200, "{}", None) is None


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_every_redirect_is_session_expired(status):
    with pytest.raises(SessionExpired):
        _raise_for_status(status, "", "https://www.linkedin.com/in/ada")


def test_redirect_records_the_location():
    with pytest.raises(SessionExpired) as exc:
        _raise_for_status(302, "", "https://www.linkedin.com/checkpoint/lg/login")
    assert "checkpoint" in (exc.value.detail or "")


def test_redirect_without_location_still_raises():
    with pytest.raises(SessionExpired):
        _raise_for_status(302, "", None)


def test_403_carrying_the_marker_is_profile_not_found():
    """LinkedIn uses 403 for both a dead session and an unreachable profile.
    Only the body separates them; reading the status alone sends operators off
    re-copying cookies that were fine."""
    with pytest.raises(ProfileNotFound):
        _raise_for_status(403, UNREACHABLE_BODY, None)


def test_bare_403_is_session_expired():
    with pytest.raises(SessionExpired):
        _raise_for_status(403, '{"status":403}', None)


def test_401_is_session_expired():
    with pytest.raises(SessionExpired):
        _raise_for_status(401, "", None)


def test_404_is_profile_not_found():
    with pytest.raises(ProfileNotFound):
        _raise_for_status(404, "", None)


def test_410_reports_a_retired_endpoint():
    with pytest.raises(UpstreamError) as exc:
        _raise_for_status(410, '{"status":410}', None)
    assert "browser_console_probe" in (exc.value.detail or "")


@pytest.mark.parametrize("status", [400, 429, 500, 502, 503])
def test_other_failures_are_upstream_errors(status):
    with pytest.raises(UpstreamError):
        _raise_for_status(status, "", None)


def test_3xx_is_checked_before_4xx():
    """Ordering is load-bearing. A 3xx must never fall through to the >= 400
    branch, where 403-with-a-body logic would misread it."""
    with pytest.raises(SessionExpired):
        _raise_for_status(302, UNREACHABLE_BODY, "https://www.linkedin.com/")


# --- revocation vs. an ordinary redirect -------------------------------------


def test_redirect_to_self_is_reported_as_revocation():
    """LinkedIn revoking a valid session looks like a 302 back to the same URL.
    Naming it separately matters: the fix is re-copying cookies, not waiting."""
    url = "https://www.linkedin.com/voyager/api/identity/dash/profiles?q=x"
    with pytest.raises(SessionExpired) as exc:
        _raise_for_status(302, "", url, requested_url=url)
    assert "revoked" in exc.value.message.lower()


def test_clear_site_data_is_reported_as_revocation():
    with pytest.raises(SessionExpired) as exc:
        _raise_for_status(
            302, "", "https://elsewhere", clear_site_data='"storage"'
        )
    assert "revoked" in exc.value.message.lower()
    assert "storage" in (exc.value.detail or "")


def test_redirect_elsewhere_is_not_reported_as_revocation():
    with pytest.raises(SessionExpired) as exc:
        _raise_for_status(
            302,
            "",
            "https://www.linkedin.com/checkpoint/lg/login",
            requested_url="https://www.linkedin.com/voyager/api/x",
        )
    assert "revoked" not in exc.value.message.lower()

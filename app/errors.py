"""Error vocabulary. Every failure path in the app raises one of these."""

from __future__ import annotations


class LinkedInAPIError(Exception):
    """Base for everything this service raises deliberately.

    `code` is the stable machine-readable identifier clients match on; the HTTP
    status is a presentation detail that may change without the code changing.
    """

    code = "internal_error"
    http_status = 500
    default_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None, detail: str | None = None):
        self.message = message or self.default_message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict:
        error: dict[str, object] = {"code": self.code, "message": self.message}
        if self.detail:
            error["detail"] = self.detail
        return {"error": error}


class InvalidProfileURL(LinkedInAPIError):
    code = "invalid_profile_url"
    http_status = 400
    default_message = "Not a LinkedIn profile URL. Expected linkedin.com/in/<slug>."


class Unauthorized(LinkedInAPIError):
    code = "unauthorized"
    http_status = 401
    default_message = "Missing or invalid API key."


class ProfileNotFound(LinkedInAPIError):
    code = "profile_not_found"
    http_status = 404
    default_message = "Profile does not exist or is not visible to this session."


class SessionExpired(LinkedInAPIError):
    # 503 rather than 401: the caller's credentials are fine, ours are not.
    code = "session_expired"
    http_status = 503
    default_message = "The upstream LinkedIn session is no longer valid."


class UpstreamError(LinkedInAPIError):
    code = "upstream_error"
    http_status = 502
    default_message = "LinkedIn returned an unexpected response."


class UpstreamTimeout(LinkedInAPIError):
    code = "upstream_timeout"
    http_status = 504
    default_message = "LinkedIn did not respond in time."

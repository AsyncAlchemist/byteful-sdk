"""Exceptions for the byteful SDK.

The byteful API signals errors with an HTTP status code plus a JSON envelope
``{"error": "...", "message": "...", "api_request_id": "..."}``. Each
documented status code has its own subclass of :class:`BytefulAPIError`, so
callers can catch specific failure modes by class:

    try:
        client.checkout_create(product_type="isp", country_id="us", quantity=5)
    except UnauthorizedError:
        rotate_keys()
    except RateLimitedError:
        back_off()
    except UnprocessableError as e:
        log.warning("byteful rejected the request: %s (request %s)", e.message, e.api_request_id)
    except BytefulAPIError as e:
        # Catch-all for anything else
        log.error("byteful %s: %s", e.status_code, e.message)

Instantiating ``BytefulAPIError(status_code, error, message, api_request_id)``
directly will return the appropriate subclass via ``__new__`` dispatch, so the
client only needs one raise site.
"""

from __future__ import annotations

from typing import Any, ClassVar


class BytefulError(Exception):
    """Base class for all byteful SDK errors."""


class BytefulAPIError(BytefulError):
    """Raised when the API returns a non-2xx HTTP response.

    Subclasses are selected automatically based on ``status_code``. Catch this
    base class to handle any API error; catch a subclass for specific cases.
    """

    status_code: ClassVar[int] = 0
    _registry: ClassVar[dict[int, type["BytefulAPIError"]]] = {}

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        code = cls.__dict__.get("status_code")
        if code:
            existing = BytefulAPIError._registry.get(code)
            if existing is not None and existing is not cls:
                raise RuntimeError(
                    f"Duplicate status_code {code} for {cls.__name__} and {existing.__name__}"
                )
            BytefulAPIError._registry[code] = cls

    def __new__(
        cls,
        status_code: int,
        error: str = "",
        message: str = "",
        api_request_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> "BytefulAPIError":
        if cls is BytefulAPIError:
            cls = BytefulAPIError._registry.get(status_code, BytefulAPIError)
        return super().__new__(cls)

    def __init__(
        self,
        status_code: int,
        error: str = "",
        message: str = "",
        api_request_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.message = message
        self.api_request_id = api_request_id
        self.extra = extra or {}
        req = f" (request {api_request_id})" if api_request_id else ""
        super().__init__(f"byteful {status_code} {error}: {message}{req}")


class BadRequestError(BytefulAPIError):
    """400 - The request was invalid or improperly formatted."""

    status_code = 400


class UnauthorizedError(BytefulAPIError):
    """401 - Authentication credentials were missing or invalid."""

    status_code = 401


class TwoFactorAuthenticationRequired(BytefulAPIError):
    """403 with the 2FA payload variant.

    The API returns HTTP 403 with extra fields when an action needs a
    second factor. The 2FA challenge fields are surfaced as attributes:

    * :attr:`two_factor_authentication_public_key`
    * :attr:`two_factor_authentication_service`
    * :attr:`two_factor_authentication_target`

    Standard 403 responses (no 2FA payload) raise :class:`ForbiddenError`
    instead.
    """

    # Distinguished from ForbiddenError by ``extra`` carrying the 2FA fields;
    # the client dispatches manually since two classes can't share a status.
    status_code = 0

    def __init__(
        self,
        status_code: int,
        error: str = "",
        message: str = "",
        api_request_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code, error, message, api_request_id, extra)
        e = extra or {}
        self.two_factor_authentication_public_key: str | None = e.get(
            "two_factor_authentication_public_key"
        )
        self.two_factor_authentication_service: str | None = e.get(
            "two_factor_authentication_service"
        )
        self.two_factor_authentication_target: str | None = e.get(
            "two_factor_authentication_target"
        )


class ForbiddenError(BytefulAPIError):
    """403 - Authentication succeeded but you don't have permission."""

    status_code = 403


class NotFoundError(BytefulAPIError):
    """404 - The requested resource doesn't exist."""

    status_code = 404


class MethodNotAllowedError(BytefulAPIError):
    """405 - Method is not supported for this endpoint."""

    status_code = 405


class ConflictError(BytefulAPIError):
    """409 - The request conflicts with the current state."""

    status_code = 409


class UnprocessableError(BytefulAPIError):
    """422 - Well-formed but couldn't be processed due to business logic."""

    status_code = 422


class RateLimitedError(BytefulAPIError):
    """429 - Rate limit exceeded.

    The API's message typically tells you how long to wait
    ("Rate limit exceeded. Please try again in 45 seconds."). When the SDK's
    built-in :class:`~byteful.RateLimiter` is enabled this should not be
    raised in practice — every client throttles to 10 req/s by default — but
    it can still occur if you disable the limiter or run multiple processes.
    """

    status_code = 429


class InternalServerError(BytefulAPIError):
    """500 - Something went wrong on byteful's servers."""

    status_code = 500


# Documented HTTP status codes
# (https://documentation.byteful.com/api-basics/error-handling.md). Kept as a
# plain mapping for callers who want the raw documentation text.
ERROR_CODES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}

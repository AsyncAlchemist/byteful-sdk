"""Typed dataclasses for every byteful API object.

Field names mirror the API verbatim (``proxy.proxy_id``, ``proxy.proxy_status``
etc.) so anyone reading the byteful docs can map directly to attributes. The
convenience helpers (:meth:`Proxy.auth_url`, :meth:`Proxy.requests_session`,
``PageResult.iter_pages``, ...) hide the verbosity for the common cases.

Every dataclass exposes ``from_api(raw)`` which is tolerant of missing keys
(returns ``None`` rather than raising), since the byteful API omits unset
fields from responses.
"""

from __future__ import annotations

import random as _random
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Generic, Iterator, TypeVar

from .enums import (
    AsnRir,
    AsnType,
    LogNetwork,
    LogProtocol,
    LogTransport,
    ProxyProtocol,
    ProxyReplacementReason,
    ProxyStatus,
    ProxyType,
    ProxyUserAccessType,
    ServiceAdjustmentStatus,
    ServiceAdjustmentType,
    ServiceStatus,
    ServiceType,
    SubscriptionScheduleStatus,
    SubscriptionScheduleType,
)

if TYPE_CHECKING:
    import aiohttp  # noqa: F401
    import httpx
    import requests


T = TypeVar("T")


# ---- low-level coercion helpers --------------------------------------------

def _parse_dt(value: Any) -> datetime | None:
    """Tolerantly parse a byteful date-time string.

    The API uses ``"YYYY-MM-DD HH:MM:SS"`` (with a space) in most examples,
    but ISO 8601 with ``T`` shows up too. Both work.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).replace("T", " ")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _coerce_enum(enum_cls: type[T], value: Any) -> T | str | None:
    """Best-effort cast a string into an enum.

    Returns the raw string if the value is unknown to the enum (forward-compat
    with new server-side values), and ``None`` if absent.
    """
    if value is None:
        return None
    try:
        return enum_cls(value)  # type: ignore[call-arg]
    except (ValueError, KeyError):
        return str(value)


def _opt_int(v: Any) -> int | None:
    return int(v) if v is not None and v != "" else None


def _opt_float(v: Any) -> float | None:
    return float(v) if v is not None and v != "" else None


def _opt_str(v: Any) -> str | None:
    return str(v) if v is not None else None


def _opt_bool(v: Any) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _str_list(v: Any) -> list[str]:
    if not v:
        return []
    return [str(x) for x in v]


# ============================================================================
# Pagination wrapper
# ============================================================================

@dataclass(slots=True)
class PageResult(Generic[T]):
    """One page of a paginated search response.

    Wraps an offset-paginated byteful search ({page, per_page, total_count,
    item_count}) and is iterable / indexable / sized so most code can treat
    it as the underlying list.
    """

    data: list[T]
    page: int
    per_page: int
    total_count: int
    item_count: int
    message: str | None = None

    def __iter__(self) -> Iterator[T]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int) -> T:
        return self.data[index]

    def __bool__(self) -> bool:
        return bool(self.data)

    @property
    def has_more(self) -> bool:
        """``True`` if more pages remain after this one."""
        seen = self.page * self.per_page
        return seen < self.total_count

    @property
    def next_page(self) -> int | None:
        """The next page number, or ``None`` if exhausted."""
        return self.page + 1 if self.has_more else None

    @classmethod
    def from_api(
        cls,
        payload: dict[str, Any],
        item_factory: Callable[[dict[str, Any]], T],
    ) -> "PageResult[T]":
        items = [item_factory(d) for d in (payload.get("data") or [])]
        return cls(
            data=items,
            page=int(payload.get("page", 1) or 1),
            per_page=int(payload.get("per_page", len(items)) or len(items)),
            total_count=int(payload.get("total_count", len(items)) or 0),
            item_count=int(payload.get("item_count", len(items)) or 0),
            message=payload.get("message"),
        )


# ============================================================================
# Proxy — the core object the SDK is designed around.
# ============================================================================

@dataclass(slots=True)
class Proxy:
    """A single proxy on your byteful account.

    A byteful proxy has two address fields per family (``proxy_ip_address`` for
    IPv4, ``proxy_ip_address_v6`` for IPv6) and two ports
    (``proxy_http_port``, ``proxy_socks5_port``). The product (ISP/datacenter)
    is a static-IP rental; the credentials for routing through it come from a
    :class:`ProxyUser` you create separately. Each proxy also exposes a
    ``default_proxy_user_username`` / ``default_proxy_user_password`` pair
    that authenticates as your account's default proxy user — convenient for
    one-off scripts.

    The :meth:`http_url`, :meth:`socks5_url`, :meth:`auth_url`,
    :meth:`requests_session`, :meth:`httpx_client`, :meth:`httpx_async_client`
    and :meth:`aiohttp_kwargs` helpers all default to those credentials so
    most callers don't have to thread a :class:`ProxyUser` through.
    """

    proxy_id: str | None = None
    proxy_status: ProxyStatus | str | None = None
    proxy_type: ProxyType | str | None = None
    proxy_protocol: ProxyProtocol | str | None = None
    proxy_ip_address: str | None = None
    proxy_ip_address_v6: str | None = None
    proxy_http_port: int | None = None
    proxy_socks5_port: int | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None
    default_proxy_user_username: str | None = None
    default_proxy_user_password: str | None = None
    proxy_user_ids: list[str] = field(default_factory=list)
    proxy_last_update_datetime: datetime | None = None
    customer_id: int | None = None
    service_id: str | None = None
    country_id: str | None = None
    country_name: str | None = None
    subdivision_id: str | None = None
    subdivision_name: str | None = None
    city_id: int | None = None
    city_name: str | None = None
    city_timezone: str | None = None
    city_example_postcode: str | None = None
    city_latitude: float | None = None
    city_longitude: float | None = None
    asn_id: int | None = None
    asn_name: str | None = None
    subnet_id: str | None = None
    subnet_id_v6: str | None = None
    ip_address_id_v4: str | None = None
    ip_address_id_v6: str | None = None
    # Search responses include these convenience-formatted strings.
    http_formatted: str | None = None
    socks5_formatted: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Proxy":
        return cls(
            proxy_id=_opt_str(raw.get("proxy_id")),
            proxy_status=_coerce_enum(ProxyStatus, raw.get("proxy_status")),
            proxy_type=_coerce_enum(ProxyType, raw.get("proxy_type")),
            proxy_protocol=_coerce_enum(ProxyProtocol, raw.get("proxy_protocol")),
            proxy_ip_address=_opt_str(raw.get("proxy_ip_address")),
            proxy_ip_address_v6=_opt_str(raw.get("proxy_ip_address_v6")),
            proxy_http_port=_opt_int(raw.get("proxy_http_port")),
            proxy_socks5_port=_opt_int(raw.get("proxy_socks5_port")),
            proxy_username=_opt_str(raw.get("proxy_username")),
            proxy_password=_opt_str(raw.get("proxy_password")),
            default_proxy_user_username=_opt_str(raw.get("default_proxy_user_username")),
            default_proxy_user_password=_opt_str(raw.get("default_proxy_user_password")),
            proxy_user_ids=_str_list(raw.get("proxy_user_ids")),
            proxy_last_update_datetime=_parse_dt(raw.get("proxy_last_update_datetime")),
            customer_id=_opt_int(raw.get("customer_id")),
            service_id=_opt_str(raw.get("service_id")),
            country_id=_opt_str(raw.get("country_id")),
            country_name=_opt_str(raw.get("country_name")),
            subdivision_id=_opt_str(raw.get("subdivision_id")),
            subdivision_name=_opt_str(raw.get("subdivision_name")),
            city_id=_opt_int(raw.get("city_id")),
            city_name=_opt_str(raw.get("city_name")),
            city_timezone=_opt_str(raw.get("city_timezone")),
            city_example_postcode=_opt_str(raw.get("city_example_postcode")),
            city_latitude=_opt_float(raw.get("city_latitude")),
            city_longitude=_opt_float(raw.get("city_longitude")),
            asn_id=_opt_int(raw.get("asn_id")),
            asn_name=_opt_str(raw.get("asn_name")),
            subnet_id=_opt_str(raw.get("subnet_id")),
            subnet_id_v6=_opt_str(raw.get("subnet_id_v6")),
            ip_address_id_v4=_opt_str(raw.get("ip_address_id_v4")),
            ip_address_id_v6=_opt_str(raw.get("ip_address_id_v6")),
            http_formatted=_opt_str(raw.get("http_formatted")),
            socks5_formatted=_opt_str(raw.get("socks5_formatted")),
        )

    # ---- credentials resolution -------------------------------------------

    def _resolve_creds(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None",
    ) -> tuple[str, str]:
        """Return ``(username, password)`` for the auth URL.

        Resolution order: explicit ``proxy_user`` (object or ``(u, p)``
        tuple) > the proxy's ``default_proxy_user_*`` > ``proxy_username`` /
        ``proxy_password``. Raises if nothing usable is set.
        """
        if isinstance(proxy_user, ProxyUser):
            if not proxy_user.proxy_user_id or not proxy_user.proxy_user_password:
                raise ValueError(
                    "ProxyUser is missing proxy_user_id or proxy_user_password; "
                    "create() returns a fully-populated one"
                )
            return proxy_user.proxy_user_id, proxy_user.proxy_user_password
        if isinstance(proxy_user, tuple):
            u, p = proxy_user
            return str(u), str(p)
        if self.default_proxy_user_username and self.default_proxy_user_password:
            return self.default_proxy_user_username, self.default_proxy_user_password
        if self.proxy_username and self.proxy_password:
            return self.proxy_username, self.proxy_password
        raise ValueError(
            "no credentials available — pass proxy_user= explicitly or use a "
            "Proxy that has default_proxy_user_username/_password set"
        )

    def _resolve_host(self, family: str) -> str:
        """Pick the right ingress IP for the requested family.

        ``family`` is one of ``"v4"`` / ``"v6"``. Falls back to whichever
        address is set if the requested one is missing.
        """
        if family == "v6":
            return self.proxy_ip_address_v6 or self.proxy_ip_address or self._raise_no_host()
        if family == "v4":
            return self.proxy_ip_address or self.proxy_ip_address_v6 or self._raise_no_host()
        raise ValueError(f"family must be 'v4' or 'v6', got {family!r}")

    def _raise_no_host(self) -> str:
        raise ValueError("proxy has no proxy_ip_address set")

    # ---- URL builders ------------------------------------------------------

    def http_url(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        family: str = "v4",
        scheme: str = "http",
    ) -> str:
        """``http://user:pass@host:http_port`` URL."""
        user, pw = self._resolve_creds(proxy_user)
        host = self._resolve_host(family)
        if self.proxy_http_port is None:
            raise ValueError("proxy has no proxy_http_port set")
        bracketed = f"[{host}]" if ":" in host else host
        return f"{scheme}://{user}:{pw}@{bracketed}:{self.proxy_http_port}"

    def socks5_url(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        family: str = "v4",
        scheme: str = "socks5",
    ) -> str:
        """``socks5://user:pass@host:socks5_port`` URL."""
        user, pw = self._resolve_creds(proxy_user)
        host = self._resolve_host(family)
        if self.proxy_socks5_port is None:
            raise ValueError("proxy has no proxy_socks5_port set")
        bracketed = f"[{host}]" if ":" in host else host
        return f"{scheme}://{user}:{pw}@{bracketed}:{self.proxy_socks5_port}"

    def auth_url(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
    ) -> str:
        """Return a credentialed proxy URL.

        ``protocol`` is ``"http"`` (default) or ``"socks5"`` / ``"socks5h"``.
        ``family`` is ``"v4"`` (default) or ``"v6"``.
        """
        if protocol == "http":
            return self.http_url(proxy_user, family=family)
        if protocol in ("socks5", "socks5h"):
            return self.socks5_url(proxy_user, family=family, scheme=protocol)
        raise ValueError(f"protocol must be 'http', 'socks5' or 'socks5h', got {protocol!r}")

    def as_requests_dict(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
    ) -> dict[str, str]:
        """Drop-in for ``requests.get(..., proxies=proxy.as_requests_dict())``."""
        url = self.auth_url(proxy_user, protocol=protocol, family=family)
        return {"http": url, "https": url}

    def as_env(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
    ) -> dict[str, str]:
        """Env-var mapping for subprocess / shell tools (curl, wget, ...)."""
        url = self.auth_url(proxy_user, protocol=protocol, family=family)
        return {
            "HTTP_PROXY": url,
            "HTTPS_PROXY": url,
            "ALL_PROXY": url,
            "http_proxy": url,
            "https_proxy": url,
            "all_proxy": url,
        }

    def requests_session(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
        session: "requests.Session | None" = None,
    ) -> "requests.Session":
        """Return a ``requests.Session`` routed through this proxy."""
        import requests as _r

        sess = session if session is not None else _r.Session()
        sess.proxies.update(self.as_requests_dict(proxy_user, protocol=protocol, family=family))
        return sess

    def httpx_client(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
        **kwargs: Any,
    ) -> "httpx.Client":
        """Return an ``httpx.Client`` routed through this proxy."""
        import httpx

        return httpx.Client(
            proxy=self.auth_url(proxy_user, protocol=protocol, family=family),
            **kwargs,
        )

    def httpx_async_client(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
        **kwargs: Any,
    ) -> "httpx.AsyncClient":
        """Return an ``httpx.AsyncClient`` routed through this proxy."""
        import httpx

        return httpx.AsyncClient(
            proxy=self.auth_url(proxy_user, protocol=protocol, family=family),
            **kwargs,
        )

    def aiohttp_kwargs(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        protocol: str = "http",
        family: str = "v4",
    ) -> dict[str, str]:
        """Return kwargs to spread into ``aiohttp`` request calls."""
        return {"proxy": self.auth_url(proxy_user, protocol=protocol, family=family)}


# ============================================================================
# ProxyList — the cached pool with filter/random/iteration.
# ============================================================================

@dataclass(slots=True)
class ProxyList:
    """Local pool of :class:`Proxy` rows, fetched from search.

    Iterable / indexable / sized — ``for p in plist``, ``len(plist)`` and
    ``plist[0]`` all do what you'd expect. ``random()`` and ``filter()``
    are provided for the common "pool" workflow.

    Unlike :class:`PageResult`, ``ProxyList`` is the *full* pool: the cache
    on :class:`~byteful.client.BytefulClient` fetches every page once and
    flattens them into this structure.
    """

    proxies: list[Proxy] = field(default_factory=list)
    total_count: int = 0

    def __iter__(self) -> Iterator[Proxy]:
        return iter(self.proxies)

    def __len__(self) -> int:
        return len(self.proxies)

    def __getitem__(self, index: int) -> Proxy:
        return self.proxies[index]

    def __bool__(self) -> bool:
        return bool(self.proxies)

    def random(self, *, rng: _random.Random | None = None) -> Proxy:
        """Pick a uniformly-random proxy. Raises ``IndexError`` if empty."""
        if not self.proxies:
            raise IndexError("ProxyList is empty")
        chooser = rng.choice if rng is not None else _random.choice
        return chooser(self.proxies)

    def filter(
        self,
        *,
        proxy_id: str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        proxy_status: ProxyStatus | str | None = None,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_id: int | None = None,
        asn_id: int | None = None,
        service_id: str | None = None,
        proxy_user_id: str | None = None,
    ) -> "ProxyList":
        """Return a new ``ProxyList`` narrowed to matching proxies.

        Each non-``None`` argument is matched for exact equality.
        ``proxy_user_id`` matches proxies whose :attr:`Proxy.proxy_user_ids`
        list contains the given user id.
        """
        def _normalize(v: Any) -> Any:
            # Enum or string: compare by their string value.
            if hasattr(v, "value"):
                return v.value
            return v

        def _attr(p: Proxy, name: str) -> Any:
            v = getattr(p, name)
            return _normalize(v)

        criteria: dict[str, Any] = {
            "proxy_id": proxy_id,
            "proxy_type": _normalize(proxy_type),
            "proxy_protocol": _normalize(proxy_protocol),
            "proxy_status": _normalize(proxy_status),
            "country_id": country_id,
            "subdivision_id": subdivision_id,
            "city_id": city_id,
            "asn_id": asn_id,
            "service_id": service_id,
        }
        active_criteria = {k: v for k, v in criteria.items() if v is not None}

        matched: list[Proxy] = []
        for p in self.proxies:
            ok = True
            for k, v in active_criteria.items():
                if _attr(p, k) != v:
                    ok = False
                    break
            if ok and proxy_user_id is not None:
                if proxy_user_id not in (p.proxy_user_ids or []):
                    ok = False
            if ok:
                matched.append(p)
        return ProxyList(proxies=matched, total_count=len(matched))


# ============================================================================
# Customer
# ============================================================================

@dataclass(slots=True)
class Customer:
    customer_id: int | None = None
    customer_email_address: str | None = None
    customer_first_name: str | None = None
    customer_last_name: str | None = None
    customer_billing_name: str | None = None
    customer_billing_line_one: str | None = None
    customer_billing_line_two: str | None = None
    customer_billing_subdivision_name: str | None = None
    customer_billing_zip_code: str | None = None
    country_id: str | None = None
    country_id_billing: str | None = None
    credit_balance: int | None = None
    customer_creation_datetime: datetime | None = None
    customer_last_login_datetime: datetime | None = None
    customer_last_update_datetime: datetime | None = None
    customer_general_terms_agreement_datetime: datetime | None = None
    customer_iso_language_code: str | None = None
    customer_kyc_level: int | None = None
    customer_email_two_factor_authentication: bool | None = None
    customer_phone_number: str | None = None
    customer_profile_image_url: str | None = None
    customer_proxy_user_limit: int | None = None
    customer_dob: str | None = None
    customer_requires_information_confirm: bool | None = None
    customer_requires_password_change: bool | None = None
    customer_discord_id: str | None = None
    customer_discord_oauth_id: str | None = None
    customer_google_oauth_id: str | None = None
    customer_is_residential_trial_eligible: bool | None = None
    customer_residential_trial_disallow_reason: str | None = None
    customer_default_residential_free_trial_bytes: int | None = None
    free_trial_is_pending: bool | None = None
    kyc_is_pending: bool | None = None
    active_service_types: list[str] = field(default_factory=list)
    active_mobile_service_id: str | None = None
    active_mobile_service_is_paused: bool | None = None
    active_residential_service_id: str | None = None
    active_residential_service_subscription_is_paused: bool | None = None
    residential_bytes_left: int | None = None
    mobile_bytes_left: int | None = None
    proxy_count: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Customer":
        return cls(
            customer_id=_opt_int(raw.get("customer_id")),
            customer_email_address=_opt_str(raw.get("customer_email_address")),
            customer_first_name=_opt_str(raw.get("customer_first_name")),
            customer_last_name=_opt_str(raw.get("customer_last_name")),
            customer_billing_name=_opt_str(raw.get("customer_billing_name")),
            customer_billing_line_one=_opt_str(raw.get("customer_billing_line_one")),
            customer_billing_line_two=_opt_str(raw.get("customer_billing_line_two")),
            customer_billing_subdivision_name=_opt_str(
                raw.get("customer_billing_subdivision_name")
            ),
            customer_billing_zip_code=_opt_str(raw.get("customer_billing_zip_code")),
            country_id=_opt_str(raw.get("country_id")),
            country_id_billing=_opt_str(raw.get("country_id_billing")),
            credit_balance=_opt_int(raw.get("credit_balance")),
            customer_creation_datetime=_parse_dt(raw.get("customer_creation_datetime")),
            customer_last_login_datetime=_parse_dt(raw.get("customer_last_login_datetime")),
            customer_last_update_datetime=_parse_dt(raw.get("customer_last_update_datetime")),
            customer_general_terms_agreement_datetime=_parse_dt(
                raw.get("customer_general_terms_agreement_datetime")
            ),
            customer_iso_language_code=_opt_str(raw.get("customer_iso_language_code")),
            customer_kyc_level=_opt_int(raw.get("customer_kyc_level")),
            customer_email_two_factor_authentication=_opt_bool(
                raw.get("customer_email_two_factor_authentication")
            ),
            customer_phone_number=_opt_str(raw.get("customer_phone_number")),
            customer_profile_image_url=_opt_str(raw.get("customer_profile_image_url")),
            customer_proxy_user_limit=_opt_int(raw.get("customer_proxy_user_limit")),
            customer_dob=_opt_str(raw.get("customer_dob")),
            customer_requires_information_confirm=_opt_bool(
                raw.get("customer_requires_information_confirm")
            ),
            customer_requires_password_change=_opt_bool(
                raw.get("customer_requires_password_change")
            ),
            customer_discord_id=_opt_str(raw.get("customer_discord_id")),
            customer_discord_oauth_id=_opt_str(raw.get("customer_discord_oauth_id")),
            customer_google_oauth_id=_opt_str(raw.get("customer_google_oauth_id")),
            customer_is_residential_trial_eligible=_opt_bool(
                raw.get("customer_is_residential_trial_eligible")
            ),
            customer_residential_trial_disallow_reason=_opt_str(
                raw.get("customer_residential_trial_disallow_reason")
            ),
            customer_default_residential_free_trial_bytes=_opt_int(
                raw.get("customer_default_residential_free_trial_bytes")
            ),
            free_trial_is_pending=_opt_bool(raw.get("free_trial_is_pending")),
            kyc_is_pending=_opt_bool(raw.get("kyc_is_pending")),
            active_service_types=_str_list(raw.get("active_service_types")),
            active_mobile_service_id=_opt_str(raw.get("active_mobile_service_id")),
            active_mobile_service_is_paused=_opt_bool(
                raw.get("active_mobile_service_is_paused")
            ),
            active_residential_service_id=_opt_str(raw.get("active_residential_service_id")),
            active_residential_service_subscription_is_paused=_opt_bool(
                raw.get("active_residential_service_subscription_is_paused")
            ),
            residential_bytes_left=_opt_int(raw.get("residential_bytes_left")),
            mobile_bytes_left=_opt_int(raw.get("mobile_bytes_left")),
            proxy_count=_opt_int(raw.get("proxy_count")),
        )


# ============================================================================
# Service
# ============================================================================

@dataclass(slots=True)
class Service:
    service_id: str | None = None
    service_name: str | None = None
    service_status: ServiceStatus | str | None = None
    service_type: ServiceType | str | None = None
    service_protocol: ProxyProtocol | str | None = None
    service_quantity: int | None = None
    service_total: int | None = None
    service_cycle: str | None = None
    service_image: str | None = None
    service_promotional_code: str | None = None
    service_metadata: dict[str, Any] = field(default_factory=dict)
    service_is_automatic_collection: bool | None = None
    service_is_pending_cancellation: bool | None = None
    service_subscription_id: str | None = None
    service_subscription_is_paused: bool | None = None
    subscription_schedule_id: str | None = None
    service_creation_datetime: datetime | None = None
    service_dispatch_datetime: datetime | None = None
    service_expiry_datetime: datetime | None = None
    service_earliest_cancellation_datetime: datetime | None = None
    service_last_update_datetime: datetime | None = None
    country_id: str | None = None
    payment_method_id: str | None = None
    open_invoice_id: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Service":
        return cls(
            service_id=_opt_str(raw.get("service_id")),
            service_name=_opt_str(raw.get("service_name")),
            service_status=_coerce_enum(ServiceStatus, raw.get("service_status")),
            service_type=_coerce_enum(ServiceType, raw.get("service_type")),
            service_protocol=_coerce_enum(ProxyProtocol, raw.get("service_protocol")),
            service_quantity=_opt_int(raw.get("service_quantity")),
            service_total=_opt_int(raw.get("service_total")),
            service_cycle=_opt_str(raw.get("service_cycle")),
            service_image=_opt_str(raw.get("service_image")),
            service_promotional_code=_opt_str(raw.get("service_promotional_code")),
            service_metadata=raw.get("service_metadata") or {},
            service_is_automatic_collection=_opt_bool(raw.get("service_is_automatic_collection")),
            service_is_pending_cancellation=_opt_bool(raw.get("service_is_pending_cancellation")),
            service_subscription_id=_opt_str(raw.get("service_subscription_id")),
            service_subscription_is_paused=_opt_bool(raw.get("service_subscription_is_paused")),
            subscription_schedule_id=_opt_str(raw.get("subscription_schedule_id")),
            service_creation_datetime=_parse_dt(raw.get("service_creation_datetime")),
            service_dispatch_datetime=_parse_dt(raw.get("service_dispatch_datetime")),
            service_expiry_datetime=_parse_dt(raw.get("service_expiry_datetime")),
            service_earliest_cancellation_datetime=_parse_dt(
                raw.get("service_earliest_cancellation_datetime")
            ),
            service_last_update_datetime=_parse_dt(raw.get("service_last_update_datetime")),
            country_id=_opt_str(raw.get("country_id")),
            payment_method_id=_opt_str(raw.get("payment_method_id")),
            open_invoice_id=_opt_str(raw.get("open_invoice_id")),
        )


# ============================================================================
# ProxyUser + ProxyUserAcl
# ============================================================================

@dataclass(slots=True)
class ProxyUser:
    proxy_user_id: str | None = None
    proxy_user_password: str | None = None
    proxy_user_access_type: ProxyUserAccessType | str | None = None
    proxy_user_is_default: bool | None = None
    proxy_user_is_deleted: bool | None = None
    proxy_user_is_strict_security: bool | None = None
    proxy_user_enforce_https: bool | None = None
    proxy_user_ip_address_authentication_limit: int | None = None
    ip_address_authentications: list[str] = field(default_factory=list)
    restricted_proxy_ids: list[str] = field(default_factory=list)
    restricted_service_ids: list[str] = field(default_factory=list)
    proxy_user_residential_bytes_limit: int | None = None
    proxy_user_residential_bytes_used: int | None = None
    residential_bytes_left: int | None = None
    proxy_user_mobile_bytes_limit: int | None = None
    proxy_user_mobile_bytes_used: int | None = None
    mobile_bytes_left: int | None = None
    proxy_user_metadata: dict[str, Any] = field(default_factory=dict)
    customer_id: int | None = None
    proxy_user_creation_datetime: datetime | None = None
    proxy_user_last_update_datetime: datetime | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ProxyUser":
        return cls(
            proxy_user_id=_opt_str(raw.get("proxy_user_id")),
            proxy_user_password=_opt_str(raw.get("proxy_user_password")),
            proxy_user_access_type=_coerce_enum(
                ProxyUserAccessType, raw.get("proxy_user_access_type")
            ),
            proxy_user_is_default=_opt_bool(raw.get("proxy_user_is_default")),
            proxy_user_is_deleted=_opt_bool(raw.get("proxy_user_is_deleted")),
            proxy_user_is_strict_security=_opt_bool(raw.get("proxy_user_is_strict_security")),
            proxy_user_enforce_https=_opt_bool(raw.get("proxy_user_enforce_https")),
            proxy_user_ip_address_authentication_limit=_opt_int(
                raw.get("proxy_user_ip_address_authentication_limit")
            ),
            ip_address_authentications=_str_list(raw.get("ip_address_authentications")),
            restricted_proxy_ids=_str_list(raw.get("restricted_proxy_ids")),
            restricted_service_ids=_str_list(raw.get("restricted_service_ids")),
            proxy_user_residential_bytes_limit=_opt_int(
                raw.get("proxy_user_residential_bytes_limit")
            ),
            proxy_user_residential_bytes_used=_opt_int(
                raw.get("proxy_user_residential_bytes_used")
            ),
            residential_bytes_left=_opt_int(raw.get("residential_bytes_left")),
            proxy_user_mobile_bytes_limit=_opt_int(raw.get("proxy_user_mobile_bytes_limit")),
            proxy_user_mobile_bytes_used=_opt_int(raw.get("proxy_user_mobile_bytes_used")),
            mobile_bytes_left=_opt_int(raw.get("mobile_bytes_left")),
            proxy_user_metadata=raw.get("proxy_user_metadata") or {},
            customer_id=_opt_int(raw.get("customer_id")),
            proxy_user_creation_datetime=_parse_dt(raw.get("proxy_user_creation_datetime")),
            proxy_user_last_update_datetime=_parse_dt(
                raw.get("proxy_user_last_update_datetime")
            ),
        )


@dataclass(slots=True)
class ProxyUserAcl:
    proxy_user_acl_id: str | None = None
    proxy_user_id: str | None = None
    proxy_id: str | None = None
    service_id: str | None = None
    proxy_user_acl_creation_datetime: datetime | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ProxyUserAcl":
        return cls(
            proxy_user_acl_id=_opt_str(raw.get("proxy_user_acl_id")),
            proxy_user_id=_opt_str(raw.get("proxy_user_id")),
            proxy_id=_opt_str(raw.get("proxy_id")),
            service_id=_opt_str(raw.get("service_id")),
            proxy_user_acl_creation_datetime=_parse_dt(
                raw.get("proxy_user_acl_creation_datetime")
            ),
        )


# ============================================================================
# Geographic resources (Country, City, Subdivision, ZipCode, Continent, Asn)
# ============================================================================

@dataclass(slots=True)
class Country:
    country_id: str | None = None
    country_name: str | None = None
    country_alias: str | None = None
    continent_id: str | None = None
    country_is_european_union: bool | None = None
    country_node_count: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Country":
        return cls(
            country_id=_opt_str(raw.get("country_id")),
            country_name=_opt_str(raw.get("country_name")),
            country_alias=_opt_str(raw.get("country_alias")),
            continent_id=_opt_str(raw.get("continent_id")),
            country_is_european_union=_opt_bool(raw.get("country_is_european_union")),
            country_node_count=_opt_int(raw.get("country_node_count")),
        )


@dataclass(slots=True)
class City:
    city_id: int | None = None
    city_name: str | None = None
    city_alias: str | None = None
    city_timezone: str | None = None
    city_is_populous: bool | None = None
    city_example_postcode: str | None = None
    city_latitude: float | None = None
    city_longitude: float | None = None
    city_population: int | None = None
    city_node_count: int | None = None
    city_creation_datetime: datetime | None = None
    city_last_update_datetime: datetime | None = None
    subdivision_id: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "City":
        return cls(
            city_id=_opt_int(raw.get("city_id")),
            city_name=_opt_str(raw.get("city_name")),
            city_alias=_opt_str(raw.get("city_alias")),
            city_timezone=_opt_str(raw.get("city_timezone")),
            city_is_populous=_opt_bool(raw.get("city_is_populous")),
            city_example_postcode=_opt_str(raw.get("city_example_postcode")),
            city_latitude=_opt_float(raw.get("city_latitude")),
            city_longitude=_opt_float(raw.get("city_longitude")),
            city_population=_opt_int(raw.get("city_population")),
            city_node_count=_opt_int(raw.get("city_node_count")),
            city_creation_datetime=_parse_dt(raw.get("city_creation_datetime")),
            city_last_update_datetime=_parse_dt(raw.get("city_last_update_datetime")),
            subdivision_id=_opt_str(raw.get("subdivision_id")),
        )


@dataclass(slots=True)
class Subdivision:
    subdivision_id: str | None = None
    subdivision_name: str | None = None
    subdivision_alias: str | None = None
    country_id: str | None = None
    subdivision_node_count: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Subdivision":
        return cls(
            subdivision_id=_opt_str(raw.get("subdivision_id")),
            subdivision_name=_opt_str(raw.get("subdivision_name")),
            subdivision_alias=_opt_str(raw.get("subdivision_alias")),
            country_id=_opt_str(raw.get("country_id")),
            subdivision_node_count=_opt_int(raw.get("subdivision_node_count")),
        )


@dataclass(slots=True)
class ZipCode:
    zip_code_id: int | None = None
    zip_code_alias: str | None = None
    subdivision_id: str | None = None
    zip_code_node_count: int | None = None
    zip_code_creation_datetime: datetime | None = None
    zip_code_last_update_datetime: datetime | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ZipCode":
        return cls(
            zip_code_id=_opt_int(raw.get("zip_code_id")),
            zip_code_alias=_opt_str(raw.get("zip_code_alias")),
            subdivision_id=_opt_str(raw.get("subdivision_id")),
            zip_code_node_count=_opt_int(raw.get("zip_code_node_count")),
            zip_code_creation_datetime=_parse_dt(raw.get("zip_code_creation_datetime")),
            zip_code_last_update_datetime=_parse_dt(
                raw.get("zip_code_last_update_datetime")
            ),
        )


@dataclass(slots=True)
class Continent:
    continent_id: str | None = None
    continent_name: str | None = None
    continent_alias: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Continent":
        return cls(
            continent_id=_opt_str(raw.get("continent_id")),
            continent_name=_opt_str(raw.get("continent_name")),
            continent_alias=_opt_str(raw.get("continent_alias")),
        )


@dataclass(slots=True)
class Asn:
    asn_id: int | None = None
    asn_name: str | None = None
    asn_type: AsnType | str | None = None
    asn_rir: AsnRir | str | None = None
    country_id: str | None = None
    asn_ip_address_count: int | None = None
    asn_node_count: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Asn":
        return cls(
            asn_id=_opt_int(raw.get("asn_id")),
            asn_name=_opt_str(raw.get("asn_name")),
            asn_type=_coerce_enum(AsnType, raw.get("asn_type")),
            asn_rir=_coerce_enum(AsnRir, raw.get("asn_rir")),
            country_id=_opt_str(raw.get("country_id")),
            asn_ip_address_count=_opt_int(raw.get("asn_ip_address_count")),
            asn_node_count=_opt_int(raw.get("asn_node_count")),
        )


# ============================================================================
# Logs / analytics / ledgers
# ============================================================================

@dataclass(slots=True)
class Log:
    log_id: str | None = None
    log_request_datetime: datetime | None = None
    log_network: LogNetwork | str | None = None
    log_protocol: LogProtocol | str | None = None
    log_protocol_version: str | None = None
    log_transport: LogTransport | str | None = None
    log_method: str | None = None
    log_hostname: str | None = None
    log_status_code: int | None = None
    log_session_id: str | None = None
    log_total_bytes: int | None = None
    log_total_elapsed_ms: int | None = None
    log_handshake_elapsed_ms: int | None = None
    log_tunnel_elapsed_ms: int | None = None
    log_concurrency: int | None = None
    log_is_tls_enabled: bool | None = None
    log_smartpath_enabled: bool | None = None
    log_smartpath_routed: bool | None = None
    log_authentication_type: int | None = None
    log_client_ip_address: str | None = None
    log_local_ip_address: str | None = None
    log_local_port: int | None = None
    log_egress_ip_address: str | None = None
    customer_id: int | None = None
    proxy_id: str | None = None
    proxy_user_id: str | None = None
    service_id: str | None = None
    asn_id: int | None = None
    city_alias: str | None = None
    country_id: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Log":
        return cls(
            log_id=_opt_str(raw.get("log_id")),
            log_request_datetime=_parse_dt(raw.get("log_request_datetime")),
            log_network=_coerce_enum(LogNetwork, raw.get("log_network")),
            log_protocol=_coerce_enum(LogProtocol, raw.get("log_protocol")),
            log_protocol_version=_opt_str(raw.get("log_protocol_version")),
            log_transport=_coerce_enum(LogTransport, raw.get("log_transport")),
            log_method=_opt_str(raw.get("log_method")),
            log_hostname=_opt_str(raw.get("log_hostname")),
            log_status_code=_opt_int(raw.get("log_status_code")),
            log_session_id=_opt_str(raw.get("log_session_id")),
            log_total_bytes=_opt_int(raw.get("log_total_bytes")),
            log_total_elapsed_ms=_opt_int(raw.get("log_total_elapsed_ms")),
            log_handshake_elapsed_ms=_opt_int(raw.get("log_handshake_elapsed_ms")),
            log_tunnel_elapsed_ms=_opt_int(raw.get("log_tunnel_elapsed_ms")),
            log_concurrency=_opt_int(raw.get("log_concurrency")),
            log_is_tls_enabled=_opt_bool(raw.get("log_is_tls_enabled")),
            log_smartpath_enabled=_opt_bool(raw.get("log_smartpath_enabled")),
            log_smartpath_routed=_opt_bool(raw.get("log_smartpath_routed")),
            log_authentication_type=_opt_int(raw.get("log_authentication_type")),
            log_client_ip_address=_opt_str(raw.get("log_client_ip_address")),
            log_local_ip_address=_opt_str(raw.get("log_local_ip_address")),
            log_local_port=_opt_int(raw.get("log_local_port")),
            log_egress_ip_address=_opt_str(raw.get("log_egress_ip_address")),
            customer_id=_opt_int(raw.get("customer_id")),
            proxy_id=_opt_str(raw.get("proxy_id")),
            proxy_user_id=_opt_str(raw.get("proxy_user_id")),
            service_id=_opt_str(raw.get("service_id")),
            asn_id=_opt_int(raw.get("asn_id")),
            city_alias=_opt_str(raw.get("city_alias")),
            country_id=_opt_str(raw.get("country_id")),
        )


@dataclass(slots=True)
class LogSummary:
    log_summary_id: str | None = None
    log_summary_period: datetime | None = None
    log_summary_network: LogNetwork | str | None = None
    log_summary_hostname: str | None = None
    log_summary_domain: str | None = None
    log_summary_requests: int | None = None
    log_summary_bytes: int | None = None
    log_summary_charged_requests: int | None = None
    log_summary_charged_bytes: int | None = None
    log_summary_smartpath_enabled_requests: int | None = None
    log_summary_smartpath_enabled_bytes: int | None = None
    log_summary_smartpath_routed_requests: int | None = None
    log_summary_smartpath_routed_bytes: int | None = None
    log_summary_creation_datetime: datetime | None = None
    log_summary_last_update_datetime: datetime | None = None
    customer_id: int | None = None
    proxy_user_id: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "LogSummary":
        return cls(
            log_summary_id=_opt_str(raw.get("log_summary_id")),
            log_summary_period=_parse_dt(raw.get("log_summary_period")),
            log_summary_network=_coerce_enum(LogNetwork, raw.get("log_summary_network")),
            log_summary_hostname=_opt_str(raw.get("log_summary_hostname")),
            log_summary_domain=_opt_str(raw.get("log_summary_domain")),
            log_summary_requests=_opt_int(raw.get("log_summary_requests")),
            log_summary_bytes=_opt_int(raw.get("log_summary_bytes")),
            log_summary_charged_requests=_opt_int(raw.get("log_summary_charged_requests")),
            log_summary_charged_bytes=_opt_int(raw.get("log_summary_charged_bytes")),
            log_summary_smartpath_enabled_requests=_opt_int(
                raw.get("log_summary_smartpath_enabled_requests")
            ),
            log_summary_smartpath_enabled_bytes=_opt_int(
                raw.get("log_summary_smartpath_enabled_bytes")
            ),
            log_summary_smartpath_routed_requests=_opt_int(
                raw.get("log_summary_smartpath_routed_requests")
            ),
            log_summary_smartpath_routed_bytes=_opt_int(
                raw.get("log_summary_smartpath_routed_bytes")
            ),
            log_summary_creation_datetime=_parse_dt(raw.get("log_summary_creation_datetime")),
            log_summary_last_update_datetime=_parse_dt(
                raw.get("log_summary_last_update_datetime")
            ),
            customer_id=_opt_int(raw.get("customer_id")),
            proxy_user_id=_opt_str(raw.get("proxy_user_id")),
        )


@dataclass(slots=True)
class MobileLedger:
    mobile_ledger_id: str | None = None
    mobile_ledger_reason: str | None = None
    mobile_ledger_bytes: int | None = None
    mobile_ledger_requests: int | None = None
    mobile_ledger_period_date: str | None = None
    mobile_ledger_creation_datetime: datetime | None = None
    mobile_ledger_last_update_datetime: datetime | None = None
    customer_id: int | None = None
    service_id: str | None = None
    service_adjustment_id: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "MobileLedger":
        return cls(
            mobile_ledger_id=_opt_str(raw.get("mobile_ledger_id")),
            mobile_ledger_reason=_opt_str(raw.get("mobile_ledger_reason")),
            mobile_ledger_bytes=_opt_int(raw.get("mobile_ledger_bytes")),
            mobile_ledger_requests=_opt_int(raw.get("mobile_ledger_requests")),
            mobile_ledger_period_date=_opt_str(raw.get("mobile_ledger_period_date")),
            mobile_ledger_creation_datetime=_parse_dt(
                raw.get("mobile_ledger_creation_datetime")
            ),
            mobile_ledger_last_update_datetime=_parse_dt(
                raw.get("mobile_ledger_last_update_datetime")
            ),
            customer_id=_opt_int(raw.get("customer_id")),
            service_id=_opt_str(raw.get("service_id")),
            service_adjustment_id=_opt_int(raw.get("service_adjustment_id")),
        )


@dataclass(slots=True)
class ResidentialLedger:
    residential_ledger_id: str | None = None
    residential_ledger_reason: str | None = None
    residential_ledger_bytes: int | None = None
    residential_ledger_requests: int | None = None
    residential_ledger_period_date: str | None = None
    residential_ledger_creation_datetime: datetime | None = None
    residential_ledger_last_update_datetime: datetime | None = None
    customer_id: int | None = None
    service_id: str | None = None
    service_adjustment_id: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ResidentialLedger":
        return cls(
            residential_ledger_id=_opt_str(raw.get("residential_ledger_id")),
            residential_ledger_reason=_opt_str(raw.get("residential_ledger_reason")),
            residential_ledger_bytes=_opt_int(raw.get("residential_ledger_bytes")),
            residential_ledger_requests=_opt_int(raw.get("residential_ledger_requests")),
            residential_ledger_period_date=_opt_str(raw.get("residential_ledger_period_date")),
            residential_ledger_creation_datetime=_parse_dt(
                raw.get("residential_ledger_creation_datetime")
            ),
            residential_ledger_last_update_datetime=_parse_dt(
                raw.get("residential_ledger_last_update_datetime")
            ),
            customer_id=_opt_int(raw.get("customer_id")),
            service_id=_opt_str(raw.get("service_id")),
            service_adjustment_id=_opt_int(raw.get("service_adjustment_id")),
        )


@dataclass(slots=True)
class ServiceAdjustment:
    service_adjustment_id: int | None = None
    service_adjustment_type: ServiceAdjustmentType | str | None = None
    service_adjustment_status: ServiceAdjustmentStatus | str | None = None
    service_adjustment_pre: dict[str, Any] = field(default_factory=dict)
    service_adjustment_post: dict[str, Any] = field(default_factory=dict)
    service_adjustment_eval: dict[str, Any] = field(default_factory=dict)
    service_adjustment_is_administrator: bool | None = None
    service_adjustment_is_automatic: bool | None = None
    service_adjustment_is_customer: bool | None = None
    service_adjustment_creation_datetime: datetime | None = None
    service_adjustment_last_update_datetime: datetime | None = None
    service_id: str | None = None
    invoice_id: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ServiceAdjustment":
        return cls(
            service_adjustment_id=_opt_int(raw.get("service_adjustment_id")),
            service_adjustment_type=_coerce_enum(
                ServiceAdjustmentType, raw.get("service_adjustment_type")
            ),
            service_adjustment_status=_coerce_enum(
                ServiceAdjustmentStatus, raw.get("service_adjustment_status")
            ),
            service_adjustment_pre=raw.get("service_adjustment_pre") or {},
            service_adjustment_post=raw.get("service_adjustment_post") or {},
            service_adjustment_eval=raw.get("service_adjustment_eval") or {},
            service_adjustment_is_administrator=_opt_bool(
                raw.get("service_adjustment_is_administrator")
            ),
            service_adjustment_is_automatic=_opt_bool(
                raw.get("service_adjustment_is_automatic")
            ),
            service_adjustment_is_customer=_opt_bool(raw.get("service_adjustment_is_customer")),
            service_adjustment_creation_datetime=_parse_dt(
                raw.get("service_adjustment_creation_datetime")
            ),
            service_adjustment_last_update_datetime=_parse_dt(
                raw.get("service_adjustment_last_update_datetime")
            ),
            service_id=_opt_str(raw.get("service_id")),
            invoice_id=_opt_str(raw.get("invoice_id")),
        )


# ============================================================================
# Availability / test servers / replacements
# ============================================================================

@dataclass(slots=True)
class MobileAvailability:
    country_id: str | None = None
    country_name: str | None = None
    subdivision_id: str | None = None
    subdivision_name: str | None = None
    city_id: int | None = None
    city_name: str | None = None
    zip_code_id: int | None = None
    zip_code_alias: str | None = None
    asn_id: int | None = None
    asn_name: str | None = None
    mobile_availability_is_available: bool | None = None
    mobile_availability_node_count: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any] | str) -> "MobileAvailability":
        # The availability/search endpoint collapses to a flat list of bare
        # string IDs when no ``group_by`` is supplied (the implicit grouping
        # is by country). Wrap so the rest of the constructor still works.
        if isinstance(raw, str):
            raw = {"country_id": raw}
        return cls(
            country_id=_opt_str(raw.get("country_id")),
            country_name=_opt_str(raw.get("country_name")),
            subdivision_id=_opt_str(raw.get("subdivision_id")),
            subdivision_name=_opt_str(raw.get("subdivision_name")),
            city_id=_opt_int(raw.get("city_id")),
            city_name=_opt_str(raw.get("city_name")),
            zip_code_id=_opt_int(raw.get("zip_code_id")),
            zip_code_alias=_opt_str(raw.get("zip_code_alias")),
            asn_id=_opt_int(raw.get("asn_id")),
            asn_name=_opt_str(raw.get("asn_name")),
            mobile_availability_is_available=_opt_bool(
                raw.get("mobile_availability_is_available")
            ),
            mobile_availability_node_count=_opt_int(
                raw.get("mobile_availability_node_count")
            ),
        )


@dataclass(slots=True)
class ResidentialAvailability:
    """Same shape as :class:`MobileAvailability` but for residential."""

    country_id: str | None = None
    country_name: str | None = None
    subdivision_id: str | None = None
    subdivision_name: str | None = None
    city_id: int | None = None
    city_name: str | None = None
    zip_code_id: int | None = None
    zip_code_alias: str | None = None
    asn_id: int | None = None
    asn_name: str | None = None
    residential_availability_is_available: bool | None = None
    residential_availability_node_count: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any] | str) -> "ResidentialAvailability":
        # See note on :meth:`MobileAvailability.from_api`.
        if isinstance(raw, str):
            raw = {"country_id": raw}
        return cls(
            country_id=_opt_str(raw.get("country_id")),
            country_name=_opt_str(raw.get("country_name")),
            subdivision_id=_opt_str(raw.get("subdivision_id")),
            subdivision_name=_opt_str(raw.get("subdivision_name")),
            city_id=_opt_int(raw.get("city_id")),
            city_name=_opt_str(raw.get("city_name")),
            zip_code_id=_opt_int(raw.get("zip_code_id")),
            zip_code_alias=_opt_str(raw.get("zip_code_alias")),
            asn_id=_opt_int(raw.get("asn_id")),
            asn_name=_opt_str(raw.get("asn_name")),
            residential_availability_is_available=_opt_bool(
                raw.get("residential_availability_is_available")
            ),
            residential_availability_node_count=_opt_int(
                raw.get("residential_availability_node_count")
            ),
        )


@dataclass(slots=True)
class ProxyTestServer:
    proxy_test_server_id: str | None = None
    country_id: str | None = None
    city_id: int | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ProxyTestServer":
        return cls(
            proxy_test_server_id=_opt_str(raw.get("proxy_test_server_id")),
            country_id=_opt_str(raw.get("country_id")),
            city_id=_opt_int(raw.get("city_id")),
        )


@dataclass(slots=True)
class ProxyReplacement:
    proxy_replacement_id: int | None = None
    proxy_replacement_reason: ProxyReplacementReason | str | None = None
    proxy_replacement_ip_address_ipv4: str | None = None
    proxy_replacement_ip_address_ipv6: str | None = None
    proxy_replacement_http_port: int | None = None
    proxy_replacement_socks5_port: int | None = None
    proxy_replacement_new_ip_address_ipv4: str | None = None
    proxy_replacement_new_ip_address_ipv6: str | None = None
    proxy_replacement_new_http_port: int | None = None
    proxy_replacement_new_socks5_port: int | None = None
    proxy_replacement_creation_datetime: datetime | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ProxyReplacement":
        return cls(
            proxy_replacement_id=_opt_int(raw.get("proxy_replacement_id")),
            proxy_replacement_reason=_coerce_enum(
                ProxyReplacementReason, raw.get("proxy_replacement_reason")
            ),
            proxy_replacement_ip_address_ipv4=_opt_str(
                raw.get("proxy_replacement_ip_address_ipv4")
            ),
            proxy_replacement_ip_address_ipv6=_opt_str(
                raw.get("proxy_replacement_ip_address_ipv6")
            ),
            proxy_replacement_http_port=_opt_int(raw.get("proxy_replacement_http_port")),
            proxy_replacement_socks5_port=_opt_int(raw.get("proxy_replacement_socks5_port")),
            proxy_replacement_new_ip_address_ipv4=_opt_str(
                raw.get("proxy_replacement_new_ip_address_ipv4")
            ),
            proxy_replacement_new_ip_address_ipv6=_opt_str(
                raw.get("proxy_replacement_new_ip_address_ipv6")
            ),
            proxy_replacement_new_http_port=_opt_int(
                raw.get("proxy_replacement_new_http_port")
            ),
            proxy_replacement_new_socks5_port=_opt_int(
                raw.get("proxy_replacement_new_socks5_port")
            ),
            proxy_replacement_creation_datetime=_parse_dt(
                raw.get("proxy_replacement_creation_datetime")
            ),
        )


@dataclass(slots=True)
class SubscriptionSchedule:
    subscription_schedule_id: str | None = None
    subscription_schedule_status: SubscriptionScheduleStatus | str | None = None
    subscription_schedule_type: SubscriptionScheduleType | str | None = None
    subscription_schedule_datetime: datetime | None = None
    subscription_schedule_is_administrator: bool | None = None
    subscription_schedule_creation_datetime: datetime | None = None
    subscription_schedule_last_update_datetime: datetime | None = None
    customer_id: int | None = None
    service_subscription_id: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "SubscriptionSchedule":
        return cls(
            subscription_schedule_id=_opt_str(raw.get("subscription_schedule_id")),
            subscription_schedule_status=_coerce_enum(
                SubscriptionScheduleStatus, raw.get("subscription_schedule_status")
            ),
            subscription_schedule_type=_coerce_enum(
                SubscriptionScheduleType, raw.get("subscription_schedule_type")
            ),
            subscription_schedule_datetime=_parse_dt(
                raw.get("subscription_schedule_datetime")
            ),
            subscription_schedule_is_administrator=_opt_bool(
                raw.get("subscription_schedule_is_administrator")
            ),
            subscription_schedule_creation_datetime=_parse_dt(
                raw.get("subscription_schedule_creation_datetime")
            ),
            subscription_schedule_last_update_datetime=_parse_dt(
                raw.get("subscription_schedule_last_update_datetime")
            ),
            customer_id=_opt_int(raw.get("customer_id")),
            service_subscription_id=_opt_str(raw.get("service_subscription_id")),
        )


# ============================================================================
# Operation result envelopes (create/edit/delete, generated lists, etc.)
# ============================================================================

@dataclass(slots=True)
class CreatedResult(Generic[T]):
    """Result of a ``POST .../create`` endpoint.

    The byteful API returns ``{"created": [id, ...], "data": {...},
    "message": "..."}`` for create operations. ``data`` is parsed into a
    type-specific object; ``created`` lists the IDs that came back.
    """

    created: list[str]
    data: T
    message: str | None = None


@dataclass(slots=True)
class EditedResult:
    """Result of a ``PATCH .../edit/{id}`` endpoint."""

    edited: list[str]
    message: str | None = None
    proxy_user_acl_deleted: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "EditedResult":
        known = {"edited", "message", "proxy_user_acl_deleted"}
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            edited=_str_list(raw.get("edited")),
            message=_opt_str(raw.get("message")),
            proxy_user_acl_deleted=_str_list(raw.get("proxy_user_acl_deleted")),
            extra=extra,
        )


@dataclass(slots=True)
class DeletedResult:
    """Result of a ``DELETE .../delete/{id}`` or ``.../cancel/{id}`` endpoint."""

    deleted: list[str]
    message: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "DeletedResult":
        known = {"deleted", "message"}
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            deleted=_str_list(raw.get("deleted") or raw.get("canceled")),
            message=_opt_str(raw.get("message")),
            extra=extra,
        )


@dataclass(slots=True)
class GeneratedProxyList:
    """Result of the ``/proxy/list_by_search``, ``/proxy/list_by_id``,
    ``/mobile/list`` and ``/residential/list`` endpoints.

    These endpoints return formatted strings ready to feed into other
    tools — ``"ip:port:user:pass"`` lines, full URLs, etc. — rather than
    structured proxy records.
    """

    data: list[str] = field(default_factory=list)
    message: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[str]:
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int) -> str:
        return self.data[index]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "GeneratedProxyList":
        data_raw = raw.get("data") or []
        # The API returns either a list of strings or list of objects depending
        # on list_format. Normalize to strings where possible.
        items: list[str] = []
        for entry in data_raw:
            if isinstance(entry, str):
                items.append(entry)
            elif isinstance(entry, dict):
                # Prefer common formatted-string keys.
                for k in ("http_formatted", "socks5_formatted", "proxy", "formatted"):
                    if k in entry:
                        items.append(str(entry[k]))
                        break
                else:
                    items.append(str(entry))
            else:
                items.append(str(entry))
        known = {"data", "message"}
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            data=items,
            message=_opt_str(raw.get("message")),
            extra=extra,
        )


@dataclass(slots=True)
class CheckoutQuote:
    """Result of ``POST /checkout/quote`` — a price estimate."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "CheckoutQuote":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class CheckoutResult:
    """Result of ``POST /checkout/create`` — the new service that was bought."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "CheckoutResult":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class AnalyticsBreakdown:
    """Result of ``GET /analytics/breakdown``."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "AnalyticsBreakdown":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class AnalyticsGraph:
    """Result of ``GET /analytics/graph``."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "AnalyticsGraph":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class AvailabilityCount:
    """Result of ``GET /{mobile,residential}_availability/count``."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "AvailabilityCount":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class CheckoutCatalog:
    """Result of ``GET /checkout/catalog``."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "CheckoutCatalog":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class ProxyListOptions:
    """Result of ``POST /proxy/list/options`` — which proxy_users can serve
    which proxies."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ProxyListOptions":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class ServiceSummary:
    """Result of ``GET /mobile/summary`` and ``GET /residential/summary``."""

    data: dict[str, Any] = field(default_factory=dict)
    message: str | None = None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "ServiceSummary":
        return cls(
            data=raw.get("data") or {},
            message=_opt_str(raw.get("message")),
        )


@dataclass(slots=True)
class Product:
    """A single entry from ``GET /product/search``."""

    product_id: str | None = None
    product_type: str | None = None
    product_protocol: str | None = None
    country_id: str | None = None
    product_is_active: bool | None = None
    product_is_one_per_customer: bool | None = None
    product_is_one_active_per_customer: bool | None = None
    product_is_per_ip: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> "Product":
        known = {f.name for f in fields(cls) if f.name != "extra"}
        extra = {k: v for k, v in raw.items() if k not in known}
        return cls(
            product_id=_opt_str(raw.get("product_id")),
            product_type=_opt_str(raw.get("product_type")),
            product_protocol=_opt_str(raw.get("product_protocol")),
            country_id=_opt_str(raw.get("country_id")),
            product_is_active=_opt_bool(raw.get("product_is_active")),
            product_is_one_per_customer=_opt_bool(raw.get("product_is_one_per_customer")),
            product_is_one_active_per_customer=_opt_bool(
                raw.get("product_is_one_active_per_customer")
            ),
            product_is_per_ip=_opt_bool(raw.get("product_is_per_ip")),
            extra=extra,
        )

"""Synchronous client for the byteful Public User API."""

from __future__ import annotations

import os
import random as _random
import time
from typing import TYPE_CHECKING, Any, Iterable

import requests

from .enums import (
    CancelFeedback,
    CycleInterval,
    ListAuthentication,
    ListFormat,
    ListMode,
    ListProtocol,
    ListSessionType,
    ListVersion,
    ProxyProtocol,
    ProxyStatus,
    ProxyType,
    ProxyUserAccessType,
    ServiceType,
)
from .exceptions import (
    BytefulAPIError,
    BytefulError,
    ForbiddenError,
    TwoFactorAuthenticationRequired,
)
from .models import (
    AnalyticsBreakdown,
    AnalyticsGraph,
    Asn,
    AvailabilityCount,
    CheckoutCatalog,
    CheckoutQuote,
    CheckoutResult,
    City,
    Continent,
    Country,
    CreatedResult,
    Customer,
    DeletedResult,
    EditedResult,
    GeneratedProxyList,
    Log,
    LogSummary,
    MobileAvailability,
    MobileLedger,
    PageResult,
    Product,
    Proxy,
    ProxyList,
    ProxyListOptions,
    ProxyReplacement,
    ProxyTestServer,
    ProxyUser,
    ProxyUserAcl,
    ResidentialAvailability,
    ResidentialLedger,
    Service,
    ServiceAdjustment,
    ServiceSummary,
    Subdivision,
    SubscriptionSchedule,
    ZipCode,
)
from .ratelimit import DEFAULT_RATE_LIMITER, RateLimiter

if TYPE_CHECKING:
    import httpx


DEFAULT_BASE_URL = "https://api.byteful.com/1.0"
DEFAULT_TIMEOUT = 30.0
DEFAULT_PROXY_CACHE_TTL = 86400.0  # 24 hours
PUBLIC_KEY_ENV_VAR = "BYTEFUL_API_PUBLIC_KEY"
PRIVATE_KEY_ENV_VAR = "BYTEFUL_API_PRIVATE_KEY"


def _enum_value(v: Any) -> Any:
    """Unwrap an enum to its raw value; pass other types through."""
    if hasattr(v, "value"):
        return v.value
    return v


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` keys and coerce enums to their string values."""
    out: dict[str, Any] = {}
    for k, v in params.items():
        if v is None:
            continue
        out[k] = _enum_value(v)
    return out


class BytefulClient:
    """Client for the byteful Public User API.

    The API keys are resolved in this order:

    1. The explicit ``api_public_key`` / ``api_private_key`` arguments.
    2. The ``BYTEFUL_API_PUBLIC_KEY`` / ``BYTEFUL_API_PRIVATE_KEY``
       environment variables.

    Both keys are required; ``ValueError`` is raised if either is missing.

    Example::

        from byteful import BytefulClient

        with BytefulClient() as client:
            me = client.customer_retrieve()
            print(me.customer_email_address, me.credit_balance)

            pool = client.proxies(refresh=True)
            print(f"Pool has {len(pool)} proxies")

            us_v4 = pool.filter(country_id="us", proxy_protocol="ipv4")
            with us_v4.random().requests_session() as s:
                print(s.get("https://api.ipify.org?format=json").json())
    """

    def __init__(
        self,
        api_public_key: str | None = None,
        api_private_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        session: requests.Session | None = None,
        rate_limiter: RateLimiter | None = DEFAULT_RATE_LIMITER,
        proxy_cache_ttl: float | None = DEFAULT_PROXY_CACHE_TTL,
        user_agent: str | None = None,
    ) -> None:
        pub = api_public_key if api_public_key is not None else os.environ.get(PUBLIC_KEY_ENV_VAR)
        priv = api_private_key if api_private_key is not None else os.environ.get(PRIVATE_KEY_ENV_VAR)
        if not pub or not priv:
            missing = []
            if not pub:
                missing.append(f"api_public_key (or ${PUBLIC_KEY_ENV_VAR})")
            if not priv:
                missing.append(f"api_private_key (or ${PRIVATE_KEY_ENV_VAR})")
            raise ValueError(", ".join(missing) + " required")
        self.api_public_key = pub
        self.api_private_key = priv
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = session or requests.Session()
        self._owns_session = session is None
        self.rate_limiter = rate_limiter
        self.proxy_cache_ttl = proxy_cache_ttl
        self._proxy_cache: ProxyList | None = None
        self._proxy_cache_at: float = 0.0
        self.user_agent = user_agent or "byteful-sdk-python"

    def __enter__(self) -> "BytefulClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    # ---- request plumbing --------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Public-Key": self.api_public_key,
            "X-API-Private-Key": self.api_private_key,
            "Accept": "application/json",
            "User-Agent": self.user_agent,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.rate_limiter is not None:
            self.rate_limiter.acquire()
        url = f"{self.base_url}{path}"
        headers = self._headers()
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        resp = self._session.request(
            method,
            url,
            params=_clean(params or {}),
            json=json_body,
            headers=headers,
            timeout=self.timeout,
        )
        return self._unwrap(resp)

    @staticmethod
    def _unwrap(resp: requests.Response) -> dict[str, Any]:
        """Parse a byteful response and raise the typed exception on failure."""
        try:
            body = resp.json() if resp.content else {}
        except ValueError as e:
            raise BytefulError(
                f"non-JSON response (HTTP {resp.status_code}): {resp.text[:200]!r}"
            ) from e
        if 200 <= resp.status_code < 300:
            if not isinstance(body, dict):
                raise BytefulError(
                    f"expected JSON object, got {type(body).__name__}: {body!r}"
                )
            return body
        # Error path. 403 with the 2FA fields is a distinct case.
        error = str(body.get("error", "")) if isinstance(body, dict) else ""
        message = str(body.get("message", "")) if isinstance(body, dict) else ""
        api_request_id = (
            str(body.get("api_request_id")) if isinstance(body, dict) and body.get("api_request_id") else None
        )
        extra = {k: v for k, v in (body if isinstance(body, dict) else {}).items()
                 if k not in ("error", "message", "api_request_id")}
        if resp.status_code == 403 and "two_factor_authentication_public_key" in extra:
            raise TwoFactorAuthenticationRequired(
                status_code=resp.status_code,
                error=error,
                message=message,
                api_request_id=api_request_id,
                extra=extra,
            )
        if resp.status_code == 403:
            raise ForbiddenError(
                status_code=resp.status_code,
                error=error,
                message=message,
                api_request_id=api_request_id,
                extra=extra,
            )
        raise BytefulAPIError(
            status_code=resp.status_code,
            error=error,
            message=message,
            api_request_id=api_request_id,
            extra=extra,
        )

    # ---- cache management --------------------------------------------------

    def invalidate_proxy_cache(self) -> None:
        """Drop the cached proxy pool. Next ``proxies()`` call re-fetches."""
        self._proxy_cache = None
        self._proxy_cache_at = 0.0

    def _proxy_cache_fresh(self) -> bool:
        if self._proxy_cache is None or self.proxy_cache_ttl is None:
            return False
        return (time.monotonic() - self._proxy_cache_at) <= self.proxy_cache_ttl

    def proxies(self, *, refresh: bool = False, per_page: int = 500) -> ProxyList:
        """Cached view of your full proxy pool.

        Walks every page of :meth:`proxy_search` once, flattens them into a
        :class:`ProxyList`, and reuses it for repeated calls. The cache is
        automatically dropped after any state-changing call (``checkout_*``,
        ``proxy_user_*``, ``service_*``, ``proxy_user_acl_*``). Pass
        ``refresh=True`` to force a re-fetch now.

        Filter the result client-side with :meth:`ProxyList.filter` and pick
        one with :meth:`ProxyList.random` — both work on the cached list
        without hitting the API again. For server-side filters call
        :meth:`proxy_search` directly.
        """
        if refresh or not self._proxy_cache_fresh():
            all_proxies: list[Proxy] = []
            page = 1
            while True:
                pr = self.proxy_search(per_page=per_page, page=page)
                all_proxies.extend(pr.data)
                if not pr.has_more:
                    break
                page = pr.next_page or page + 1
            self._proxy_cache = ProxyList(proxies=all_proxies, total_count=len(all_proxies))
            self._proxy_cache_at = time.monotonic()
        return self._proxy_cache

    # ---- pool selection / HTTP-client convenience --------------------------

    def select_proxy(
        self,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_id: int | None = None,
        asn_id: int | None = None,
        service_id: str | None = None,
        proxy_user_id: str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        proxy_status: ProxyStatus | str | None = ProxyStatus.IN_USE,
        rng: _random.Random | None = None,
    ) -> Proxy:
        """Pick one proxy from the cached pool that matches the given filters.

        ``proxy_status`` defaults to ``IN_USE`` since that's the only state in
        which a proxy is actually serving traffic. Pass ``proxy_status=None``
        to include every state.
        """
        pool = self.proxies().filter(
            country_id=country_id,
            subdivision_id=subdivision_id,
            city_id=city_id,
            asn_id=asn_id,
            service_id=service_id,
            proxy_user_id=proxy_user_id,
            proxy_type=proxy_type,
            proxy_protocol=proxy_protocol,
            proxy_status=proxy_status,
        )
        if not pool:
            criteria = {
                "country_id": country_id,
                "subdivision_id": subdivision_id,
                "city_id": city_id,
                "asn_id": asn_id,
                "service_id": service_id,
                "proxy_user_id": proxy_user_id,
                "proxy_type": proxy_type,
                "proxy_protocol": proxy_protocol,
                "proxy_status": proxy_status,
            }
            active = {k: v for k, v in criteria.items() if v is not None}
            raise LookupError(f"no proxy in pool matches filters: {active}")
        return pool.random(rng=rng)

    def requests_session(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_id: int | None = None,
        asn_id: int | None = None,
        service_id: str | None = None,
        proxy_user_id: str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        proxy_status: ProxyStatus | str | None = ProxyStatus.IN_USE,
        protocol: str = "http",
        family: str = "v4",
        rng: _random.Random | None = None,
        session: requests.Session | None = None,
    ) -> requests.Session:
        """Pick a proxy and return a ``requests.Session`` preconfigured for it."""
        return self.select_proxy(
            country_id=country_id,
            subdivision_id=subdivision_id,
            city_id=city_id,
            asn_id=asn_id,
            service_id=service_id,
            proxy_user_id=proxy_user_id,
            proxy_type=proxy_type,
            proxy_protocol=proxy_protocol,
            proxy_status=proxy_status,
            rng=rng,
        ).requests_session(proxy_user, protocol=protocol, family=family, session=session)

    def httpx_client(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_id: int | None = None,
        asn_id: int | None = None,
        service_id: str | None = None,
        proxy_user_id: str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        proxy_status: ProxyStatus | str | None = ProxyStatus.IN_USE,
        protocol: str = "http",
        family: str = "v4",
        rng: _random.Random | None = None,
        **kwargs: Any,
    ) -> "httpx.Client":
        """Pick a proxy and return an ``httpx.Client`` routed through it."""
        return self.select_proxy(
            country_id=country_id,
            subdivision_id=subdivision_id,
            city_id=city_id,
            asn_id=asn_id,
            service_id=service_id,
            proxy_user_id=proxy_user_id,
            proxy_type=proxy_type,
            proxy_protocol=proxy_protocol,
            proxy_status=proxy_status,
            rng=rng,
        ).httpx_client(proxy_user, protocol=protocol, family=family, **kwargs)

    def httpx_async_client(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_id: int | None = None,
        asn_id: int | None = None,
        service_id: str | None = None,
        proxy_user_id: str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        proxy_status: ProxyStatus | str | None = ProxyStatus.IN_USE,
        protocol: str = "http",
        family: str = "v4",
        rng: _random.Random | None = None,
        **kwargs: Any,
    ) -> "httpx.AsyncClient":
        """Pick a proxy and return an ``httpx.AsyncClient`` routed through it."""
        return self.select_proxy(
            country_id=country_id,
            subdivision_id=subdivision_id,
            city_id=city_id,
            asn_id=asn_id,
            service_id=service_id,
            proxy_user_id=proxy_user_id,
            proxy_type=proxy_type,
            proxy_protocol=proxy_protocol,
            proxy_status=proxy_status,
            rng=rng,
        ).httpx_async_client(proxy_user, protocol=protocol, family=family, **kwargs)

    def aiohttp_kwargs(
        self,
        proxy_user: "ProxyUser | tuple[str, str] | None" = None,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_id: int | None = None,
        asn_id: int | None = None,
        service_id: str | None = None,
        proxy_user_id: str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        proxy_status: ProxyStatus | str | None = ProxyStatus.IN_USE,
        protocol: str = "http",
        family: str = "v4",
        rng: _random.Random | None = None,
    ) -> dict[str, str]:
        """Pick a proxy and return kwargs to spread into ``aiohttp`` requests."""
        return self.select_proxy(
            country_id=country_id,
            subdivision_id=subdivision_id,
            city_id=city_id,
            asn_id=asn_id,
            service_id=service_id,
            proxy_user_id=proxy_user_id,
            proxy_type=proxy_type,
            proxy_protocol=proxy_protocol,
            proxy_status=proxy_status,
            rng=rng,
        ).aiohttp_kwargs(proxy_user, protocol=protocol, family=family)

    # ========================================================================
    # Customer
    # ========================================================================

    def customer_retrieve(self) -> Customer:
        """``GET /public/user/customer/retrieve`` — the authenticated customer."""
        data = self._request("GET", "/public/user/customer/retrieve")
        return Customer.from_api(data.get("data") or {})

    # ========================================================================
    # Proxy
    # ========================================================================

    def proxy_retrieve(self, proxy_id: str) -> Proxy:
        """``GET /public/user/proxy/retrieve/{proxy_id}``."""
        data = self._request("GET", f"/public/user/proxy/retrieve/{proxy_id}")
        return Proxy.from_api(data.get("data") or {})

    def proxy_search(
        self,
        *,
        proxy_id: str | int | None = None,
        service_id: str | None = None,
        proxy_ip_address: str | None = None,
        subnet_id: str | None = None,
        subnet_id_v6: str | None = None,
        ip_address_id_v4: str | None = None,
        ip_address_id_v6: str | None = None,
        proxy_http_port: int | None = None,
        proxy_socks5_port: int | None = None,
        proxy_status: ProxyStatus | str | None = None,
        proxy_type: ProxyType | str | None = None,
        proxy_protocol: ProxyProtocol | str | None = None,
        country_id: str | None = None,
        country_name: str | None = None,
        subdivision_id: str | None = None,
        subdivision_name: str | None = None,
        city_id: int | None = None,
        city_name: str | None = None,
        city_timezone: str | None = None,
        city_example_postcode: str | None = None,
        city_latitude: str | None = None,
        city_longitude: str | None = None,
        asn_id: int | str | None = None,
        asn_name: str | None = None,
        proxy_last_update_datetime: str | None = None,
        proxy_user_id: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Proxy]:
        """``GET /public/user/proxy/search`` — list your proxies."""
        params = {
            "proxy_id": proxy_id,
            "service_id": service_id,
            "proxy_ip_address": proxy_ip_address,
            "subnet_id": subnet_id,
            "subnet_id_v6": subnet_id_v6,
            "ip_address_id_v4": ip_address_id_v4,
            "ip_address_id_v6": ip_address_id_v6,
            "proxy_http_port": proxy_http_port,
            "proxy_socks5_port": proxy_socks5_port,
            "proxy_status": proxy_status,
            "proxy_type": proxy_type,
            "proxy_protocol": proxy_protocol,
            "country_id": country_id,
            "country_name": country_name,
            "subdivision_id": subdivision_id,
            "subdivision_name": subdivision_name,
            "city_id": city_id,
            "city_name": city_name,
            "city_timezone": city_timezone,
            "city_example_postcode": city_example_postcode,
            "city_latitude": city_latitude,
            "city_longitude": city_longitude,
            "asn_id": asn_id,
            "asn_name": asn_name,
            "proxy_last_update_datetime": proxy_last_update_datetime,
            "proxy_user_id": proxy_user_id,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/proxy/search", params=params)
        return PageResult.from_api(data, Proxy.from_api)

    def proxy_list_by_search(
        self,
        *,
        list_protocol: ListProtocol | str | None = None,
        list_version: ListVersion | str | None = None,
        list_format: ListFormat | str | None = None,
        list_authentication: ListAuthentication | str | None = None,
        proxy_user_id: str | None = None,
        **search_filters: Any,
    ) -> GeneratedProxyList:
        """``GET /public/user/proxy/list_by_search`` — generate formatted
        proxy strings (``"ip:port:user:pass"``, etc.) from a search query.

        ``**search_filters`` accepts the same filter parameters as
        :meth:`proxy_search` (e.g. ``country_id``, ``proxy_type``,
        ``page``, ``per_page``).
        """
        params: dict[str, Any] = {
            "list_protocol": list_protocol,
            "list_version": list_version,
            "list_format": list_format,
            "list_authentication": list_authentication,
            "proxy_user_id": proxy_user_id,
            **search_filters,
        }
        data = self._request("GET", "/public/user/proxy/list_by_search", params=params)
        return GeneratedProxyList.from_api(data)

    def proxy_list_by_id(
        self,
        proxy_ids: Iterable[str],
        *,
        list_protocol: ListProtocol | str | None = None,
        list_version: ListVersion | str | None = None,
        list_format: ListFormat | str | None = None,
        list_authentication: ListAuthentication | str | None = None,
        proxy_user_id: str | None = None,
    ) -> GeneratedProxyList:
        """``POST /public/user/proxy/list_by_id`` — generate formatted proxy
        strings for a specific set of proxy UUIDs."""
        body: dict[str, Any] = {
            "proxy_ids": list(proxy_ids),
            "list_protocol": _enum_value(list_protocol),
            "list_version": _enum_value(list_version),
            "list_format": _enum_value(list_format),
            "list_authentication": _enum_value(list_authentication),
            "proxy_user_id": proxy_user_id,
        }
        data = self._request(
            "POST", "/public/user/proxy/list_by_id", json_body=_clean(body)
        )
        return GeneratedProxyList.from_api(data)

    def proxy_list_options(
        self,
        *,
        proxy_ids: Iterable[str] | None = None,
        search_filter: dict[str, Any] | None = None,
    ) -> ProxyListOptions:
        """``POST /public/user/proxy/list/options`` — for the given proxies,
        list which of your proxy users have access to them.

        Pass either ``proxy_ids`` (explicit UUID list) or ``search_filter``
        (search parameters in the same shape as ``proxy_search``)."""
        body: dict[str, Any] = {}
        if proxy_ids is not None:
            body["proxy_ids"] = list(proxy_ids)
        if search_filter is not None:
            body["search_filter"] = search_filter
        data = self._request(
            "POST", "/public/user/proxy/list/options", json_body=body
        )
        return ProxyListOptions.from_api(data)

    # ========================================================================
    # Proxy User
    # ========================================================================

    def proxy_user_retrieve(self, proxy_user_id: str) -> ProxyUser:
        data = self._request("GET", f"/public/user/proxy_user/retrieve/{proxy_user_id}")
        return ProxyUser.from_api(data.get("data") or {})

    def proxy_user_search(
        self,
        *,
        proxy_user_id: str | None = None,
        proxy_user_password: str | None = None,
        proxy_user_ip_address_authentication_limit: int | None = None,
        proxy_user_is_deleted: bool | None = None,
        proxy_user_access_type: ProxyUserAccessType | str | None = None,
        proxy_user_is_strict_security: bool | None = None,
        proxy_user_is_default: bool | None = None,
        proxy_user_creation_datetime: str | None = None,
        proxy_user_last_update_datetime: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[ProxyUser]:
        params = {
            "proxy_user_id": proxy_user_id,
            "proxy_user_password": proxy_user_password,
            "proxy_user_ip_address_authentication_limit": proxy_user_ip_address_authentication_limit,
            "proxy_user_is_deleted": proxy_user_is_deleted,
            "proxy_user_access_type": proxy_user_access_type,
            "proxy_user_is_strict_security": proxy_user_is_strict_security,
            "proxy_user_is_default": proxy_user_is_default,
            "proxy_user_creation_datetime": proxy_user_creation_datetime,
            "proxy_user_last_update_datetime": proxy_user_last_update_datetime,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/proxy_user/search", params=params)
        return PageResult.from_api(data, ProxyUser.from_api)

    def proxy_user_create(
        self,
        *,
        proxy_user_id: str | None = None,
        proxy_user_password: str | None = None,
        proxy_user_access_type: ProxyUserAccessType | str | None = None,
        proxy_user_is_strict_security: bool | None = None,
        proxy_user_enforce_https: bool | None = None,
        ip_address_authentications: Iterable[str] | None = None,
        proxy_user_metadata: dict[str, Any] | None = None,
        proxy_user_residential_bytes_limit: int | None = None,
        proxy_user_mobile_bytes_limit: int | None = None,
    ) -> CreatedResult[ProxyUser]:
        """``POST /public/user/proxy_user/create``. Either provide an explicit
        ``proxy_user_id`` / ``proxy_user_password`` or omit them and let byteful
        generate random credentials."""
        body = {
            "proxy_user_id": proxy_user_id,
            "proxy_user_password": proxy_user_password,
            "proxy_user_access_type": _enum_value(proxy_user_access_type),
            "proxy_user_is_strict_security": proxy_user_is_strict_security,
            "proxy_user_enforce_https": proxy_user_enforce_https,
            "ip_address_authentications": (
                list(ip_address_authentications) if ip_address_authentications is not None else None
            ),
            "proxy_user_metadata": proxy_user_metadata,
            "proxy_user_residential_bytes_limit": proxy_user_residential_bytes_limit,
            "proxy_user_mobile_bytes_limit": proxy_user_mobile_bytes_limit,
        }
        data = self._request(
            "POST", "/public/user/proxy_user/create", json_body=_clean(body)
        )
        self.invalidate_proxy_cache()
        return CreatedResult(
            created=[str(x) for x in (data.get("created") or [])],
            data=ProxyUser.from_api(data.get("data") or {}),
            message=data.get("message"),
        )

    def proxy_user_edit(
        self,
        proxy_user_id: str,
        *,
        proxy_user_password: str | None = None,
        proxy_user_access_type: ProxyUserAccessType | str | None = None,
        proxy_user_is_strict_security: bool | None = None,
        proxy_user_enforce_https: bool | None = None,
        ip_address_authentications: Iterable[str] | None = None,
        proxy_user_metadata: dict[str, Any] | None = None,
        proxy_user_residential_bytes_limit: int | None = None,
        proxy_user_mobile_bytes_limit: int | None = None,
        clear_proxy_user_acl: bool | None = None,
    ) -> EditedResult:
        body = {
            "proxy_user_password": proxy_user_password,
            "proxy_user_access_type": _enum_value(proxy_user_access_type),
            "proxy_user_is_strict_security": proxy_user_is_strict_security,
            "proxy_user_enforce_https": proxy_user_enforce_https,
            "ip_address_authentications": (
                list(ip_address_authentications) if ip_address_authentications is not None else None
            ),
            "proxy_user_metadata": proxy_user_metadata,
            "proxy_user_residential_bytes_limit": proxy_user_residential_bytes_limit,
            "proxy_user_mobile_bytes_limit": proxy_user_mobile_bytes_limit,
            "clear_proxy_user_acl": clear_proxy_user_acl,
        }
        data = self._request(
            "PATCH",
            f"/public/user/proxy_user/edit/{proxy_user_id}",
            json_body=_clean(body),
        )
        self.invalidate_proxy_cache()
        return EditedResult.from_api(data)

    def proxy_user_delete(self, proxy_user_id: str) -> DeletedResult:
        data = self._request(
            "DELETE", f"/public/user/proxy_user/delete/{proxy_user_id}"
        )
        self.invalidate_proxy_cache()
        return DeletedResult.from_api(data)

    # ========================================================================
    # Proxy User ACL
    # ========================================================================

    def proxy_user_acl_retrieve(self, proxy_user_acl_id: str) -> ProxyUserAcl:
        data = self._request(
            "GET", f"/public/user/proxy_user_acl/retrieve/{proxy_user_acl_id}"
        )
        return ProxyUserAcl.from_api(data.get("data") or {})

    def proxy_user_acl_search(
        self,
        *,
        proxy_user_acl_id: str | None = None,
        proxy_user_id: str | None = None,
        service_id: str | None = None,
        proxy_id: str | None = None,
        proxy_user_acl_creation_datetime: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[ProxyUserAcl]:
        params = {
            "proxy_user_acl_id": proxy_user_acl_id,
            "proxy_user_id": proxy_user_id,
            "service_id": service_id,
            "proxy_id": proxy_id,
            "proxy_user_acl_creation_datetime": proxy_user_acl_creation_datetime,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request(
            "GET", "/public/user/proxy_user_acl/search", params=params
        )
        return PageResult.from_api(data, ProxyUserAcl.from_api)

    def proxy_user_acl_create(
        self,
        *,
        proxy_user_id: str,
        proxy_id: str | None = None,
        service_id: str | None = None,
    ) -> CreatedResult[ProxyUserAcl]:
        """Grant a proxy user access to a specific proxy or service.

        Exactly one of ``proxy_id`` / ``service_id`` must be supplied.
        """
        if (proxy_id is None) == (service_id is None):
            raise ValueError(
                "proxy_user_acl_create requires exactly one of proxy_id or service_id"
            )
        body = {
            "proxy_user_id": proxy_user_id,
            "proxy_id": proxy_id,
            "service_id": service_id,
        }
        data = self._request(
            "POST", "/public/user/proxy_user_acl/create", json_body=_clean(body)
        )
        self.invalidate_proxy_cache()
        return CreatedResult(
            created=[str(x) for x in (data.get("created") or [])],
            data=ProxyUserAcl.from_api(data.get("data") or {}),
            message=data.get("message"),
        )

    def proxy_user_acl_delete(self, proxy_user_acl_id: str) -> DeletedResult:
        data = self._request(
            "DELETE", f"/public/user/proxy_user_acl/delete/{proxy_user_acl_id}"
        )
        self.invalidate_proxy_cache()
        return DeletedResult.from_api(data)

    # ========================================================================
    # Service
    # ========================================================================

    def service_retrieve(self, service_id: str) -> Service:
        data = self._request("GET", f"/public/user/service/retrieve/{service_id}")
        return Service.from_api(data.get("data") or {})

    def service_search(
        self,
        *,
        service_id: str | None = None,
        service_status: Any = None,
        service_name: str | None = None,
        service_type: ServiceType | str | None = None,
        service_protocol: ProxyProtocol | str | None = None,
        service_quantity: int | None = None,
        payment_method_id: int | None = None,
        service_total: str | None = None,
        service_cycle: str | None = None,
        service_dispatch_datetime: str | None = None,
        service_expiry_datetime: str | None = None,
        service_image: str | None = None,
        service_is_automatic_collection: bool | None = None,
        service_is_pending_cancellation: bool | None = None,
        country_id: str | None = None,
        service_price_id: int | None = None,
        product_id: int | None = None,
        service_promotional_code: str | None = None,
        service_subscription_id: int | None = None,
        service_creation_datetime: str | None = None,
        service_last_update_datetime: str | None = None,
        proxies: bool | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Service]:
        params = {
            "service_id": service_id,
            "service_status": service_status,
            "service_name": service_name,
            "service_type": service_type,
            "service_protocol": service_protocol,
            "service_quantity": service_quantity,
            "payment_method_id": payment_method_id,
            "service_total": service_total,
            "service_cycle": service_cycle,
            "service_dispatch_datetime": service_dispatch_datetime,
            "service_expiry_datetime": service_expiry_datetime,
            "service_image": service_image,
            "service_is_automatic_collection": service_is_automatic_collection,
            "service_is_pending_cancellation": service_is_pending_cancellation,
            "country_id": country_id,
            "service_price_id": service_price_id,
            "product_id": product_id,
            "service_promotional_code": service_promotional_code,
            "service_subscription_id": service_subscription_id,
            "service_creation_datetime": service_creation_datetime,
            "service_last_update_datetime": service_last_update_datetime,
            "proxies": proxies,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/service/search", params=params)
        return PageResult.from_api(data, Service.from_api)

    def service_edit(
        self,
        service_id: str,
        *,
        payment_method_id: str | None = None,
        service_is_automatic_collection: bool | None = None,
        service_is_pending_cancellation: bool | None = None,
        service_metadata: dict[str, Any] | None = None,
        cancel_comment: str | None = None,
        cancel_feedback: CancelFeedback | str | None = None,
    ) -> EditedResult:
        body = {
            "payment_method_id": payment_method_id,
            "service_is_automatic_collection": service_is_automatic_collection,
            "service_is_pending_cancellation": service_is_pending_cancellation,
            "service_metadata": service_metadata,
            "cancel_comment": cancel_comment,
            "cancel_feedback": _enum_value(cancel_feedback),
        }
        data = self._request(
            "PATCH", f"/public/user/service/edit/{service_id}", json_body=_clean(body)
        )
        self.invalidate_proxy_cache()
        return EditedResult.from_api(data)

    def service_cancel(
        self,
        service_id: str,
        *,
        cancel_comment: str | None = None,
        cancel_feedback: CancelFeedback | str | None = None,
    ) -> DeletedResult:
        body = {
            "cancel_comment": cancel_comment,
            "cancel_feedback": _enum_value(cancel_feedback),
        }
        data = self._request(
            "DELETE",
            f"/public/user/service/cancel/{service_id}",
            json_body=_clean(body),
        )
        self.invalidate_proxy_cache()
        return DeletedResult.from_api(data)

    # ========================================================================
    # Service Adjustment
    # ========================================================================

    def service_adjustment_retrieve(self, service_adjustment_id: int) -> ServiceAdjustment:
        data = self._request(
            "GET",
            f"/public/user/service_adjustment/retrieve/{service_adjustment_id}",
        )
        return ServiceAdjustment.from_api(data.get("data") or {})

    def service_adjustment_search(
        self,
        *,
        invoice_id: str | None = None,
        service_id: str | None = None,
        service_adjustment_id: int | None = None,
        service_adjustment_type: Any = None,
        service_adjustment_status: Any = None,
        service_adjustment_is_administrator: bool | None = None,
        service_adjustment_is_automatic: bool | None = None,
        service_adjustment_is_customer: bool | None = None,
        service_adjustment_creation_datetime: str | None = None,
        service_adjustment_last_update_datetime: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[ServiceAdjustment]:
        params = {
            "invoice_id": invoice_id,
            "service_id": service_id,
            "service_adjustment_id": service_adjustment_id,
            "service_adjustment_type": service_adjustment_type,
            "service_adjustment_status": service_adjustment_status,
            "service_adjustment_is_administrator": service_adjustment_is_administrator,
            "service_adjustment_is_automatic": service_adjustment_is_automatic,
            "service_adjustment_is_customer": service_adjustment_is_customer,
            "service_adjustment_creation_datetime": service_adjustment_creation_datetime,
            "service_adjustment_last_update_datetime": service_adjustment_last_update_datetime,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request(
            "GET", "/public/user/service_adjustment/search", params=params
        )
        return PageResult.from_api(data, ServiceAdjustment.from_api)

    # ========================================================================
    # Checkout
    # ========================================================================

    def checkout_catalog(self) -> CheckoutCatalog:
        """``GET /public/user/checkout/catalog`` — simplified product catalog."""
        data = self._request("GET", "/public/user/checkout/catalog")
        return CheckoutCatalog.from_api(data)

    def checkout_quote(
        self,
        *,
        product_type: ServiceType | str | None = None,
        product_code: str | None = None,
        product_protocol: ProxyProtocol | str | None = None,
        country_id: str | None = None,
        quantity: int | None = None,
        cycle_interval: CycleInterval | str | None = None,
        cycle_interval_count: int | None = None,
        promotional_code: str | None = None,
        service_fulfillment_filter: dict[str, Any] | None = None,
    ) -> CheckoutQuote:
        """``POST /public/user/checkout/quote`` — price estimate for a
        prospective purchase."""
        body = {
            "product_type": _enum_value(product_type),
            "product_code": product_code,
            "product_protocol": _enum_value(product_protocol),
            "country_id": country_id,
            "quantity": quantity,
            "cycle_interval": _enum_value(cycle_interval),
            "cycle_interval_count": cycle_interval_count,
            "promotional_code": promotional_code,
            "service_fulfillment_filter": service_fulfillment_filter,
        }
        data = self._request(
            "POST", "/public/user/checkout/quote", json_body=_clean(body)
        )
        return CheckoutQuote.from_api(data)

    def checkout_create(
        self,
        *,
        product_type: ServiceType | str | None = None,
        product_code: str | None = None,
        product_protocol: ProxyProtocol | str | None = None,
        country_id: str | None = None,
        quantity: int | None = None,
        cycle_interval: CycleInterval | str | None = None,
        cycle_interval_count: int | None = None,
        promotional_code: str | None = None,
        service_fulfillment_filter: dict[str, Any] | None = None,
    ) -> CheckoutResult:
        """``POST /public/user/checkout/create`` — purchase a service."""
        body = {
            "product_type": _enum_value(product_type),
            "product_code": product_code,
            "product_protocol": _enum_value(product_protocol),
            "country_id": country_id,
            "quantity": quantity,
            "cycle_interval": _enum_value(cycle_interval),
            "cycle_interval_count": cycle_interval_count,
            "promotional_code": promotional_code,
            "service_fulfillment_filter": service_fulfillment_filter,
        }
        data = self._request(
            "POST", "/public/user/checkout/create", json_body=_clean(body)
        )
        self.invalidate_proxy_cache()
        return CheckoutResult.from_api(data)

    # ========================================================================
    # Mobile
    # ========================================================================

    def mobile_list(
        self,
        *,
        list_count: int | None = None,
        list_format: ListFormat | str | None = None,
        proxy_user_id: str | None = None,
        list_session_type: ListSessionType | str | None = None,
        country_id: str | None = None,
        city_id: int | None = None,
        city_alias: str | None = None,
        zip_code_id: int | None = None,
        subdivision_id: int | str | None = None,
        list_smartpath_enabled: bool | None = None,
        list_session_ttl: str | None = None,
        list_mode: ListMode | str | None = None,
    ) -> GeneratedProxyList:
        params = {
            "list_count": list_count,
            "list_format": list_format,
            "proxy_user_id": proxy_user_id,
            "list_session_type": list_session_type,
            "country_id": country_id,
            "city_id": city_id,
            "city_alias": city_alias,
            "zip_code_id": zip_code_id,
            "subdivision_id": subdivision_id,
            "list_smartpath_enabled": list_smartpath_enabled,
            "list_session_ttl": list_session_ttl,
            "list_mode": list_mode,
        }
        data = self._request("GET", "/public/user/mobile/list", params=params)
        return GeneratedProxyList.from_api(data)

    def mobile_summary(self) -> ServiceSummary:
        data = self._request("GET", "/public/user/mobile/summary")
        return ServiceSummary.from_api(data)

    def mobile_availability_count(
        self,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_name: str | None = None,
        asn_id: int | None = None,
        zip_code_alias: str | None = None,
    ) -> AvailabilityCount:
        params = {
            "country_id": country_id,
            "subdivision_id": subdivision_id,
            "city_name": city_name,
            "asn_id": asn_id,
            "zip_code_alias": zip_code_alias,
        }
        data = self._request(
            "GET", "/public/user/mobile_availability/count", params=params
        )
        return AvailabilityCount.from_api(data)

    def mobile_availability_search(
        self,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_name: str | None = None,
        asn_id: int | None = None,
        zip_code_alias: str | None = None,
        mobile_availability_node_count: int | None = None,
        group_by: Any = None,
        sort_by: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> PageResult[MobileAvailability]:
        params = {
            "country_id": country_id,
            "subdivision_id": subdivision_id,
            "city_name": city_name,
            "asn_id": asn_id,
            "zip_code_alias": zip_code_alias,
            "mobile_availability_node_count": mobile_availability_node_count,
            "group_by": group_by,
            "sort_by": sort_by,
            "per_page": per_page,
            "page": page,
        }
        data = self._request(
            "GET", "/public/user/mobile_availability/search", params=params
        )
        return PageResult.from_api(data, MobileAvailability.from_api)

    def mobile_ledger_retrieve(self, mobile_ledger_id: str) -> MobileLedger:
        data = self._request(
            "GET", f"/public/user/mobile_ledger/retrieve/{mobile_ledger_id}"
        )
        return MobileLedger.from_api(data.get("data") or {})

    def mobile_ledger_search(
        self,
        *,
        mobile_ledger_id: str | None = None,
        service_id: str | None = None,
        service_adjustment_id: int | None = None,
        mobile_ledger_reason: str | None = None,
        mobile_ledger_requests: int | None = None,
        mobile_ledger_bytes: int | None = None,
        mobile_ledger_period_date: str | None = None,
        mobile_ledger_creation_datetime: str | None = None,
        mobile_ledger_last_update_datetime: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[MobileLedger]:
        params = {
            "mobile_ledger_id": mobile_ledger_id,
            "service_id": service_id,
            "service_adjustment_id": service_adjustment_id,
            "mobile_ledger_reason": mobile_ledger_reason,
            "mobile_ledger_requests": mobile_ledger_requests,
            "mobile_ledger_bytes": mobile_ledger_bytes,
            "mobile_ledger_period_date": mobile_ledger_period_date,
            "mobile_ledger_creation_datetime": mobile_ledger_creation_datetime,
            "mobile_ledger_last_update_datetime": mobile_ledger_last_update_datetime,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request(
            "GET", "/public/user/mobile_ledger/search", params=params
        )
        return PageResult.from_api(data, MobileLedger.from_api)

    # ========================================================================
    # Residential
    # ========================================================================

    def residential_list(
        self,
        *,
        list_count: int | None = None,
        list_format: ListFormat | str | None = None,
        proxy_user_id: str | None = None,
        list_session_type: ListSessionType | str | None = None,
        country_id: str | None = None,
        city_id: int | None = None,
        city_alias: str | None = None,
        zip_code_id: int | None = None,
        subdivision_id: int | str | None = None,
        list_smartpath_enabled: bool | None = None,
        list_session_ttl: str | None = None,
        list_mode: ListMode | str | None = None,
    ) -> GeneratedProxyList:
        params = {
            "list_count": list_count,
            "list_format": list_format,
            "proxy_user_id": proxy_user_id,
            "list_session_type": list_session_type,
            "country_id": country_id,
            "city_id": city_id,
            "city_alias": city_alias,
            "zip_code_id": zip_code_id,
            "subdivision_id": subdivision_id,
            "list_smartpath_enabled": list_smartpath_enabled,
            "list_session_ttl": list_session_ttl,
            "list_mode": list_mode,
        }
        data = self._request("GET", "/public/user/residential/list", params=params)
        return GeneratedProxyList.from_api(data)

    def residential_summary(self) -> ServiceSummary:
        data = self._request("GET", "/public/user/residential/summary")
        return ServiceSummary.from_api(data)

    def residential_availability_count(
        self,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_name: str | None = None,
        asn_id: int | None = None,
        zip_code_alias: str | None = None,
    ) -> AvailabilityCount:
        params = {
            "country_id": country_id,
            "subdivision_id": subdivision_id,
            "city_name": city_name,
            "asn_id": asn_id,
            "zip_code_alias": zip_code_alias,
        }
        data = self._request(
            "GET", "/public/user/residential_availability/count", params=params
        )
        return AvailabilityCount.from_api(data)

    def residential_availability_search(
        self,
        *,
        country_id: str | None = None,
        subdivision_id: str | None = None,
        city_name: str | None = None,
        asn_id: int | None = None,
        zip_code_alias: str | None = None,
        residential_availability_node_count: int | None = None,
        group_by: Any = None,
        sort_by: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
    ) -> PageResult[ResidentialAvailability]:
        params = {
            "country_id": country_id,
            "subdivision_id": subdivision_id,
            "city_name": city_name,
            "asn_id": asn_id,
            "zip_code_alias": zip_code_alias,
            "residential_availability_node_count": residential_availability_node_count,
            "group_by": group_by,
            "sort_by": sort_by,
            "per_page": per_page,
            "page": page,
        }
        data = self._request(
            "GET", "/public/user/residential_availability/search", params=params
        )
        return PageResult.from_api(data, ResidentialAvailability.from_api)

    def residential_ledger_retrieve(self, residential_ledger_id: str) -> ResidentialLedger:
        data = self._request(
            "GET",
            f"/public/user/residential_ledger/retrieve/{residential_ledger_id}",
        )
        return ResidentialLedger.from_api(data.get("data") or {})

    def residential_ledger_search(
        self,
        *,
        residential_ledger_id: str | None = None,
        service_id: str | None = None,
        service_adjustment_id: int | None = None,
        residential_ledger_reason: str | None = None,
        residential_ledger_requests: int | None = None,
        residential_ledger_bytes: int | None = None,
        residential_ledger_period_date: str | None = None,
        residential_ledger_creation_datetime: str | None = None,
        residential_ledger_last_update_datetime: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[ResidentialLedger]:
        params = {
            "residential_ledger_id": residential_ledger_id,
            "service_id": service_id,
            "service_adjustment_id": service_adjustment_id,
            "residential_ledger_reason": residential_ledger_reason,
            "residential_ledger_requests": residential_ledger_requests,
            "residential_ledger_bytes": residential_ledger_bytes,
            "residential_ledger_period_date": residential_ledger_period_date,
            "residential_ledger_creation_datetime": residential_ledger_creation_datetime,
            "residential_ledger_last_update_datetime": residential_ledger_last_update_datetime,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request(
            "GET", "/public/user/residential_ledger/search", params=params
        )
        return PageResult.from_api(data, ResidentialLedger.from_api)

    # ========================================================================
    # Product
    # ========================================================================

    def product_search(
        self,
        *,
        product_id: str | None = None,
        product_type: str | None = None,
        product_protocol: ProxyProtocol | str | None = None,
        country_id: str | None = None,
        product_is_active: bool | None = None,
        product_is_one_per_customer: bool | None = None,
        product_is_one_active_per_customer: bool | None = None,
        product_is_per_ip: bool | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Product]:
        params = {
            "product_id": product_id,
            "product_type": product_type,
            "product_protocol": product_protocol,
            "country_id": country_id,
            "product_is_active": product_is_active,
            "product_is_one_per_customer": product_is_one_per_customer,
            "product_is_one_active_per_customer": product_is_one_active_per_customer,
            "product_is_per_ip": product_is_per_ip,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/product/search", params=params)
        return PageResult.from_api(data, Product.from_api)

    # ========================================================================
    # Analytics
    # ========================================================================

    def analytics_breakdown(
        self,
        *,
        preset: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        hostname: str | None = None,
        network: Any = None,
        proxy_user_id: str | None = None,
        return_proxy_users: bool | None = None,
        return_hostnames: bool | None = None,
        return_networks: bool | None = None,
        sort_by: str | None = None,
        limit: int | None = None,
    ) -> AnalyticsBreakdown:
        params = {
            "preset": preset,
            "period_start": period_start,
            "period_end": period_end,
            "hostname": hostname,
            "network": network,
            "proxy_user_id": proxy_user_id,
            "return_proxy_users": return_proxy_users,
            "return_hostnames": return_hostnames,
            "return_networks": return_networks,
            "sort_by": sort_by,
            "limit": limit,
        }
        data = self._request("GET", "/public/user/analytics/breakdown", params=params)
        return AnalyticsBreakdown.from_api(data)

    def analytics_graph(
        self,
        *,
        preset: str | None = None,
        period_start: str | None = None,
        period_end: str | None = None,
        interval: Any = None,
        hostname: str | None = None,
        network: Any = None,
        proxy_user_id: str | None = None,
        service_id: str | None = None,
        show_log_concurrency: bool | None = None,
    ) -> AnalyticsGraph:
        params = {
            "preset": preset,
            "period_start": period_start,
            "period_end": period_end,
            "interval": interval,
            "hostname": hostname,
            "network": network,
            "proxy_user_id": proxy_user_id,
            "service_id": service_id,
            "show_log_concurrency": show_log_concurrency,
        }
        data = self._request("GET", "/public/user/analytics/graph", params=params)
        return AnalyticsGraph.from_api(data)

    # ========================================================================
    # Logs
    # ========================================================================

    def log_retrieve(self, log_id: str) -> Log:
        data = self._request("GET", f"/public/user/log/retrieve/{log_id}")
        return Log.from_api(data.get("data") or {})

    def log_search(
        self,
        *,
        log_id: str | None = None,
        log_network: Any = None,
        proxy_user_id: str | None = None,
        service_id: str | None = None,
        log_protocol: Any = None,
        country_id: str | None = None,
        city_alias: str | None = None,
        asn_id: int | None = None,
        log_session_id: str | None = None,
        proxy_id: str | None = None,
        log_method: str | None = None,
        log_client_ip_address: str | None = None,
        log_local_ip_address: str | None = None,
        log_local_port: int | None = None,
        log_egress_ip_address: str | None = None,
        log_hostname: str | None = None,
        log_status_code: int | None = None,
        log_total_bytes: int | None = None,
        log_concurrency: int | None = None,
        log_smartpath_routed: bool | None = None,
        log_transport: Any = None,
        log_request_datetime: str | None = None,
        log_total_elapsed_ms: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Log]:
        params = {
            "log_id": log_id,
            "log_network": log_network,
            "proxy_user_id": proxy_user_id,
            "service_id": service_id,
            "log_protocol": log_protocol,
            "country_id": country_id,
            "city_alias": city_alias,
            "asn_id": asn_id,
            "log_session_id": log_session_id,
            "proxy_id": proxy_id,
            "log_method": log_method,
            "log_client_ip_address": log_client_ip_address,
            "log_local_ip_address": log_local_ip_address,
            "log_local_port": log_local_port,
            "log_egress_ip_address": log_egress_ip_address,
            "log_hostname": log_hostname,
            "log_status_code": log_status_code,
            "log_total_bytes": log_total_bytes,
            "log_concurrency": log_concurrency,
            "log_smartpath_routed": log_smartpath_routed,
            "log_transport": log_transport,
            "log_request_datetime": log_request_datetime,
            "log_total_elapsed_ms": log_total_elapsed_ms,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/log/search", params=params)
        return PageResult.from_api(data, Log.from_api)

    def log_summary_retrieve(self, log_summary_id: str) -> LogSummary:
        data = self._request(
            "GET", f"/public/user/log_summary/retrieve/{log_summary_id}"
        )
        return LogSummary.from_api(data.get("data") or {})

    def log_summary_search(
        self,
        *,
        log_summary_id: str | None = None,
        proxy_user_id: str | None = None,
        log_summary_network: Any = None,
        log_summary_hostname: str | None = None,
        log_summary_requests: int | None = None,
        log_summary_successful: int | None = None,
        log_summary_error: int | None = None,
        log_summary_bytes: int | None = None,
        log_summary_period: str | None = None,
        log_summary_creation_datetime: str | None = None,
        log_summary_last_update_datetime: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[LogSummary]:
        params = {
            "log_summary_id": log_summary_id,
            "proxy_user_id": proxy_user_id,
            "log_summary_network": log_summary_network,
            "log_summary_hostname": log_summary_hostname,
            "log_summary_requests": log_summary_requests,
            "log_summary_successful": log_summary_successful,
            "log_summary_error": log_summary_error,
            "log_summary_bytes": log_summary_bytes,
            "log_summary_period": log_summary_period,
            "log_summary_creation_datetime": log_summary_creation_datetime,
            "log_summary_last_update_datetime": log_summary_last_update_datetime,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/log_summary/search", params=params)
        return PageResult.from_api(data, LogSummary.from_api)

    # ========================================================================
    # Proxy Test Server
    # ========================================================================

    def proxy_test_server_search(
        self,
        *,
        proxy_test_server_id: str | None = None,
        city_id: Any = None,
        country_id: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[ProxyTestServer]:
        params = {
            "proxy_test_server_id": proxy_test_server_id,
            "city_id": city_id,
            "country_id": country_id,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request(
            "GET", "/public/user/proxy_test_server/search", params=params
        )
        return PageResult.from_api(data, ProxyTestServer.from_api)

    # ========================================================================
    # Geographic resources
    # ========================================================================

    def country_retrieve(self, country_id: str) -> Country:
        data = self._request("GET", f"/public/user/country/retrieve/{country_id}")
        return Country.from_api(data.get("data") or {})

    def country_search(
        self,
        *,
        country_id: str | None = None,
        country_name: str | None = None,
        continent_id: str | None = None,
        country_is_european_union: bool | None = None,
        country_alias: str | None = None,
        country_node_count: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Country]:
        params = {
            "country_id": country_id,
            "country_name": country_name,
            "continent_id": continent_id,
            "country_is_european_union": country_is_european_union,
            "country_alias": country_alias,
            "country_node_count": country_node_count,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/country/search", params=params)
        return PageResult.from_api(data, Country.from_api)

    def city_retrieve(self, city_id: int) -> City:
        data = self._request("GET", f"/public/user/city/retrieve/{city_id}")
        return City.from_api(data.get("data") or {})

    def city_search(
        self,
        *,
        city_id: int | str | None = None,
        city_name: str | None = None,
        subdivision_id: str | None = None,
        city_timezone: str | None = None,
        city_is_populous: bool | None = None,
        city_alias: str | None = None,
        city_example_postcode: str | None = None,
        city_latitude: str | None = None,
        city_longitude: str | None = None,
        city_node_count: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[City]:
        params = {
            "city_id": city_id,
            "city_name": city_name,
            "subdivision_id": subdivision_id,
            "city_timezone": city_timezone,
            "city_is_populous": city_is_populous,
            "city_alias": city_alias,
            "city_example_postcode": city_example_postcode,
            "city_latitude": city_latitude,
            "city_longitude": city_longitude,
            "city_node_count": city_node_count,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/city/search", params=params)
        return PageResult.from_api(data, City.from_api)

    def subdivision_retrieve(self, subdivision_id: str) -> Subdivision:
        data = self._request(
            "GET", f"/public/user/subdivision/retrieve/{subdivision_id}"
        )
        return Subdivision.from_api(data.get("data") or {})

    def subdivision_search(
        self,
        *,
        subdivision_id: str | None = None,
        subdivision_name: str | None = None,
        country_id: str | None = None,
        subdivision_alias: str | None = None,
        subdivision_node_count: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Subdivision]:
        params = {
            "subdivision_id": subdivision_id,
            "subdivision_name": subdivision_name,
            "country_id": country_id,
            "subdivision_alias": subdivision_alias,
            "subdivision_node_count": subdivision_node_count,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/subdivision/search", params=params)
        return PageResult.from_api(data, Subdivision.from_api)

    def zip_code_retrieve(self, zip_code_id: int) -> ZipCode:
        data = self._request("GET", f"/public/user/zip_code/retrieve/{zip_code_id}")
        return ZipCode.from_api(data.get("data") or {})

    def zip_code_search(
        self,
        *,
        zip_code_id: int | None = None,
        zip_code_alias: str | None = None,
        subdivision_id: str | None = None,
        zip_code_node_count: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[ZipCode]:
        params = {
            "zip_code_id": zip_code_id,
            "zip_code_alias": zip_code_alias,
            "subdivision_id": subdivision_id,
            "zip_code_node_count": zip_code_node_count,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/zip_code/search", params=params)
        return PageResult.from_api(data, ZipCode.from_api)

    def continent_retrieve(self, continent_id: str) -> Continent:
        data = self._request(
            "GET", f"/public/user/continent/retrieve/{continent_id}"
        )
        return Continent.from_api(data.get("data") or {})

    def continent_search(
        self,
        *,
        continent_id: str | None = None,
        continent_name: str | None = None,
        continent_alias: str | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Continent]:
        params = {
            "continent_id": continent_id,
            "continent_name": continent_name,
            "continent_alias": continent_alias,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/continent/search", params=params)
        return PageResult.from_api(data, Continent.from_api)

    def asn_retrieve(self, asn_id: int) -> Asn:
        data = self._request("GET", f"/public/user/asn/retrieve/{asn_id}")
        return Asn.from_api(data.get("data") or {})

    def asn_search(
        self,
        *,
        asn_id: int | str | None = None,
        asn_name: str | None = None,
        country_id: str | None = None,
        asn_type: Any = None,
        asn_rir: Any = None,
        asn_ip_address_count: str | int | None = None,
        asn_node_count: int | None = None,
        per_page: int | None = None,
        page: int | None = None,
        sort_by: str | None = None,
    ) -> PageResult[Asn]:
        params = {
            "asn_id": asn_id,
            "asn_name": asn_name,
            "country_id": country_id,
            "asn_type": asn_type,
            "asn_rir": asn_rir,
            "asn_ip_address_count": asn_ip_address_count,
            "asn_node_count": asn_node_count,
            "per_page": per_page,
            "page": page,
            "sort_by": sort_by,
        }
        data = self._request("GET", "/public/user/asn/search", params=params)
        return PageResult.from_api(data, Asn.from_api)

    # ========================================================================
    # Misc
    # ========================================================================

    def ip_address_geolocate(self, ip_address: str) -> dict[str, Any]:
        """``GET /public/user/ip_address/geolocate/{ip_address}``."""
        data = self._request(
            "GET", f"/public/user/ip_address/geolocate/{ip_address}"
        )
        return data.get("data") or {}

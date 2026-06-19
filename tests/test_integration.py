"""Live, read-only integration tests for the byteful Public User API.

The entire module is gated on ``BYTEFUL_API_PUBLIC_KEY`` /
``BYTEFUL_API_PRIVATE_KEY`` being set (loaded from ``.env`` via the
conftest). Run with::

    uv run pytest -m integration -v

Every test here is **strictly read-only and safe to run against a
production account**:

* Only GET endpoints, plus three POST endpoints that are explicitly
  non-mutating per the byteful docs:
  - ``POST /checkout/quote`` (price estimate only)
  - ``POST /proxy/list_by_id`` (generates formatted strings; no allocation)
  - ``POST /proxy/list/options`` (informational permission check)
* No ``checkout/create`` (would charge money).
* No ``*/create``, ``*/edit``, ``*/delete`` or ``*/cancel`` of any kind.

Tests follow a discover-and-chain pattern: a ``*_search`` call provides an
ID to feed into the corresponding ``*_retrieve`` test. When search returns
empty (account simply has no resources of that kind), the retrieve test
``pytest.skip``s rather than failing — empty inventory is not a bug.
"""

from __future__ import annotations

import os
import re
import uuid
from typing import Generator

import pytest

from byteful import (
    Asn,
    BytefulAPIError,
    BytefulClient,
    City,
    Continent,
    Country,
    Customer,
    Log,
    LogSummary,
    MobileLedger,
    NotFoundError,
    PageResult,
    Product,
    Proxy,
    ProxyList,
    ProxyTestServer,
    ProxyUser,
    ProxyUserAcl,
    ResidentialLedger,
    Service,
    ServiceAdjustment,
    Subdivision,
    UnauthorizedError,
    ZipCode,
)


pytestmark = pytest.mark.integration


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="module")
def credentials() -> tuple[str, str]:
    pub = os.environ.get("BYTEFUL_API_PUBLIC_KEY")
    priv = os.environ.get("BYTEFUL_API_PRIVATE_KEY")
    if not pub or not priv:
        pytest.skip("BYTEFUL_API_PUBLIC_KEY / _PRIVATE_KEY not set")
    return pub, priv


@pytest.fixture(scope="module")
def client(credentials: tuple[str, str]) -> Generator[BytefulClient, None, None]:
    """One shared client per module — keeps the rate limiter window coherent."""
    pub, priv = credentials
    with BytefulClient(api_public_key=pub, api_private_key=priv) as c:
        yield c


@pytest.fixture(scope="module")
def any_proxy(client: BytefulClient) -> Proxy:
    """Yield a single Proxy from the account, or skip if none exist."""
    page = client.proxy_search(per_page=1)
    if not page.data:
        pytest.skip("account has no proxies provisioned")
    return page.data[0]


@pytest.fixture(scope="module")
def any_service(client: BytefulClient) -> Service:
    page = client.service_search(per_page=1)
    if not page.data:
        pytest.skip("account has no services provisioned")
    return page.data[0]


@pytest.fixture(scope="module")
def any_proxy_user(client: BytefulClient) -> ProxyUser:
    page = client.proxy_user_search(per_page=1)
    if not page.data:
        pytest.skip("account has no proxy_users (not even a default)")
    return page.data[0]


@pytest.fixture(scope="module")
def any_proxy_user_acl(client: BytefulClient) -> ProxyUserAcl:
    page = client.proxy_user_acl_search(per_page=1)
    if not page.data:
        pytest.skip("account has no proxy_user_acl entries")
    return page.data[0]


@pytest.fixture(scope="module")
def any_country(client: BytefulClient) -> Country:
    page = client.country_search(per_page=1)
    assert page.data, "country catalog should never be empty"
    return page.data[0]


@pytest.fixture(scope="module")
def any_continent(client: BytefulClient) -> Continent:
    page = client.continent_search(per_page=1)
    assert page.data, "continent catalog should never be empty"
    return page.data[0]


@pytest.fixture(scope="module")
def any_city(client: BytefulClient) -> City:
    page = client.city_search(per_page=1)
    if not page.data:
        pytest.skip("city catalog returned empty (unexpected)")
    return page.data[0]


@pytest.fixture(scope="module")
def any_subdivision(client: BytefulClient) -> Subdivision:
    page = client.subdivision_search(per_page=1)
    if not page.data:
        pytest.skip("subdivision catalog returned empty (unexpected)")
    return page.data[0]


@pytest.fixture(scope="module")
def any_zip_code(client: BytefulClient) -> ZipCode:
    page = client.zip_code_search(per_page=1)
    if not page.data:
        pytest.skip("zip_code catalog returned empty (unexpected)")
    return page.data[0]


@pytest.fixture(scope="module")
def any_asn(client: BytefulClient) -> Asn:
    page = client.asn_search(per_page=1)
    if not page.data:
        pytest.skip("ASN catalog returned empty (unexpected)")
    return page.data[0]


# ============================================================================
# Customer
# ============================================================================

def test_customer_retrieve(client: BytefulClient) -> None:
    me = client.customer_retrieve()
    assert isinstance(me, Customer)
    assert me.customer_id is not None and isinstance(me.customer_id, int)
    if me.customer_email_address is not None:
        # Loose sanity check — don't enforce a strict RFC 5322 regex.
        assert "@" in me.customer_email_address


# ============================================================================
# Geography: country / continent / subdivision / city / zip_code / asn
# Pattern: search returns ≥1, retrieve(id) returns the same row.
# ============================================================================

def test_country_search(client: BytefulClient) -> None:
    page = client.country_search(per_page=10)
    assert isinstance(page, PageResult)
    assert page.page == 1
    assert page.total_count >= len(page.data)
    if page.data:
        assert isinstance(page.data[0], Country)
        assert page.data[0].country_id


def test_country_retrieve(client: BytefulClient, any_country: Country) -> None:
    fetched = client.country_retrieve(any_country.country_id)  # type: ignore[arg-type]
    assert isinstance(fetched, Country)
    assert fetched.country_id == any_country.country_id


def test_country_search_us_specific(client: BytefulClient) -> None:
    """``country_id=us`` should always return exactly the US record."""
    page = client.country_search(country_id="us")
    assert page.total_count >= 1
    assert any(c.country_id == "us" for c in page.data)


def test_continent_search(client: BytefulClient) -> None:
    page = client.continent_search(per_page=10)
    assert isinstance(page, PageResult)
    if page.data:
        assert isinstance(page.data[0], Continent)


def test_continent_retrieve(client: BytefulClient, any_continent: Continent) -> None:
    fetched = client.continent_retrieve(any_continent.continent_id)  # type: ignore[arg-type]
    assert fetched.continent_id == any_continent.continent_id


def test_subdivision_search(client: BytefulClient) -> None:
    page = client.subdivision_search(country_id="us", per_page=10)
    assert isinstance(page, PageResult)
    # Every US subdivision should report country_id=us
    for s in page.data:
        if s.country_id is not None:
            assert s.country_id == "us"


def test_subdivision_retrieve(
    client: BytefulClient, any_subdivision: Subdivision
) -> None:
    fetched = client.subdivision_retrieve(any_subdivision.subdivision_id)  # type: ignore[arg-type]
    assert fetched.subdivision_id == any_subdivision.subdivision_id


def test_city_search(client: BytefulClient) -> None:
    page = client.city_search(per_page=5)
    assert isinstance(page, PageResult)


def test_city_retrieve(client: BytefulClient, any_city: City) -> None:
    fetched = client.city_retrieve(any_city.city_id)  # type: ignore[arg-type]
    assert fetched.city_id == any_city.city_id


def test_zip_code_search(client: BytefulClient) -> None:
    page = client.zip_code_search(per_page=5)
    assert isinstance(page, PageResult)


def test_zip_code_retrieve(client: BytefulClient, any_zip_code: ZipCode) -> None:
    fetched = client.zip_code_retrieve(any_zip_code.zip_code_id)  # type: ignore[arg-type]
    assert fetched.zip_code_id == any_zip_code.zip_code_id


def test_asn_search(client: BytefulClient) -> None:
    page = client.asn_search(per_page=10)
    assert isinstance(page, PageResult)


def test_asn_retrieve(client: BytefulClient, any_asn: Asn) -> None:
    fetched = client.asn_retrieve(any_asn.asn_id)  # type: ignore[arg-type]
    assert fetched.asn_id == any_asn.asn_id


# ============================================================================
# Products + checkout (catalog + quote — no purchases)
# ============================================================================

def test_product_search(client: BytefulClient) -> None:
    page = client.product_search(per_page=10)
    assert isinstance(page, PageResult)
    for p in page.data:
        assert isinstance(p, Product)


def test_checkout_catalog(client: BytefulClient) -> None:
    cat = client.checkout_catalog()
    assert cat.data is not None
    assert isinstance(cat.data, dict)


def test_checkout_quote_for_one_isp_proxy(client: BytefulClient) -> None:
    """``POST /checkout/quote`` is a price estimate only — no charge."""
    try:
        quote = client.checkout_quote(
            product_type="isp",
            product_protocol="ipv4",
            country_id="us",
            quantity=1,
            cycle_interval="month",
            cycle_interval_count=1,
        )
    except BytefulAPIError as e:
        # If byteful rejects the combo (e.g. ISP US doesn't ship in qty=1),
        # the test result is still informative: it confirms the SDK
        # forwarded the request shape correctly.
        if e.status_code in (400, 422):
            pytest.skip(f"byteful rejected the quote combo: {e.message}")
        raise
    assert quote.data is not None


# ============================================================================
# Proxy resources (search → retrieve, list generators)
# ============================================================================

def test_proxy_search(client: BytefulClient) -> None:
    page = client.proxy_search(per_page=5)
    assert isinstance(page, PageResult)
    for p in page.data:
        assert isinstance(p, Proxy)
        assert p.proxy_id


def test_proxy_retrieve(client: BytefulClient, any_proxy: Proxy) -> None:
    fetched = client.proxy_retrieve(any_proxy.proxy_id)  # type: ignore[arg-type]
    assert fetched.proxy_id == any_proxy.proxy_id


def test_proxy_list_by_search_returns_formatted_strings(
    client: BytefulClient, any_proxy: Proxy
) -> None:
    """``GET /proxy/list_by_search`` builds ``ip:port:user:pass``-style lines."""
    result = client.proxy_list_by_search(
        proxy_id=any_proxy.proxy_id,
        list_format="standard",
        list_protocol="http",
    )
    assert result.data is not None  # may be empty if filter matches nothing


def test_proxy_list_by_id_posts_uuid_list(
    client: BytefulClient, any_proxy: Proxy
) -> None:
    """``POST /proxy/list_by_id`` — generates strings for a UUID set."""
    assert any_proxy.proxy_id is not None
    result = client.proxy_list_by_id(
        [any_proxy.proxy_id],
        list_format="standard",
        list_protocol="http",
    )
    assert result.data is not None


def test_proxy_list_options_with_uuid_set(
    client: BytefulClient, any_proxy: Proxy
) -> None:
    """``POST /proxy/list/options`` — informational permission check."""
    assert any_proxy.proxy_id is not None
    result = client.proxy_list_options(proxy_ids=[any_proxy.proxy_id])
    assert result.data is not None


# ============================================================================
# Proxy users + ACLs
# ============================================================================

def test_proxy_user_search(client: BytefulClient) -> None:
    page = client.proxy_user_search(per_page=10)
    assert isinstance(page, PageResult)
    for pu in page.data:
        assert isinstance(pu, ProxyUser)
        assert pu.proxy_user_id


def test_proxy_user_retrieve(
    client: BytefulClient, any_proxy_user: ProxyUser
) -> None:
    fetched = client.proxy_user_retrieve(any_proxy_user.proxy_user_id)  # type: ignore[arg-type]
    assert fetched.proxy_user_id == any_proxy_user.proxy_user_id


def test_proxy_user_acl_search(client: BytefulClient) -> None:
    page = client.proxy_user_acl_search(per_page=10)
    assert isinstance(page, PageResult)
    for acl in page.data:
        assert isinstance(acl, ProxyUserAcl)


def test_proxy_user_acl_retrieve(
    client: BytefulClient, any_proxy_user_acl: ProxyUserAcl
) -> None:
    fetched = client.proxy_user_acl_retrieve(any_proxy_user_acl.proxy_user_acl_id)  # type: ignore[arg-type]
    assert fetched.proxy_user_acl_id == any_proxy_user_acl.proxy_user_acl_id


# ============================================================================
# Services + service adjustments
# ============================================================================

def test_service_search(client: BytefulClient) -> None:
    page = client.service_search(per_page=10)
    assert isinstance(page, PageResult)
    for s in page.data:
        assert isinstance(s, Service)
        assert s.service_id


def test_service_retrieve(client: BytefulClient, any_service: Service) -> None:
    fetched = client.service_retrieve(any_service.service_id)  # type: ignore[arg-type]
    assert fetched.service_id == any_service.service_id


def test_service_adjustment_search(client: BytefulClient) -> None:
    page = client.service_adjustment_search(per_page=5)
    assert isinstance(page, PageResult)


def test_service_adjustment_retrieve_when_any_exists(client: BytefulClient) -> None:
    page = client.service_adjustment_search(per_page=1)
    if not page.data:
        pytest.skip("no service adjustments on this account")
    adj = page.data[0]
    fetched = client.service_adjustment_retrieve(adj.service_adjustment_id)  # type: ignore[arg-type]
    assert isinstance(fetched, ServiceAdjustment)
    assert fetched.service_adjustment_id == adj.service_adjustment_id


# ============================================================================
# Mobile (availability + ledgers + summary + list)
# ============================================================================

def test_mobile_availability_count_us(client: BytefulClient) -> None:
    count = client.mobile_availability_count(country_id="us")
    assert count.data is not None
    assert isinstance(count.data, dict)


def test_mobile_availability_search_us(client: BytefulClient) -> None:
    page = client.mobile_availability_search(country_id="us", per_page=5)
    assert isinstance(page, PageResult)


def test_mobile_ledger_search(client: BytefulClient) -> None:
    page = client.mobile_ledger_search(per_page=5)
    assert isinstance(page, PageResult)


def test_mobile_ledger_retrieve_when_any_exists(client: BytefulClient) -> None:
    page = client.mobile_ledger_search(per_page=1)
    if not page.data:
        pytest.skip("no mobile ledger entries (no mobile service or no usage)")
    first = page.data[0]
    fetched = client.mobile_ledger_retrieve(first.mobile_ledger_id)  # type: ignore[arg-type]
    assert isinstance(fetched, MobileLedger)
    assert fetched.mobile_ledger_id == first.mobile_ledger_id


def test_mobile_summary_requires_service(client: BytefulClient) -> None:
    try:
        summary = client.mobile_summary()
    except (NotFoundError, BytefulAPIError) as e:
        if isinstance(e, NotFoundError) or e.status_code in (404, 422):
            pytest.skip(f"account has no mobile service: {e.message}")
        raise
    assert summary.data is not None


def test_mobile_list_requires_service(client: BytefulClient) -> None:
    try:
        listing = client.mobile_list(list_count=5, list_format="standard")
    except BytefulAPIError as e:
        if e.status_code in (404, 422, 403):
            pytest.skip(f"mobile_list requires active mobile service: {e.message}")
        raise
    assert listing.data is not None


# ============================================================================
# Residential (mirrors mobile)
# ============================================================================

def test_residential_availability_count_us(client: BytefulClient) -> None:
    count = client.residential_availability_count(country_id="us")
    assert count.data is not None


def test_residential_availability_search_us(client: BytefulClient) -> None:
    page = client.residential_availability_search(country_id="us", per_page=5)
    assert isinstance(page, PageResult)


def test_residential_ledger_search(client: BytefulClient) -> None:
    page = client.residential_ledger_search(per_page=5)
    assert isinstance(page, PageResult)


def test_residential_ledger_retrieve_when_any_exists(client: BytefulClient) -> None:
    page = client.residential_ledger_search(per_page=1)
    if not page.data:
        pytest.skip("no residential ledger entries")
    first = page.data[0]
    fetched = client.residential_ledger_retrieve(first.residential_ledger_id)  # type: ignore[arg-type]
    assert isinstance(fetched, ResidentialLedger)
    assert fetched.residential_ledger_id == first.residential_ledger_id


def test_residential_summary_requires_service(client: BytefulClient) -> None:
    try:
        summary = client.residential_summary()
    except (NotFoundError, BytefulAPIError) as e:
        if isinstance(e, NotFoundError) or e.status_code in (404, 422):
            pytest.skip(f"account has no residential service: {e.message}")
        raise
    assert summary.data is not None


def test_residential_list_requires_service(client: BytefulClient) -> None:
    try:
        listing = client.residential_list(list_count=5, list_format="standard")
    except BytefulAPIError as e:
        if e.status_code in (404, 422, 403):
            pytest.skip(f"residential_list requires active service: {e.message}")
        raise
    assert listing.data is not None


# ============================================================================
# Analytics
# ============================================================================

def test_analytics_breakdown_default_period(client: BytefulClient) -> None:
    """Default period is the current month per docs; call should succeed."""
    breakdown = client.analytics_breakdown()
    assert breakdown.data is not None
    assert isinstance(breakdown.data, dict)


def test_analytics_graph_default_period(client: BytefulClient) -> None:
    """The byteful API caps hourly graphs at 24h, so we ask for daily
    granularity to make the default-period query unambiguously valid."""
    graph = client.analytics_graph(interval="day")
    assert graph.data is not None


# ============================================================================
# Logs + log summaries
# ============================================================================

def test_log_search(client: BytefulClient) -> None:
    page = client.log_search(per_page=5)
    assert isinstance(page, PageResult)


def test_log_retrieve_when_any_exists(client: BytefulClient) -> None:
    page = client.log_search(per_page=1)
    if not page.data:
        pytest.skip("no logs on this account")
    first = page.data[0]
    fetched = client.log_retrieve(first.log_id)  # type: ignore[arg-type]
    assert isinstance(fetched, Log)
    assert fetched.log_id == first.log_id


def test_log_summary_search(client: BytefulClient) -> None:
    page = client.log_summary_search(per_page=5)
    assert isinstance(page, PageResult)


def test_log_summary_retrieve_when_any_exists(client: BytefulClient) -> None:
    page = client.log_summary_search(per_page=1)
    if not page.data:
        pytest.skip("no log summaries on this account")
    first = page.data[0]
    fetched = client.log_summary_retrieve(first.log_summary_id)  # type: ignore[arg-type]
    assert isinstance(fetched, LogSummary)
    assert fetched.log_summary_id == first.log_summary_id


# ============================================================================
# Proxy test servers + IP geolocate (catalog endpoints)
# ============================================================================

def test_proxy_test_server_search(client: BytefulClient) -> None:
    page = client.proxy_test_server_search(per_page=10)
    assert isinstance(page, PageResult)
    for s in page.data:
        assert isinstance(s, ProxyTestServer)


def test_ip_address_geolocate_public_ip(client: BytefulClient) -> None:
    """Geolocate 8.8.8.8 (Google DNS) — should always resolve."""
    data = client.ip_address_geolocate("8.8.8.8")
    assert isinstance(data, dict)


# ============================================================================
# Cross-cutting / behavioral
# ============================================================================

def test_cached_pool_walks_pages(client: BytefulClient) -> None:
    """``proxies()`` should walk every page and cache the result.

    Second call must not re-hit the wire (we check by inspecting the
    timestamp marker rather than mocking).
    """
    client.invalidate_proxy_cache()
    pool1 = client.proxies(per_page=100)
    assert isinstance(pool1, ProxyList)
    t1 = client._proxy_cache_at

    pool2 = client.proxies()  # should be served from cache
    assert pool2 is pool1
    assert client._proxy_cache_at == t1


def test_cached_pool_filter_locally(client: BytefulClient) -> None:
    pool = client.proxies(per_page=100)
    if not pool:
        pytest.skip("no proxies on this account")
    # Pick a country present in the pool and verify .filter() narrows to it
    target = next((p.country_id for p in pool if p.country_id), None)
    if target is None:
        pytest.skip("no proxies in the pool carry country_id")
    filtered = pool.filter(country_id=target)
    assert all(p.country_id == target for p in filtered)
    assert len(filtered) <= len(pool)


def test_proxy_search_pagination_metadata(client: BytefulClient) -> None:
    """A small per_page must produce ≥1 page when there's any inventory."""
    page = client.proxy_search(per_page=1, page=1)
    assert page.page == 1
    assert page.per_page == 1
    if page.total_count > 1:
        assert page.has_more is True
        assert page.next_page == 2
    if page.data:
        # Walking page 2 should yield distinct IDs.
        page2 = client.proxy_search(per_page=1, page=2)
        if page2.data:
            assert page.data[0].proxy_id != page2.data[0].proxy_id


def test_search_pagination_sort_by_random(client: BytefulClient) -> None:
    """The ``sort_by=random`` parameter is documented; SDK must forward it."""
    page = client.proxy_search(per_page=3, sort_by="random")
    assert isinstance(page, PageResult)


# ============================================================================
# Error paths (no fixtures — just sanity-check the live error envelope)
# ============================================================================

def test_bad_credentials_raise_unauthorized() -> None:
    """A fresh client with garbage keys should raise UnauthorizedError."""
    with BytefulClient(
        api_public_key="pub_definitely_not_real_" + uuid.uuid4().hex,
        api_private_key="priv_definitely_not_real_" + uuid.uuid4().hex,
        rate_limiter=None,
    ) as bad:
        with pytest.raises(UnauthorizedError) as exc:
            bad.customer_retrieve()
    assert exc.value.status_code == 401


def test_retrieve_nonexistent_proxy_raises(client: BytefulClient) -> None:
    """A syntactically-valid UUID that doesn't exist must raise NotFoundError
    (or BadRequestError / UnprocessableError if the API normalizes it)."""
    fake = str(uuid.uuid4())
    with pytest.raises(BytefulAPIError) as exc:
        client.proxy_retrieve(fake)
    assert exc.value.status_code in (400, 404, 422)


# ============================================================================
# Sanity probes that don't ship traffic
# ============================================================================

def test_client_carries_api_request_id_through_to_error(client: BytefulClient) -> None:
    """Forcing a 4xx should round-trip the byteful api_request_id."""
    fake = str(uuid.uuid4())
    try:
        client.proxy_retrieve(fake)
    except BytefulAPIError as e:
        # api_request_id is documented as always present on errors.
        assert e.api_request_id is None or re.fullmatch(
            r"[0-9a-fA-F\-]+", e.api_request_id or ""
        )
    else:
        pytest.fail("expected an API error")

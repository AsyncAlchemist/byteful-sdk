"""End-to-end tests for ``BytefulClient`` using ``responses`` to mock the HTTP layer."""

from __future__ import annotations

import json

import pytest
import responses

from byteful import (
    BadRequestError,
    BytefulAPIError,
    BytefulClient,
    ConflictError,
    Customer,
    ForbiddenError,
    NotFoundError,
    PageResult,
    Proxy,
    ProxyStatus,
    ProxyType,
    RateLimitedError,
    Service,
    TwoFactorAuthenticationRequired,
    UnauthorizedError,
    UnprocessableError,
)


BASE = "https://api.byteful.com/1.0"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> BytefulClient:
    monkeypatch.setenv("BYTEFUL_API_PUBLIC_KEY", "pub_xxx")
    monkeypatch.setenv("BYTEFUL_API_PRIVATE_KEY", "priv_xxx")
    # Disable the rate limiter so tests don't sleep.
    return BytefulClient(rate_limiter=None)


def test_missing_keys_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BYTEFUL_API_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("BYTEFUL_API_PRIVATE_KEY", raising=False)
    with pytest.raises(ValueError):
        BytefulClient()


def test_explicit_keys_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTEFUL_API_PUBLIC_KEY", "envpub")
    monkeypatch.setenv("BYTEFUL_API_PRIVATE_KEY", "envpriv")
    c = BytefulClient(api_public_key="argpub", api_private_key="argpriv", rate_limiter=None)
    assert c.api_public_key == "argpub"
    assert c.api_private_key == "argpriv"


@responses.activate
def test_customer_retrieve_unwraps_data_envelope(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/customer/retrieve",
        json={
            "data": {
                "customer_id": 1955,
                "customer_email_address": "steve@apple.com",
                "credit_balance": 1245,
            },
            "message": "ok",
        },
        status=200,
    )
    me = client.customer_retrieve()
    assert isinstance(me, Customer)
    assert me.customer_id == 1955
    assert me.customer_email_address == "steve@apple.com"
    assert me.credit_balance == 1245


@responses.activate
def test_auth_headers_are_sent(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/customer/retrieve",
        json={"data": {"customer_id": 1}, "message": "ok"},
        status=200,
    )
    client.customer_retrieve()
    [call] = responses.calls
    assert call.request.headers["X-API-Public-Key"] == "pub_xxx"
    assert call.request.headers["X-API-Private-Key"] == "priv_xxx"


@responses.activate
def test_proxy_search_paginates(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json={
            "data": [
                {"proxy_id": "a", "proxy_ip_address": "1.1.1.1", "proxy_http_port": 80, "country_id": "us"},
                {"proxy_id": "b", "proxy_ip_address": "2.2.2.2", "proxy_http_port": 80, "country_id": "us"},
            ],
            "page": 1,
            "per_page": 2,
            "total_count": 5,
            "item_count": 2,
            "message": "ok",
        },
        status=200,
    )
    pr = client.proxy_search(country_id="us", per_page=2, page=1)
    assert isinstance(pr, PageResult)
    assert pr.has_more is True
    assert pr.next_page == 2
    assert len(pr) == 2
    assert pr[0].proxy_id == "a"
    assert pr[0].proxy_ip_address == "1.1.1.1"


@responses.activate
def test_proxy_search_drops_none_params(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json={"data": [], "page": 1, "per_page": 0, "total_count": 0, "item_count": 0, "message": "ok"},
        status=200,
    )
    client.proxy_search(country_id="us", proxy_type=None, per_page=10)
    [call] = responses.calls
    # ``proxy_type`` was None and should have been dropped, ``country_id`` and
    # ``per_page`` should be present.
    assert "country_id=us" in call.request.url
    assert "per_page=10" in call.request.url
    assert "proxy_type" not in call.request.url


@responses.activate
def test_enum_params_are_serialized_to_strings(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/proxy/search",
        json={"data": [], "page": 1, "per_page": 0, "total_count": 0, "item_count": 0, "message": "ok"},
        status=200,
    )
    client.proxy_search(proxy_type=ProxyType.ISP, proxy_status=ProxyStatus.IN_USE)
    [call] = responses.calls
    assert "proxy_type=isp" in call.request.url
    assert "proxy_status=in_use" in call.request.url


@responses.activate
def test_proxy_user_create_invalidates_cache(client: BytefulClient) -> None:
    # Pre-seed the cache so we can prove it gets cleared.
    from byteful import ProxyList
    client._proxy_cache = ProxyList(proxies=[], total_count=0)
    client._proxy_cache_at = 999999.0

    responses.add(
        responses.POST,
        f"{BASE}/public/user/proxy_user/create",
        json={
            "created": ["stevejobs"],
            "data": {"proxy_user_id": "stevejobs", "proxy_user_password": "apple1984"},
            "message": "Proxy User successfully created.",
        },
        status=201,
    )
    result = client.proxy_user_create()
    assert result.created == ["stevejobs"]
    assert result.data.proxy_user_id == "stevejobs"
    assert client._proxy_cache is None


@responses.activate
def test_proxy_user_acl_create_requires_exactly_one_target(client: BytefulClient) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        client.proxy_user_acl_create(proxy_user_id="u")
    with pytest.raises(ValueError, match="exactly one"):
        client.proxy_user_acl_create(proxy_user_id="u", proxy_id="p", service_id="s")


@responses.activate
def test_service_cancel_sends_json_body(client: BytefulClient) -> None:
    responses.add(
        responses.DELETE,
        f"{BASE}/public/user/service/cancel/svc-1",
        json={"deleted": ["svc-1"], "message": "ok"},
        status=200,
    )
    result = client.service_cancel(
        "svc-1", cancel_comment="not needed", cancel_feedback="unused"
    )
    [call] = responses.calls
    body = json.loads(call.request.body)
    assert body == {"cancel_comment": "not needed", "cancel_feedback": "unused"}
    assert result.deleted == ["svc-1"]


@responses.activate
def test_proxy_list_by_id_posts_body(client: BytefulClient) -> None:
    responses.add(
        responses.POST,
        f"{BASE}/public/user/proxy/list_by_id",
        json={"data": ["1.1.1.1:80:u:p"], "message": "ok"},
        status=200,
    )
    result = client.proxy_list_by_id(
        ["uuid-1", "uuid-2"], list_format="standard", list_protocol="http"
    )
    [call] = responses.calls
    body = json.loads(call.request.body)
    assert body["proxy_ids"] == ["uuid-1", "uuid-2"]
    assert body["list_format"] == "standard"
    assert body["list_protocol"] == "http"
    assert list(result) == ["1.1.1.1:80:u:p"]


# ---- Error dispatch --------------------------------------------------------

@pytest.mark.parametrize(
    "status,exc_class",
    [
        (400, BadRequestError),
        (401, UnauthorizedError),
        (404, NotFoundError),
        (409, ConflictError),
        (422, UnprocessableError),
        (429, RateLimitedError),
    ],
)
def test_error_dispatch(client: BytefulClient, status: int, exc_class: type) -> None:
    with responses.RequestsMock() as rs:
        rs.add(
            responses.GET,
            f"{BASE}/public/user/customer/retrieve",
            json={
                "error": exc_class.__name__,
                "message": "boom",
                "api_request_id": "req-1",
            },
            status=status,
        )
        with pytest.raises(exc_class) as exc:
            client.customer_retrieve()
    assert exc.value.status_code == status
    assert exc.value.api_request_id == "req-1"
    assert exc.value.message == "boom"


@responses.activate
def test_403_plain_is_forbidden(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/customer/retrieve",
        json={"error": "Forbidden", "message": "no", "api_request_id": "r"},
        status=403,
    )
    with pytest.raises(ForbiddenError):
        client.customer_retrieve()


@responses.activate
def test_403_with_2fa_payload_is_two_factor(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/customer/retrieve",
        json={
            "error": "Two-Factor Authentication Required",
            "message": "need code",
            "two_factor_authentication_public_key": "pk_123",
            "two_factor_authentication_service": "email",
            "two_factor_authentication_target": "e******@byteful.com",
        },
        status=403,
    )
    with pytest.raises(TwoFactorAuthenticationRequired) as exc:
        client.customer_retrieve()
    assert exc.value.two_factor_authentication_public_key == "pk_123"
    assert exc.value.two_factor_authentication_service == "email"
    assert exc.value.two_factor_authentication_target == "e******@byteful.com"


@responses.activate
def test_unknown_status_falls_back_to_base(client: BytefulClient) -> None:
    responses.add(
        responses.GET,
        f"{BASE}/public/user/customer/retrieve",
        json={"error": "Teapot", "message": "no coffee"},
        status=418,
    )
    with pytest.raises(BytefulAPIError) as exc:
        client.customer_retrieve()
    assert exc.value.status_code == 418
    # Not a recognised subclass — falls back to the base class.
    assert type(exc.value) is BytefulAPIError

"""Tests for the ``Proxy`` URL builders and HTTP-client helpers."""

from __future__ import annotations

import pytest

from byteful import Proxy, ProxyProtocol, ProxyUser


def make_proxy(**overrides) -> Proxy:
    base = {
        "proxy_id": "p-1",
        "proxy_ip_address": "1.2.3.4",
        "proxy_ip_address_v6": "2001:db8::1",
        "proxy_http_port": 8080,
        "proxy_socks5_port": 1080,
        "default_proxy_user_username": "defaultu",
        "default_proxy_user_password": "defaultp",
        "proxy_username": "specificu",
        "proxy_password": "specificp",
        "proxy_protocol": "dual",
    }
    base.update(overrides)
    return Proxy.from_api(base)


def test_http_url_uses_default_proxy_user() -> None:
    p = make_proxy()
    assert p.http_url() == "http://defaultu:defaultp@1.2.3.4:8080"


def test_socks5_url_uses_default_proxy_user() -> None:
    p = make_proxy()
    assert p.socks5_url() == "socks5://defaultu:defaultp@1.2.3.4:1080"


def test_auth_url_with_socks5_protocol() -> None:
    p = make_proxy()
    assert p.auth_url(protocol="socks5") == "socks5://defaultu:defaultp@1.2.3.4:1080"
    assert p.auth_url(protocol="socks5h") == "socks5h://defaultu:defaultp@1.2.3.4:1080"


def test_auth_url_invalid_protocol_raises() -> None:
    p = make_proxy()
    with pytest.raises(ValueError, match="protocol"):
        p.auth_url(protocol="https")


def test_family_v6_uses_v6_address_in_brackets() -> None:
    p = make_proxy()
    assert p.http_url(family="v6") == "http://defaultu:defaultp@[2001:db8::1]:8080"


def test_explicit_proxy_user_object_overrides_default() -> None:
    p = make_proxy()
    pu = ProxyUser(proxy_user_id="other", proxy_user_password="otherp")
    assert p.http_url(pu) == "http://other:otherp@1.2.3.4:8080"


def test_explicit_proxy_user_tuple_overrides_default() -> None:
    p = make_proxy()
    assert p.http_url(("u", "p")) == "http://u:p@1.2.3.4:8080"


def test_falls_back_to_proxy_specific_creds_when_no_default() -> None:
    p = make_proxy(default_proxy_user_username=None, default_proxy_user_password=None)
    assert p.http_url() == "http://specificu:specificp@1.2.3.4:8080"


def test_raises_when_no_credentials_available() -> None:
    p = make_proxy(
        default_proxy_user_username=None,
        default_proxy_user_password=None,
        proxy_username=None,
        proxy_password=None,
    )
    with pytest.raises(ValueError, match="no credentials"):
        p.http_url()


def test_proxy_user_object_missing_password_raises() -> None:
    p = make_proxy()
    bad = ProxyUser(proxy_user_id="u")  # password missing
    with pytest.raises(ValueError, match="ProxyUser"):
        p.http_url(bad)


def test_raises_when_port_missing() -> None:
    p = make_proxy(proxy_http_port=None)
    with pytest.raises(ValueError, match="proxy_http_port"):
        p.http_url()


def test_as_requests_dict_uses_same_url_for_http_and_https() -> None:
    p = make_proxy()
    d = p.as_requests_dict()
    assert d["http"] == d["https"]
    assert d["http"].startswith("http://defaultu:")


def test_as_env_has_both_cases() -> None:
    p = make_proxy()
    env = p.as_env()
    assert env["HTTP_PROXY"] == env["http_proxy"]
    assert env["HTTPS_PROXY"] == env["https_proxy"]
    assert env["ALL_PROXY"] == env["all_proxy"]
    assert env["HTTP_PROXY"].startswith("http://defaultu:")


def test_aiohttp_kwargs_shape() -> None:
    p = make_proxy()
    kw = p.aiohttp_kwargs()
    assert kw == {"proxy": p.auth_url()}


def test_requests_session_sets_proxies_dict() -> None:
    p = make_proxy()
    sess = p.requests_session()
    expected = p.auth_url()
    assert sess.proxies["http"] == expected
    assert sess.proxies["https"] == expected
    sess.close()


def test_from_api_handles_missing_fields() -> None:
    p = Proxy.from_api({})
    assert p.proxy_id is None
    assert p.proxy_user_ids == []


def test_proxy_protocol_enum_coercion() -> None:
    p = make_proxy(proxy_protocol="ipv4")
    assert p.proxy_protocol == ProxyProtocol.IPV4

    # Unknown value falls through as raw string (forward-compat).
    p2 = make_proxy(proxy_protocol="some_future_protocol")
    assert p2.proxy_protocol == "some_future_protocol"


def test_availability_models_accept_bare_string() -> None:
    """The availability/search endpoint returns bare country-id strings when
    no ``group_by`` is supplied. Both Mobile and Residential models must
    tolerate that shape — found live: 422-free queries returning lists of
    ``"us"`` blew up with AttributeError before this was added."""
    from byteful import MobileAvailability, ResidentialAvailability

    m = MobileAvailability.from_api("us")
    assert m.country_id == "us"
    assert m.city_id is None

    r = ResidentialAvailability.from_api("de")
    assert r.country_id == "de"
    assert r.city_id is None

    # Structured shape still works.
    m2 = MobileAvailability.from_api({
        "country_id": "us", "city_id": 42, "mobile_availability_node_count": 100,
    })
    assert m2.country_id == "us"
    assert m2.city_id == 42
    assert m2.mobile_availability_node_count == 100

"""Tests for ``ProxyVerifier`` and the built-in providers."""

from __future__ import annotations

import json

import pytest

from byteful import (
    IcanhazipProvider,
    IfconfigCoProvider,
    IpifyProvider,
    IpinfoIoProvider,
    LeakCheck,
    ListVersion,
    Proxy,
    ProxyVerifier,
    VerificationError,
    VerificationResult,
)


def _proxy(ipv4: str = "203.0.113.5", ipv6: str | None = None) -> Proxy:
    return Proxy.from_api({
        "proxy_id": "p",
        "proxy_ip_address": ipv4,
        "proxy_ip_address_v6": ipv6,
        "proxy_http_port": 8080,
        "proxy_socks5_port": 1080,
        "default_proxy_user_username": "u",
        "default_proxy_user_password": "p",
        "proxy_protocol": "ipv6" if ipv6 else "ipv4",
    })


# ---- Provider parsing -----------------------------------------------------

def test_ipify_parses_json() -> None:
    p = IpifyProvider()
    r = p.parse(b'{"ip": "1.2.3.4"}', 200)
    assert r.ip == "1.2.3.4"
    assert r.provider == "ipify"


def test_ipify_url_picks_family() -> None:
    p = IpifyProvider()
    assert "api.ipify.org" in p.url(ListVersion.IPV4)
    assert "api6.ipify.org" in p.url(ListVersion.IPV6)


def test_icanhazip_parses_text() -> None:
    p = IcanhazipProvider()
    r = p.parse(b"1.2.3.4\n", 200)
    assert r.ip == "1.2.3.4"


def test_icanhazip_empty_body_raises() -> None:
    p = IcanhazipProvider()
    with pytest.raises(VerificationError):
        p.parse(b"   \n", 200)


def test_ifconfig_parses_asn_string() -> None:
    p = IfconfigCoProvider()
    body = json.dumps({
        "ip": "9.9.9.9",
        "country_iso": "US",
        "asn": "AS13335",
        "asn_org": "Cloudflare",
        "city": "Dallas",
        "region_name": "Texas",
    }).encode()
    r = p.parse(body, 200)
    assert r.asn == 13335
    assert r.asn_org == "Cloudflare"
    assert r.country == "US"


def test_ipinfo_parses_org_field() -> None:
    p = IpinfoIoProvider(token="x")
    body = json.dumps({"ip": "5.5.5.5", "org": "AS13335 Cloudflare Inc.",
                       "country": "US", "region": "TX", "city": "Dallas"}).encode()
    r = p.parse(body, 200)
    assert r.ip == "5.5.5.5"
    assert r.asn == 13335
    assert r.asn_org == "Cloudflare Inc."


def test_ipinfo_skips_ipv6_by_default() -> None:
    p = IpinfoIoProvider()
    assert ListVersion.IPV4 in p.supported_versions
    assert ListVersion.IPV6 not in p.supported_versions


def test_non_json_body_raises_verification_error() -> None:
    p = IpifyProvider()
    with pytest.raises(VerificationError):
        p.parse(b"<html>not json</html>", 200)


# ---- ProxyVerifier chain --------------------------------------------------

class _StubProvider:
    """Test double that returns a canned VerificationResult or raises."""

    def __init__(self, name: str, *, fail: bool = False, ip: str = "8.8.8.8",
                 supported_versions=None) -> None:
        self.name = name
        self.fail = fail
        self.ip = ip
        if supported_versions is not None:
            self.supported_versions = frozenset(supported_versions)
        self.called = 0

    def url(self, version):
        return f"https://stub-{self.name}.invalid/"

    def parse(self, body, status_code):
        return VerificationResult(ip=self.ip, provider=self.name, raw={})


class _StubVerifier(ProxyVerifier):
    """ProxyVerifier subclass that doesn't touch the network."""

    def _try_one(self, provider, proxy, family, proxy_user, protocol):
        provider.called += 1
        if provider.fail:
            raise VerificationError(f"{provider.name} planned failure")
        return provider.parse(b"", 200)


def test_chain_returns_first_success() -> None:
    p1 = _StubProvider("first", fail=True)
    p2 = _StubProvider("second", ip="203.0.113.5")
    p3 = _StubProvider("third")
    v = _StubVerifier(providers=[p1, p2, p3])
    r = v.check(_proxy())
    assert r.provider == "second"
    assert r.ip == "203.0.113.5"
    assert p3.called == 0  # short-circuited


def test_chain_all_failures_raises_with_summary() -> None:
    p1 = _StubProvider("first", fail=True)
    p2 = _StubProvider("second", fail=True)
    v = _StubVerifier(providers=[p1, p2])
    with pytest.raises(VerificationError) as exc:
        v.check(_proxy())
    assert "first" in str(exc.value)
    assert "second" in str(exc.value)


def test_provider_supported_versions_filters_chain() -> None:
    only_v6 = _StubProvider("v6only", supported_versions={ListVersion.IPV6})
    v = _StubVerifier(providers=[only_v6])
    with pytest.raises(VerificationError, match="IPV4"):
        v.check(_proxy(), family=ListVersion.IPV4)
    assert only_v6.called == 0


def test_check_leak_compares_to_egress() -> None:
    egress = "203.0.113.5"
    p2 = _StubProvider("v4", ip=egress)
    v = _StubVerifier(providers=[p2])
    leak = v.check_leak(_proxy(ipv4=egress))
    assert isinstance(leak, LeakCheck)
    assert leak.expected_ip == egress
    assert leak.matches is True
    assert leak.leaked is False


def test_check_leak_detects_mismatch() -> None:
    seen = "198.51.100.99"
    p2 = _StubProvider("v4", ip=seen)
    v = _StubVerifier(providers=[p2])
    leak = v.check_leak(_proxy(ipv4="203.0.113.5"))
    assert leak.leaked is True


def test_check_leak_ipv6_uses_v6_egress() -> None:
    v6 = "2001:db8::42"
    p = _StubProvider("v6", ip=v6, supported_versions={ListVersion.IPV6})
    v = _StubVerifier(providers=[p])
    leak = v.check_leak(_proxy(ipv4="203.0.113.5", ipv6=v6))
    assert leak.expected_ip == v6
    assert leak.matches


def test_provider_and_providers_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="not both"):
        ProxyVerifier(provider=IpifyProvider(), providers=[IpifyProvider()])


def test_empty_providers_rejected() -> None:
    with pytest.raises(ValueError, match="empty"):
        ProxyVerifier(providers=[])

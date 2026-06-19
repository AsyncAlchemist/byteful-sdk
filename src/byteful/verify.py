"""Modular proxy IP verification.

Built-in providers hit small public "what's my IP" services and convert their
responses to a common :class:`VerificationResult`. Users can plug in their own
by implementing the :class:`VerificationProvider` protocol.

For a byteful proxy, the destination sees the egress IP, which is
:attr:`Proxy.proxy_ip_address` (or :attr:`Proxy.proxy_ip_address_v6` when
routed over IPv6). :meth:`ProxyVerifier.check_leak` compares whatever the
verifier saw to that egress IP.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

import requests

from .enums import ListProtocol, ListVersion, ProxyProtocol
from .models import Proxy, ProxyUser


ALL_FAMILIES: frozenset[ListVersion] = frozenset({ListVersion.IPV4, ListVersion.IPV6})


class VerificationError(Exception):
    """Raised when a verification call fails to produce a usable result."""


@dataclass(slots=True)
class VerificationResult:
    """Normalized output from any verification provider.

    Only ``ip`` and ``provider`` are guaranteed to be set. Richer providers
    populate location/ASN fields; minimal ones leave them ``None``. The
    untouched payload is kept on ``raw`` for debugging or custom checks.
    """

    ip: str
    provider: str
    country: str | None = None
    region: str | None = None
    city: str | None = None
    asn: int | None = None
    asn_org: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LeakCheck:
    """Comparison of the IP a verifier saw against the proxy's expected egress.

    For byteful, the expected egress is whichever of
    :attr:`Proxy.proxy_ip_address` (IPv4) or :attr:`Proxy.proxy_ip_address_v6`
    (IPv6) corresponds to the family the request was routed over.
    """

    result: VerificationResult
    expected_ip: str

    @property
    def matches(self) -> bool:
        return self.result.ip == self.expected_ip

    @property
    def leaked(self) -> bool:
        return not self.matches


@runtime_checkable
class VerificationProvider(Protocol):
    """A pluggable IP-check endpoint.

    Implement :meth:`url` to return the URL to hit (the provider may pick a
    different host per address family) and :meth:`parse` to convert the
    response to a :class:`VerificationResult`.

    Providers MAY declare a ``supported_versions: Container[ListVersion]``
    attribute listing the address families they can handle. When set,
    :class:`ProxyVerifier` skips this provider for requests whose family
    isn't in the set. Providers without the attribute are treated as
    supporting all families.
    """

    name: str

    def url(self, version: ListVersion) -> str: ...
    def parse(self, body: bytes, status_code: int) -> VerificationResult: ...


def _safe_json(body: bytes) -> dict[str, Any]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise VerificationError(f"non-JSON body: {body[:200]!r}") from e
    if not isinstance(data, dict):
        raise VerificationError(f"expected JSON object, got {type(data).__name__}")
    return data


def _is_ipv6(version: ListVersion | str) -> bool:
    return str(version) == ListVersion.IPV6.value


class IpifyProvider:
    """``api.ipify.org`` / ``api6.ipify.org`` — minimal, returns just the IP."""

    name = "ipify"

    def __init__(self, *, supported_versions: Iterable[ListVersion] | None = None) -> None:
        self.supported_versions: frozenset[ListVersion] = (
            frozenset(supported_versions) if supported_versions is not None else ALL_FAMILIES
        )

    def url(self, version: ListVersion) -> str:
        host = "api6.ipify.org" if _is_ipv6(version) else "api.ipify.org"
        return f"https://{host}?format=json"

    def parse(self, body: bytes, status_code: int) -> VerificationResult:
        data = _safe_json(body)
        if "ip" not in data:
            raise VerificationError(f"ipify response missing 'ip': {data!r}")
        return VerificationResult(ip=str(data["ip"]), provider=self.name, raw=data)


class IcanhazipProvider:
    """``ipv4.icanhazip.com`` / ``ipv6.icanhazip.com`` — plain-text IP only."""

    name = "icanhazip"

    def __init__(self, *, supported_versions: Iterable[ListVersion] | None = None) -> None:
        self.supported_versions: frozenset[ListVersion] = (
            frozenset(supported_versions) if supported_versions is not None else ALL_FAMILIES
        )

    def url(self, version: ListVersion) -> str:
        host = "ipv6.icanhazip.com" if _is_ipv6(version) else "ipv4.icanhazip.com"
        return f"https://{host}"

    def parse(self, body: bytes, status_code: int) -> VerificationResult:
        ip = body.decode("ascii", errors="replace").strip()
        if not ip:
            raise VerificationError("icanhazip returned an empty body")
        return VerificationResult(ip=ip, provider=self.name, raw={"ip": ip})


class IfconfigCoProvider:
    """``ifconfig.co/json`` — JSON with country/ASN."""

    name = "ifconfig.co"

    def __init__(self, *, supported_versions: Iterable[ListVersion] | None = None) -> None:
        self.supported_versions: frozenset[ListVersion] = (
            frozenset(supported_versions) if supported_versions is not None else ALL_FAMILIES
        )

    def url(self, version: ListVersion) -> str:
        return "https://ifconfig.co/json"

    def parse(self, body: bytes, status_code: int) -> VerificationResult:
        data = _safe_json(body)
        if "ip" not in data:
            raise VerificationError(f"ifconfig.co response missing 'ip': {data!r}")
        asn_raw = data.get("asn")
        asn: int | None = None
        if isinstance(asn_raw, str) and asn_raw.startswith("AS"):
            try:
                asn = int(asn_raw[2:])
            except ValueError:
                asn = None
        elif isinstance(asn_raw, int):
            asn = asn_raw
        return VerificationResult(
            ip=str(data["ip"]),
            country=data.get("country_iso") or None,
            region=data.get("region_name") or None,
            city=data.get("city") or None,
            asn=asn,
            asn_org=data.get("asn_org") or None,
            raw=data,
            provider=self.name,
        )


class IpinfoIoProvider:
    """``ipinfo.io/json`` — city/region/country plus ASN in the ``org`` field.

    Defaults to **IPv4 only** because ``ipinfo.io`` has no AAAA record. Pass
    ``supported_versions=`` to opt back in over a v6-reachable mirror.
    """

    name = "ipinfo.io"

    def __init__(
        self,
        token: str | None = None,
        *,
        supported_versions: Iterable[ListVersion] | None = None,
    ) -> None:
        self.token = token
        self.supported_versions: frozenset[ListVersion] = (
            frozenset(supported_versions)
            if supported_versions is not None
            else frozenset({ListVersion.IPV4})
        )

    def url(self, version: ListVersion) -> str:
        if self.token:
            return f"https://ipinfo.io/json?token={self.token}"
        return "https://ipinfo.io/json"

    def parse(self, body: bytes, status_code: int) -> VerificationResult:
        data = _safe_json(body)
        if "ip" not in data:
            raise VerificationError(f"ipinfo.io response missing 'ip': {data!r}")
        org = data.get("org", "")
        asn: int | None = None
        asn_org: str | None = None
        if isinstance(org, str) and org.startswith("AS"):
            head, _, tail = org.partition(" ")
            try:
                asn = int(head[2:])
            except ValueError:
                pass
            asn_org = tail or None
        return VerificationResult(
            ip=str(data["ip"]),
            country=data.get("country") or None,
            region=data.get("region") or None,
            city=data.get("city") or None,
            asn=asn,
            asn_org=asn_org,
            raw=data,
            provider=self.name,
        )


DEFAULT_VERIFICATION_PROVIDER: VerificationProvider = IpifyProvider()
DEFAULT_VERIFICATION_PROVIDERS: tuple[VerificationProvider, ...] = (
    IpifyProvider(),
    IcanhazipProvider(),
    IfconfigCoProvider(),
    IpinfoIoProvider(),
)
DEFAULT_VERIFICATION_TIMEOUT = 10.0


class ProxyVerifier:
    """Route a verification request through a byteful proxy and parse the result.

    With no arguments, tries the four built-in providers (ipify, icanhazip,
    ifconfig.co, ipinfo.io) in order and returns the first success. Pass
    ``provider=`` to pin one (failures will raise instead of falling back),
    or ``providers=`` to control the fallback order explicitly.

    Example::

        with ProxyVerifier() as v:
            leak = v.check_leak(proxy)
            assert not leak.leaked, f"saw {leak.result.ip}, expected {leak.expected_ip}"
    """

    def __init__(
        self,
        provider: VerificationProvider | None = None,
        *,
        providers: Sequence[VerificationProvider] | None = None,
        timeout: float = DEFAULT_VERIFICATION_TIMEOUT,
        session: requests.Session | None = None,
    ) -> None:
        if provider is not None and providers is not None:
            raise ValueError("pass either `provider` or `providers`, not both")
        if provider is not None:
            chain: tuple[VerificationProvider, ...] = (provider,)
        elif providers is not None:
            chain = tuple(providers)
            if not chain:
                raise ValueError("`providers` cannot be empty")
        else:
            chain = DEFAULT_VERIFICATION_PROVIDERS
        self.providers: tuple[VerificationProvider, ...] = chain
        self.timeout = timeout
        self._session = session or requests.Session()
        self._owns_session = session is None

    @property
    def provider(self) -> VerificationProvider:
        """Convenience: the first (and possibly only) provider in the chain."""
        return self.providers[0]

    def __enter__(self) -> "ProxyVerifier":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    @staticmethod
    def _autodetect_family(proxy: Proxy) -> ListVersion:
        # If the proxy is v6-only, route over v6; otherwise default to v4.
        if (
            proxy.proxy_protocol == ProxyProtocol.IPV6
            and proxy.proxy_ip_address_v6
        ):
            return ListVersion.IPV6
        return ListVersion.IPV4

    @staticmethod
    def _family_arg(family: ListVersion) -> str:
        return "v6" if family == ListVersion.IPV6 else "v4"

    def _expected_egress(self, proxy: Proxy, family: ListVersion) -> str:
        if family == ListVersion.IPV6:
            ip = proxy.proxy_ip_address_v6
        else:
            ip = proxy.proxy_ip_address
        if not ip:
            raise VerificationError(
                f"proxy is missing proxy_ip_address{'_v6' if family == ListVersion.IPV6 else ''}"
            )
        return ip

    def _try_one(
        self,
        provider: VerificationProvider,
        proxy: Proxy,
        family: ListVersion,
        proxy_user: ProxyUser | tuple[str, str] | None,
        protocol: ListProtocol | str,
    ) -> VerificationResult:
        url = provider.url(family)
        auth = proxy.auth_url(
            proxy_user,
            protocol=(protocol.value if hasattr(protocol, "value") else str(protocol)),
            family=self._family_arg(family),
        )
        try:
            resp = self._session.get(
                url,
                proxies={"http": auth, "https": auth},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise VerificationError(
                f"transport error via {provider.name}: {e}"
            ) from e
        if resp.status_code >= 400:
            raise VerificationError(
                f"{provider.name} returned HTTP {resp.status_code}: "
                f"{resp.text[:200]!r}"
            )
        return provider.parse(resp.content, resp.status_code)

    def check(
        self,
        proxy: Proxy,
        *,
        family: ListVersion | str | None = None,
        proxy_user: ProxyUser | tuple[str, str] | None = None,
        protocol: ListProtocol | str = ListProtocol.HTTP,
    ) -> VerificationResult:
        """Issue a request through ``proxy`` and return the normalized result.

        Tries each configured provider in order and returns the first one that
        succeeds. Providers that declare a ``supported_versions`` attribute
        without the requested family are skipped (without counting as a
        failure). If every provider that could be tried fails, raises a
        single :class:`VerificationError` summarizing each failure.
        """
        v: ListVersion
        if family is None:
            v = self._autodetect_family(proxy)
        elif isinstance(family, ListVersion):
            v = family
        else:
            v = ListVersion(family)

        errors: list[tuple[str, str]] = []
        skipped: list[str] = []
        for p in self.providers:
            supported = getattr(p, "supported_versions", None)
            if supported is not None and v not in supported:
                skipped.append(p.name)
                continue
            try:
                return self._try_one(p, proxy, v, proxy_user, protocol)
            except VerificationError as e:
                errors.append((p.name, str(e)))
        if not errors:
            skipped_str = ", ".join(skipped) if skipped else "(none)"
            raise VerificationError(
                f"no verification provider in chain supports {v.name}; "
                f"skipped: {skipped_str}"
            )
        names = ", ".join(name for name, _ in errors)
        details = "; ".join(f"{name}: {err}" for name, err in errors)
        msg = f"all {len(errors)} verification providers failed ({names}): {details}"
        if skipped:
            msg += (
                f" (also skipped {len(skipped)} provider(s) that don't support "
                f"{v.name}: {', '.join(skipped)})"
            )
        raise VerificationError(msg)

    def check_leak(
        self,
        proxy: Proxy,
        *,
        family: ListVersion | str | None = None,
        proxy_user: ProxyUser | tuple[str, str] | None = None,
        protocol: ListProtocol | str = ListProtocol.HTTP,
    ) -> LeakCheck:
        """As :meth:`check`, but also compare the seen IP to the proxy's egress."""
        v: ListVersion
        if family is None:
            v = self._autodetect_family(proxy)
        elif isinstance(family, ListVersion):
            v = family
        else:
            v = ListVersion(family)
        result = self.check(proxy, family=v, proxy_user=proxy_user, protocol=protocol)
        return LeakCheck(result=result, expected_ip=self._expected_egress(proxy, v))

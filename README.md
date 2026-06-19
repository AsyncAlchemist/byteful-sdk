# byteful-sdk

[![CI](https://github.com/AsyncAlchemist/byteful-sdk/actions/workflows/ci.yml/badge.svg)](https://github.com/AsyncAlchemist/byteful-sdk/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/AsyncAlchemist/byteful-sdk/graph/badge.svg)](https://codecov.io/gh/AsyncAlchemist/byteful-sdk)
[![PyPI version](https://badge.fury.io/py/byteful-sdk.svg)](https://pypi.org/project/byteful-sdk/)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Unofficial** — this project is a community-built client for
> [byteful](https://byteful.com/) and is **not affiliated with, endorsed by,
> or supported by byteful**. All trademarks belong to their respective
> owners.

A typed Python SDK for the [byteful Public User API](https://documentation.byteful.com/api-introduction).

Covers the full 50+ endpoint surface — proxies, proxy users, ACLs, services,
checkout, generated proxy lists (mobile/residential), availability,
analytics, logs, ledgers, geographic resources (country/city/subdivision/zip
code/continent/ASN), service adjustments, and more. Responses are parsed
into dataclasses with proper types (`datetime`, `int`, `bool`, enums) instead
of raw JSON.

> **Status:** alpha (`0.1.0a1`). The public API may change before `0.1.0`.
> See [CHANGELOG.md](CHANGELOG.md) for what shipped.

## Install

```sh
uv add byteful-sdk
# or
pip install byteful-sdk
```

The distribution name is `byteful-sdk`; the import name is `byteful`:

```python
from byteful import BytefulClient
```

Requires Python 3.13+.

## Quick start

```python
from byteful import BytefulClient, ProxyType

# Pass the keys explicitly...
with BytefulClient(
    api_public_key="YOUR_PUBLIC_KEY",
    api_private_key="YOUR_PRIVATE_KEY",
) as client:
    ...

# ...or set BYTEFUL_API_PUBLIC_KEY + BYTEFUL_API_PRIVATE_KEY in the
# environment and omit them.
with BytefulClient() as client:
    me = client.customer_retrieve()
    print(f"Hello {me.customer_first_name}, balance is {me.credit_balance}")

    # Find available residential capacity in the US
    avail = client.residential_availability_count(country_id="us")
    print(avail.data)

    # Buy a small ISP service
    order = client.checkout_create(
        product_type="isp",
        product_protocol="ipv4",
        country_id="us",
        quantity=5,
        cycle_interval="month",
        cycle_interval_count=1,
    )
    print(order.data)

    # List the proxies that just landed
    for p in client.proxy_search(proxy_type=ProxyType.ISP, country_id="us"):
        print(p.proxy_id, p.proxy_ip_address, p.proxy_http_port)
```

## Authentication

The byteful API requires two header-based keys:

| Header                 | Where it comes from                       |
| ---------------------- | ----------------------------------------- |
| `X-API-Public-Key`     | Identifies your account                   |
| `X-API-Private-Key`    | Verifies your identity — keep this secret |

The SDK reads them in this order:

1. The `api_public_key=` / `api_private_key=` constructor arguments
2. The `BYTEFUL_API_PUBLIC_KEY` / `BYTEFUL_API_PRIVATE_KEY` environment variables

If either is missing, `BytefulClient()` raises `ValueError`. The SDK does
**not** load `.env` files itself; if you keep your keys in `.env`, use
[python-dotenv](https://github.com/theskumar/python-dotenv):

```python
from dotenv import load_dotenv
from byteful import BytefulClient

load_dotenv()
client = BytefulClient()
```

Generate keys at `dashboard.byteful.com/developer/api-key`.

## API surface

Methods on `BytefulClient` mirror the URL path 1:1, so you can find any
documented endpoint by its URL:

| URL                                              | Method                                       |
| ------------------------------------------------ | -------------------------------------------- |
| `GET /customer/retrieve`                         | `customer_retrieve()`                        |
| `GET /proxy/retrieve/{id}`                       | `proxy_retrieve(proxy_id)`                   |
| `GET /proxy/search`                              | `proxy_search(...)`                          |
| `GET /proxy/list_by_search`                      | `proxy_list_by_search(...)`                  |
| `POST /proxy/list_by_id`                         | `proxy_list_by_id(proxy_ids, ...)`           |
| `POST /proxy/list/options`                       | `proxy_list_options(...)`                    |
| `GET /proxy_user/retrieve/{id}`                  | `proxy_user_retrieve(id)`                    |
| `GET /proxy_user/search`                         | `proxy_user_search(...)`                     |
| `POST /proxy_user/create`                        | `proxy_user_create(...)`                     |
| `PATCH /proxy_user/edit/{id}`                    | `proxy_user_edit(id, ...)`                   |
| `DELETE /proxy_user/delete/{id}`                 | `proxy_user_delete(id)`                      |
| `GET /proxy_user_acl/retrieve/{id}`              | `proxy_user_acl_retrieve(id)`                |
| `GET /proxy_user_acl/search`                     | `proxy_user_acl_search(...)`                 |
| `POST /proxy_user_acl/create`                    | `proxy_user_acl_create(...)`                 |
| `DELETE /proxy_user_acl/delete/{id}`             | `proxy_user_acl_delete(id)`                  |
| `GET /service/retrieve/{id}`                     | `service_retrieve(id)`                       |
| `GET /service/search`                            | `service_search(...)`                        |
| `PATCH /service/edit/{id}`                       | `service_edit(id, ...)`                      |
| `DELETE /service/cancel/{id}`                    | `service_cancel(id, ...)`                    |
| `GET /service_adjustment/retrieve/{id}`          | `service_adjustment_retrieve(id)`            |
| `GET /service_adjustment/search`                 | `service_adjustment_search(...)`             |
| `GET /checkout/catalog`                          | `checkout_catalog()`                         |
| `POST /checkout/quote`                           | `checkout_quote(...)`                        |
| `POST /checkout/create`                          | `checkout_create(...)`                       |
| `GET /mobile/list`                               | `mobile_list(...)`                           |
| `GET /mobile/summary`                            | `mobile_summary()`                           |
| `GET /mobile_availability/count`                 | `mobile_availability_count(...)`             |
| `GET /mobile_availability/search`                | `mobile_availability_search(...)`            |
| `GET /mobile_ledger/retrieve/{id}`               | `mobile_ledger_retrieve(id)`                 |
| `GET /mobile_ledger/search`                      | `mobile_ledger_search(...)`                  |
| `GET /residential/list`                          | `residential_list(...)`                      |
| `GET /residential/summary`                       | `residential_summary()`                      |
| `GET /residential_availability/count`            | `residential_availability_count(...)`        |
| `GET /residential_availability/search`           | `residential_availability_search(...)`       |
| `GET /residential_ledger/retrieve/{id}`          | `residential_ledger_retrieve(id)`            |
| `GET /residential_ledger/search`                 | `residential_ledger_search(...)`             |
| `GET /product/search`                            | `product_search(...)`                        |
| `GET /analytics/breakdown`                       | `analytics_breakdown(...)`                   |
| `GET /analytics/graph`                           | `analytics_graph(...)`                       |
| `GET /log/retrieve/{id}`                         | `log_retrieve(id)`                           |
| `GET /log/search`                                | `log_search(...)`                            |
| `GET /log_summary/retrieve/{id}`                 | `log_summary_retrieve(id)`                   |
| `GET /log_summary/search`                        | `log_summary_search(...)`                    |
| `GET /proxy_test_server/search`                  | `proxy_test_server_search(...)`              |
| `GET /country/retrieve/{id}`                     | `country_retrieve(id)`                       |
| `GET /country/search`                            | `country_search(...)`                        |
| `GET /city/retrieve/{id}`                        | `city_retrieve(id)`                          |
| `GET /city/search`                               | `city_search(...)`                           |
| `GET /subdivision/retrieve/{id}`                 | `subdivision_retrieve(id)`                   |
| `GET /subdivision/search`                        | `subdivision_search(...)`                    |
| `GET /zip_code/retrieve/{id}`                    | `zip_code_retrieve(id)`                      |
| `GET /zip_code/search`                           | `zip_code_search(...)`                       |
| `GET /continent/retrieve/{id}`                   | `continent_retrieve(id)`                     |
| `GET /continent/search`                          | `continent_search(...)`                      |
| `GET /asn/retrieve/{id}`                         | `asn_retrieve(id)`                           |
| `GET /asn/search`                                | `asn_search(...)`                            |
| `GET /ip_address/geolocate/{ip}`                 | `ip_address_geolocate(ip)`                   |

Convenience helpers built on top of `proxy_search`:

| Method                                              | Purpose                                          |
| --------------------------------------------------- | ------------------------------------------------ |
| `proxies(refresh?)`                                 | Cached view of the full pool                     |
| `invalidate_proxy_cache()`                          | Drop the pool cache                              |
| `select_proxy(...)`                                 | Pick one proxy matching filters, raises if none  |
| `requests_session(...)`                             | One-shot: pick a proxy → `requests.Session`      |
| `httpx_client(...)`                                 | One-shot: pick a proxy → `httpx.Client`          |
| `httpx_async_client(...)`                           | One-shot: pick a proxy → `httpx.AsyncClient`     |
| `aiohttp_kwargs(...)`                               | One-shot: pick a proxy → kwargs for `aiohttp`    |

## Pagination

Search responses are paginated and wrapped in a `PageResult`:

```python
page = client.proxy_search(per_page=100, page=1)
print(page.total_count, page.item_count, page.has_more)
for proxy in page:
    print(proxy.proxy_id)

# Walk every page
all_proxies = []
page_n = 1
while True:
    p = client.proxy_search(per_page=500, page=page_n)
    all_proxies.extend(p.data)
    if not p.has_more:
        break
    page_n = p.next_page
```

For the common "give me my pool, I'll filter locally" workflow there's
`proxies()`, which walks every page once and reuses the result:

```python
pool = client.proxies()                       # one walk, every page
us_isp = pool.filter(country_id="us", proxy_type="isp")
proxy = us_isp.random()
client.proxies()                              # served from cache
```

- Default TTL is 24 hours. Override with
  `BytefulClient(proxy_cache_ttl=3600)` (seconds) or pass `None` to disable.
- The cache is **automatically invalidated** after any state-changing call
  (`checkout_*`, `proxy_user_*`, `proxy_user_acl_*`, `service_*`).
- Force a refresh with `client.proxies(refresh=True)` or drop the cache
  explicitly with `client.invalidate_proxy_cache()`.

## Using your proxies in an HTTP client

The SDK ships convenience helpers at two levels so you don't have to stitch
proxy URLs together by hand. byteful authenticates proxies with a
[proxy user](https://documentation.byteful.com/general/creating-a-proxy-user.md);
each `Proxy` carries the default proxy user credentials, so by default no
extra setup is needed.

**One-liner on the client** — picks a proxy from the cached pool
(auto-filtered to `IN_USE` by default) and hands back a ready-to-use client:

```python
with BytefulClient() as c:
    with c.requests_session(country_id="us") as s:
        r = s.get("https://api.ipify.org?format=json", timeout=10)
        print(r.json()["ip"])
```

**Per-proxy** — pick the proxy yourself, produce a client from it:

```python
with BytefulClient() as c:
    proxy = c.select_proxy(country_id="us", proxy_type="isp")
    with proxy.requests_session() as s:
        r = s.get("https://api.ipify.org?format=json", timeout=10)
```

Both forms share the cache.

### Examples per library

**requests**

```python
from byteful import BytefulClient

with BytefulClient() as c:
    with c.requests_session(country_id="us") as s:
        print(s.get("https://api.ipify.org?format=json", timeout=10).json()["ip"])
```

**httpx (sync)**

```python
from byteful import BytefulClient

with BytefulClient() as c:
    with c.httpx_client(country_id="us", timeout=10) as client:
        print(client.get("https://api.ipify.org?format=json").json()["ip"])
```

**httpx (async)**

```python
import asyncio
from byteful import BytefulClient

async def main() -> None:
    with BytefulClient() as c:
        async with c.httpx_async_client(country_id="us", timeout=10) as client:
            r = await client.get("https://api.ipify.org?format=json")
            print(r.json()["ip"])

asyncio.run(main())
```

**aiohttp** — `aiohttp` has no session-level proxy setting:

```python
import asyncio
import aiohttp
from byteful import BytefulClient

async def main() -> None:
    with BytefulClient() as c:
        kw = c.aiohttp_kwargs(country_id="us")  # {"proxy": "http://u:p@host:port"}
        async with aiohttp.ClientSession() as s:
            async with s.get("https://api.ipify.org?format=json", **kw) as r:
                print((await r.json())["ip"])

asyncio.run(main())
```

**subprocess / curl / wget** — env-var format for shelling out:

```python
import os
import subprocess
from byteful import BytefulClient

with BytefulClient() as c:
    proxy = c.select_proxy(country_id="us")
    subprocess.run(
        ["curl", "https://api.ipify.org"],
        env={**os.environ, **proxy.as_env()},
    )
```

**Using a custom proxy user**

Pass a `ProxyUser` (or a raw `(username, password)` tuple) to any of the
URL builders to authenticate as that user instead of the proxy's default:

```python
pu = client.proxy_user_create(proxy_user_access_type="all").data
url = proxy.auth_url(pu, protocol="http", family="v4")
```

**Just give me the URL / dict** — if you're plugging into something else:

```python
proxy.http_url()                  # "http://user:pass@host:8080"
proxy.socks5_url()                # "socks5://user:pass@host:1080"
proxy.auth_url(protocol="socks5") # same as socks5_url
proxy.as_requests_dict()          # {"http": url, "https": url}
proxy.aiohttp_kwargs()            # {"proxy": url}
```

`httpx` and `aiohttp` are imported lazily — they only need to be installed
if you actually call the corresponding helper.

## Generated proxy lists

For mobile and residential traffic (and for "give me a chunk of formatted
strings" workflows on ISP/datacenter), use the generated-list endpoints:

```python
# 1000 sticky US residential proxies, formatted ip:port:user:pass
batch = client.residential_list(
    country_id="us",
    list_count=1000,
    list_format="standard",
    list_session_type="sticky",
)
for line in batch:
    print(line)
```

Same shape for `mobile_list()`, `proxy_list_by_search()` (filter by location
or service) and `proxy_list_by_id()` (specific UUIDs).

## Enums

```python
from byteful import (
    ProxyType,         # DATACENTER / ISP / RESIDENTIAL / MOBILE
    ProxyProtocol,     # IPV4 / IPV6 / DUAL
    ProxyStatus,       # AVAILABLE / IN_USE / RESERVED / WAITING / PENDING_DELETION
    ServiceStatus,     # ACTIVE / CANCELED / AWAITING_FULFILLMENT / ...
    ServiceType,       # DATACENTER / ISP / RESIDENTIAL / MOBILE / OFF_CATALOG
    CycleInterval,     # YEAR / MONTH / WEEK / DAY
    ListFormat,        # STANDARD / HTTP / HTTPS / SOCKS5 / SOCKS5H
    ListSessionType,   # STICKY / ROTATING
    ListMode,          # GENERAL / SIZE / SPEED
    ListAuthentication,# USERNAME_AND_PASSWORD / IP_ADDRESS / PROXY_SPECIFIC
    CancelFeedback,    # TOO_EXPENSIVE / SWITCHED_SERVICE / ...
)
```

Unknown values from the server are passed through as raw strings rather than
raising, so a newly-added enum variant doesn't break the SDK.

## Errors

The API uses an envelope of `{"error":"...","message":"...","api_request_id":"..."}`
on non-2xx HTTP responses. Each documented HTTP status code has its own
exception subclass:

```python
from byteful import (
    BytefulAPIError,
    BadRequestError,
    UnauthorizedError,
    ForbiddenError,
    TwoFactorAuthenticationRequired,
    NotFoundError,
    MethodNotAllowedError,
    ConflictError,
    UnprocessableError,
    RateLimitedError,
    InternalServerError,
)

try:
    client.checkout_create(product_type="isp", country_id="us", quantity=5)
except UnauthorizedError:
    rotate_keys()
except TwoFactorAuthenticationRequired as e:
    prompt_for_2fa(e.two_factor_authentication_target)
except UnprocessableError as e:
    log.warning("byteful rejected the request: %s (req %s)", e.message, e.api_request_id)
except BytefulAPIError as e:
    log.error("byteful %s: %s", e.status_code, e.message)
```

| Code | Exception                          | Meaning                                  |
| ---: | ---------------------------------- | ---------------------------------------- |
|  400 | `BadRequestError`                  | Invalid or improperly formatted request  |
|  401 | `UnauthorizedError`                | Missing or invalid auth credentials      |
|  403 | `ForbiddenError`                   | Authenticated but lacks permission       |
|  403 | `TwoFactorAuthenticationRequired`  | 2FA challenge issued (2FA fields populated) |
|  404 | `NotFoundError`                    | Resource does not exist                  |
|  405 | `MethodNotAllowedError`            | HTTP method not supported on the URL     |
|  409 | `ConflictError`                    | Conflicts with current state             |
|  422 | `UnprocessableError`               | Failed business-logic validation         |
|  429 | `RateLimitedError`                 | Rate limit exceeded                      |
|  500 | `InternalServerError`              | Server-side fault                        |

The raw documented messages are also exposed as the `byteful.ERROR_CODES`
dict.

## Rate limiting

The API allows **10 requests per second per customer**; over that limit it
returns HTTP 429. The SDK ships with a thread-safe sliding-window limiter
that all `BytefulClient` instances share by default, so you don't have to
think about it — concurrent calls just block long enough to stay under the
cap.

```python
from byteful import BytefulClient, RateLimiter

# Default — uses the process-wide DEFAULT_RATE_LIMITER (10/s).
client = BytefulClient()

# Custom limit (e.g. you have a higher-tier agreement).
client = BytefulClient(rate_limiter=RateLimiter(max_requests=30, period=1.0))

# Disable entirely (you're handling throttling yourself).
client = BytefulClient(rate_limiter=None)
```

## Verifying a proxy against a live IP-check service

`ProxyVerifier` routes a request through a proxy and asks a public
"what's my IP" service what it sees, so you can confirm the proxy is
egressing as expected and your real IP isn't leaking. By default it walks
through four built-in providers in order and returns the first success,
so one provider being down or blocking your IP doesn't break the check.

```python
from byteful import BytefulClient, ProxyVerifier

with BytefulClient() as c:
    proxy = c.proxies().filter(country_id="us").random()

with ProxyVerifier() as v:
    leak = v.check_leak(proxy)
    print(leak.result.ip, leak.result.country, leak.leaked, leak.result.provider)
```

`check_leak()` returns a `LeakCheck` whose `leaked` property is `True`
whenever the IP the service saw differs from the proxy's expected egress
(`proxy.proxy_ip_address` for IPv4 / `proxy.proxy_ip_address_v6` for IPv6).

Built-in providers (the default chain, in order):

| Provider              | Endpoint                                          | Data returned                                      |
| --------------------- | ------------------------------------------------- | -------------------------------------------------- |
| `IpifyProvider`       | `api.ipify.org` / `api6.ipify.org`                | IP only — smallest moving part                     |
| `IcanhazipProvider`   | `ipv4.icanhazip.com` / `ipv6.icanhazip.com`       | IP only, plain text                                |
| `IfconfigCoProvider`  | `ifconfig.co/json`                                | IP + country + region + city + ASN                 |
| `IpinfoIoProvider` *(IPv4 only)* | `ipinfo.io/json`                       | IP + country + region + city + ASN                 |

Pin a single provider (no fallback) or control the chain explicitly:

```python
# Single provider — failures raise instead of falling back.
ProxyVerifier(provider=IpifyProvider()).check(proxy)

# Custom fallback chain, tried in order.
ProxyVerifier(providers=[my_checker, IpifyProvider(), IcanhazipProvider()]).check(proxy)
```

## Using a custom session

Inject any `requests.Session` (e.g. with retry policies or a proxy of your
own):

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(
    total=5, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504)
)))
client = BytefulClient(session=session)
```

## Development

```sh
uv sync
uv run pytest                    # unit tests only (integration is gated)
uv run pytest -m integration     # hit the real API; needs the BYTEFUL_API_* keys
```

Put your keys in a local `.env`; `tests/conftest.py` loads it automatically.

User-visible changes are tracked in [CHANGELOG.md](CHANGELOG.md) — add an
entry under `[Unreleased]` whenever you ship something that affects the
public API.

## License

MIT — see [LICENSE](LICENSE). This is an unofficial project and ships with
no warranty of fitness for any particular purpose.

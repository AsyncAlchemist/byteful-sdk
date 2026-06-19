# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0a1] - 2026-06-19

### Added
- Initial alpha release.
- `BytefulClient` covering every documented endpoint of the byteful Public
  User API (`/public/user/...`):
  - Customer: `customer_retrieve`
  - Proxy: `proxy_retrieve`, `proxy_search`, `proxy_list_by_search`,
    `proxy_list_by_id`, `proxy_list_options`
  - Proxy User: `proxy_user_retrieve`, `proxy_user_search`,
    `proxy_user_create`, `proxy_user_edit`, `proxy_user_delete`
  - Proxy User ACL: `proxy_user_acl_retrieve`, `proxy_user_acl_search`,
    `proxy_user_acl_create`, `proxy_user_acl_delete`
  - Service: `service_retrieve`, `service_search`, `service_edit`,
    `service_cancel`
  - Service Adjustment: `service_adjustment_retrieve`,
    `service_adjustment_search`
  - Checkout: `checkout_catalog`, `checkout_quote`, `checkout_create`
  - Mobile: `mobile_list`, `mobile_summary`, `mobile_availability_count`,
    `mobile_availability_search`, `mobile_ledger_retrieve`,
    `mobile_ledger_search`
  - Residential: `residential_list`, `residential_summary`,
    `residential_availability_count`, `residential_availability_search`,
    `residential_ledger_retrieve`, `residential_ledger_search`
  - Product: `product_search`
  - Analytics: `analytics_breakdown`, `analytics_graph`
  - Logs: `log_retrieve`, `log_search`, `log_summary_retrieve`,
    `log_summary_search`
  - Proxy Test Server: `proxy_test_server_search`
  - Geography: `country_*`, `city_*`, `subdivision_*`, `zip_code_*`,
    `continent_*`, `asn_*`
  - Misc: `ip_address_geolocate`
- Typed dataclasses for every API object (`Proxy`, `Service`, `Customer`,
  `ProxyUser`, `ProxyUserAcl`, `Country`, `City`, `Subdivision`,
  `ZipCode`, `Continent`, `Asn`, `Log`, `LogSummary`, `MobileLedger`,
  `ResidentialLedger`, `ServiceAdjustment`, `MobileAvailability`,
  `ResidentialAvailability`, `ProxyTestServer`, `ProxyReplacement`,
  `SubscriptionSchedule`, `Product`).
- `PageResult` wrapper for paginated search responses, with `has_more`
  / `next_page` and iteration.
- Cached `proxies()` pool with `ProxyList.filter` and `random()`, auto-
  invalidated after state-changing calls.
- `select_proxy`, `requests_session`, `httpx_client`, `httpx_async_client`
  and `aiohttp_kwargs` HTTP-client helpers — both on `BytefulClient` and
  on individual `Proxy` instances. `httpx` / `aiohttp` are imported lazily.
- `Proxy.http_url`, `Proxy.socks5_url`, `Proxy.auth_url`,
  `Proxy.as_requests_dict`, `Proxy.as_env`, `Proxy.aiohttp_kwargs`.
- Process-wide rate limiter (`RateLimiter`, defaulting to 10 req/s per the
  byteful docs), shared by default across all `BytefulClient` instances.
- Typed exception hierarchy under `BytefulAPIError`: `BadRequestError`,
  `UnauthorizedError`, `ForbiddenError`, `TwoFactorAuthenticationRequired`,
  `NotFoundError`, `MethodNotAllowedError`, `ConflictError`,
  `UnprocessableError`, `RateLimitedError`, `InternalServerError`.
  Subclasses are selected automatically by HTTP status code.
- `ProxyVerifier` for leak-checking proxies against public IP-info
  services, with four built-in providers (`ipify`, `icanhazip`,
  `ifconfig.co`, `ipinfo.io`) and a pluggable `VerificationProvider`
  protocol.
- Enums for every documented enumerated value: `ProxyType`,
  `ProxyProtocol`, `ProxyStatus`, `ProxyUserAccessType`, `ServiceStatus`,
  `ServiceType`, `ServiceAdjustmentStatus`, `ServiceAdjustmentType`,
  `CycleInterval`, `ListFormat`, `ListProtocol`, `ListVersion`,
  `ListSessionType`, `ListMode`, `ListAuthentication`, `AsnType`,
  `AsnRir`, `LogNetwork`, `LogProtocol`, `LogTransport`,
  `CancelFeedback`, `AnalyticsInterval`, `AvailabilityGroupBy`,
  `ProxyReplacementReason`, `SubscriptionScheduleStatus`,
  `SubscriptionScheduleType`. Unknown server-side values fall through as
  raw strings rather than raising.

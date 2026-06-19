from __future__ import annotations

from enum import StrEnum


class ProxyType(StrEnum):
    """The product family a proxy belongs to."""

    DATACENTER = "datacenter"
    ISP = "isp"
    RESIDENTIAL = "residential"
    MOBILE = "mobile"


class ProxyProtocol(StrEnum):
    """IP address family a proxy is configured for."""

    IPV4 = "ipv4"
    IPV6 = "ipv6"
    DUAL = "dual"


class ProxyStatus(StrEnum):
    """Provisioning state of an individual proxy on byteful."""

    AVAILABLE = "available"
    IN_USE = "in_use"
    RESERVED = "reserved"
    WAITING = "waiting"
    PENDING_DELETION = "pending_deletion"


class ProxyUserAccessType(StrEnum):
    ALL = "all"
    SERVICE_RESTRICTED = "service_restricted"
    PROXY_RESTRICTED = "proxy_restricted"


class ServiceStatus(StrEnum):
    AWAITING_MANUAL_FULFILLMENT = "awaiting_manual_fulfillment"
    AWAITING_ADDITIONAL_FULFILLMENT = "awaiting_additional_fulfillment"
    AWAITING_FULFILLMENT = "awaiting_fulfillment"
    ACTIVE = "active"
    CANCELED = "canceled"
    COMPLETE = "complete"
    PAUSED = "paused"
    OVERDUE = "overdue"


class ServiceType(StrEnum):
    DATACENTER = "datacenter"
    ISP = "isp"
    RESIDENTIAL = "residential"
    MOBILE = "mobile"
    OFF_CATALOG = "off_catalog"


class ServiceAdjustmentStatus(StrEnum):
    COMPLETE = "complete"
    PENDING = "pending"
    FAILED = "failed"


class ServiceAdjustmentType(StrEnum):
    INGESTION = "ingestion"
    FULFILLMENT = "fulfillment"
    REMOVE_PROXY = "remove_proxy"
    ADDITIONAL_FULFILLMENT = "additional_fulfillment"
    UPDATE = "update"
    PROXY_REPLACEMENT = "proxy_replacement"
    EXTENSION = "extension"
    TOP_UP = "top_up"
    TOP_UP_AND_EXTENSION = "top_up_and_extension"
    CANCEL = "cancel"


class CycleInterval(StrEnum):
    """Recurring billing intervals accepted by checkout."""

    YEAR = "year"
    MONTH = "month"
    WEEK = "week"
    DAY = "day"


class ListFormat(StrEnum):
    """Output format for the generated proxy-list endpoints."""

    STANDARD = "standard"
    HTTP = "http"
    HTTPS = "https"
    SOCKS5 = "socks5"
    SOCKS5H = "socks5h"


class ListProtocol(StrEnum):
    HTTP = "http"
    SOCKS5 = "socks5"


class ListVersion(StrEnum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"


class ListSessionType(StrEnum):
    STICKY = "sticky"
    ROTATING = "rotating"


class ListMode(StrEnum):
    """Mobile/residential network optimization mode."""

    GENERAL = "general"
    SIZE = "size"
    SPEED = "speed"


class ListAuthentication(StrEnum):
    USERNAME_AND_PASSWORD = "username_and_password"
    IP_ADDRESS = "ip_address"
    PROXY_SPECIFIC = "proxy_specific"


class AsnType(StrEnum):
    BUSINESS = "business"
    CDN = "cdn"
    EDUCATION = "education"
    GOV = "gov"
    HOSTING = "hosting"
    ISP = "isp"


class AsnRir(StrEnum):
    ARIN = "arin"
    RIPE = "ripe"
    APNIC = "apnic"
    LACNIC = "lacnic"
    AFRINIC = "afrinic"
    JPNIC = "jpnic"


class LogNetwork(StrEnum):
    DATACENTER = "datacenter"
    ISP = "isp"
    RESIDENTIAL = "residential"
    MOBILE = "mobile"


class LogProtocol(StrEnum):
    HTTP = "http"
    SOCKS = "socks"


class LogTransport(StrEnum):
    TCP = "tcp"
    UDP = "udp"
    QUIC = "quic"


class CancelFeedback(StrEnum):
    """Documented codes the API accepts for service cancellation feedback."""

    TOO_EXPENSIVE = "too_expensive"
    MISSING_FEATURES = "missing_features"
    SWITCHED_SERVICE = "switched_service"
    UNUSED = "unused"
    CUSTOMER_SERVICE = "customer_service"
    TOO_COMPLEX = "too_complex"
    LOW_QUALITY = "low_quality"
    OTHER = "other"


class AnalyticsInterval(StrEnum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


class AvailabilityGroupBy(StrEnum):
    COUNTRY = "country"
    SUBDIVISION = "subdivision"
    CITY = "city"
    ASN = "asn"
    ZIP_CODE = "zip_code"


class ProxyReplacementReason(StrEnum):
    CUSTOMER_REQUEST = "customer_request"
    IP_REPUTATION = "ip_reputation"
    END_OF_DEPLOYMENT = "end_of_deployment"
    OUTAGE = "outage"
    OTHER = "other"


class SubscriptionScheduleStatus(StrEnum):
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    COMPLETED = "completed"
    RELEASED = "released"
    CANCELED = "canceled"


class SubscriptionScheduleType(StrEnum):
    END_OF_INTRODUCTORY_OFFER = "end_of_introductory_offer"
    CHANGE_PRICE = "change_price"
    INCREASE_QUANTITY = "increase_quantity"
    DECREASE_QUANTITY = "decrease_quantity"
    INCREASE_QUANTITY_CHANGE_PRICE = "increase_quantity_change_price"
    DECREASE_QUANTITY_CHANGE_PRICE = "decrease_quantity_change_price"

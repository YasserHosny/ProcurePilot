from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx


class UnsafeUrlError(ValueError):
    """Raised when an endpoint URL is not permitted for webhooks."""


def is_ip_disallowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if IP is private, loopback, link-local, reserved, multicast, or unspecified."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None and is_ip_disallowed(ip.ipv4_mapped):
            return True
        if ip.sixtofour is not None and is_ip_disallowed(ip.sixtofour):
            return True
    return False


def validate_webhook_url(url: str, *, allow_private: bool = False) -> str:
    """Validate a webhook endpoint URL for safety against SSRF.

    Enforces:
    - Scheme must be https (unless allow_private is True, which permits http as well).
    - URL must not contain userinfo (username or password).
    - Hostname must be present.
    - If host is an IP literal: must not be in private/loopback/link-local/reserved ranges
      (unless allow_private is True).
    - If host is a domain: cannot be 'localhost' or end with '.localhost', and must contain a dot
      (unless allow_private is True).
    """
    try:
        parts = urlsplit(url)
    except Exception as exc:
        raise UnsafeUrlError("Invalid endpoint URL structure") from exc

    scheme = parts.scheme.lower()
    if allow_private:
        if scheme not in ("https", "http"):
            raise UnsafeUrlError("Endpoint URL scheme must be https or http")
    else:
        if scheme != "https":
            raise UnsafeUrlError("Endpoint URL scheme must be https")

    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UnsafeUrlError("Endpoint URL must not include user credentials")

    hostname = parts.hostname
    if not hostname:
        raise UnsafeUrlError("Endpoint URL must include a host")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None:
        if not allow_private and is_ip_disallowed(ip):
            raise UnsafeUrlError(f"Endpoint URL IP literal {hostname} is not allowed")
    else:
        if not allow_private:
            norm_host = hostname.lower().rstrip(".")
            if norm_host == "localhost" or norm_host.endswith(".localhost"):
                raise UnsafeUrlError("Endpoint URL host 'localhost' is not allowed")
            if "." not in norm_host:
                raise UnsafeUrlError("Endpoint URL host must contain a dot")
            if any(not part for part in norm_host.split(".")):
                raise UnsafeUrlError("Endpoint URL host contains empty segments")

    return url


def _extract_ip_from_addrinfo_entry(entry: object) -> str:
    if isinstance(entry, (tuple, list)):
        if len(entry) >= 5:
            sockaddr = entry[4]
            if isinstance(sockaddr, (tuple, list)) and len(sockaddr) > 0:
                return str(sockaddr[0])
            return str(sockaddr)
        if len(entry) >= 1:
            first = entry[0]
            if isinstance(first, (tuple, list)) and len(first) > 0:
                return str(first[0])
            return str(first)
    return str(entry)


def check_endpoint_url_safety(url: str, *, allow_private: bool = False) -> None:
    """Validate endpoint URL and resolve host to ensure no resolved IP is in disallowed ranges."""
    validate_webhook_url(url, allow_private=allow_private)
    if allow_private:
        return

    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        raise UnsafeUrlError("Endpoint URL must include a host")

    port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    addrinfo = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    if not addrinfo:
        raise UnsafeUrlError(f"Endpoint host {hostname} did not resolve to any addresses")

    for entry in addrinfo:
        ip_str = _extract_ip_from_addrinfo_entry(entry)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError as exc:
            raise UnsafeUrlError(f"Invalid resolved IP address: {ip_str}") from exc
        if is_ip_disallowed(ip):
            raise UnsafeUrlError(
                f"Endpoint host {hostname} resolved to disallowed address: {ip_str}"
            )


def categorize_delivery_error(exc: Exception) -> str:
    """Map exceptions to short generic category strings for tenant visibility."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.ConnectError):
        return "connect_error"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_status_{exc.response.status_code}"
    return "error"

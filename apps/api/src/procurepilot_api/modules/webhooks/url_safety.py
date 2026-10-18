from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import urlsplit

import httpcore
import httpx


class UnsafeUrlError(ValueError):
    """Raised when an endpoint URL is not permitted for webhooks."""


def is_ip_disallowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True unless IP is a globally routable unicast address.

    ``is_global`` also covers ranges none of the named flags do, such as RFC 6598 shared
    address space (100.64.0.0/10) used by carrier-grade NAT and overlay networks.
    """
    if (
        not ip.is_global
        or ip.is_private
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


def resolve_allowed_addresses(hostname: str, port: int) -> list[str]:
    """Resolve hostname and return its addresses, refusing if any is disallowed."""
    addrinfo = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    if not addrinfo:
        raise UnsafeUrlError(f"Endpoint host {hostname} did not resolve to any addresses")

    addresses: list[str] = []
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
        if ip_str not in addresses:
            addresses.append(ip_str)
    return addresses


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
    resolve_allowed_addresses(hostname, port)


class _PinnedNetworkBackend(httpcore.NetworkBackend):
    """Resolves and validates the host at connect time, then connects to a validated address.

    The pre-flight check and the connection would otherwise resolve the name separately, so
    a rebinding DNS answer could pass the check and still connect inward. TLS SNI and the
    Host header keep the original hostname: httpcore takes both from the request origin.
    """

    def __init__(self) -> None:
        self._backend = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        try:
            addresses = resolve_allowed_addresses(host, port)
        except OSError as exc:
            raise httpcore.ConnectError(str(exc)) from exc
        last_error: httpcore.ConnectError | httpcore.ConnectTimeout | None = None
        for address in addresses:
            try:
                return self._backend.connect_tcp(
                    address,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise UnsafeUrlError("Unix socket webhook endpoints are not allowed")

    def sleep(self, seconds: float) -> None:
        self._backend.sleep(seconds)


class PinnedWebhookTransport(httpx.HTTPTransport):
    """HTTP transport whose connections only ever reach validated public addresses."""

    def __init__(self) -> None:
        super().__init__()
        self._pool = httpcore.ConnectionPool(
            ssl_context=httpx.create_ssl_context(),
            network_backend=_PinnedNetworkBackend(),
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

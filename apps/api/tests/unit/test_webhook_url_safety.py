"""Webhook endpoint URLs cannot reach internal addresses (security review 2026-10-18)."""

from __future__ import annotations

import socket
import ssl
from uuid import uuid4

import httpcore
import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from procurepilot_api.config import Settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import UnprocessableEntityError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.webhooks.schemas import WebhookSubscriptionCreate
from procurepilot_api.modules.webhooks.service import WebhookService
from procurepilot_api.modules.webhooks.url_safety import (
    PinnedWebhookTransport,
    UnsafeUrlError,
    check_endpoint_url_safety,
    validate_webhook_url,
)

DISALLOWED = [
    "http://example.com",
    "https://127.0.0.1",
    "https://169.254.169.254",
    "https://10.0.0.1",
    "https://[::1]",
    "https://[::ffff:127.0.0.1]",
    "https://localhost",
    "https://user:pw@example.com",
]


def test_validator_accepts_https_example_com_hook() -> None:
    url = "https://example.com/hook"
    assert validate_webhook_url(url) == url


@pytest.mark.parametrize("url", DISALLOWED)
def test_validator_rejects_disallowed_urls(url: str) -> None:
    with pytest.raises(ValueError):
        validate_webhook_url(url)


@pytest.mark.parametrize("url", DISALLOWED)
def test_create_subscription_refuses_disallowed_urls_with_422(url: str) -> None:
    test_key = Fernet.generate_key().decode()
    service = WebhookService(
        Settings(
            webhook_allow_private_endpoints=False,
            webhook_token_encryption_key=SecretStr(test_key),
        )
    )
    member = CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email="owner@example.test",
        role=MemberRole.owner,
    )
    with pytest.raises(UnprocessableEntityError):
        service.create_subscription(
            bearer_token="token",
            member=member,
            payload=WebhookSubscriptionCreate(endpoint_url=url),
        )


def test_escape_hatch_allows_private_endpoints() -> None:
    assert (
        validate_webhook_url("http://localhost:8000/hook", allow_private=True)
        == "http://localhost:8000/hook"
    )
    assert (
        validate_webhook_url("http://127.0.0.1:8000/hook", allow_private=True)
        == "http://127.0.0.1:8000/hook"
    )
    with pytest.raises(ValueError):
        validate_webhook_url("https://user:pw@example.com", allow_private=True)


@pytest.mark.parametrize(
    "url",
    [
        "https://100.64.0.1/hook",  # RFC 6598 shared address space (CGNAT, Tailscale)
        "https://100.127.255.254/hook",
        "https://192.0.2.10/hook",  # TEST-NET-1
        "https://198.18.0.1/hook",  # benchmarking
        "https://[2001:db8::1]/hook",  # IPv6 documentation
        "https://[::ffff:100.64.0.1]/hook",
    ],
)
def test_validator_rejects_non_global_ranges(url: str) -> None:
    with pytest.raises(ValueError):
        validate_webhook_url(url)


def _addrinfo(*ips: str) -> list[tuple[object, ...]]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]


def test_resolution_into_shared_address_space_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: _addrinfo("100.64.12.7"))
    with pytest.raises(UnsafeUrlError):
        check_endpoint_url_safety("https://overlay.example.com/hook")


class _RecordingStream(httpcore.NetworkStream):
    def __init__(self, calls: dict[str, object]) -> None:
        self.calls = calls

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> httpcore.NetworkStream:
        self.calls["sni"] = server_hostname
        raise httpcore.ConnectError("stop after recording SNI")

    def close(self) -> None:
        pass


def _record_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    calls: dict[str, object] = {"hosts": []}

    def fake_connect_tcp(
        _self: object, host: str, port: int, **_kwargs: object
    ) -> httpcore.NetworkStream:
        hosts = calls["hosts"]
        assert isinstance(hosts, list)
        hosts.append(host)
        return _RecordingStream(calls)

    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", fake_connect_tcp)
    return calls


def test_pinned_transport_connects_to_validated_address_keeping_sni(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: _addrinfo("93.184.216.34"))
    calls = _record_connects(monkeypatch)

    with (
        httpx.Client(transport=PinnedWebhookTransport()) as client,
        pytest.raises(httpx.ConnectError),
    ):
        client.post("https://hooks.example.com/hook", content=b"{}")

    assert calls["hosts"] == ["93.184.216.34"]
    assert calls["sni"] == "hooks.example.com"


def test_pinned_transport_refuses_dns_rebinding_after_the_preflight_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    answers = iter([_addrinfo("93.184.216.34"), _addrinfo("127.0.0.1")])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: next(answers))
    calls = _record_connects(monkeypatch)

    url = "https://rebind.example.com/hook"
    check_endpoint_url_safety(url)  # first answer: public
    with httpx.Client(transport=PinnedWebhookTransport()) as client, pytest.raises(UnsafeUrlError):
        client.post(url, content=b"{}")  # second answer: loopback

    assert calls["hosts"] == []

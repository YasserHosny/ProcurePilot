from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import httpx
import pytest

from procurepilot_api.modules.webhooks.schemas import WebhookDelivery
from procurepilot_api.modules.webhooks.service import (
    build_webhook_body,
    retry_delay_seconds,
    sign_webhook_payload,
)
from procurepilot_api.workers import webhook_worker


def test_webhook_signature_is_sha256_over_canonical_json() -> None:
    payload = {"event_id": 42, "event_type": "orders.submitted", "target": {"id": "order-1"}}

    body = build_webhook_body(payload)
    signature = sign_webhook_payload(body, "secret-123")

    assert body == json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    assert signature.startswith("sha256=")
    assert len(signature) == len("sha256=") + 64


def test_retry_delay_is_bounded_exponential_backoff() -> None:
    assert retry_delay_seconds(1) == 60
    assert retry_delay_seconds(2) == 120
    assert retry_delay_seconds(8) == 3600
    assert retry_delay_seconds(99) == 3600


def _public_addrinfo(*args: object, **kwargs: object) -> list[object]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def test_delivery_posts_signed_event_headers_and_marks_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def post(
            self,
            url: str,
            *,
            content: bytes,
            headers: dict[str, str],
            follow_redirects: bool = False,
        ) -> _Response:
            captured.update(
                {
                    "url": url,
                    "content": content,
                    "headers": headers,
                    "follow_redirects": follow_redirects,
                }
            )
            return _Response()

    monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)

    marked: list[UUID] = []
    monkeypatch.setattr(
        webhook_worker,
        "_mark_succeeded",
        lambda _settings, delivery_id: marked.append(delivery_id),
    )
    delivery_id = UUID("00000000-0000-0000-0000-000000000010")
    settings = SimpleNamespace(
        webhook_token_encryption_key=None,
        webhook_max_attempts=8,
        webhook_allow_private_endpoints=False,
    )
    delivery = {
        "id": delivery_id,
        "audit_event_id": 42,
        "event_type": "orders.submitted",
        "payload": {"event_id": 42, "event_type": "orders.submitted"},
        "secret_encrypted": "secret-123",
        "endpoint_url": "https://partner.example.test/events",
        "attempts": 1,
    }

    assert webhook_worker._deliver_one(settings, _Client(), delivery) == "succeeded"
    assert marked == [delivery_id]
    headers = cast(dict[str, str], captured["headers"])
    body = cast(bytes, captured["content"])
    assert headers["X-ProcurePilot-Event-Id"] == "42"
    assert headers["X-ProcurePilot-Signature"] == sign_webhook_payload(body, "secret-123")
    assert captured["follow_redirects"] is False


def test_webhook_delivery_validates_database_row_with_audit_event_id() -> None:
    now = datetime.now(UTC)
    row = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "subscription_id": UUID("00000000-0000-0000-0000-000000000002"),
        "audit_event_id": 99,
        "event_type": "orders.submitted",
        "status": "pending",
        "attempts": 0,
        "next_attempt_at": now,
        "delivered_at": None,
        "last_error": None,
        "created_at": now,
    }
    delivery = WebhookDelivery.model_validate(row)
    assert delivery.event_id == 99
    dumped = delivery.model_dump()
    assert dumped["event_id"] == 99
    assert "audit_event_id" not in dumped


def test_worker_refuses_when_getaddrinfo_returns_private_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    class _Client:
        def post(self, *args: object, **kwargs: object) -> object:
            nonlocal called
            called = True
            raise AssertionError("Client post should not be called for unsafe destinations")

    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 443))],
    )

    failed_errors: list[str] = []
    monkeypatch.setattr(
        webhook_worker,
        "_mark_failed",
        lambda _settings, _id, error: failed_errors.append(error),
    )

    delivery_id = UUID("00000000-0000-0000-0000-000000000020")
    settings = SimpleNamespace(
        webhook_token_encryption_key=None,
        webhook_max_attempts=8,
        webhook_allow_private_endpoints=False,
    )
    delivery = {
        "id": delivery_id,
        "audit_event_id": 42,
        "event_type": "orders.submitted",
        "payload": {"event_id": 42, "event_type": "orders.submitted"},
        "secret_encrypted": "secret-123",
        "endpoint_url": "https://attacker.example.com/hook",
        "attempts": 1,
    }

    outcome = webhook_worker._deliver_one(settings, _Client(), delivery)
    assert outcome == "failed"
    assert failed_errors == ["endpoint_not_allowed"]
    assert not called


def test_last_error_category_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Client:
        def post(self, *args: object, **kwargs: object) -> object:
            raise httpx.ReadTimeout("read timed out")

    monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)

    retried_errors: list[str] = []
    monkeypatch.setattr(
        webhook_worker,
        "_mark_retry",
        lambda _settings, _id, _attempts, error: retried_errors.append(error),
    )

    delivery_id = UUID("00000000-0000-0000-0000-000000000030")
    settings = SimpleNamespace(
        webhook_token_encryption_key=None,
        webhook_max_attempts=8,
        webhook_allow_private_endpoints=False,
    )
    delivery = {
        "id": delivery_id,
        "audit_event_id": 42,
        "event_type": "orders.submitted",
        "payload": {"event_id": 42, "event_type": "orders.submitted"},
        "secret_encrypted": "secret-123",
        "endpoint_url": "https://partner.example.com/hook",
        "attempts": 1,
    }

    outcome = webhook_worker._deliver_one(settings, _Client(), delivery)
    assert outcome == "retrying"
    assert retried_errors == ["timeout"]


def test_last_error_category_http_500(monkeypatch: pytest.MonkeyPatch) -> None:
    req = httpx.Request("POST", "https://partner.example.com/hook")
    resp = httpx.Response(500, request=req)

    class _Client:
        def post(self, *args: object, **kwargs: object) -> object:
            raise httpx.HTTPStatusError("500 Internal Server Error", request=req, response=resp)

    monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)

    retried_errors: list[str] = []
    monkeypatch.setattr(
        webhook_worker,
        "_mark_retry",
        lambda _settings, _id, _attempts, error: retried_errors.append(error),
    )

    delivery_id = UUID("00000000-0000-0000-0000-000000000040")
    settings = SimpleNamespace(
        webhook_token_encryption_key=None,
        webhook_max_attempts=8,
        webhook_allow_private_endpoints=False,
    )
    delivery = {
        "id": delivery_id,
        "audit_event_id": 42,
        "event_type": "orders.submitted",
        "payload": {"event_id": 42, "event_type": "orders.submitted"},
        "secret_encrypted": "secret-123",
        "endpoint_url": "https://partner.example.com/hook",
        "attempts": 1,
    }

    outcome = webhook_worker._deliver_one(settings, _Client(), delivery)
    assert outcome == "retrying"
    assert retried_errors == ["http_status_500"]

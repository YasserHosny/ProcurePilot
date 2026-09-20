from __future__ import annotations

import json
from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest

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


def test_delivery_posts_signed_event_headers_and_marks_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

    class _Client:
        def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> _Response:
            captured.update({"url": url, "content": content, "headers": headers})
            return _Response()

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
    )
    delivery = {
        "id": delivery_id,
        "event_id": 42,
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
    assert headers["X-ProcurePilot-Signature"] == sign_webhook_payload(
        body, "secret-123"
    )

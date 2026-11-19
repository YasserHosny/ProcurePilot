"""Spec 025 T034 / T053: storage helper behaviour with a fake Supabase client."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from procurepilot_api.config import Settings
from procurepilot_api.errors import ServiceUnavailableError
from procurepilot_api.modules.feedback.storage import (
    FeedbackStorage,
    attachment_storage_path,
    extract_signed_url,
)


class _Bucket:
    def __init__(self, log: list[tuple[str, object]], fail: bool) -> None:
        self._log = log
        self._fail = fail

    def upload(self, path: str, content: bytes, options: dict[str, str]) -> None:
        if self._fail:
            raise RuntimeError("storage down")
        self._log.append(("upload", (path, len(content), options)))

    def remove(self, paths: list[str]) -> None:
        if self._fail:
            raise RuntimeError("storage down")
        self._log.append(("remove", paths))

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, str]:
        if self._fail:
            raise RuntimeError("storage down")
        self._log.append(("sign", (path, expires_in)))
        return {"signedURL": f"http://storage.test/{path}?token=t"}


class _Client:
    def __init__(self, key: str, log: list[tuple[str, object]], fail: bool) -> None:
        self.key = key
        self.storage = SimpleNamespace(
            session=SimpleNamespace(headers={"Authorization": f"Bearer {key}"}),
            from_=lambda bucket: self._bucket(bucket),
        )
        self._log = log
        self._fail = fail

    def _bucket(self, bucket: str) -> _Bucket:
        self._log.append(("bucket", bucket))
        return _Bucket(self._log, self._fail)


def _storage(fail: bool = False) -> tuple[FeedbackStorage, list[tuple[str, object]], list[_Client]]:
    log: list[tuple[str, object]] = []
    clients: list[_Client] = []

    def factory(_url: str, key: str) -> _Client:
        client = _Client(key, log, fail)
        clients.append(client)
        return client

    return FeedbackStorage(Settings(), client_factory=factory), log, clients  # type: ignore[arg-type]


def test_path_has_tenant_as_second_segment_and_is_ascii_safe() -> None:
    tenant, submission = uuid4(), uuid4()
    path = attachment_storage_path(
        tenant_id=tenant, submission_id=submission, filename="لقطة شاشة (1).PNG"
    )
    parts = path.split("/")
    assert parts[:4] == ["tenants", str(tenant), "feedback", str(submission)]
    assert parts[1] == str(tenant)  # (storage.foldername(name))[2] in the bucket policy
    assert path.isascii()
    assert len(parts) == 6


def test_upload_uses_the_callers_token_and_never_overwrites() -> None:
    storage, log, clients = _storage()
    storage.upload(
        bearer_token="member-jwt",
        path="tenants/t/feedback/s/u/a.png",
        content=b"abc",
        content_type="image/png",
    )
    (client,) = clients
    assert client.storage.session.headers["Authorization"] == "Bearer member-jwt"
    assert ("bucket", "feedback-attachments") in log
    assert (
        "upload",
        ("tenants/t/feedback/s/u/a.png", 3, {"content-type": "image/png", "upsert": "false"}),
    ) in log


def test_upload_failure_is_service_unavailable() -> None:
    storage, _log, _clients = _storage(fail=True)
    with pytest.raises(ServiceUnavailableError):
        storage.upload(bearer_token="t", path="p", content=b"x", content_type="image/png")


def test_delete_uses_service_role_and_reports_failures_without_raising() -> None:
    storage, log, clients = _storage()
    assert storage.delete(["a", "b"]) == []
    assert ("remove", ["a", "b"]) in log
    assert clients[-1].key == Settings().supabase_service_role_key.get_secret_value()

    failing, _log, _clients = _storage(fail=True)
    assert failing.delete(["a", "b"]) == ["a", "b"]
    assert failing.delete([]) == []


def test_signed_url_uses_the_configured_ttl() -> None:
    storage, log, _clients = _storage()
    assert storage.signed_url("p/x.png") == "http://storage.test/p/x.png?token=t"
    assert ("sign", ("p/x.png", 300)) in log


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("http://x/y", "http://x/y"),
        ({"signedURL": "http://a"}, "http://a"),
        ({"signedUrl": "http://b"}, "http://b"),
        ({"url": "http://c"}, "http://c"),
    ],
)
def test_extract_signed_url_accepts_known_shapes(result: object, expected: str) -> None:
    assert extract_signed_url(result) == expected


@pytest.mark.parametrize("result", [None, {}, {"signedURL": ""}, 5])
def test_extract_signed_url_rejects_the_rest(result: object) -> None:
    with pytest.raises(ServiceUnavailableError):
        extract_signed_url(result)

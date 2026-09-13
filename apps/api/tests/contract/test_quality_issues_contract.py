from __future__ import annotations

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from starlette.datastructures import FormData, Headers, UploadFile

from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, UnprocessableEntityError
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.requests import router as requests_router
from procurepilot_api.modules.requests import service as requests_service_module
from procurepilot_api.modules.requests.schemas import (
    QualityIssue,
    QualityIssueCreate,
    QualityIssueList,
    QualityIssuePhoto,
)
from procurepilot_api.modules.requests.service import RequestsService


def _photo(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": uuid4(),
        "delivery_quality_issue_id": uuid4(),
        "url": "https://storage.example.test/signed/photo.jpg",
        "created_at": "2026-09-13T12:05:00Z",
    }
    base.update(overrides)
    return base


def _issue(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": uuid4(),
        "purchase_request_id": uuid4(),
        "reported_by_membership_id": uuid4(),
        "description": "Damaged packaging",
        "photos": [],
        "created_at": "2026-09-13T12:00:00Z",
    }
    base.update(overrides)
    return base


def test_quality_issue_body_accepts_contract_shape() -> None:
    payload = QualityIssueCreate.model_validate(
        {"description": "Wrong item delivered"}
    )

    assert payload.description == "Wrong item delivered"


def test_quality_issue_body_rejects_empty_description() -> None:
    with pytest.raises(ValidationError, match="too_short"):
        QualityIssueCreate(description="")


def test_quality_issue_body_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        QualityIssueCreate.model_validate(
            {"description": "Spoiled item", "photo_required": True}
        )


def test_quality_issue_response_embeds_photos_list() -> None:
    issue_id = uuid4()
    issue = QualityIssue.model_validate(
        _issue(id=issue_id, photos=[_photo(delivery_quality_issue_id=issue_id)])
    )

    assert len(issue.photos) == 1
    assert issue.photos[0].delivery_quality_issue_id == issue_id
    assert issue.photos[0].url.startswith("https://")


def test_quality_issue_zero_photos_response_is_empty_list() -> None:
    issue = QualityIssue.model_validate(_issue())

    assert issue.photos == []


def test_quality_issue_photo_response_never_requires_storage_path() -> None:
    photo = QualityIssuePhoto.model_validate(_photo())

    assert photo.url == "https://storage.example.test/signed/photo.jpg"
    assert "storage_path" not in photo.model_dump()


def test_quality_issue_list_response_matches_contract_shape() -> None:
    listed = QualityIssueList.model_validate({"items": [_issue()]})

    assert len(listed.items) == 1


def test_not_delivered_conflict_reason_is_contract_reason() -> None:
    error = ConflictError(details={"reason": "not_delivered"})

    assert error.status_code == 409
    assert error.details == {"reason": "not_delivered"}


def test_quality_issue_routes_are_registered() -> None:
    app_paths = {route.path for route in create_app().routes}

    assert "/api/v1/requests/{request_id}/quality-issues" in app_paths
    assert "/api/v1/quality-issues/{issue_id}/photos" in app_paths


def test_contract_declares_quality_issue_paths_and_signed_url() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    text = (
        repo_root
        / "specs/010-mobile-approvals-receipt/contracts/"
        / "mobile-approvals-receipt.openapi.yaml"
    ).read_text(encoding="utf-8")

    assert "  /requests/{request_id}/quality-issues:" in text
    assert "  /quality-issues/{issue_id}/photos:" in text
    assert "reason `not_delivered`" in text
    assert "A signed, time-limited URL" in text


def test_create_quality_issue_router_passes_payload_to_service() -> None:
    request_id = uuid4()
    payload = QualityIssueCreate(description="Damaged tins")
    captured: dict[str, object] = {}
    expected = object()
    fake_service = SimpleNamespace(
        create_quality_issue=lambda **kwargs: captured.update(kwargs)
        or expected
    )

    result = requests_router.create_quality_issue(
        request_id=request_id,
        payload=payload,
        token="token",
        member=object(),
        service=fake_service,
    )

    assert result is expected
    assert captured["bearer_token"] == "token"
    assert captured["request_id"] == request_id
    assert captured["payload"] is payload


class _Response:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class _TableQuery:
    def __init__(
        self,
        table: str,
        issue_id: UUID,
        tenant_id: UUID,
        inserted_photo_id: UUID,
    ) -> None:
        self._table = table
        self._issue_id = issue_id
        self._tenant_id = tenant_id
        self._inserted_photo_id = inserted_photo_id
        self._operation = "select"
        self._payload: dict[str, object] | None = None

    def select(self, _columns: str) -> _TableQuery:
        self._operation = "select"
        return self

    def eq(self, _column: str, _value: object) -> _TableQuery:
        return self

    def limit(self, _value: int) -> _TableQuery:
        return self

    def insert(self, payload: dict[str, object]) -> _TableQuery:
        self._operation = "insert"
        self._payload = payload
        return self

    def execute(self) -> _Response:
        if self._table == "delivery_quality_issue":
            return _Response(
                [
                    {
                        "id": self._issue_id,
                        "tenant_id": self._tenant_id,
                        "purchase_request_id": uuid4(),
                        "reported_by_membership_id": uuid4(),
                        "description": "Damaged",
                        "created_at": "2026-09-13T12:00:00Z",
                    }
                ]
            )
        assert self._payload is not None
        return _Response(
            [
                {
                    "id": self._inserted_photo_id,
                    "tenant_id": self._tenant_id,
                    "delivery_quality_issue_id": self._issue_id,
                    "storage_path": self._payload["storage_path"],
                    "created_at": "2026-09-13T12:05:00Z",
                }
            ]
        )


class _StorageBucket:
    def __init__(self) -> None:
        self.uploaded: dict[str, object] = {}

    def upload(
        self,
        path: str,
        content: bytes,
        *,
        file_options: dict[str, str],
    ) -> dict[str, object]:
        self.uploaded = {
            "path": path,
            "content": content,
            "file_options": file_options,
        }
        return {"path": path}

    def create_signed_url(
        self, path: str, *, expires_in: int
    ) -> dict[str, object]:
        return {
            "signedURL": f"https://storage.example.test/{path}?expires={expires_in}"
        }


class _Storage:
    def __init__(self, bucket: _StorageBucket) -> None:
        self.bucket = bucket
        self.bucket_name: str | None = None

    def from_(self, bucket_name: str) -> _StorageBucket:
        self.bucket_name = bucket_name
        return self.bucket


class _Client:
    def __init__(
        self,
        issue_id: UUID,
        tenant_id: UUID,
        inserted_photo_id: UUID,
        bucket: _StorageBucket,
    ) -> None:
        self._issue_id = issue_id
        self._tenant_id = tenant_id
        self._inserted_photo_id = inserted_photo_id
        self.storage = _Storage(bucket)

    def table(self, name: str) -> _TableQuery:
        return _TableQuery(
            name, self._issue_id, self._tenant_id, self._inserted_photo_id
        )


def test_attach_quality_issue_photo_uses_mocked_tenant_client_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    member_id = uuid4()
    user_id = uuid4()
    issue_id = uuid4()
    photo_id = uuid4()
    bucket = _StorageBucket()
    client = _Client(issue_id, tenant_id, photo_id, bucket)
    service = RequestsService()
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        requests_service_module,
        "authenticated_client",
        lambda _settings, _token: client,
    )
    monkeypatch.setattr(service, "_record", lambda **kwargs: recorded.append(kwargs))

    photo = service.attach_quality_issue_photo(
        bearer_token="token",
        member=CurrentMember(
            membership_id=member_id,
            tenant_id=tenant_id,
            user_id=user_id,
            email="member@example.test",
            role=MemberRole.branch_manager,
        ),
        issue_id=issue_id,
        filename="../damaged box.jpg",
        content_type="image/jpeg",
        content=b"jpeg-bytes",
    )

    assert photo.id == photo_id
    assert photo.delivery_quality_issue_id == issue_id
    assert photo.url.startswith("https://storage.example.test/")
    assert "/../" not in photo.url
    assert bucket.uploaded["content"] == b"jpeg-bytes"
    assert bucket.uploaded["file_options"] == {
        "upsert": "false",
        "content-type": "image/jpeg",
    }
    assert [row["action"] for row in recorded] == [
        "requests.quality_issue_photo_attached"
    ]


def test_list_quality_issues_router_passes_request_id_to_service() -> None:
    request_id = uuid4()
    captured: dict[str, object] = {}
    expected = object()
    fake_service = SimpleNamespace(
        list_quality_issues=lambda **kwargs: captured.update(kwargs)
        or expected
    )

    result = requests_router.list_quality_issues(
        request_id=request_id,
        token="token",
        _member=object(),
        service=fake_service,
    )

    assert result is expected
    assert captured["bearer_token"] == "token"
    assert captured["request_id"] == request_id


@pytest.mark.asyncio
async def test_photo_upload_router_accepts_multipart_file_and_returns_url() -> None:
    issue_id = uuid4()
    captured: dict[str, object] = {}
    expected = QualityIssuePhoto.model_validate(
        _photo(delivery_quality_issue_id=issue_id)
    )
    fake_service = SimpleNamespace(
        attach_quality_issue_photo=lambda **kwargs: captured.update(kwargs)
        or expected
    )
    upload = UploadFile(
        file=BytesIO(b"not-used"),
        filename="damage.jpg",
        headers=Headers({"content-type": "image/jpeg"}),
    )

    class FakeRequest:
        async def form(self) -> FormData:
            return FormData({"file": upload})

    result = await requests_router.attach_quality_issue_photo(
        issue_id=issue_id,
        request=FakeRequest(),
        token="token",
        member=object(),
        service=fake_service,
    )

    assert result.url == expected.url
    assert "storage_path" not in result.model_dump()
    assert captured["bearer_token"] == "token"
    assert captured["issue_id"] == issue_id
    assert captured["filename"] == "damage.jpg"
    assert captured["content_type"] == "image/jpeg"
    assert captured["content"] == b"not-used"


@pytest.mark.asyncio
async def test_photo_upload_router_requires_file_field() -> None:
    class FakeRequest:
        async def form(self) -> FormData:
            return FormData({})

    with pytest.raises(UnprocessableEntityError) as exc:
        await requests_router.attach_quality_issue_photo(
            issue_id=uuid4(),
            request=FakeRequest(),
            token="token",
            member=object(),
            service=object(),
        )

    assert exc.value.details == {"file": "required"}

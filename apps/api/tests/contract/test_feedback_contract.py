"""Spec 025 T016: the member and owner endpoints match contracts/feedback.openapi.yaml.

Runs the real app and router with the service mocked, so it needs no database. The drift tests
compare the live OpenAPI document with the contract file.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from httpx import Response
from integration.feedback_helpers import MIB, audio_fixture, jpeg_bytes, png_bytes

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, bearer_token, current_member
from procurepilot_api.errors import FeedbackCooldownError, FeedbackWithdrawRefusedError
from procurepilot_api.main import create_app
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.feedback.schemas import (
    Attachment,
    AttachmentKind,
    Category,
    SignedUrl,
    Status,
    Submission,
    SubmissionPage,
)
from procurepilot_api.modules.feedback.service import (
    FeedbackService,
    SubmitResult,
    get_feedback_service,
)

KEY = "5d0c8a64-6f6c-4a53-9f0a-0d4a4c0a9f10"


def _member(role: MemberRole = MemberRole.buyer) -> CurrentMember:
    return CurrentMember(
        membership_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        email=f"{role.value}@example.test",
        role=role,
    )


def _submission(**overrides: object) -> Submission:
    data: dict[str, object] = {
        "id": uuid4(),
        "text": "The approvals page is slow",
        "category": Category.bug,
        "status": Status.new,
        "member_role": MemberRole.buyer,
        "page_path": "/approvals",
        "locale": "en",
        "created_at": datetime(2026, 11, 18, 9, 30, tzinfo=UTC),
        "can_withdraw": True,
        "attachments": [],
    }
    data.update(overrides)
    return Submission.model_validate(data)


@pytest.fixture(autouse=True)
def _generous_rate_limit(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # The in-memory limiter is shared by every request in this process.
    monkeypatch.setenv("RATE_LIMIT_FEEDBACK_SUBMIT", "10000/minute")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def service() -> Mock:
    return Mock(spec=FeedbackService)


@pytest.fixture
def role() -> list[MemberRole]:
    return [MemberRole.buyer]


@pytest.fixture
def client(service: Mock, role: list[MemberRole]) -> TestClient:
    app = create_app()
    caller = _member(role[0])
    app.dependency_overrides[bearer_token] = lambda: "verified-token"
    app.dependency_overrides[current_member] = lambda: caller
    app.dependency_overrides[get_feedback_service] = lambda: service
    test_client = TestClient(app)
    test_client.caller = caller  # type: ignore[attr-defined]
    return test_client


def _post(
    client: TestClient,
    *,
    fields: dict[str, str],
    files: list[tuple[str, tuple]] | None = None,
    headers: dict[str, str] | None = None,
    key: str | None = KEY,
) -> Response:
    parts: list[tuple[str, tuple]] = [(name, (None, value)) for name, value in fields.items()]
    parts.extend(files or [])
    request_headers = dict(headers or {})
    if key is not None:
        request_headers["Idempotency-Key"] = key
    return client.post("/api/v1/feedback", files=parts, headers=request_headers)


# ----------------------------------------------------------------- POST /feedback


def test_submit_text_and_category_returns_201_in_the_contract_shape(
    client: TestClient, service: Mock
) -> None:
    service.submit.return_value = SubmitResult(_submission(), created=True)

    response = _post(client, fields={"text": "The approvals page is slow", "category": "bug"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "id",
        "text",
        "category",
        "status",
        "submitter_name",
        "member_role",
        "page_path",
        "locale",
        "created_at",
        "can_withdraw",
        "attachments",
    }
    assert "labels" not in body
    assert body["status"] == "new"
    assert body["category"] == "bug"
    assert body["can_withdraw"] is True
    kwargs = service.submit.call_args.kwargs
    assert kwargs["text"] == "The approvals page is slow"
    assert kwargs["category"] == Category.bug
    assert kwargs["idempotency_key"] == UUID(KEY)
    assert kwargs["bearer_token"] == "verified-token"
    assert kwargs["images"] == []
    assert kwargs["audio"] is None


def test_category_is_optional(client: TestClient, service: Mock) -> None:
    service.submit.return_value = SubmitResult(_submission(category=None), created=True)
    response = _post(client, fields={"text": "hello"})
    assert response.status_code == 201
    assert service.submit.call_args.kwargs["category"] is None
    assert response.json()["category"] is None


def test_idempotent_replay_returns_200_with_the_original_body(
    client: TestClient, service: Mock
) -> None:
    original = _submission()
    service.submit.return_value = SubmitResult(original, created=False)
    response = _post(client, fields={"text": "again"})
    assert response.status_code == 200
    assert response.json()["id"] == str(original.id)


@pytest.mark.parametrize("key", [None, "not-a-uuid", ""])
def test_idempotency_key_is_required_and_must_be_a_uuid(
    client: TestClient, service: Mock, key: str | None
) -> None:
    response = _post(client, fields={"text": "hello"}, key=key)
    assert response.status_code == 422
    assert response.json()["code"] == "validation.invalid_request"
    service.submit.assert_not_called()


def test_missing_text_and_unknown_category_are_422(client: TestClient, service: Mock) -> None:
    assert _post(client, fields={"category": "bug"}).status_code == 422
    assert _post(client, fields={"text": "x", "category": "praise"}).status_code == 422
    service.submit.assert_not_called()


def test_referer_and_accept_language_are_forwarded_for_validation(
    client: TestClient, service: Mock
) -> None:
    service.submit.return_value = SubmitResult(_submission(), created=True)
    _post(
        client,
        fields={"text": "hello"},
        headers={"Referer": "http://localhost:4200/approvals?x=1", "Accept-Language": "ar-EG,ar"},
    )
    kwargs = service.submit.call_args.kwargs
    assert kwargs["referer"] == "http://localhost:4200/approvals?x=1"
    assert kwargs["accept_language"] == "ar-EG,ar"


def test_client_supplied_workspace_user_role_and_demo_values_are_ignored(
    client: TestClient, service: Mock
) -> None:
    service.submit.return_value = SubmitResult(_submission(), created=True)
    _post(
        client,
        fields={
            "text": "hello",
            "tenant_id": str(uuid4()),
            "user_id": str(uuid4()),
            "member_role": "owner",
            "is_demo": "true",
            "app_version": "evil",
            "status": "resolved",
            "labels": "x",
            "submitter_email": "someone@else.test",
        },
    )
    kwargs = service.submit.call_args.kwargs
    assert kwargs["member"] is client.caller  # type: ignore[attr-defined]
    assert set(kwargs) == {
        "member",
        "bearer_token",
        "idempotency_key",
        "text",
        "category",
        "images",
        "audio",
        "referer",
        "accept_language",
    }


def test_images_and_audio_are_read_as_uploaded_files(client: TestClient, service: Mock) -> None:
    service.submit.return_value = SubmitResult(_submission(), created=True)
    jpg, png, wav = jpeg_bytes(), png_bytes(), audio_fixture("tone.wav")
    response = _post(
        client,
        fields={"text": "with files"},
        files=[
            ("images", ("a.jpg", jpg, "image/jpeg")),
            ("images", ("b.png", png, "image/png")),
            ("audio", ("note.wav", wav, "audio/wav")),
        ],
    )
    assert response.status_code == 201
    kwargs = service.submit.call_args.kwargs
    assert [(f.filename, f.content) for f in kwargs["images"]] == [("a.jpg", jpg), ("b.png", png)]
    assert kwargs["audio"].filename == "note.wav"
    assert kwargs["audio"].content == wav


def test_untouched_file_inputs_send_empty_unnamed_parts_that_are_dropped(
    client: TestClient, service: Mock
) -> None:
    service.submit.return_value = SubmitResult(_submission(), created=True)
    response = _post(
        client,
        fields={"text": "no files really"},
        files=[
            ("images", ("", b"", "application/octet-stream")),
            ("audio", ("", b"", "application/octet-stream")),
        ],
    )
    assert response.status_code == 201
    kwargs = service.submit.call_args.kwargs
    assert kwargs["images"] == []
    assert kwargs["audio"] is None


def test_a_second_voice_message_is_422_not_silently_dropped(
    client: TestClient, service: Mock
) -> None:
    wav = audio_fixture("tone.wav")
    response = _post(
        client,
        fields={"text": "two notes"},
        files=[("audio", ("a.wav", wav, "audio/wav")), ("audio", ("b.wav", wav, "audio/wav"))],
    )
    assert response.status_code == 422
    assert response.json()["details"] == {"reason": "too_many_audio", "max": 1}
    service.submit.assert_not_called()


def test_a_non_file_value_in_a_file_field_is_422(client: TestClient, service: Mock) -> None:
    response = _post(client, fields={"text": "hi", "images": "not-a-file"})
    assert response.status_code == 422
    service.submit.assert_not_called()


def test_an_oversize_part_is_read_only_one_byte_past_its_limit(
    client: TestClient, service: Mock
) -> None:
    service.submit.return_value = SubmitResult(_submission(), created=True)
    limit = get_settings().feedback_image_max_bytes
    _post(
        client,
        fields={"text": "big"},
        files=[("images", ("big.jpg", jpeg_bytes(extra=limit + 10 * MIB), "image/jpeg"))],
    )
    (image,) = service.submit.call_args.kwargs["images"]
    assert len(image.content) == limit + 1  # the service answers 413 from this


def test_service_errors_use_the_error_envelope(client: TestClient, service: Mock) -> None:
    service.submit.side_effect = FeedbackCooldownError(retry_after_seconds=17)
    response = _post(client, fields={"text": "too soon"})
    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "feedback.cooldown"
    assert body["details"] == {"retry_after_seconds": 17}
    assert body["trace_id"]
    assert set(body) == {"code", "message", "details", "trace_id"}


def test_abuse_rate_limit_returns_429(
    client: TestClient, service: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from procurepilot_api.shared.rate_limit import mutation_limiter

    service.submit.return_value = SubmitResult(_submission(), created=True)
    monkeypatch.setenv("RATE_LIMIT_FEEDBACK_SUBMIT", "2/minute")
    get_settings.cache_clear()
    mutation_limiter.reset()
    statuses = [_post(client, fields={"text": f"n{i}"}).status_code for i in range(4)]
    assert statuses[:2] == [201, 201]
    assert statuses[2:] == [429, 429]
    mutation_limiter.reset()


# -------------------------------------------------------------------- GET lists


def test_get_mine_matches_the_contract_and_never_carries_labels(
    client: TestClient, service: Mock
) -> None:
    attachment = Attachment(
        id=uuid4(),
        kind=AttachmentKind.image,
        content_type="image/png",
        size_bytes=10,
        display_order=0,
    )
    service.list_mine.return_value = SubmissionPage(
        items=[_submission(attachments=[attachment])], next_cursor="abc", total=7
    )

    response = client.get("/api/v1/feedback/mine", params={"limit": 10, "cursor": "zzz"})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "next_cursor", "total"}
    assert body["next_cursor"] == "abc"
    assert body["total"] == 7
    assert "labels" not in response.text
    assert set(body["items"][0]["attachments"][0]) == {
        "id",
        "kind",
        "content_type",
        "size_bytes",
        "display_order",
    }
    kwargs = service.list_mine.call_args.kwargs
    assert kwargs["limit"] == 10 and kwargs["cursor"] == "zzz"


@pytest.mark.parametrize("limit", [0, 101, -1])
def test_limit_is_capped_at_100(client: TestClient, service: Mock, limit: int) -> None:
    service.list_mine.return_value = SubmissionPage(items=[])
    assert client.get("/api/v1/feedback/mine", params={"limit": limit}).status_code == 422
    assert client.get("/api/v1/feedback/mine", params={"limit": 100}).status_code == 200


@pytest.mark.parametrize("caller_role", [r for r in MemberRole if r != MemberRole.owner])
def test_workspace_inbox_is_404_not_403_for_everyone_but_the_owner(
    service: Mock, caller_role: MemberRole
) -> None:
    app = create_app()
    caller = _member(caller_role)
    app.dependency_overrides[bearer_token] = lambda: "t"
    app.dependency_overrides[current_member] = lambda: caller
    app.dependency_overrides[get_feedback_service] = lambda: service
    response = TestClient(app).get("/api/v1/feedback")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    service.list_workspace.assert_not_called()


def test_owner_reads_the_workspace_inbox_with_filters(service: Mock) -> None:
    app = create_app()
    caller = _member(MemberRole.owner)
    app.dependency_overrides[bearer_token] = lambda: "t"
    app.dependency_overrides[current_member] = lambda: caller
    app.dependency_overrides[get_feedback_service] = lambda: service
    service.list_workspace.return_value = SubmissionPage(
        items=[_submission(submitter_name="Salma", can_withdraw=False)]
    )
    response = TestClient(app).get(
        "/api/v1/feedback", params={"status": "reviewed", "category": "idea"}
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["submitter_name"] == "Salma"
    kwargs = service.list_workspace.call_args.kwargs
    assert kwargs["status"] == Status.reviewed and kwargs["category"] == Category.idea
    assert "labels" not in response.text


def test_mine_is_not_read_as_an_id(client: TestClient, service: Mock) -> None:
    service.list_mine.return_value = SubmissionPage(items=[])
    assert client.get("/api/v1/feedback/mine").status_code == 200
    service.get.assert_not_called()


# ---------------------------------------------------- GET one, DELETE, attachment url


def test_get_one_and_404_envelope(client: TestClient, service: Mock) -> None:
    from procurepilot_api.errors import NotFoundError

    wanted = _submission()
    service.get.return_value = wanted
    assert client.get(f"/api/v1/feedback/{wanted.id}").json()["id"] == str(wanted.id)

    service.get.side_effect = NotFoundError(details={"resource": "feedback"})
    missing = client.get(f"/api/v1/feedback/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["code"] == "not_found"
    assert client.get("/api/v1/feedback/not-a-uuid").status_code == 422


def test_withdraw_is_204_and_409_after_the_status_moved(client: TestClient, service: Mock) -> None:
    submission_id = uuid4()
    response = client.delete(f"/api/v1/feedback/{submission_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert service.withdraw.call_args.kwargs["submission_id"] == submission_id
    assert service.withdraw.call_args.kwargs["bearer_token"] == "verified-token"

    service.withdraw.side_effect = FeedbackWithdrawRefusedError(details={"status": "reviewed"})
    refused = client.delete(f"/api/v1/feedback/{submission_id}")
    assert refused.status_code == 409
    assert refused.json()["code"] == "feedback.withdraw_refused"


def test_attachment_url_returns_a_signed_url(client: TestClient, service: Mock) -> None:
    service.attachment_url.return_value = SignedUrl(url="http://storage.test/x?t=1", expires_in=300)
    response = client.get(f"/api/v1/feedback/{uuid4()}/attachments/{uuid4()}/url")
    assert response.status_code == 200
    assert response.json() == {"url": "http://storage.test/x?t=1", "expires_in": 300}


# --------------------------------------------------------------- contract drift

CONTRACT = (
    Path(__file__).resolve().parents[4] / "specs/025-user-feedback/contracts/feedback.openapi.yaml"
)
MEMBER_OPERATIONS = {
    ("/feedback", "post"): "submitFeedback",
    ("/feedback", "get"): "listWorkspaceFeedback",
    ("/feedback/mine", "get"): "listMyFeedback",
    ("/feedback/{id}", "get"): "getFeedback",
    ("/feedback/{id}", "delete"): "withdrawFeedback",
    ("/feedback/{id}/attachments/{attachmentId}/url", "get"): "getAttachmentUrl",
}


@pytest.fixture(scope="module")
def contract() -> dict:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live() -> dict:
    return create_app().openapi()


def _live_path(path: str) -> str:
    return "/api/v1" + path.replace("{id}", "{submission_id}").replace(
        "{attachmentId}", "{attachment_id}"
    )


def test_every_member_operation_in_the_contract_is_registered(contract: dict, live: dict) -> None:
    for (path, method), operation_id in MEMBER_OPERATIONS.items():
        assert method in contract["paths"][path], f"{method} {path} missing from the contract"
        assert contract["paths"][path][method]["operationId"] == operation_id
        live_operation = live["paths"][_live_path(path)][method]
        assert live_operation["operationId"] == operation_id


def test_submission_and_attachment_schemas_match_the_contract(contract: dict, live: dict) -> None:
    for name in ("Submission", "Attachment"):
        wanted = contract["components"]["schemas"][name]
        actual = live["components"]["schemas"][name]
        assert set(actual["properties"]) == set(wanted["properties"]), name
        assert set(wanted["required"]) <= set(actual["required"]), name
    # Tenant-facing models never carry operator labels.
    assert "labels" not in live["components"]["schemas"]["Submission"]["properties"]


def test_enums_match_the_contract(contract: dict, live: dict) -> None:
    for name in ("Status", "Category"):
        assert (
            live["components"]["schemas"][name]["enum"]
            == (contract["components"]["schemas"][name]["enum"])
        )


def test_submit_declares_the_required_uuid_idempotency_key_and_multipart_body(
    contract: dict, live: dict
) -> None:
    operation = live["paths"]["/api/v1/feedback"]["post"]
    header = next(p for p in operation["parameters"] if p["name"] == "Idempotency-Key")
    assert header["in"] == "header" and header["required"] is True
    assert header["schema"]["format"] == "uuid"
    content = operation["requestBody"]["content"]
    assert "multipart/form-data" in content
    body_ref = content["multipart/form-data"]["schema"]["$ref"].rsplit("/", 1)[-1]
    body = live["components"]["schemas"][body_ref]
    assert set(body["properties"]) == {"text", "category", "images", "audio"}
    assert body["required"] == ["text"]
    assert set(contract["paths"]["/feedback"]["post"]["responses"]) >= {
        "200",
        "201",
        "413",
        "415",
        "422",
        "429",
    }
    assert set(operation["responses"]) >= {"200", "201", "413", "415", "422", "429"}


def test_list_endpoints_cap_limit_at_100(contract: dict, live: dict) -> None:
    assert contract["components"]["parameters"]["Limit"]["schema"]["maximum"] == 100
    for path in ("/api/v1/feedback", "/api/v1/feedback/mine"):
        limit = next(p for p in live["paths"][path]["get"]["parameters"] if p["name"] == "limit")
        assert limit["schema"]["maximum"] == 100
        assert limit["schema"]["default"] == 25

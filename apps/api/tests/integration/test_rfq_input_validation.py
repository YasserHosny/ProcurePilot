"""RFQ validation regressions exercised through HTTP and real Postgres."""

import base64
import json
import uuid
from collections.abc import AsyncIterator

import psycopg
import pytest
from httpx import ASGITransport, AsyncClient, Response

from procurepilot_api.config import get_settings
from procurepilot_api.deps import CurrentMember, current_member
from procurepilot_api.main import app
from procurepilot_api.modules.auth.jwt import MemberRole
from tests.integration.test_rfq_api import _seed_product, _seed_supplier, _seed_tenant


@pytest.fixture(scope="module")
def seeded() -> dict:
    with psycopg.connect(
        get_settings().database_url.get_secret_value(), prepare_threshold=None
    ) as conn:
        with conn.cursor() as cur:
            tenant, user, membership = _seed_tenant(cur)
            product = _seed_product(cur, tenant)
            suppliers = [
                _seed_supplier(cur, tenant, f"validation-{i}@example.test") for i in range(2)
            ]
            branch = uuid.uuid4()
            cur.execute(
                "insert into branch (id,tenant_id,name) values (%s,%s,'Main')", (branch, tenant)
            )
        conn.commit()
    return dict(
        tenant=tenant,
        user=user,
        membership=membership,
        product=product,
        suppliers=suppliers,
        branch=branch,
    )


@pytest.fixture
async def client(seeded: dict) -> AsyncIterator[AsyncClient]:
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[current_member] = lambda: CurrentMember(
        tenant_id=seeded["tenant"],
        user_id=seeded["user"],
        membership_id=seeded["membership"],
        email="rfq-validation@example.test",
        role=MemberRole.owner,
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
            yield value
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _payload(seeded: dict) -> dict:
    return {
        "lines": [{"workspace_product_id": str(seeded["product"]), "quantity": "1"}],
        "recipient_supplier_ids": [],
        "needed_by_date": "2099-12-01",
    }


def _guardrail(seeded: dict) -> dict:
    return dict(
        max_order_value_amount="1000",
        max_order_value_currency="GBP",
        max_price_variance_pct="0.10",
        default_branch_id=str(seeded["branch"]),
    )


def _status(response: Response, expected: int) -> None:
    print(f"HTTP {response.status_code} expected {expected}")
    assert response.status_code == expected, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["0", "-1", "1.1234567", "1000000000000"])
async def test_quantity_rejected_without_rfq(client: AsyncClient, seeded: dict, bad: str) -> None:
    payload = _payload(seeded)
    payload["lines"][0]["quantity"] = bad
    key = uuid.uuid4()
    response = await client.post("/api/v1/rfq", json=payload, headers={"Idempotency-Key": str(key)})
    _status(response, 422)
    assert response.json()["code"] == "validation.invalid_request"
    with psycopg.connect(
        get_settings().database_url.get_secret_value(), prepare_threshold=None
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select count(*) from rfq where tenant_id=%s and idempotency_key=%s",
                (seeded["tenant"], key),
            )
            assert cur.fetchone()[0] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["empty_lines", "too_many_lines", "too_many_recipients"])
async def test_collection_limits(client: AsyncClient, seeded: dict, case: str) -> None:
    payload = _payload(seeded)
    if case == "empty_lines":
        payload["lines"] = []
    elif case == "too_many_lines":
        payload["lines"] = [
            {"workspace_product_id": str(uuid.uuid4()), "quantity": "1"} for _ in range(201)
        ]
    else:
        payload["recipient_supplier_ids"] = [str(uuid.uuid4()) for _ in range(101)]
    response = await client.post(
        "/api/v1/rfq", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(response, 422)
    assert response.json()["code"] == "validation.invalid_request"


@pytest.mark.asyncio
async def test_duplicate_recipients_create_and_update(client: AsyncClient, seeded: dict) -> None:
    payload = _payload(seeded)
    first, second = map(str, seeded["suppliers"])
    payload["recipient_supplier_ids"] = [second, first, second, first]
    response = await client.post(
        "/api/v1/rfq", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(response, 201)
    rfq_id = response.json()["rfq"]["id"]
    assert [row["supplier_id"] for row in response.json()["recipients"]] == [second, first]
    payload["recipient_supplier_ids"] = [first, first]
    response = await client.put(
        f"/api/v1/rfq/{rfq_id}", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(response, 200)
    assert [row["supplier_id"] for row in response.json()["recipients"]] == [first]
    with psycopg.connect(
        get_settings().database_url.get_secret_value(), prepare_threshold=None
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "select supplier_id from rfq_recipient where tenant_id=%s and rfq_id=%s",
                (seeded["tenant"], rfq_id),
            )
            assert cur.fetchall() == [(uuid.UUID(first),)]


@pytest.mark.asyncio
@pytest.mark.parametrize("offset", [-1, "1", True, 1_000_001])
async def test_invalid_cursor(client: AsyncClient, offset: object) -> None:
    cursor = base64.urlsafe_b64encode(json.dumps({"offset": offset}).encode()).decode()
    response = await client.get("/api/v1/rfq", params={"cursor": cursor})
    _status(response, 422)
    assert response.json()["details"] == {"cursor": "invalid_format"}


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("min_response_count", 0),
        ("min_response_count", -1),
        ("max_price_variance_pct", "-0.0001"),
        ("max_price_variance_pct", "1.0001"),
        ("max_order_value_amount", "0"),
        ("max_order_value_amount", "-1"),
    ],
)
async def test_guardrail_bounds(
    client: AsyncClient, seeded: dict, method: str, field: str, value: object
) -> None:
    path = "/api/v1/rfq/guardrails"
    payload = _guardrail(seeded)
    if method == "patch":
        created = await client.post(path, json=payload)
        _status(created, 201)
        path += f"/{created.json()['id']}"
        payload = {}
    payload[field] = value
    response = await client.request(method, path, json=payload)
    _status(response, 422)
    if field == "max_order_value_amount":
        assert response.json()["details"] == {field: "Must be greater than 0"}
    else:
        assert response.json()["code"] == "validation.invalid_request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "min_response_count",
        "max_price_variance_pct",
        "max_order_value_amount",
        "max_order_value_currency",
        "enabled",
    ],
)
async def test_guardrail_patch_explicit_null(client: AsyncClient, seeded: dict, field: str) -> None:
    created = await client.post("/api/v1/rfq/guardrails", json=_guardrail(seeded))
    _status(created, 201)
    response = await client.patch(
        f"/api/v1/rfq/guardrails/{created.json()['id']}", json={field: None}
    )
    _status(response, 422)
    assert response.json()["code"] == "validation.invalid_request"


@pytest.mark.asyncio
@pytest.mark.parametrize("variance", ["0", "1"])
async def test_guardrail_inclusive_bounds_and_omitted_fields(
    client: AsyncClient, seeded: dict, variance: str
) -> None:
    payload = {**_guardrail(seeded), "max_price_variance_pct": variance, "min_response_count": 1}
    created = await client.post("/api/v1/rfq/guardrails", json=payload)
    _status(created, 201)
    path = f"/api/v1/rfq/guardrails/{created.json()['id']}"
    response = await client.patch(path, json={"enabled": False})
    _status(response, 200)
    assert response.json() == {**created.json(), "enabled": False}
    response = await client.patch(
        path, json={"max_price_variance_pct": variance, "default_cost_centre_id": None}
    )
    _status(response, 200)


@pytest.mark.asyncio
async def test_quantity_boundary_and_empty_draft_recipients(
    client: AsyncClient, seeded: dict
) -> None:
    payload = _payload(seeded)
    payload["lines"][0]["quantity"] = "999999999999.999999"
    response = await client.post(
        "/api/v1/rfq", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(response, 201)
    rfq_id = response.json()["rfq"]["id"]
    assert response.json()["recipients"] == []
    response = await client.post(
        f"/api/v1/rfq/{rfq_id}/send", headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(response, 422)
    assert response.json()["details"]["reason"] == "nothing_to_send"


@pytest.mark.asyncio
async def test_duplicate_recipients_on_update(client: AsyncClient, seeded: dict) -> None:
    payload = _payload(seeded)
    created = await client.post(
        "/api/v1/rfq", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(created, 201)
    rfq_id = created.json()["rfq"]["id"]
    supplier = str(seeded["suppliers"][0])
    payload["recipient_supplier_ids"] = [supplier, supplier]
    response = await client.put(
        f"/api/v1/rfq/{rfq_id}", json=payload, headers={"Idempotency-Key": str(uuid.uuid4())}
    )
    _status(response, 200)
    assert [row["supplier_id"] for row in response.json()["recipients"]] == [supplier]

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from procurepilot_api.modules.offers.schemas import (
    BasketItemRequest,
    BasketOptimiseRequest,
    BasketSplitJob,
)


def test_basket_contract_uses_workspace_product_id_and_queued_job_status() -> None:
    supplier_ids = [uuid4(), uuid4()]
    item = BasketItemRequest(workspace_product_id=uuid4(), quantity="10.000000")
    request = BasketOptimiseRequest(supplier_ids=supplier_ids, items=[item])
    job = BasketSplitJob(
        id=uuid4(),
        supplier_ids=request.supplier_ids,
        items=request.items,
        status="queued",
        created_at=datetime.now(UTC),
        result_url="/api/v1/baskets/test",
    )
    assert job.model_dump(mode="json")["items"][0]["workspace_product_id"] == str(
        item.workspace_product_id
    )


def test_basket_contract_rejects_duplicate_supplier_ids() -> None:
    supplier_id = uuid4()
    with pytest.raises(ValueError, match="two unique"):
        BasketOptimiseRequest(
            supplier_ids=[supplier_id, supplier_id],
            items=[BasketItemRequest(workspace_product_id=uuid4(), quantity="1.000000")],
        )

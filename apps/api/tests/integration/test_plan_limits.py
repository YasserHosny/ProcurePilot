from __future__ import annotations

import psycopg
import pytest

from integration.catalogue_helpers import (
    TEST_DATABASE_URL,
    make_workspace,
    make_workspace_product,
    reset_role,
)
from integration.smart_compare_helpers import (
    cleanup_workspace,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.billing.service import (
    BillingService,
    assign_default_plan_in_signup,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_starter_plan_allows_100_active_products_then_refuses_101st(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with psycopg.connect(TEST_DATABASE_URL or "") as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "plan-limit")
            reset_role(cur)
            assign_default_plan_in_signup(cur, tenant_id=workspace.tenant_id)
            for index in range(100):
                make_workspace_product(cur, workspace, name=f"Plan Product {index}")
        conn.commit()
    try:
        member = member_from_workspace(workspace)
        check = BillingService(settings).check_limit(
            member=member,
            resource="active_catalogue_products",
        )

        assert check.used == 100
        assert check.allowed is False
        assert check.remaining == 0
        with pytest.raises(ConflictError) as exc_info:
            BillingService(settings).ensure_can_add_active_product(member=member)
        assert exc_info.value.details["reason"] == "plan_limit_reached"
    finally:
        cleanup_workspace(workspace)

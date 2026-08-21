from __future__ import annotations

import psycopg
import pytest
from psycopg.rows import dict_row

from integration.catalogue_helpers import TEST_DATABASE_URL, make_workspace, reset_role
from integration.smart_compare_helpers import (
    cleanup_workspace,
    member_from_workspace,
    settings_for_test_db,
)
from procurepilot_api.errors import NotFoundError
from procurepilot_api.modules.billing.service import (
    BillingService,
    assign_default_plan_in_signup,
)

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


def test_default_plan_assignment_creates_stub_billing_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "billing-account")
            reset_role(cur)
            assign_default_plan_in_signup(cur, tenant_id=workspace.tenant_id)
        conn.commit()
    try:
        account = BillingService(settings).current_account(member=member_from_workspace(workspace))

        assert account.plan.code == "starter"
        assert account.plan.limits.active_catalogue_products == 100
        assert account.provider_customer_id == f"stub_customer:{workspace.tenant_id}"
        assert account.provider_subscription_id == (
            f"stub_subscription:{workspace.tenant_id}:starter"
        )
    finally:
        cleanup_workspace(workspace)


def test_missing_billing_account_is_configuration_not_empty_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with psycopg.connect(TEST_DATABASE_URL or "", row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            workspace = make_workspace(cur, "billing-missing")
        conn.commit()
    try:
        with pytest.raises(NotFoundError):
            BillingService(settings).current_account(member=member_from_workspace(workspace))
    finally:
        cleanup_workspace(workspace)

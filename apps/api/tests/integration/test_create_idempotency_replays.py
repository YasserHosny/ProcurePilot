from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, act_as
from integration.quotation_helpers import make_document
from integration.smart_compare_helpers import (
    committed_smart_context,
    settings_for_test_db,
)
from integration.test_idempotent_replay import _PsycopgReplayClient
from procurepilot_api.modules.catalogue.models import PackInput, ProductCreate, SupplierCreate
from procurepilot_api.modules.catalogue.service import CatalogueService
from procurepilot_api.modules.devices.schemas import DeviceRegistrationCreate
from procurepilot_api.modules.devices.service import DevicesService
from procurepilot_api.modules.digests.schemas import DigestSubscriptionCreate
from procurepilot_api.modules.digests.service import DigestsService
from procurepilot_api.modules.exports.schemas import ExportCreate, ExportFilters
from procurepilot_api.modules.exports.service import ExportService
from procurepilot_api.modules.offers import refresh_schedule_service
from procurepilot_api.modules.offers.refresh_schedule_service import create_schedule
from procurepilot_api.modules.offers.schemas import (
    Money,
    RefreshScheduleCreate,
    SupplierCommercialTermCreate,
)
from procurepilot_api.modules.offers.supplier_terms import SupplierTermsService
from procurepilot_api.modules.organisation.schemas import (
    BranchCreate,
    BudgetCreate,
    CostCentreCreate,
)
from procurepilot_api.modules.organisation.service import OrganisationService
from procurepilot_api.modules.quotations.schemas import QuotationCreate
from procurepilot_api.modules.quotations.service import QuotationService

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is not set; needs a migrated local Postgres",
)


class _NoAuditWriter:
    def record(self, event: object, bearer_token: str | None = None) -> None:
        return None


def _patch_supabase(
    monkeypatch: pytest.MonkeyPatch, conn: psycopg.Connection, module: object
) -> None:
    client = _PsycopgReplayClient(conn)
    monkeypatch.setattr(module, "authenticated_client", lambda _settings, _token: client)
    if hasattr(module, "get_audit_writer"):
        monkeypatch.setattr(module, "get_audit_writer", lambda: _NoAuditWriter())
    return None


def _count(conn: psycopg.Connection, table: str, tenant_id: UUID) -> int:
    with conn.cursor() as cur:
        cur.execute(f"select count(*) from {table} where tenant_id = %s", (tenant_id,))
        return int(cur.fetchone()[0])


def test_product_create_replay_returns_original_product(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.catalogue import service as module

    with committed_smart_context("replay-product") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into billing_account (id,tenant_id,plan_code,provider_customer_id) "
                    "values (%s,%s,'starter',%s)",
                    (
                        uuid4(),
                        context.workspace.tenant_id,
                        f"stub_customer:{context.workspace.tenant_id}",
                    ),
                )
            conn.commit()
            _patch_supabase(monkeypatch, conn, module)
            service = CatalogueService(settings_for_test_db(monkeypatch))
            service._service_role_client = lambda: _PsycopgReplayClient(conn)  # type: ignore[method-assign]
            payload = ProductCreate(
                tenant_name="Replay product",
                canonical_name="Replay product",
                base_unit="kg",
                pack=PackInput(pack_count=1, unit_size="1"),
            )
            key = uuid4()
            first, first_created = service.create_product(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            second, second_created = service.create_product(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            assert first_created is True
            assert second_created is False
            assert second.id == first.id
            assert _count(conn, "workspace_product", context.workspace.tenant_id) == 2


def test_supplier_create_replay_returns_original_supplier(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.catalogue import service as module

    with committed_smart_context("replay-supplier") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            _patch_supabase(monkeypatch, conn, module)
            service = CatalogueService(settings_for_test_db(monkeypatch))
            key = uuid4()
            payload = SupplierCreate(name="Replay supplier")
            first, created = service.create_supplier(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            second, replayed = service.create_supplier(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            assert created is True and replayed is False
            assert second.id == first.id
            assert _count(conn, "supplier", context.workspace.tenant_id) == 3


def test_device_registration_replay_returns_original_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = settings_for_test_db(monkeypatch)
    with committed_smart_context("replay-device") as context:
        key = uuid4()
        service = DevicesService(settings)
        payload = DeviceRegistrationCreate(platform="ios", push_token="replay-device-token")
        first, created = service.register_device(
            bearer_token="unused", member=context.member, payload=payload, idempotency_key=key
        )
        second, replayed = service.register_device(
            bearer_token="unused", member=context.member, payload=payload, idempotency_key=key
        )
        assert created is True and replayed is False
        assert second.id == first.id
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            assert _count(conn, "device_registration", context.workspace.tenant_id) == 1


def test_digest_subscription_replay_returns_original_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.modules.digests import service as digests_module

    monkeypatch.setattr(digests_module, "get_audit_writer", lambda: _NoAuditWriter())
    service = DigestsService(settings_for_test_db(monkeypatch))
    with committed_smart_context("replay-digest") as context:
        payload = DigestSubscriptionCreate(channel="in_app", locale="en")
        key = uuid4()
        first, created = service.create_subscription(
            member=context.member, payload=payload, idempotency_key=key
        )
        second, replayed = service.create_subscription(
            member=context.member, payload=payload, idempotency_key=key
        )
        assert created is True and replayed is False
        assert second.id == first.id
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            assert _count(conn, "digest_subscription", context.workspace.tenant_id) == 1


def test_digest_subscription_replay_bypasses_the_active_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.modules.digests import service as digests_module

    monkeypatch.setattr(digests_module, "get_audit_writer", lambda: _NoAuditWriter())
    settings = settings_for_test_db(monkeypatch)
    settings.active_digest_subscription_cap_per_member = 1
    service = DigestsService(settings)
    with committed_smart_context("replay-digest-cap") as context:
        payload = DigestSubscriptionCreate(channel="in_app", locale="en")
        key = uuid4()
        first, created = service.create_subscription(
            member=context.member, payload=payload, idempotency_key=key
        )
        # The one call above already put this member's active-subscription count AT the cap.
        # A retry of that same call must still replay, not fail with cap_exceeded.
        second, replayed = service.create_subscription(
            member=context.member, payload=payload, idempotency_key=key
        )
        assert created is True and replayed is False
        assert second.id == first.id


def test_digest_subscription_fresh_key_colliding_on_filters_is_a_conflict_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.errors import ConflictError
    from procurepilot_api.modules.digests import service as digests_module

    monkeypatch.setattr(digests_module, "get_audit_writer", lambda: _NoAuditWriter())
    service = DigestsService(settings_for_test_db(monkeypatch))
    with committed_smart_context("replay-digest-collide") as context:
        payload = DigestSubscriptionCreate(channel="in_app", locale="en")
        service.create_subscription(
            member=context.member, payload=payload, idempotency_key=uuid4()
        )
        # Same member, same (default) filters -> hits digest_subscription_owner_unique, not the
        # idempotency index. A FRESH key must not be mistaken for a replay of this row.
        with pytest.raises(ConflictError):
            service.create_subscription(
                member=context.member, payload=payload, idempotency_key=uuid4()
            )


def test_product_fresh_key_colliding_on_canonical_product_is_a_conflict_not_lookup_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.errors import ConflictError
    from procurepilot_api.modules.catalogue import service as module

    with committed_smart_context("replay-product-collide") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into billing_account (id,tenant_id,plan_code,provider_customer_id) "
                    "values (%s,%s,'starter',%s)",
                    (
                        uuid4(),
                        context.workspace.tenant_id,
                        f"stub_customer:{context.workspace.tenant_id}",
                    ),
                )
            conn.commit()
            _patch_supabase(monkeypatch, conn, module)
            service = CatalogueService(settings_for_test_db(monkeypatch))
            service._service_role_client = lambda: _PsycopgReplayClient(conn)  # type: ignore[method-assign]
            payload = ProductCreate(
                tenant_name="Collide product one",
                canonical_name="Collide canonical",
                base_unit="kg",
                pack=PackInput(pack_count=1, unit_size="1"),
            )
            service.create_product(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=uuid4(),
            )
            # Same canonical (name/brand/variant/base_unit) resolves to the same
            # canonical_product_id -> hits workspace_product_one_view_per_canonical, not the
            # idempotency index. A FRESH key must not be mistaken for a replay of that row.
            second_payload = ProductCreate(
                tenant_name="Collide product two",
                canonical_name="Collide canonical",
                base_unit="kg",
                pack=PackInput(pack_count=1, unit_size="1"),
            )
            with pytest.raises(ConflictError):
                service.create_product(
                    bearer_token="test-token",
                    member=context.member,
                    payload=second_payload,
                    idempotency_key=uuid4(),
                )


def test_cost_centre_fresh_key_colliding_on_code_is_a_conflict_not_lookup_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.errors import ConflictError
    from procurepilot_api.modules.organisation import service as module

    with committed_smart_context("replay-cost-centre-collide") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            _patch_supabase(monkeypatch, conn, module)
            service = OrganisationService(settings_for_test_db(monkeypatch))
            service.create_cost_centre(
                bearer_token="test-token",
                member=context.member,
                payload=CostCentreCreate(name="Collide kitchen one", code="COLLIDE-1"),
                idempotency_key=uuid4(),
            )
            # Same code -> hits cost_centre_tenant_code_key, not the idempotency index. A FRESH
            # key must not be mistaken for a replay of that row.
            with pytest.raises(ConflictError):
                service.create_cost_centre(
                    bearer_token="test-token",
                    member=context.member,
                    payload=CostCentreCreate(name="Collide kitchen two", code="COLLIDE-1"),
                    idempotency_key=uuid4(),
                )


def test_export_create_replay_returns_original_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.exports import service as module

    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(module, "get_audit_writer", lambda: _NoAuditWriter())
    monkeypatch.setattr(module, "_enqueue_export_job", lambda *_args: None)
    with committed_smart_context("replay-export") as context:
        payload = ExportCreate(
            kind="savings_ledger",
            format="csv",
            filters=ExportFilters(period_start=datetime.now(UTC).date()),
        )
        key = uuid4()
        first, created = ExportService(settings).create_job(
            member=context.member, payload=payload, idempotency_key=key
        )
        second, replayed = ExportService(settings).create_job(
            member=context.member, payload=payload, idempotency_key=key
        )
        assert created is True and replayed is False
        assert second.id == first.id
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            assert _count(conn, "export_job", context.workspace.tenant_id) == 1


def test_refresh_schedule_replay_returns_original_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = settings_for_test_db(monkeypatch)
    monkeypatch.setattr(refresh_schedule_service, "get_audit_writer", lambda: _NoAuditWriter())
    with committed_smart_context("replay-refresh") as context:
        payload = RefreshScheduleCreate(
            workspace_product_id=context.product_id,
            supplier_id=context.supplier_ids[0],
            cadence_days=14,
        )
        key = uuid4()
        first, created = create_schedule(
            member=context.member, payload=payload, settings=settings, idempotency_key=key
        )
        second, replayed = create_schedule(
            member=context.member, payload=payload, settings=settings, idempotency_key=key
        )
        assert created is True and replayed is False
        assert second.id == first.id
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            assert _count(conn, "offer_refresh_schedule", context.workspace.tenant_id) == 1


def test_supplier_commercial_term_replay_returns_original_term(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = SupplierTermsService(settings_for_test_db(monkeypatch))
    with committed_smart_context("replay-term") as context:
        payload = SupplierCommercialTermCreate(
            effective_from=datetime.now(UTC),
            minimum_order_value=Money(amount="100", currency="GBP"),
        )
        key = uuid4()
        first, created = service.create_term(
            member=context.member,
            supplier_id=context.supplier_ids[0],
            payload=payload,
            idempotency_key=key,
        )
        second, replayed = service.create_term(
            member=context.member,
            supplier_id=context.supplier_ids[0],
            payload=payload,
            idempotency_key=key,
        )
        assert created is True and replayed is False
        assert second.id == first.id
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            assert _count(conn, "supplier_commercial_term", context.workspace.tenant_id) == 1


def test_branch_create_replay_returns_original_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.organisation import service as module

    with committed_smart_context("replay-branch") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            _patch_supabase(monkeypatch, conn, module)
            service = OrganisationService(settings_for_test_db(monkeypatch))
            payload = BranchCreate(name="Replay branch", region="GB")
            key = uuid4()
            first, created = service.create_branch(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            second, replayed = service.create_branch(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            assert created is True and replayed is False
            assert second.id == first.id
            assert _count(conn, "branch", context.workspace.tenant_id) == 1


def test_cost_centre_create_replay_returns_original_cost_centre(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.modules.organisation import service as module

    with committed_smart_context("replay-cost-centre") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            _patch_supabase(monkeypatch, conn, module)
            service = OrganisationService(settings_for_test_db(monkeypatch))
            payload = CostCentreCreate(name="Replay kitchen", code="REPLAY-1")
            key = uuid4()
            first, created = service.create_cost_centre(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            second, replayed = service.create_cost_centre(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            assert created is True and replayed is False
            assert second.id == first.id
            assert _count(conn, "cost_centre", context.workspace.tenant_id) == 1


def test_budget_create_replay_returns_original_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.organisation import service as module

    with committed_smart_context("replay-budget") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            _patch_supabase(monkeypatch, conn, module)
            service = OrganisationService(settings_for_test_db(monkeypatch))
            payload = BudgetCreate(
                amount="1000",
                currency="GBP",
                period="monthly",
                period_start=datetime.now(UTC).date(),
                scope="organisation",
            )
            key = uuid4()
            first, created = service.create_budget(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            second, replayed = service.create_budget(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            assert created is True and replayed is False
            assert second.id == first.id
            assert _count(conn, "budget", context.workspace.tenant_id) == 1


def test_quotation_create_replay_returns_original_quotation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from procurepilot_api.modules.quotations import service as module

    with committed_smart_context("replay-quotation") as context:
        with psycopg.connect(TEST_DATABASE_URL) as conn:
            with conn.cursor() as cur:
                act_as(cur, context.workspace)
                document_id = make_document(cur, context.workspace)
            conn.commit()
            _patch_supabase(monkeypatch, conn, module)
            service = QuotationService(settings_for_test_db(monkeypatch))
            payload = QuotationCreate(document_id=document_id, supplier_id=context.supplier_ids[0])
            key = uuid4()
            first, created = service.create_quotation(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            second, replayed = service.create_quotation(
                bearer_token="test-token",
                member=context.member,
                payload=payload,
                idempotency_key=key,
            )
            assert created is True and replayed is False
            assert second.id == first.id
            assert _count(conn, "quotation", context.workspace.tenant_id) == 1

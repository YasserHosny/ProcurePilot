from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from integration.catalogue_helpers import TEST_DATABASE_URL, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    make_extracted_quotation,
    make_field,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import review_service, service
from procurepilot_api.modules.quotations.review_service import (
    QuotationReviewService,
    _recompute_arithmetic_status,
)
from procurepilot_api.modules.quotations.schemas import (
    FieldCorrection,
    QuotationDetail,
    QuotationReviewPatch,
)
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set")


@pytest.fixture(autouse=True)
def block_postgrest_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    from procurepilot_api.modules.members import service as members_service
    from procurepilot_api.shared import audit

    def blocked_client(*args: object, **kwargs: object) -> None:
        raise AssertionError("VAT tests must use the in-test psycopg client")

    monkeypatch.setattr(members_service, "create_client", blocked_client)
    monkeypatch.setattr(audit, "create_client", blocked_client)


@pytest.fixture
def conn() -> object:
    yield from connection()


@pytest.mark.parametrize("via_correction", [False, True])
def test_review_vat_basis_mirrors_canonical_rows_preserving_line_rates(
    conn: object, monkeypatch: pytest.MonkeyPatch, via_correction: bool
) -> None:
    events = []

    class AuditWriter:
        def record(self, event: object, **kwargs: object) -> None:
            events.append(event)

    with conn.cursor() as cur:
        ws = make_workspace(cur, "vat-review")
        fixture = make_extracted_quotation(cur, ws)
        other = uuid4()
        cur.execute(
            "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text,"
            "quantity,unit_price_amount,unit_price_currency,vat_rate) "
            "values (%s,%s,%s,2,'own VAT',1,5,'GBP',0.05)",
            (other, ws.tenant_id, fixture.quotation_id),
        )
        make_field(
            cur,
            ws,
            fixture.quotation_id,
            entity_type="quotation_line",
            entity_id=other,
            field_name="vat_rate",
            extracted_value="0.05",
        )
        flag = make_field(
            cur,
            ws,
            fixture.quotation_id,
            field_name="prices_include_vat",
            extracted_value=False,
            confidence=Decimal("0.8"),
        )
        rate = make_field(
            cur,
            ws,
            fixture.quotation_id,
            field_name="vat_rate",
            extracted_value="0.10",
            confidence=Decimal("0.8"),
        )
        cur.execute(
            "update quotation set stated_total_amount=29, stated_total_currency='GBP' where id=%s",
            (fixture.quotation_id,),
        )
        client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(review_service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(review_service, "get_audit_writer", lambda: AuditWriter())
        patch = (
            QuotationReviewPatch(
                corrections=[
                    FieldCorrection(field_extraction_id=flag, corrected_value=True),
                    FieldCorrection(field_extraction_id=rate, corrected_value="0.15"),
                ]
            )
            if via_correction
            else QuotationReviewPatch(prices_include_vat=True, vat_rate=Decimal("0.15"))
        )
        detail = QuotationReviewService().apply_review_patch(
            bearer_token="test",
            member=CurrentMember(
                membership_id=ws.membership_id,
                tenant_id=ws.tenant_id,
                user_id=ws.user_id,
                email="buyer@example.test",
                role=MemberRole.owner,
            ),
            quotation_id=fixture.quotation_id,
            patch=patch,
        )
        assert detail.prices_include_vat is True
        # The header extraction is the authoritative rate (corrected when present).
        assert detail.vat_rate == ("0.1500" if via_correction else "0.1000")
        assert detail.arithmetic_status == "reconciled"
        assert [line.vat_rate for line in detail.lines] == ["0.1500", "0.0500"]
        assert events[-1].target["vat_basis_changed"] is True
        cur.execute("select prices_include_vat from quotation where id=%s", (fixture.quotation_id,))
        assert cur.fetchone() == (True,)


def test_inclusive_arithmetic_uses_gross_lines(conn: object) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "vat-arithmetic")
        f = make_extracted_quotation(cur, ws)
        cur.execute(
            "update quotation set prices_include_vat=true, stated_total_amount=24, "
            "stated_total_currency='GBP', arithmetic_status='mismatch' where id=%s",
            (f.quotation_id,),
        )
        cur.execute("update quotation_line set vat_rate=0.15 where id=%s", (f.line_id,))
        _recompute_arithmetic_status(PsycopgSupabaseClient(conn), f.quotation_id)
        cur.execute("select arithmetic_status from quotation where id=%s", (f.quotation_id,))
        assert cur.fetchone() == ("reconciled",)


def test_detail_rate_falls_back_to_common_priced_line_rate(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with conn.cursor() as cur:
        ws = make_workspace(cur, "vat-common")
        f = make_extracted_quotation(cur, ws)
        client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(service, "authenticated_client", lambda *_: client)

        def read() -> QuotationDetail:
            return service.QuotationService().get_quotation(
                bearer_token="test", quotation_id=f.quotation_id
            )

        assert read().vat_rate is None
        cur.execute("update quotation_line set vat_rate=0.15 where id=%s", (f.line_id,))
        assert read().vat_rate == "0.1500"
        cur.execute(
            "insert into quotation_line (tenant_id,quotation_id,line_number,original_text,"
            "quantity,unit_price_amount,unit_price_currency,vat_rate) "
            "values (%s,%s,2,'different VAT',1,5,'GBP',0.05)",
            (ws.tenant_id, f.quotation_id),
        )
        assert read().vat_rate is None


@pytest.mark.parametrize("rate", ["-0.01", "1", "1.01"])
def test_patch_rejects_invalid_vat_rate(rate: str) -> None:
    with pytest.raises(ValidationError):
        QuotationReviewPatch(vat_rate=Decimal(rate))


@pytest.mark.parametrize(
    "name,value", [("vat_rate", "1.2"), ("vat_rate", "invalid"), ("prices_include_vat", "yes")]
)
def test_invalid_header_vat_correction_is_rejected_before_any_write(
    conn: object, monkeypatch: pytest.MonkeyPatch, name: str, value: object
) -> None:
    from procurepilot_api.errors import ConflictError

    with conn.cursor() as cur:
        ws = make_workspace(cur, "invalid-vat-correction")
        f = make_extracted_quotation(cur, ws)
        field = make_field(
            cur,
            ws,
            f.quotation_id,
            field_name=name,
            extracted_value="0.15" if name == "vat_rate" else False,
        )
        client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(review_service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(service, "authenticated_client", lambda *_: client)

        class AuditWriter:
            def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
                raise AssertionError("Invalid corrections must not append an audit event")

        monkeypatch.setattr(review_service, "get_audit_writer", lambda: AuditWriter())
        with pytest.raises(ConflictError) as exc:
            QuotationReviewService().apply_review_patch(
                bearer_token="test",
                member=CurrentMember(
                    membership_id=ws.membership_id,
                    tenant_id=ws.tenant_id,
                    user_id=ws.user_id,
                    email="buyer@example.test",
                    role=MemberRole.owner,
                ),
                quotation_id=f.quotation_id,
                patch=QuotationReviewPatch(
                    corrections=[FieldCorrection(field_extraction_id=field, corrected_value=value)]
                ),
            )
        assert exc.value.details["reason"] == "invalid_vat_correction"
        cur.execute("select status from quotation where id=%s", (f.quotation_id,))
        assert cur.fetchone() == ("extracted",)
        cur.execute("select corrected_by from field_extraction where id=%s", (field,))
        assert cur.fetchone() == (None,)


@pytest.mark.parametrize("rate", ["invalid", "NaN", "Infinity", "-Infinity"])
def test_patch_rejects_non_numeric_or_non_finite_vat_rate(rate: str) -> None:
    with pytest.raises(ValidationError):
        QuotationReviewPatch(vat_rate=rate)


@pytest.mark.parametrize("value", ["yes", "false", 1, 0, None])
def test_patch_rejects_non_boolean_vat_basis(value: object) -> None:
    with pytest.raises(ValidationError):
        QuotationReviewPatch(prices_include_vat=value)


def test_a_second_vat_basis_change_is_what_the_detail_shows(
    conn: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The header field keeps its first correction (one per field); the quote and its lines hold
    # the reviewer's latest choice, and the detail must show that one.
    class AuditWriter:
        def record(self, event: object, **kwargs: object) -> None:
            del event, kwargs

    with conn.cursor() as cur:
        ws = make_workspace(cur, "vat-second-change")
        f = make_extracted_quotation(cur, ws)
        flag = make_field(
            cur, ws, f.quotation_id, field_name="prices_include_vat", extracted_value=False,
            confidence=Decimal("0.8"),
        )
        rate = make_field(
            cur, ws, f.quotation_id, field_name="vat_rate", extracted_value="0.10",
            confidence=Decimal("0.8"),
        )
        client = PsycopgSupabaseClient(conn)
        monkeypatch.setattr(review_service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(review_service, "get_audit_writer", lambda: AuditWriter())
        member = CurrentMember(
            membership_id=ws.membership_id,
            tenant_id=ws.tenant_id,
            user_id=ws.user_id,
            email="buyer@example.test",
            role=MemberRole.owner,
        )

        def review(patch: QuotationReviewPatch) -> QuotationDetail:
            return QuotationReviewService().apply_review_patch(
                bearer_token="test", member=member, quotation_id=f.quotation_id, patch=patch
            )

        first = review(
            QuotationReviewPatch(
                prices_include_vat=True,
                vat_rate=Decimal("0.15"),
                corrections=[
                    FieldCorrection(field_extraction_id=flag, corrected_value=True),
                    FieldCorrection(field_extraction_id=rate, corrected_value="0.15"),
                ],
            )
        )
        assert (first.prices_include_vat, first.vat_rate) == (True, "0.1500")

        second = review(QuotationReviewPatch(prices_include_vat=False, vat_rate=Decimal("0.05")))
        assert (second.prices_include_vat, second.vat_rate) == (False, "0.0500")

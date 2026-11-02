from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal

import psycopg
import pytest

from integration.catalogue_helpers import TEST_DATABASE_URL, Workspace, connection, make_workspace
from integration.quotation_helpers import (
    PsycopgSupabaseClient,
    QuotationFixture,
    make_extracted_quotation,
    make_field,
)
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError
from procurepilot_api.modules.auth.jwt import MemberRole
from procurepilot_api.modules.quotations import review_service, service
from procurepilot_api.modules.quotations.review_gate import blocking_low_confidence_fields
from procurepilot_api.modules.quotations.schemas import (
    FieldCorrection,
    QuotationDetail,
    QuotationReviewPatch,
)
from procurepilot_api.shared.audit import AuditEventCreate

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")


ReviewContext = tuple[
    psycopg.Connection,
    Workspace,
    QuotationFixture,
    PsycopgSupabaseClient,
    list[AuditEventCreate],
    Callable[[QuotationReviewPatch], QuotationDetail],
]


@contextmanager
def db_connection() -> Iterator[psycopg.Connection]:
    yield from connection()


@pytest.fixture
def review(monkeypatch: pytest.MonkeyPatch) -> Iterator[ReviewContext]:
    with db_connection() as conn:
        with conn.cursor() as cur:
            ws = make_workspace(cur, "line-evidence")
            quote = make_extracted_quotation(cur, ws)
        client = PsycopgSupabaseClient(conn)
        events = []

        class Writer:
            def record(self, event: AuditEventCreate, bearer_token: str | None = None) -> None:
                events.append(event)

        monkeypatch.setattr(review_service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(service, "authenticated_client", lambda *_: client)
        monkeypatch.setattr(review_service, "get_audit_writer", lambda: Writer())
        member = CurrentMember(
            membership_id=ws.membership_id,
            tenant_id=ws.tenant_id,
            user_id=ws.user_id,
            email="buyer@example.test",
            role=MemberRole.buyer,
        )

        def apply(patch: QuotationReviewPatch) -> QuotationDetail:
            return review_service.QuotationReviewService().apply_review_patch(
                bearer_token="test", member=member, quotation_id=quote.quotation_id, patch=patch
            )

        yield conn, ws, quote, client, events, apply


CASES = [
    ("pack_count", 3, "pack_count", (3,)),
    ("pack_count", "3.0", "pack_count", (3,)),
    ("unit_size", "2.5", "unit_size", (Decimal("2.5"),)),
    ("pack_unit", "gram", "pack_unit", ("gram",)),
    ("description", "Fresh tomatoes", "original_text", ("Fresh tomatoes",)),
    ("original_text", "Fresh tomatoes", "original_text", ("Fresh tomatoes",)),
    (
        "delivery_fee",
        {"amount": "4.25", "currency": "USD"},
        "delivery_fee_amount,delivery_fee_currency",
        (Decimal("4.25"), "USD"),
    ),
    (
        "discount",
        {"amount": "1.25", "currency": "GBP"},
        "discount_amount,discount_currency",
        (Decimal("1.25"), "GBP"),
    ),
    ("vat_rate", "0.15", "vat_rate", (Decimal("0.15"),)),
]


@pytest.mark.parametrize(("name", "value", "columns", "expected"), CASES)
def test_corrections_reach_canonical_columns(
    review: ReviewContext, name: str, value: object, columns: str, expected: tuple[object, ...]
) -> None:
    conn, ws, q, _, _, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name=name,
        )
        apply(
            QuotationReviewPatch(
                corrections=[FieldCorrection(field_extraction_id=field, corrected_value=value)]
            )
        )
        cur.execute(f"select {columns} from quotation_line where id=%s", (q.line_id,))
        assert cur.fetchone() == expected
        cur.execute("select corrected_value from field_extraction where id=%s", (field,))
        assert cur.fetchone()[0] == value


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("pack_count", 0),
        ("pack_count", 1.5),
        ("pack_count", True),
        ("unit_size", "NaN"),
        ("unit_size", "-1"),
        ("pack_unit", "unknown-unit"),
        ("description", ""),
        ("description", {}),
        ("delivery_fee", {"amount": "2"}),
        ("discount", {"amount": "NaN", "currency": "GBP"}),
        ("discount", {"amount": "2", "currency": "ZZZ"}),
        ("vat_rate", "1.1"),
        ("vat_rate", False),
        ("quantity", "0"),
        ("unit_price", {"amount": "2"}),
    ],
)
def test_invalid_correction_is_conflict_before_any_mutation(
    review: ReviewContext, name: str, value: object
) -> None:
    conn, ws, q, _, _, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name=name,
        )
        with pytest.raises(ConflictError) as error:
            apply(
                QuotationReviewPatch(
                    corrections=[FieldCorrection(field_extraction_id=field, corrected_value=value)]
                )
            )
        assert error.value.details["reason"].startswith("invalid_")
        cur.execute("select status from quotation where id=%s", (q.quotation_id,))
        assert cur.fetchone() == ("extracted",)
        cur.execute("select corrected_by from field_extraction where id=%s", (field,))
        assert cur.fetchone() == (None,)


def test_remove_preserves_evidence_and_audits_snapshot(review: ReviewContext) -> None:
    conn, ws, q, client, events, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="quantity",
            extracted_value="2",
            confidence=Decimal("0.1"),
        )
        cur.execute("select * from field_extraction where id=%s", (field,))
        evidence_before = cur.fetchone()
        detail = apply(QuotationReviewPatch(remove_line_ids=[q.line_id]))
        cur.execute("select * from field_extraction where id=%s", (field,))
        assert cur.fetchone() == evidence_before
        assert detail.lines == []
        assert all(f.id != field for f in detail.field_extractions)
        assert (
            blocking_low_confidence_fields(client, q.quotation_id, 0.8, supplier_id=q.supplier_id)
            == []
        )
        assert detail.review_task.reason == "ready_to_authorise"
        removed = next(event for event in events if event.action == "quotation.line_removed")
        assert removed.target == {
            "quotation_id": str(q.quotation_id),
            "line_id": str(q.line_id),
            "line_number": 1,
            "original_text": "Tomatoes case 10 kg",
            "quantity": "2.000000",
            "unit_price": {"amount": "12.0000", "currency": "GBP"},
        }


def test_orphan_evidence_does_not_block_or_appear_in_detail(review: ReviewContext) -> None:
    conn, ws, q, client, _, _ = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="quantity",
            confidence=Decimal("0.1"),
        )
        cur.execute("delete from quotation_line where id=%s", (q.line_id,))
        assert (
            blocking_low_confidence_fields(client, q.quotation_id, 0.8, supplier_id=q.supplier_id)
            == []
        )
        detail = service.QuotationService().get_quotation(
            bearer_token="test", quotation_id=q.quotation_id
        )
        assert all(f.id != field for f in detail.field_extractions)


def test_absent_pack_requires_both_columns_in_one_patch(review: ReviewContext) -> None:
    conn, ws, q, _, _, apply = review
    with conn.cursor() as cur:
        cur.execute(
            "update quotation_line set pack_count=null,unit_size=null where id=%s", (q.line_id,)
        )
        count = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="pack_count",
        )
        size = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="unit_size",
        )
        with pytest.raises(ConflictError):
            apply(
                QuotationReviewPatch(
                    corrections=[FieldCorrection(field_extraction_id=count, corrected_value=2)]
                )
            )
        detail = apply(
            QuotationReviewPatch(
                corrections=[
                    FieldCorrection(field_extraction_id=count, corrected_value=2),
                    FieldCorrection(field_extraction_id=size, corrected_value="5"),
                ]
            )
        )
        assert detail.lines[0].pack.pack_count == 2
        assert Decimal(detail.lines[0].pack.unit_size) == 5


def test_retained_evidence_excluded_from_arithmetic_and_matching(review: ReviewContext) -> None:
    from uuid import uuid4

    from procurepilot_api.modules.matching.service import _with_line_extracted_fields

    conn, ws, q, client, _, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="quantity",
            extracted_value="999",
            confidence=Decimal("0.1"),
        )
        live_id = uuid4()
        cur.execute(
            "insert into quotation_line (id,tenant_id,quotation_id,line_number,original_text,"
            "quantity,unit_price_amount,unit_price_currency) "
            "values (%s,%s,%s,2,'Tea',1,10,'GBP')",
            (live_id, ws.tenant_id, q.quotation_id),
        )
        cur.execute(
            "update quotation set stated_total_amount=10,stated_total_currency='GBP',"
            "arithmetic_status='mismatch' where id=%s",
            (q.quotation_id,),
        )
        detail = apply(QuotationReviewPatch(remove_line_ids=[q.line_id]))
        assert detail.arithmetic_status == "reconciled"
        assert [line.id for line in detail.lines] == [live_id]
        assert all(f.id != field for f in detail.field_extractions)
        rows = (
            client.table("quotation_line")
            .select("*")
            .eq("quotation_id", str(q.quotation_id))
            .execute()
            .data
        )
        matched = _with_line_extracted_fields(client, rows, quote={"id": q.quotation_id})
        assert len(matched) == 1
        assert matched[0]["extracted_fields"] == {}


def test_removed_evidence_cannot_be_corrected_as_a_live_line(review: ReviewContext) -> None:
    from procurepilot_api.errors import NotFoundError

    conn, ws, q, _, _, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="quantity",
        )
        apply(QuotationReviewPatch(remove_line_ids=[q.line_id]))
        with pytest.raises(NotFoundError):
            apply(
                QuotationReviewPatch(
                    corrections=[FieldCorrection(field_extraction_id=field, corrected_value="3")]
                )
            )
        cur.execute("select corrected_by from field_extraction where id=%s", (field,))
        assert cur.fetchone() == (None,)


def test_foreign_line_removal_returns_not_found_and_preserves_evidence(
    review: ReviewContext,
) -> None:
    from procurepilot_api.errors import NotFoundError

    conn, _, q, _, _, apply = review
    with conn.cursor() as cur:
        other_ws = make_workspace(cur, "foreign-evidence")
        other = make_extracted_quotation(cur, other_ws)
        field = make_field(
            cur,
            other_ws,
            other.quotation_id,
            entity_type="quotation_line",
            entity_id=other.line_id,
            field_name="quantity",
        )
        # Authenticated RLS context for the original tenant, not a privileged client.
        cur.execute("select set_config('request.jwt.claims', %s, true)", (review[1].claims(),))
        with pytest.raises(NotFoundError):
            apply(QuotationReviewPatch(remove_line_ids=[other.line_id]))
        cur.execute("reset role")
        cur.execute("select count(*) from field_extraction where id=%s", (field,))
        assert cur.fetchone() == (1,)
        cur.execute("select count(*) from quotation_line where id=%s", (other.line_id,))
        assert cur.fetchone() == (1,)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("line_total", {"amount": "24", "currency": "GBP"}),
        ("pack_text", "two cases"),
    ],
)
def test_evidence_only_fields_remain_correctable(
    review: ReviewContext, name: str, value: object
) -> None:
    conn, ws, q, _, _, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name=name,
            confidence=Decimal("0.1"),
        )
        detail = apply(
            QuotationReviewPatch(
                corrections=[FieldCorrection(field_extraction_id=field, corrected_value=value)]
            )
        )
        assert next(f for f in detail.field_extractions if f.id == field).corrected_value == value
        assert detail.review_task.reason == "ready_to_authorise"


def test_removal_snapshot_includes_same_patch_corrections(review: ReviewContext) -> None:
    conn, ws, q, _, events, apply = review
    with conn.cursor() as cur:
        field = make_field(
            cur,
            ws,
            q.quotation_id,
            entity_type="quotation_line",
            entity_id=q.line_id,
            field_name="quantity",
        )
        apply(
            QuotationReviewPatch(
                remove_line_ids=[q.line_id],
                corrections=[FieldCorrection(field_extraction_id=field, corrected_value="3")],
            )
        )
        assert (
            next(e for e in events if e.action == "quotation.line_removed").target["quantity"]
            == "3.000000"
        )


@pytest.mark.parametrize(
    ("name", "invalid", "valid"),
    [
        (
            "stated_total",
            {"amount": "12,5", "currency": "GBP"},
            {"amount": "12.5", "currency": "USD"},
        ),
        ("stated_total", {"amount": "12.5"}, {"amount": "12.5", "currency": "USD"}),
        (
            "stated_total",
            {"amount": "12.5", "currency": "ZZZ"},
            {"amount": "12.5", "currency": "USD"},
        ),
        ("currency", "ZZZ", "USD"),
        ("currency", None, "USD"),
    ],
)
def test_rejected_header_correction_preserves_evidence_and_allows_retry(
    review: ReviewContext, name: str, invalid: object, valid: object
) -> None:
    conn, ws, q, _, events, apply = review
    with conn.cursor() as cur:
        field = (
            q.field_id
            if name == "currency"
            else make_field(cur, ws, q.quotation_id, field_name=name)
        )
        cur.execute(
            "update quotation set stated_total_amount=24,stated_total_currency='GBP' where id=%s",
            (q.quotation_id,),
        )
        cur.execute("select * from field_extraction where id=%s", (field,))
        evidence_before = cur.fetchone()
        cur.execute("select * from quotation where id=%s", (q.quotation_id,))
        quotation_before = cur.fetchone()
        with pytest.raises(ConflictError) as error:
            apply(
                QuotationReviewPatch(
                    reviewer_notes="must not persist",
                    corrections=[
                        FieldCorrection(field_extraction_id=field, corrected_value=invalid)
                    ],
                )
            )
        assert error.value.details == {"reason": f"invalid_{name}_correction"}
        cur.execute("select * from field_extraction where id=%s", (field,))
        assert cur.fetchone() == evidence_before
        cur.execute("select * from quotation where id=%s", (q.quotation_id,))
        assert cur.fetchone() == quotation_before
        assert events == []

        apply(
            QuotationReviewPatch(
                corrections=[FieldCorrection(field_extraction_id=field, corrected_value=valid)]
            )
        )
        cur.execute(
            "select corrected_value,corrected_by,corrected_at from field_extraction where id=%s",
            (field,),
        )
        corrected_value, corrected_by, corrected_at = cur.fetchone()
        assert corrected_value == valid
        assert corrected_by == ws.membership_id
        assert corrected_at is not None
        cur.execute(
            "select currency,stated_total_amount,stated_total_currency from quotation where id=%s",
            (q.quotation_id,),
        )
        assert cur.fetchone() == (
            ("USD", Decimal("24"), "GBP") if name == "currency" else ("GBP", Decimal("12.5"), "USD")
        )

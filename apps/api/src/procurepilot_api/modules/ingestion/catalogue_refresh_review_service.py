from __future__ import annotations

import base64
import csv
import io
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import UUID

from psycopg.rows import dict_row

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import ConflictError, NotFoundError, UnprocessableEntityError
from procurepilot_api.modules.ingestion.catalogue_import_service import import_catalogue
from procurepilot_api.modules.ingestion.schemas import (
    CatalogueRefreshReview,
    CatalogueRefreshReviewList,
)
from procurepilot_api.modules.offers.service import _authenticated_db
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id


def get_review(
    *, member: CurrentMember, review_id: UUID, settings: Settings | None = None
) -> dict[str, Any]:
    active_settings = settings or get_settings()
    with _authenticated_db(active_settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select r.*, ci.file_name as source_file_name, ci.file_format as source_file_format
                from catalogue_refresh_review r
                join catalogue_imports ci
                  on ci.tenant_id = r.tenant_id and ci.id = r.source_import_id
                where r.tenant_id = %s and r.id = %s
                """,
                (member.tenant_id, review_id),
            )
            row = cur.fetchone()
    if row is None:
        raise NotFoundError(details={"resource": "catalogue_refresh_review"})
    return dict(row)


def list_reviews(
    *,
    member: CurrentMember,
    status: str = "pending_review",
    cursor: str | None = None,
    limit: int = 50,
    settings: Settings | None = None,
) -> CatalogueRefreshReviewList:
    if status not in {"pending_review", "processing", "approved", "rejected", "all"}:
        raise UnprocessableEntityError(details={"status": "invalid"})
    offset = _decode_cursor(cursor)
    fetch_limit = min(max(limit, 1), 100)
    active_settings = settings or get_settings()
    with _authenticated_db(active_settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                select r.*, ci.file_name as source_file_name, ci.file_format as source_file_format
                from catalogue_refresh_review r
                join catalogue_imports ci
                  on ci.tenant_id = r.tenant_id and ci.id = r.source_import_id
                where r.tenant_id = %s
                  and (%s = 'all' or r.status = %s)
                order by r.created_at desc, r.id desc
                offset %s limit %s
                """,
                (member.tenant_id, status, status, offset, fetch_limit + 1),
            )
            rows = [dict(row) for row in cur.fetchall()]
    has_more = len(rows) > fetch_limit
    page_rows = rows[:fetch_limit]
    return CatalogueRefreshReviewList(
        items=[CatalogueRefreshReview.model_validate(row) for row in page_rows],
        next_cursor=_encode_cursor(offset + fetch_limit) if has_more else None,
    )


def approve_review(
    settings: Settings,
    *,
    member: CurrentMember,
    review_id: UUID,
    bearer_token: str,
) -> dict[str, Any]:
    review = _claim_review(settings, member=member, review_id=review_id)
    try:
        content = build_approval_csv(review.get("normalized_rows"))
        result = import_catalogue(
            settings,
            member=member,
            supplier_id=UUID(str(review["supplier_id"])),
            file_content=content,
            filename=f"catalogue-refresh-{review_id}.csv",
            file_format="csv",
            bearer_token=bearer_token,
        )
        if result.get("status") != "completed" or int(result.get("imported_rows") or 0) < 1:
            raise ConflictError(details={"reason": "catalogue_refresh_import_failed"})
        _reactivate_schedule_after_approval(
            settings,
            member=member,
            schedule_id=UUID(str(review["refresh_schedule_id"])),
            source_import_id=UUID(str(result["id"])),
        )
        _finish_review(settings, member=member, review_id=review_id, status="approved")
        _record_decision_audit(
            member=member,
            bearer_token=bearer_token,
            review_id=review_id,
            action="catalogue_refresh_review_approved",
            outcome="success",
        )
        return {
            "review_id": review_id,
            "status": "approved",
            "catalogue_import_id": result["id"],
            "supplier_id": result["supplier_id"],
            "imported_rows": result["imported_rows"],
            "error_rows": result["error_rows"],
        }
    except Exception:
        _reset_review(settings, member=member, review_id=review_id)
        raise


def reject_review(
    settings: Settings,
    *,
    member: CurrentMember,
    review_id: UUID,
    bearer_token: str,
) -> dict[str, Any]:
    _claim_review(settings, member=member, review_id=review_id)
    _finish_review(settings, member=member, review_id=review_id, status="rejected")
    _record_decision_audit(
        member=member,
        bearer_token=bearer_token,
        review_id=review_id,
        action="catalogue_refresh_review_rejected",
        outcome="success",
    )
    return {"review_id": review_id, "status": "rejected"}


def _record_decision_audit(
    *,
    member: CurrentMember,
    bearer_token: str,
    review_id: UUID,
    action: str,
    outcome: Literal["success", "refused"],
) -> None:
    get_audit_writer().record(
        AuditEventCreate(
            tenant_id=member.tenant_id,
            actor_membership_id=member.membership_id,
            actor_email=member.email,
            action=action,
            target={"catalogue_refresh_review_id": str(review_id)},
            outcome=outcome,
            trace_id=get_trace_id(),
        ),
        bearer_token=bearer_token,
    )


def build_approval_csv(rows: object) -> bytes:
    if not isinstance(rows, list) or not rows:
        raise UnprocessableEntityError(details={"reason": "catalogue_refresh_has_no_rows"})

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("product_name", "unit_price", "currency", "unit"))
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise UnprocessableEntityError(details={"reason": "invalid_preview_row", "row": index})
        product_name = _required_text(row, "product_name", index)
        amount = _required_decimal(row, "unit_price_amount", index)
        currency = _required_text(row, "unit_price_currency", index).upper()
        if amount <= 0 or len(currency) != 3 or not currency.isalpha():
            raise UnprocessableEntityError(details={"reason": "invalid_preview_row", "row": index})
        unit = row.get("base_unit") or "each"
        if not isinstance(unit, str) or not unit.strip():
            unit = "each"
        writer.writerow((product_name, amount, currency, unit.strip()))
    return output.getvalue().encode("utf-8")


def _claim_review(
    settings: Settings, *, member: CurrentMember, review_id: UUID
) -> dict[str, Any]:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                update catalogue_refresh_review
                set status = 'processing'
                where tenant_id = %s and id = %s and status = 'pending_review'
                returning *
                """,
                (member.tenant_id, review_id),
            )
            row = cur.fetchone()
        conn.commit()
    if row is not None:
        return dict(row)
    raise _review_state_error(settings, member=member, review_id=review_id)


def _review_state_error(
    settings: Settings, *, member: CurrentMember, review_id: UUID
) -> ConflictError:
    review = get_review(member=member, review_id=review_id, settings=settings)
    return ConflictError(
        details={
            "reason": "catalogue_refresh_review_not_pending",
            "status": review["status"],
        }
    )


def _finish_review(
    settings: Settings,
    *,
    member: CurrentMember,
    review_id: UUID,
    status: Literal["approved", "rejected"],
) -> None:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update catalogue_refresh_review
                set status = %s, reviewed_at = now(), reviewed_by = %s
                where tenant_id = %s and id = %s and status = 'processing'::text
                """,
                (status, member.membership_id, member.tenant_id, review_id),
            )
            if cur.rowcount != 1:
                raise ConflictError(details={"reason": "catalogue_refresh_review_not_processing"})
        conn.commit()


def _reactivate_schedule_after_approval(
    settings: Settings,
    *,
    member: CurrentMember,
    schedule_id: UUID,
    source_import_id: UUID,
) -> None:
    with _authenticated_db(settings, member) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                update offer_refresh_schedule
                set status = case when status = 'due' then 'active' else status end,
                    source_import_id = %s,
                    next_refresh_at = now() + make_interval(days => cadence_days),
                    updated_at = now()
                where tenant_id = %s
                  and id = %s
                  and status in ('active', 'due', 'paused')
                """,
                (source_import_id, member.tenant_id, schedule_id),
            )
        conn.commit()


def _reset_review(settings: Settings, *, member: CurrentMember, review_id: UUID) -> None:
    try:
        with _authenticated_db(settings, member) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    update catalogue_refresh_review
                    set status = 'pending_review', reviewed_at = null, reviewed_by = null
                    where tenant_id = %s and id = %s and status = 'processing'
                    """,
                    (member.tenant_id, review_id),
                )
            conn.commit()
    except Exception:
        # Preserve the original import failure; the review can be recovered by the operator.
        return


def _required_text(row: Mapping[str, object], key: str, index: int) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise UnprocessableEntityError(details={"reason": "invalid_preview_row", "row": index})
    return value.strip()


def _required_decimal(row: Mapping[str, object], key: str, index: int) -> Decimal:
    value = row.get(key)
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise UnprocessableEntityError(
            details={"reason": "invalid_preview_row", "row": index}
        ) from exc
    if not decimal.is_finite():
        raise UnprocessableEntityError(details={"reason": "invalid_preview_row", "row": index})
    return decimal


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        value = int(base64.urlsafe_b64decode(cursor.encode("ascii")))
    except (ValueError, UnicodeError) as exc:
        raise UnprocessableEntityError(details={"cursor": "invalid"}) from exc
    if value < 0:
        raise UnprocessableEntityError(details={"cursor": "invalid"})
    return value

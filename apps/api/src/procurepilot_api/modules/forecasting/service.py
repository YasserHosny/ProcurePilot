from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from postgrest.exceptions import APIError
from supabase import Client

from procurepilot_api.config import Settings, get_settings
from procurepilot_api.deps import CurrentMember
from procurepilot_api.errors import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    UnprocessableEntityError,
)
from procurepilot_api.modules.forecasting.calculator import (
    MODEL_VERSION,
    ForecastInput,
    ForecastResult,
    calculate_forecast,
)
from procurepilot_api.modules.forecasting.schemas import (
    PrepareRequestInput,
    PrepareRequestResponse,
    RecomputeResponse,
    ReorderProposal,
    ReorderProposalList,
)
from procurepilot_api.modules.members.service import authenticated_client
from procurepilot_api.modules.requests.schemas import (
    PurchaseRequestCreate,
    PurchaseRequestLineInput,
)
from procurepilot_api.modules.requests.service import RequestsService
from procurepilot_api.shared.audit import AuditEventCreate, get_audit_writer
from procurepilot_api.shared.logging import get_trace_id

SIGNAL_COLUMNS = (
    "id,external_item_name,stock_on_hand,sales_velocity_per_day,"
    "velocity_window_days_observed,velocity_computed_at"
)
MATCH_COLUMNS = "synced_product_signal_id,workspace_product_id"
PRODUCT_COLUMNS = "id,tenant_name"
FORECAST_COLUMNS = (
    "id,tenant_id,workspace_product_id,synced_product_signal_id,model_version,"
    "horizon_days,source_window_start,source_window_end,observed_history_days,"
    "expected_daily_demand,expected_demand,uncertainty_lower,uncertainty_upper,"
    "stock_on_hand,suggested_quantity,confidence,state,release_posture,valid_from,"
    "valid_until,created_at"
)
PROPOSAL_COLUMNS = (
    "id,tenant_id,demand_forecast_id,workspace_product_id,status,purchase_request_id,"
    "prepared_branch_id,created_at,prepared_at,dismissed_at"
)
PREPARE_NAMESPACE = UUID("8a80b8cc-84c3-5b6e-80e4-0fd3eeb2d6af")


class ForecastingService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def recompute(
        self, *, bearer_token: str, member: CurrentMember
    ) -> RecomputeResponse:
        client = authenticated_client(self._settings, bearer_token)
        signals = self._rows(client, "synced_product_signal", SIGNAL_COLUMNS)
        if not signals:
            return RecomputeResponse(generated_forecasts=0, open_proposals=0)

        signal_ids = [str(row["id"]) for row in signals]
        matches = self._rows(
            client,
            "pos_product_match",
            MATCH_COLUMNS,
            filters=("synced_product_signal_id", signal_ids),
        )
        match_by_signal = {str(row["synced_product_signal_id"]): row for row in matches}
        product_ids = list({str(row["workspace_product_id"]) for row in matches})
        products = self._rows(
            client,
            "workspace_product",
            PRODUCT_COLUMNS,
            filters=("id", product_ids),
        )
        product_names = {str(row["id"]): str(row["tenant_name"]) for row in products}

        generated = 0
        open_proposals = 0
        for signal in signals:
            signal_id = str(signal["id"])
            match = match_by_signal.get(signal_id)
            if match is None:
                continue
            product_id = str(match["workspace_product_id"])
            if product_id not in product_names:
                continue

            result, source_start, source_end, fingerprint = self._calculate(signal)
            forecast = self._get_or_insert_forecast(
                client,
                tenant_id=member.tenant_id,
                product_id=UUID(product_id),
                signal_id=UUID(signal_id),
                fingerprint=fingerprint,
                source_start=source_start,
                source_end=source_end,
                result=result,
            )
            if forecast[1]:
                generated += 1
                self._record(
                    bearer_token=bearer_token,
                    member=member,
                    action="forecasting.forecast_generated",
                    target={"demand_forecast_id": str(forecast[0]["id"])},
                )
            proposal, created = self._get_or_insert_proposal(
                client,
                tenant_id=member.tenant_id,
                forecast_row=forecast[0],
                product_id=UUID(product_id),
            )
            if created or proposal.get("status") == "open":
                open_proposals += 1

        return RecomputeResponse(
            generated_forecasts=generated,
            open_proposals=open_proposals,
        )

    def list_proposals(
        self,
        *,
        bearer_token: str,
        cursor: str | None = None,
        limit: int = 50,
    ) -> ReorderProposalList:
        client = authenticated_client(self._settings, bearer_token)
        offset = _decode_cursor(cursor)
        capped = min(max(limit, 1), 100)
        try:
            response = (
                client.table("reorder_proposal")
                .select(PROPOSAL_COLUMNS)
                .neq("status", "dismissed")
                .order("created_at", desc=True)
                .order("id")
                .range(0, 1000)
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        proposal_rows = _rows(response.data)
        latest_by_product: dict[str, dict[str, object]] = {}
        for row in proposal_rows:
            latest_by_product.setdefault(str(row["workspace_product_id"]), row)
        latest_rows = list(latest_by_product.values())
        visible = latest_rows[offset : offset + capped]
        if not visible:
            return ReorderProposalList(items=[], next_cursor=None)

        forecast_ids = [str(row["demand_forecast_id"]) for row in visible]
        forecasts = self._rows(
            client,
            "demand_forecast",
            FORECAST_COLUMNS,
            filters=("id", forecast_ids),
        )
        forecast_by_id = {str(row["id"]): row for row in forecasts}
        product_ids = list({str(row["workspace_product_id"]) for row in visible})
        products = self._rows(
            client,
            "workspace_product",
            PRODUCT_COLUMNS,
            filters=("id", product_ids),
        )
        product_names = {str(row["id"]): str(row["tenant_name"]) for row in products}
        items = [
            _proposal(
                proposal,
                forecast_by_id[str(proposal["demand_forecast_id"])],
                product_names[str(proposal["workspace_product_id"])],
            )
            for proposal in visible
            if str(proposal["demand_forecast_id"]) in forecast_by_id
            and str(proposal["workspace_product_id"]) in product_names
        ]
        next_cursor = (
            _encode_cursor(offset + capped)
            if len(latest_rows) > offset + capped
            else None
        )
        return ReorderProposalList(items=items, next_cursor=next_cursor)

    def prepare_request(
        self,
        *,
        bearer_token: str,
        member: CurrentMember,
        proposal_id: UUID,
        payload: PrepareRequestInput,
    ) -> PrepareRequestResponse:
        client = authenticated_client(self._settings, bearer_token)
        proposal = self._fetch_proposal(client, proposal_id)
        if proposal["status"] == "prepared":
            if str(proposal.get("prepared_branch_id")) != str(payload.branch_id):
                raise ConflictError(details={"reason": "proposal_prepared_for_other_branch"})
            forecast = self._fetch_forecast(client, UUID(str(proposal["demand_forecast_id"])))
            product_name = self._product_name(client, UUID(str(proposal["workspace_product_id"])))
            return PrepareRequestResponse(
                proposal=_proposal(proposal, forecast, product_name),
                purchase_request_id=UUID(str(proposal["purchase_request_id"])),
            )
        if proposal["status"] != "open":
            raise ConflictError(details={"reason": "proposal_not_open"})

        forecast = self._fetch_forecast(client, UUID(str(proposal["demand_forecast_id"])))
        suggested = forecast.get("suggested_quantity")
        if suggested is None or forecast.get("state") == "insufficient_data":
            raise UnprocessableEntityError(details={"reason": "forecast_insufficient_data"})

        idempotency_key = uuid5(
            PREPARE_NAMESPACE,
            f"{member.tenant_id}:{proposal_id}:{payload.branch_id}",
        )
        request_payload = PurchaseRequestCreate(
            branch_id=payload.branch_id,
            cost_centre_id=payload.cost_centre_id,
            required_by_date=payload.required_by_date,
            lines=[
                PurchaseRequestLineInput(
                    workspace_product_id=UUID(str(proposal["workspace_product_id"])),
                    quantity=_decimal_string(suggested),
                )
            ],
        )
        purchase_request, _ = RequestsService(self._settings).create_request(
            bearer_token=bearer_token,
            member=member,
            payload=request_payload,
            idempotency_key=idempotency_key,
        )
        try:
            updated = (
                client.table("reorder_proposal")
                .update(
                    {
                        "status": "prepared",
                        "purchase_request_id": str(purchase_request.id),
                        "prepared_branch_id": str(payload.branch_id),
                        "prepared_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("id", str(proposal_id))
                .eq("status", "open")
                .execute()
            )
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        updated_rows = _rows(updated.data)
        if not updated_rows:
            current = self._fetch_proposal(client, proposal_id)
            if current["status"] == "prepared" and str(current.get("prepared_branch_id")) == str(
                payload.branch_id
            ):
                proposal = current
            else:
                raise ConflictError(details={"reason": "proposal_changed"})
        else:
            proposal = updated_rows[0]

        self._record(
            bearer_token=bearer_token,
            member=member,
            action="forecasting.reorder_proposal_prepared",
            target={
                "reorder_proposal_id": str(proposal_id),
                "purchase_request_id": str(purchase_request.id),
            },
        )
        product_name = self._product_name(client, UUID(str(proposal["workspace_product_id"])))
        return PrepareRequestResponse(
            proposal=_proposal(proposal, forecast, product_name),
            purchase_request_id=purchase_request.id,
        )

    def _calculate(
        self, signal: dict[str, object]
    ) -> tuple[ForecastResult, date, date, str]:
        computed_at = _datetime(signal.get("velocity_computed_at")) or datetime.now(UTC)
        observed = _int_or_none(signal.get("velocity_window_days_observed"))
        source_end = computed_at.date()
        source_start = source_end - timedelta(days=max((observed or 1) - 1, 0))
        sales_velocity = _decimal_or_none(signal.get("sales_velocity_per_day"))
        stock_on_hand = _decimal_or_none(signal.get("stock_on_hand"))
        result = calculate_forecast(
            ForecastInput(
                sales_velocity_per_day=sales_velocity,
                stock_on_hand=stock_on_hand,
                observed_history_days=observed,
            )
        )
        fingerprint_payload = {
            "signal_id": str(signal["id"]),
            "model_version": MODEL_VERSION,
            "horizon_days": 14,
            "sales_velocity_per_day": str(sales_velocity) if sales_velocity is not None else None,
            "stock_on_hand": str(stock_on_hand) if stock_on_hand is not None else None,
            "observed_history_days": observed,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return result, source_start, source_end, fingerprint

    def _get_or_insert_forecast(
        self,
        client: Client,
        *,
        tenant_id: UUID,
        product_id: UUID,
        signal_id: UUID,
        fingerprint: str,
        source_start: date,
        source_end: date,
        result: ForecastResult,
    ) -> tuple[dict[str, object], bool]:
        existing = self._rows(
            client,
            "demand_forecast",
            FORECAST_COLUMNS,
            filters=("source_fingerprint", [fingerprint]),
        )
        if existing:
            return existing[0], False
        now = datetime.now(UTC)
        payload = {
            "tenant_id": str(tenant_id),
            "workspace_product_id": str(product_id),
            "synced_product_signal_id": str(signal_id),
            "source_fingerprint": fingerprint,
            "model_version": result.model_version,
            "horizon_days": 14,
            "source_window_start": source_start.isoformat(),
            "source_window_end": source_end.isoformat(),
            "observed_history_days": result.observed_history_days,
            "expected_daily_demand": _db_decimal(result.expected_daily_demand),
            "expected_demand": _db_decimal(result.expected_demand),
            "uncertainty_lower": _db_decimal(result.uncertainty_lower),
            "uncertainty_upper": _db_decimal(result.uncertainty_upper),
            "stock_on_hand": _db_decimal(result.stock_on_hand),
            "suggested_quantity": _db_decimal(result.suggested_quantity),
            "confidence": result.confidence,
            "state": result.state,
            "release_posture": result.release_posture,
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=14)).isoformat(),
        }
        try:
            response = client.table("demand_forecast").insert(payload).execute()
        except APIError as exc:
            if _api_error_code(exc) == "23505":
                existing = self._rows(
                    client,
                    "demand_forecast",
                    FORECAST_COLUMNS,
                    filters=("source_fingerprint", [fingerprint]),
                )
                if existing:
                    return existing[0], False
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        if not rows:
            raise ServiceUnavailableError(details={"dependency": "database"})
        return rows[0], True

    def _get_or_insert_proposal(
        self,
        client: Client,
        *,
        tenant_id: UUID,
        forecast_row: dict[str, object],
        product_id: UUID,
    ) -> tuple[dict[str, object], bool]:
        existing = self._rows(
            client,
            "reorder_proposal",
            PROPOSAL_COLUMNS,
            filters=("demand_forecast_id", [str(forecast_row["id"])]),
        )
        if existing:
            return existing[0], False
        try:
            response = (
                client.table("reorder_proposal")
                .insert(
                    {
                        "tenant_id": str(tenant_id),
                        "demand_forecast_id": str(forecast_row["id"]),
                        "workspace_product_id": str(product_id),
                        "status": "open",
                    }
                )
                .execute()
            )
        except APIError as exc:
            if _api_error_code(exc) == "23505":
                existing = self._rows(
                    client,
                    "reorder_proposal",
                    PROPOSAL_COLUMNS,
                    filters=("demand_forecast_id", [str(forecast_row["id"])]),
                )
                if existing:
                    return existing[0], False
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc
        rows = _rows(response.data)
        if not rows:
            raise ServiceUnavailableError(details={"dependency": "database"})
        return rows[0], True

    def _fetch_proposal(self, client: Client, proposal_id: UUID) -> dict[str, object]:
        rows = self._rows(
            client,
            "reorder_proposal",
            PROPOSAL_COLUMNS,
            filters=("id", [str(proposal_id)]),
        )
        if not rows:
            raise NotFoundError(details={"resource": "reorder_proposal"})
        return rows[0]

    def _fetch_forecast(self, client: Client, forecast_id: UUID) -> dict[str, object]:
        rows = self._rows(
            client,
            "demand_forecast",
            FORECAST_COLUMNS,
            filters=("id", [str(forecast_id)]),
        )
        if not rows:
            raise NotFoundError(details={"resource": "demand_forecast"})
        return rows[0]

    def _product_name(self, client: Client, product_id: UUID) -> str:
        rows = self._rows(
            client,
            "workspace_product",
            PRODUCT_COLUMNS,
            filters=("id", [str(product_id)]),
        )
        if not rows:
            raise NotFoundError(details={"resource": "workspace_product"})
        return str(rows[0]["tenant_name"])

    @staticmethod
    def _rows(
        client: Client,
        table: str,
        columns: str,
        filters: tuple[str, list[str]] | None = None,
    ) -> list[dict[str, object]]:
        try:
            query = client.table(table).select(columns)
            if filters is not None:
                column, values = filters
                if values:
                    query = query.in_(column, values)
                else:
                    return []
            return _rows(query.execute().data)
        except APIError as exc:
            raise ServiceUnavailableError(details={"dependency": "database"}) from exc

    @staticmethod
    def _record(
        *,
        bearer_token: str,
        member: CurrentMember,
        action: str,
        target: dict[str, object],
    ) -> None:
        get_audit_writer().record(
            AuditEventCreate(
                tenant_id=member.tenant_id,
                actor_membership_id=member.membership_id,
                actor_email=member.email,
                action=action,
                target=target,
                outcome="success",
                trace_id=get_trace_id(),
            ),
            bearer_token=bearer_token,
        )


def get_forecasting_service() -> ForecastingService:
    return ForecastingService()


def _proposal(
    proposal: dict[str, object], forecast: dict[str, object], product_name: str
) -> ReorderProposal:
    return ReorderProposal(
        id=UUID(str(proposal["id"])),
        demand_forecast_id=UUID(str(proposal["demand_forecast_id"])),
        workspace_product_id=UUID(str(proposal["workspace_product_id"])),
        product_name=product_name,
        status=str(proposal["status"]),
        horizon_days=int(forecast["horizon_days"]),
        source_window_start=forecast["source_window_start"],
        source_window_end=forecast["source_window_end"],
        observed_history_days=_int_or_none(forecast.get("observed_history_days")),
        expected_daily_demand=_decimal_string(forecast.get("expected_daily_demand")),
        expected_demand=_decimal_string(forecast.get("expected_demand")),
        uncertainty_lower=_decimal_string(forecast.get("uncertainty_lower")),
        uncertainty_upper=_decimal_string(forecast.get("uncertainty_upper")),
        stock_on_hand=_decimal_string(forecast.get("stock_on_hand")),
        suggested_quantity=_decimal_string(forecast.get("suggested_quantity")),
        confidence=str(forecast["confidence"]),
        state=str(forecast["state"]),
        release_posture="g3_unmet",
        valid_from=forecast["valid_from"],
        valid_until=forecast["valid_until"],
        purchase_request_id=(
            UUID(str(proposal["purchase_request_id"]))
            if proposal.get("purchase_request_id")
            else None
        ),
        prepared_branch_id=(
            UUID(str(proposal["prepared_branch_id"]))
            if proposal.get("prepared_branch_id")
            else None
        ),
        created_at=proposal["created_at"],
    )


def _rows(data: object) -> list[dict[str, object]]:
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _db_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _decimal_string(value: object) -> str | None:
    return str(value) if value is not None else None


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _int_or_none(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _api_error_code(exc: APIError) -> str | None:
    code = getattr(exc, "code", None)
    return str(code) if code else None


def _encode_cursor(offset: int) -> str:
    return str(offset)


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return max(0, int(cursor))
    except ValueError as exc:
        raise UnprocessableEntityError(details={"field": "cursor"}) from exc

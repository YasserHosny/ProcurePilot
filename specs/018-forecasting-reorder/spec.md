# Feature Specification: R4.0 Forecasting and Reorder Proposals

**Feature Branch**: `018-forecasting-reorder`
**Created**: 2026-09-20
**Status**: Approved exception implementation
**Input**: Product-owner direction to proceed with R4 while keeping G3 unmet.

## Release posture

G3 remains unmet. This feature may display forecasts from connected POS signals, but every
forecast is marked `g3_unmet` and history shorter than 180 days is marked provisional. Synthetic
fixtures are test-only and do not update G3 evidence.

## User stories

### US1 - Review a demand-backed forecast (P1)

As a buyer, I can see expected demand, current stock, an uncertainty range, evidence age,
confidence, and validity before deciding whether to replenish a product.

### US2 - Prepare a draft request (P1)

As a buyer, I can turn a reviewed reorder proposal into a draft purchase request for a selected
branch. The action remains human initiated and follows the existing approval workflow.

### US3 - Honest cold-start behavior (P1)

As a buyer, I can distinguish no connection, unmatched product, missing history, provisional
forecast, and valid forecast. The system never presents a point prediction without its interval
and evidence window.

## Functional requirements

- **FR-001**: The system MUST calculate forecasts deterministically from matched POS signal data,
  a pinned model version, a configured horizon, and a configured safety factor.
- **FR-002**: Every forecast MUST include expected demand, lower and upper uncertainty bounds,
  confidence, validity start and end, source signal ID, source window, observed history days,
  model version, and release posture.
- **FR-003**: The system MUST return an `insufficient_data` state with no suggested quantity when
  product matching, velocity, or stock evidence is absent.
- **FR-004**: Forecasts with fewer than 180 observed history days MUST be marked provisional and
  MUST expose the observed history days.
- **FR-005**: Suggested quantity MUST never be negative and MUST be expressed in the product's
  normalised base unit.
- **FR-006**: The list endpoint MUST be tenant-scoped, cursor-paginated, and limited to the
  latest proposal per matched workspace product.
- **FR-007**: Preparing a request MUST require an authenticated owner or buyer and a branch,
  MUST create only a `draft` purchase request, and MUST never create or mutate a purchase order.
- **FR-008**: Preparing the same proposal for the same branch more than once MUST return the
  original draft request and MUST not create a duplicate.
- **FR-009**: New tenant-scoped tables MUST have forced RLS and policies with both `USING` and
  `WITH CHECK`; cross-tenant rows MUST be invisible.
- **FR-010**: Every forecast generation and request preparation MUST append an audit event.
- **FR-011**: All user-facing text MUST come from the English and Arabic i18n catalogues.
- **FR-012**: G3 evidence MUST remain unchanged and R4 responses MUST expose `g3_unmet`.

## Data model

### `demand_forecast`

Tenant-scoped immutable snapshot with: `id`, `tenant_id`, `workspace_product_id`, optional
`synced_product_signal_id`, `model_version`, `horizon_days`, `source_window_start`,
`source_window_end`, `observed_history_days`, `expected_daily_demand`, `expected_demand`,
`uncertainty_lower`, `uncertainty_upper`, `stock_on_hand`, `suggested_quantity`, `confidence`,
`state`, `release_posture`, `valid_from`, `valid_until`, and `created_at`.

### `reorder_proposal`

Tenant-scoped workflow row with: `id`, `tenant_id`, `demand_forecast_id`, `workspace_product_id`,
`status` (`open`, `prepared`, `dismissed`, `expired`), optional `purchase_request_id`,
`prepared_branch_id`, `created_at`, `prepared_at`, and `dismissed_at`.

Both tables have composite tenant-pinned foreign keys, tenant indexes, and forced RLS. Forecast
rows are append-only. Proposal decision changes use explicit transition policies and audit events.

## Success criteria

- The deterministic unit suite covers all forecast states and passes without external services.
- An authenticated tenant can list only its own proposals.
- One preparation creates exactly one draft request and zero purchase orders.
- A second identical preparation returns the same draft request.
- Angular tests cover `g3_unmet`, provisional, insufficient-data, and prepared states in English
  and Arabic.
- API and web production verification remain green; G3 evidence still reports unmet.


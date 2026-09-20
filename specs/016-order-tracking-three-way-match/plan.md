# Implementation Plan: Order Tracking and Three-Way Match

**Branch**: `016-order-tracking-three-way-match` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

## Summary

Add internal purchase-order evidence, supplier confirmations, delivery receipts, a normalized
three-way reconciliation engine, and a read-only Xero connector while preserving QuickBooks and
all existing purchasing workflows.

## Architecture

Extend the existing accounting module and connector protocol rather than creating a new service.
Internal order/receipt workflows live in a focused order-tracking module. The reconciliation
service consumes normalized order, receipt, and bill projections. A dedicated sync worker reuses
the advisory-lock and encrypted-token patterns from R3.1.

## Files and Boundaries

- `apps/api/src/procurepilot_api/modules/orders/`: order, confirmation, and receipt schemas,
  services, and routers.
- `apps/api/src/procurepilot_api/modules/accounting/connector.py`: add normalized read-only order
  and bill capability types.
- `apps/api/src/procurepilot_api/modules/accounting/xero_client.py`: Xero OAuth and read-only API
  normalization; no provider write methods.
- `apps/api/src/procurepilot_api/modules/accounting/three_way_match_service.py`: deterministic
  candidate selection, tolerance comparison, and discrepancy upsert/reopen behavior.
- `apps/api/src/procurepilot_api/workers/accounting_sync_worker.py`: include provider capability
  sync without changing the existing claim and advisory-lock behavior.
- `supabase/migrations/`: forward-only order, receipt, match, and discrepancy extensions with RLS.
- `apps/web/src/app/features/orders/`: order detail, confirmation, receipt, and evidence timeline.
- `apps/web/src/app/features/accounting/`: Xero connection and three-way discrepancy presentation.
- `packages/i18n/{en,ar}.json`: all new UI messages.
- `docs/architecture/api-specification.md`, `docs/architecture/data-dictionary.md`,
  `docs/quality/test-strategy.md`, and `docs/user/user-documentation.md`: delivered surfaces.

## Execution Tasks

### Phase 1: Data and provider foundation

1. Add the migration for `purchase_order` and `purchase_order_line` with tenant-pinned supplier,
   product, and member references, forced RLS, lifecycle checks, and explicit currency columns.
2. Add supplier-confirmation and delivery-receipt migrations with immutable source references,
   cumulative quantity constraints, and forced RLS.
3. Add `three_way_match` and extend reconciliation discrepancy types/evidence with unique source
   relationships and re-open-safe timestamps.
4. Add Xero settings, encrypted token fields, provider enum support, and connector protocol types.
5. Write failing unit tests for Xero OAuth/token parsing and normalized bill/order parsing.
6. Implement `xero_client.py` with OAuth state-compatible authorization, token exchange/refresh,
   provider pagination, and read-only bill/order retrieval.
7. Run the Xero unit suite and connector static write-method check.

### Phase 2: Internal order and receipt workflow

1. Write failing API tests for order creation, line validation, confirmation, partial receipt, and
   multiple-receipt accumulation.
2. Implement Pydantic schemas and order service methods with owner/buyer mutation authorization.
3. Implement order, confirmation, and receipt routers with idempotency keys and not-found behavior.
4. Add audit events for order submitted, confirmation recorded, and receipt recorded.
5. Add frontend order detail/evidence timeline with explicit pending/unavailable states.
6. Add English/Arabic translations and RTL/a11y component tests.

### Phase 3: Three-way reconciliation

1. Write pure failing tests for exact match, currency mismatch, quantity variance, price variance,
   missing receipt, invoice-without-order, and ambiguous candidates.
2. Implement provider-reference-first candidate selection and exactly-one-candidate matching.
3. Implement versioned tolerance comparison with explicit ordered/confirmed/received/invoiced
   quantities and amounts.
4. Implement idempotent discrepancy upsert and re-open-on-source-change logic.
5. Extend accounting bills and discrepancy APIs with three-way evidence projections.
6. Add UI actions for review and resolution without allowing external provider mutation.

### Phase 4: Verification and release hardening

1. Add integration tests for RLS visibility/write pairs across every new table.
2. Add sync worker tests for advisory-lock exclusivity, retries, stale data, and reauthorization.
3. Add E2E coverage for order -> confirmation -> receipt -> invoice -> discrepancy resolution.
4. Add English/Arabic axe-core and keyboard-only coverage for order and reconciliation screens.
5. Run QuickBooks regression tests, all order/accounting unit tests, and API linting.
6. Record the R3.3 security review covering OAuth state, encrypted tokens, read-only provider calls,
   rate limits, audit events, and tenant isolation.
7. Update roadmap evidence and define G3 measurements for freshness and integration-sourced data.

## Verification Commands

```bash
uv run --project apps/api pytest apps/api/tests/unit/test_xero_client.py apps/api/tests/unit/test_three_way_match_service.py -q
uv run --project apps/api pytest apps/api/tests/integration/test_order_tracking.py apps/api/tests/integration/test_three_way_match.py -q
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/orders apps/api/src/procurepilot_api/modules/accounting
pnpm --dir apps/web exec ng test --watch=false --browsers=ChromeHeadless --include='src/app/features/orders/**/*.spec.ts'
pnpm test:e2e -- --grep 'three-way|order tracking'
```

## Constitutional Checks

- No autonomous purchasing or provider write-back.
- Every money field has an explicit currency and every derived comparison stores its ruleset basis.
- Every tenant table ships with forced RLS and both policy predicates.
- Cross-tenant reads return not found.
- All visible strings are localized in English and Arabic.
- Existing R3.1 and R3.2 functionality remains green before release.

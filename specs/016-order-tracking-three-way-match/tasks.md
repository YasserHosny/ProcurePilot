---
description: "Focused task list for User Story 4: Create draft purchase order from approved request"
---

# Tasks: Order Tracking - User Story 4

**Input**: Design documents from `/specs/016-order-tracking-three-way-match/`
**Prerequisites**:
- Existing order, request, approval, audit, and RLS foundations are in place.
- **Scope Note**: This focused task list covers *only* User Story 4. Other stories (US1, US2, US3) detailed in `plan.md` are outside this scope.

**Organization**: Tasks are structured to prioritize database and API invariants before user interface implementation, ensuring core rules are established first.

## Phase 1: Tests for User Story 4 (Future Execution)

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T001 [US4] Write failing API integration tests in `apps/api/tests/integration/test_order_tracking.py` sequentially for:
  - Draft order creation from request with explicit price requirement and line validation.
  - Idempotent draft edit mutations.
  - Transactional allocation limits (concurrency) at request scope.
  - Cancellation with unreceived quantity release (leaving received quantity consumed).
  - Cross-tenant RLS visibility and isolation (ensuring references resolve as not found).

## Phase 2: Database & Linkage

- [ ] T002 [US4] Create forward-only DB migration in `supabase/migrations/` extending `purchase_order` with `source_request_id` and `purchase_order_line` with `source_request_line_id`. Ensure tenant-pinned composite foreign keys, forced RLS with `USING` and `WITH CHECK` policies, and preserve backwards compatibility.

## Phase 3: API Allocation Invariants

- [ ] T003 [US4] Update schemas in `apps/api/src/procurepilot_api/modules/orders/schemas.py` to support `source_request_id` and `source_request_line_id` linkages, enforcing actual price, currency, and tax inputs. Add an edit-draft schema.
- [ ] T004 [US4] Expose a defined interface in `apps/api/src/procurepilot_api/modules/requests/service.py` to validate a recorded human approval decision (do not use legacy `ordered` status as sole proof).
- [ ] T005 [US4] Implement draft order creation logic in `apps/api/src/procurepilot_api/modules/orders/service.py`. Enforce the human approval decision via the new requests interface. Ensure one source request per PO and support splitting a request across multiple POs without exceeding allocated quantities.
- [ ] T006 [US4] Implement an idempotent draft-edit service method in `apps/api/src/procurepilot_api/modules/orders/service.py` allowing modification of a draft purchase order.
- [ ] T007 [US4] Implement transactional allocation limits in `apps/api/src/procurepilot_api/modules/orders/service.py` using advisory locks at the request scope to serialize every linked draft mutation (create/edit/cancel) atomically.
- [ ] T008 [US4] Implement internal cancellation logic in `apps/api/src/procurepilot_api/modules/orders/service.py`. Ensure cancellation retains immutable received evidence, releases unreceived quantity, and explicitly prevents external provider calls.
- [ ] T009 [US4] Implement a tenant-scoped allocation projection endpoint in `apps/api/src/procurepilot_api/modules/orders/router.py` that exposes allocated and remaining quantities per source request line, including the cancelled-order received-quantity rule.
- [ ] T010 [US4] Implement router endpoints in `apps/api/src/procurepilot_api/modules/orders/router.py` for draft creation, draft edit, and cancellation. Enforce owner/buyer role RBAC, `Idempotency-Key` headers, and record audit events. Handle cross-tenant references as not found. Note: submit changes internal state only; no external provider call is made.

## Phase 4: User Interface & Localization

- [ ] T011 [US4] Add a frontend entry point in `apps/web/src/app/features/requests/request-list/request-list.component.ts` (and corresponding HTML) to initiate draft PO creation from an approved request.
- [ ] T012 [US4] Add/update UI components in `apps/web/src/app/features/orders/order-create/order-create.component.ts` to surface request estimates as reference only and mandate buyer-entered actual prices, currencies, and tax. Integrate with the new remaining-quantity read contract to display accurate allocations.
- [ ] T013 [US4] Add an order detail edit/cancel affordance in `apps/web/src/app/features/orders/order-detail/order-detail.component.ts` (and HTML) for modifying drafts or cancelling orders, displaying computed remaining quantities based on non-cancelled PO allocations.
- [ ] T014 [US4] Add English and Arabic localization keys in `packages/i18n/en.json` and `packages/i18n/ar.json` for the entry points, draft edit/creation, split allocations, remaining quantities, and cancellation flows.
- [ ] T015 [US4] Verify RTL layout integrity and add an E2E path (via Playwright) testing the order detail edit/cancel flow and ensuring zero WCAG 2.1 AA violations using `axe-core`.

## Phase 5: Documentation & Verification

- [ ] T016 [US4] Update `docs/architecture/api-specification.md` and `docs/architecture/data-dictionary.md` to document the new `source_request_id` relationships, the draft edit API, and draft/cancel state transitions.

## Verification Commands

```bash
uv run --project apps/api pytest apps/api/tests/integration/test_order_tracking.py -q
pnpm --dir apps/web exec ng test --watch=false --browsers=ChromeHeadless --include='src/app/features/orders/**/*.spec.ts'
uv run --project apps/api ruff check apps/api/src/procurepilot_api/modules/orders
pnpm test:e2e
pnpm test:a11y
pnpm test:isolation
```

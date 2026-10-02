# Feature Specification: Order Tracking and Three-Way Match

**Feature Branch**: `016-order-tracking-three-way-match`  
**Created**: 2026-09-19  
**Status**: Planned  
**Roadmap Release**: R3.3, Phase 3 Connected Operations  
**Provider**: Xero as the second accounting provider after QuickBooks Online

## Summary

Extend reconciliation from accounting bills to the full purchasing evidence chain:

`Purchase Order -> Supplier Confirmation -> Delivery Receipt -> Accounting Bill`

ProcurePilot remains read-only against external providers. Humans authorize purchases and resolve
exceptions; the system never sends, changes, pays, or cancels an order through an integration.

## Clarifications

- Xero is the second accounting provider for R3.3.
- QuickBooks support remains available and must not regress.
- Supplier confirmations and delivery receipts are entered or imported by authorized ProcurePilot
  users in this release; a supplier portal is out of scope.
- A provider capability gap is represented as unavailable evidence, never as a successful delivery,
  zero quantity, or inferred match.
- All quantity and money tolerances are explicit, versioned, and visible in discrepancy evidence.

## User Stories and Acceptance Scenarios

### User Story 1: Track a purchase order lifecycle (Priority: P1)

A buyer records or creates a purchase order and can see confirmation, delivery, and invoice state
against the same order.

**Independent Test**: Create an order with two lines, record a supplier confirmation, record a
partial delivery, and verify the order header and line state show the correct lifecycle without any
external provider connection.

**Acceptance Scenarios**

1. Given a submitted purchase order, when a buyer records a supplier confirmation, then the order
   shows confirmed quantities and expected delivery dates per line.
2. Given a confirmed order, when a buyer records a partial delivery, then received quantities are
   cumulative, the order is `partially_received`, and the remaining quantity is visible.
3. Given multiple delivery receipts, when a later receipt is recorded, then previous receipts are
   preserved and the line's received total is recomputed deterministically.
4. Given an order with no confirmation or receipt, then the absence is shown as pending evidence,
   never as zero delivered.

### User Story 2: Reconcile orders, receipts, and invoices (Priority: P1)

A buyer sees whether the supplier invoice agrees with what was ordered and received.

**Independent Test**: Seed an order, receipt, and Xero/QuickBooks bill with matching and mismatched
lines, run reconciliation, and verify exact match, partial delivery, over-billing, and unmatched
invoice outcomes.

**Acceptance Scenarios**

1. Given one unambiguous order, receipt, and bill with matching supplier, currency, quantities,
   and prices within configured tolerances, then the three-way match is `matched`.
2. Given an invoice quantity above the received quantity, then an `over_billed_quantity`
   discrepancy is created with ordered, received, and invoiced values side by side.
3. Given an invoice unit price above the order price beyond tolerance, then an `over_billed_price`
   discrepancy is created with both currencies and amounts explicit.
4. Given an invoice with no qualifying order, then it remains visible as `invoice_without_order`;
   it is never silently dropped or force-matched.
5. Given two equally qualifying orders, then the invoice remains unmatched for human review.
6. Given a source record changes after a discrepancy is resolved, then the discrepancy is reopened
   and recomputed rather than duplicated.

### User Story 3: Use Xero without changing purchasing behavior (Priority: P2)

An owner connects Xero, sees its status, and can synchronize read-only accounting evidence. If Xero
is disconnected or unavailable, existing purchasing workflows continue with manual input.

**Independent Test**: Complete the stub-backed Xero connection lifecycle, synchronize a bill, then
disconnect the provider and verify historical evidence remains visible and purchase workflows still
work.

**Acceptance Scenarios**

1. Given no Xero connection, when an owner opens accounting settings, then QuickBooks and Xero
   connection states are independently visible.
2. Given a connected Xero account, when a sync runs, then normalized bills retain explicit
   provider, supplier, currency, date, and source identifiers.
3. Given provider OAuth failure, then the connection becomes `needs_reauth` and prior evidence is
   retained.
4. Given an integration is disconnected, then no purchasing screen blocks, loses drafts, or
   changes manual quantity entry behavior.

### User Story 4: Create draft purchase order from approved request (Priority: P1)

A buyer creates a draft purchase order based on a previously approved purchase request, preparing
the order for buyer review rather than establishing a commitment or purchase. The legacy request
service represents a human-approved request as status `ordered` (legacy R2.3 behavior); this legacy
status is not evidence that a `purchase_order` exists. Draft PO creation preserves the existing
request state and approval decision.

**Independent Test**: Create an approved purchase request, generate a draft order from it by
selecting a supplier and specifying actual prices, then verify the draft order traces to the request
and the request's approval status remains unchanged.

**Acceptance Scenarios**

1. Given an approved purchase request, when an authorized buyer initiates order creation, then they MUST select a supplier and manually provide/confirm actual unit prices, currency, tax, dates, and order quantities.
2. Given a purchase request with estimated prices, when creating a draft order, then the estimates
   MUST NEVER silently become the purchase order actual prices. Request estimates can be shown as
   reference only; actual unit price, currency, and tax remain buyer-entered and confirmed.
3. Given a created draft purchase order, then the action does NOT submit, send, authorize, or
   execute a purchase, and the underlying request's approval decision/status remains unchanged.
   The request's recorded approval step is the evidence of human approval; its legacy `ordered`
   status is not sufficient proof of approval by itself and does not prove a `purchase_order`
   exists.
4. Given a draft purchase order, submit is a separate explicit human operation. It changes internal
   status only; no external provider send/write is performed.
5. Given a purchase order line, it MUST preserve explicit traceability back to the originating purchase request line. One purchase order may reference only one purchase request; one approved request may be split across multiple supplier purchase orders.
6. Given a request line, it may be allocated across multiple PO lines/orders. Creating or editing a linked draft MUST NOT allocate more than the approved requested quantity.
7. Given an order, all non-cancelled POs (draft, submitted, confirmed, received) reserve their full ordered quantity. The remaining quantity MUST be computed from these allocations.
8. Given a cancelled PO, its immutable received quantity remains consumed, while its unreceived quantity is released. A cancel operation is an explicit internal human action and MUST NOT call a provider or delete evidence.
9. Given concurrent create, edit, or cancel operations, they MUST serialize atomically at the
   request scope (transaction/locking or equivalent) so no race condition can exceed the approved
   quantity, and mutations remain idempotent.
10. Given a request whose status is `ordered` but which has no recorded human approval decision,
    when a buyer attempts to create a draft purchase order, then creation is rejected.

## Functional Requirements

- **FR-001**: The system MUST store purchase orders and order lines with tenant-scoped RLS and
  explicit currency for every monetary value.
- **FR-002**: The system MUST support supplier confirmations and partial/multiple delivery receipts
  without overwriting prior receipt evidence.
- **FR-003**: The system MUST extend the provider-agnostic accounting connector with a read-only
  Xero implementation; no external create, update, delete, send, payment, or cancellation method
  may exist.
- **FR-004**: The system MUST normalize provider identifiers and statuses at the connector boundary.
- **FR-005**: The system MUST match bills to orders using provider references first, then supplier,
  currency, document references, product identity, and bounded date evidence.
- **FR-006**: Automatic matching MUST require exactly one qualifying candidate. Ambiguity MUST remain
  unresolved for human review.
- **FR-007**: The system MUST compare ordered, confirmed, received, and invoiced quantities and
  prices using a versioned tolerance ruleset.
- **FR-008**: Currency mismatches MUST be surfaced explicitly and MUST NOT be silently converted or
  accepted as a match.
- **FR-009**: The system MUST create and update discrepancy evidence for missing confirmation,
  missing receipt, quantity variance, price variance, and invoices without orders.
- **FR-010**: Resolved discrepancies MUST reopen when an underlying source record changes later.
- **FR-011**: Syncs MUST use advisory-lock concurrency, retry-safe upserts, encrypted OAuth tokens,
  and `needs_reauth` transitions on provider authentication failure.
- **FR-012**: Connect, disconnect, sync, order, confirmation, receipt, match, and resolution
  actions MUST be auditable.
- **FR-013**: Cross-tenant reads MUST resolve as not found, and all tenant-scoped records MUST be
  protected by database RLS with both `USING` and `WITH CHECK` policies.
- **FR-014**: The release MUST preserve purchasing operation when integrations are absent,
  disconnected, stale, or temporarily unavailable.
- **FR-015**: All user-facing strings MUST come from `packages/i18n` in English and Arabic, and new
  screens MUST support RTL and WCAG 2.1 AA.
- **FR-016**: The system MUST restrict draft order creation to authorized buyer/owner roles and require a recorded human approval decision for the source request; the request's legacy `ordered` status alone MUST NOT be treated as proof of approval or of an existing purchase order. The system MUST audit draft creation and preserve traceability to the source request and lines. References MUST be tenant-pinned and enforced by the database; cross-tenant references MUST resolve as not found.
- **FR-017**: The system MUST support splitting one approved purchase request across multiple supplier purchase orders. One purchase order MUST reference at most one purchase request.
- **FR-018**: The system MUST reserve the full ordered quantity for all non-cancelled POs (draft, submitted, confirmed, received) and compute remaining quantities from these allocations.
- **FR-019**: The system MUST serialize concurrent create, edit, and cancel operations atomically at the purchase request scope to prevent over-allocation races. Mutations MUST remain idempotent.
- **FR-020**: The system MUST NOT delete evidence on PO cancellation. The cancel operation MUST leave immutable received quantity consumed, release unreceived quantity, and MUST NOT call an external provider.

## Data Entities

- `purchase_order`: internal order header, supplier, lifecycle status, dates, currency, totals, and `source_request_id` to link to at most one purchase request.
- `purchase_order_line`: product/description, ordered quantity, unit price, currency, tax, line
  total, and `source_request_line_id` for request traceability.
- `supplier_confirmation`: supplier reference, confirmed dates, and confirmation metadata.
- `supplier_confirmation_line`: confirmed quantity and price per order line.
- `delivery_receipt`: receipt reference, receipt date, receiving member, and source metadata.
- `delivery_receipt_line`: received quantity per purchase-order line.
- `three_way_match`: normalized order/receipt/bill relationship, comparison result, tolerance
  ruleset version, and source references.
- `reconciliation_discrepancy`: existing R3.1 entity extended with R3.3 discrepancy types and
  evidence fields; re-evaluation is idempotent.

Every new tenant-scoped table has `tenant_id`, forced RLS, composite tenant-pinned foreign keys
where available, and append-only evidence fields where mutation would destroy provenance.

## Success Criteria

- A buyer can inspect an order's full evidence chain without leaving the order-tracking surface.
- Matching is deterministic and repeatable for a pinned tolerance-ruleset version.
- Ambiguous and unsupported evidence is visibly unresolved rather than silently accepted.
- Xero and QuickBooks syncs remain read-only and tenant isolated.
- Disconnecting either provider preserves historical records and leaves purchasing usable.
- English and Arabic UI tests pass axe-core with no WCAG 2.1 AA violations.
- R3.3 integration tests demonstrate no cross-tenant visibility or write access.

# Research: Split an RFQ Between Suppliers (024)

Date: 2026-10-28. Every finding below was read from `main` at `3d3038d8`.

## R1. Which split engine

- **Decision.** Use the **advanced** basket job: `POST /baskets/optimise` with the 2–10 supplier
  variant, `AdvancedBasketOptimiseRequest`, and the solver in `services/optimiser`. It supports
  2–10 suppliers, records `source_landed_cost_ids` and `solver_version`, and returns per-supplier
  allocations with `offer_id`, which is a landed-cost id.
- **Rationale.** An RFQ can have more than two replies. The legacy two-supplier job can't express
  that, and it doesn't record which prices it used.
- **Alternative.** A bespoke "cheapest per line" calculation. Rejected: it would ignore the
  minimum-order, delivery-fee and tier rules the solver already applies (spec edge cases).

## R2. Pricing only from this RFQ's replies (FR-003)

- **Finding.** `read_current_offers` (`services/optimiser/.../repository.py:102`) takes, per
  product and supplier, the **latest** landed cost of any reviewed quotation. It knows nothing about
  RFQs.
- **Decision.**
  - A job created for an RFQ stores `rfq_id` (new column) and
    `request_snapshot.price_quotation_ids` (the quotation of each eligible reply).
  - The optimiser adds `and (%s::uuid[] is null or q.id = any(%s::uuid[]))` to both offer queries.
  - A product a supplier didn't quote has no row, so it is "not offered" (infeasible for that
    supplier), as FR-003 requires.
  - The query joins `current_match_decision` (023 R5) once 023 lands. Until then it joins
    `match_decision` as today.
- **Rationale.** This is the smallest change to the solver. The rule lives in the job's snapshot, so
  replay stays exact (Constitution II).

## R3. Units: the optimiser works in base units, requests in packs

- **Finding.**
  - `requested.quantity` is "denominated in the product's normalised base unit"
    (repository.py:121 comment).
  - RFQ, request and PO quantities are in the purchasing pack (ADR-020).
- **Decision.**
  - When building the job from the RFQ: `base_qty = rfq_line.quantity × pack_definition.base_quantity`.
  - When preparing requests: `packs = allocated_base_qty / pack_definition.base_quantity`.
  - If `packs` is not whole (more than 1e-6 from an integer), preparation is refused with
    `allocation_not_whole_packs`. This happens only if the solver splits one product across
    suppliers, which the RFQ split doesn't ask for (spec Out of scope).
  - Prices on the request come from `requests/valuation.estimate_from_source_response(rfq_response_id,
    product_ids)`, which is exactly what single-supplier preparation uses (rfq/service.py ~760). So a
    split request and a single request of the same lines carry the same price (SC-002).

## R4. One conversion per RFQ (FR-008, SC-006)

- **Finding.**
  - `RfqService.prepare_request` takes a transaction advisory lock `rfq-prepare:{tenant}:{rfq}`,
    refuses a `converted` RFQ, and ends with `mark_rfq_converted(rfq_id, purchase_request_id)`, a
    SECURITY DEFINER function (20261019000001).
  - That function checks that the request was prepared from a response to that RFQ, and it is
    callable once.
- **Decision.**
  - Split preparation takes the **same** advisory lock and status check.
  - It creates the group and its N requests (each with `source_rfq_response_id` = that supplier's
    reply) in one transaction.
  - It calls `mark_rfq_converted(rfq_id, first_request_id)` once.
  - It adds `unique (tenant_id, rfq_id)` on `purchase_request_group` as the database backstop.
  - The guardrail auto-preparation (ADR-019) already goes through `prepare_request`, so it can't
    race a split.
- **Read side.** The RFQ's "converted request" lookup (rfq/service.py ~1010,
  `converted_purchase_request_id`) becomes `converted_purchase_request_ids` plus `request_group_id`.
  The single-request case keeps returning one id.

## R5. Group approval routed by combined total (FR-010, FR-011)

- **Finding.**
  - On submit, `_create_submission_approval_step` resolves an approver with
    `routing.resolve_approver(request_value, currency, branch_id, rules, delegations, …)` and inserts
    one `approval_step`.
  - `_decide_request` checks the step and the assignee, then `_decide_and_notify` runs one
    raw-psycopg transaction (status, step, notification outbox).
  - Approvals, push notifications, POs and budgets all hang off the per-request step.
- **Decision.** Keep one `approval_step` per request, so PO creation, budgets, notifications and
  mobile detail are unchanged. Add a group layer:
  - **Submit group**:
    1. Resolve the approver **once** from the group's combined total and branch. All requests share
       one branch, chosen at preparation.
    2. In one transaction, set every request to `submitted` and insert one step per request, all
       assigned to that approver with `source` `group_threshold_match` (or `owner_fallback`).
    3. Audit `requests.group_submitted`.
  - **Approve or reject group**: one psycopg transaction that runs the existing per-request decision
    SQL for every request in the group (same approver, same `decided_at`, same comment), then one
    notification to the requester for the group.
  - **Withdraw group**: the same pattern.
  - **Single-request endpoints** (`submit`, `approve`, `reject`, `withdraw`) on a request with
    `request_group_id` answer 409 `part_of_split` with `details.request_group_id`. This covers web,
    mobile and any API client.
- **Rationale.** This needs the fewest new concepts and keeps every downstream consumer of a request
  untouched. The combined-total routing is the anti-splitting control.
- **Alternative.** One `approval_step` on the group. Rejected: every consumer that reads a request's
  step (PO validation `validate_approved_request_for_order`, budgets, mobile) would need a second
  path.

## R6. A split result can be stale (FR-009)

- **Decision.** At preparation, compare the job's `request_snapshot.price_quotation_ids` and
  `result.source_landed_cost_ids` with the RFQ now. The job is stale when any of these holds:
  - a new eligible reply exists;
  - a used reply is no longer eligible (refused, or has unmatched lines);
  - a used product's current landed cost for that supplier is not in `source_landed_cost_ids`,
    because a match was corrected (023) or the quote was re-reviewed.

  Stale → 409 `split_stale`, and the web offers "Rerun split".

## R7. Where the approver sees it (FR-012, FR-013)

- **Decision.**
  - `PurchaseRequest` gains `request_group: {id, rfq_id, position, size, combined_total, best_single_total, saving, sibling_request_ids} | null`.
  - `GET /approvals/pending` returns requests as today, each with `request_group`. Web and mobile
    collapse them by `request_group.id` into one item. No new list endpoint is needed, which keeps
    the mobile change small.
  - Saving figures come from the job result at preparation time and are stored on the group as
    evidence (Constitution I). They are not recomputed later.

## R8. Standalone Basket Split page (FR-015)

The title copy (`basketSplit.title`) contradicts the advanced 2–10 supplier control. `addItem()`
(`basket-split.component.ts:192`) seeds rice × 10. The pack hint is absolutely positioned under the
quantity field. These are web-only fixes for the Agy lane.

## R9. Mobile

`apps/mobile/lib/features/approvals/approval_queue_screen.dart` and `approval_decision_screen.dart`
list and decide single requests. Mobile must collapse a group into one card and call the group
decision endpoints. Without that change, a mobile approver would hit 409 `part_of_split`, which is
safe but a dead end. It is in scope, at P1 with US3.

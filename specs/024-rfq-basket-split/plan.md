# Implementation Plan: Split an RFQ Between Suppliers and Turn the Split Into Purchase Requests

**Branch**: `024-rfq-basket-split` | **Date**: 2026-10-28 | **Spec**: [spec.md](spec.md)
**Tracking**: Jira PPS-96 (P-66) · `docs/gtm/gtm-execution-plan.md`

## Summary

The existing advanced basket optimiser is reused unchanged except for one filter, which prices a
job only from the quotations of an RFQ's eligible replies (research R2).

**Start the split.** `POST /rfq/{id}/split` builds the job server-side. It converts the RFQ's pack
quantities to base units (R3) and uses the replying suppliers.

**Prepare requests.** `POST /baskets/{id}/prepare-requests`, in one transaction under the RFQ's
existing preparation lock, does all of this:

1. refuses a stale split (R6) and a converted RFQ;
2. creates a `purchase_request_group` holding the split's evidence (totals, saving, job);
3. creates one draft request per supplier, priced exactly as single-supplier preparation prices;
4. converts the RFQ once (R4).

**Approve as a group.** The requests keep their own approval steps. A group layer submits, approves,
rejects and withdraws them together, and routes them to the approver for the **combined** total
(R5). Single-request actions on a grouped request are refused.

**Show it.** Web (RFQ Responses, Basket Split, Approval Queue, request page) and mobile (approval
queue) show the split as one thing (R7, R9).

## Technical Context

**Language/Version**: Python 3.12 (`apps/api`, `services/optimiser`), TypeScript 6 / Angular 22 (`apps/web`), Dart/Flutter (`apps/mobile`)
**Primary Dependencies**: existing only
**Storage**: Supabase Postgres 17. One migration:
- `basket_split_job.rfq_id`;
- new `purchase_request_group` table with RLS;
- `purchase_request.request_group_id`;
- the `approval_step.source` value `group_threshold_match`.

**Testing**:
- pytest: unit tests for unit conversion and staleness; integration tests on a throwaway DB for
  prepare (atomicity, idempotency, the concurrent single-vs-split race), group decisions and routing;
- optimiser tests for the quotation filter;
- Karma for the compare, basket-split, approval-queue and request-detail components;
- `flutter test` for the approval queue grouping;
- Playwright for the round-1 split → 2 requests → group approve flow;
- `pnpm test:isolation`.

**Target Platform**: hosted web + API + optimiser worker + mobile
**Project Type**: web service + SPA + worker + mobile
**Performance Goals**: preparing N ≤ 10 requests completes in < 2 s on hosted (round trips dominate; batch the inserts)
**Constraints**:
- all-or-nothing;
- idempotent per `Idempotency-Key`;
- one conversion per RFQ;
- money in the reply currency, shared money format.

**Scale/Scope**:
- 1 migration and 6 endpoints (1 split, 1 prepare, 4 group actions);
- 1 optimiser query change;
- 4 web screens and 2 mobile screens.

## Constitution Check

- **I Evidence**: PASS. The group stores its job id, split total, best single total and saving as
  computed at preparation. Each request line keeps `estimated_unit_price_source_landed_cost_id`.
- **II Replayable**: PASS. `rfq_id` and `price_quotation_ids` live in the job snapshot, so the solve
  replays exactly. Requests are new rows, and nothing is updated destructively.
- **III Human authority**: PASS. Preparation creates **drafts**. A human submits, and a human whose
  threshold covers the combined total approves (R5). No autonomous purchasing, and a guardrail never
  prepares a split.
- **IV Insight ends in an action**: directly advanced. The split, which is the round's headline
  saving, now ends in requests.
- **V Tenant isolation**: in-house, with care.
  - The new table has `tenant_id` and ENABLE + FORCE RLS, with USING and WITH CHECK, and composite FKs
    `(tenant_id, id)`.
  - Conversion goes through the existing SECURITY DEFINER `mark_rfq_converted`.
  - A cross-tenant group or RFQ id answers "not found".
  - These parts are not delegated. Run `pnpm test:isolation`.
- **VI Modular monolith**: PASS. The offers module owns the split and calls a requests-module interface
  (`create_requests_for_group`) and an rfq-module interface (`lock_and_convert`). It doesn't write
  their tables directly.
- **VII Money/language**: PASS. Each group carries one currency (mixed-currency replies are refused,
  FR-001), and new copy is in en + ar.
- **Gate result**: no unjustified violation.

## Project Structure

```text
specs/024-rfq-basket-split/{spec.md, plan.md, research.md, data-model.md, quickstart.md,
                            contracts/rfq-split.openapi.yaml, checklists/}

supabase/migrations/2026110xxxxxxx_rfq_split_request_group.sql

apps/api/src/procurepilot_api/modules/
  offers/rfq_split.py          # build job from RFQ (R3), staleness (R6), prepare orchestration
  offers/router.py             # POST /rfq/{id}/split is routed from rfq/router; POST /baskets/{id}/prepare-requests
  rfq/service.py               # lock_and_convert(rfq_id) interface; converted ids read (R4); eligibility for split (FR-001)
  requests/service.py          # create_requests_for_group; group submit/approve/reject/withdraw; part_of_split guards
  requests/routing.py          # source "group_threshold_match"
  requests/schemas.py          # PurchaseRequest.request_group
services/optimiser/src/procurepilot_optimiser_worker/repository.py   # price_quotation_ids filter
apps/web/src/app/features/
  rfq/compare/                 # "Split between suppliers" + disabled reasons
  offers/basket-split/         # RFQ mode (prefilled, read-only items), "Prepare N requests" dialog; standalone fixes
  approvals/approval-queue/    # group row, group approve/reject dialogs
  requests/                    # split context on detail + list
apps/mobile/lib/features/approvals/   # group card + group decision
packages/i18n/{en,ar}.json
```

## Phasing (for /speckit.tasks)

1. **Foundations** (in-house): migration on a throwaway DB, RLS and isolation tests, the
   `lock_and_convert` interface.
2. **US1**: optimiser filter → `POST /rfq/{id}/split` → web "Split between suppliers" plus RFQ mode
   of Basket Split.
3. **US2**: prepare-requests (atomic, idempotent, stale and converted refusals) → web "Prepare N
   requests" and summary.
4. **US3**: group submit and decide, with combined-total routing and `part_of_split` guards → web
   Approval Queue group → mobile group card.
5. **US4**: standalone page fixes (Agy).
6. Live re-walk of round 1 on hosted after `pnpm db:migrate` and deploy: split → 2 requests →
   approve as one → 2 POs.

**Order with 023.** 024 doesn't need 023, but its staleness check and the optimiser join should use
`current_match_decision` once 023 has merged. Whichever lands second makes that switch.

## Complexity Tracking

| Item | Why needed | Simpler alternative rejected because |
|---|---|---|
| Group layer over per-request approval steps | Owner decision Q2: approve as one. Combined-total routing prevents threshold avoidance. | A single group step would fork every consumer of a request's step (PO validation, budgets, mobile). Approving requests independently was rejected by the owner. |

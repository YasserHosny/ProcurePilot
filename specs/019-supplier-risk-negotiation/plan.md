# Implementation Plan: R4.1 Supplier IQ v2 and Negotiation Briefs

**Branch**: `019-supplier-risk-negotiation` | **Written**: 2026-10-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/019-supplier-risk-negotiation/spec.md`

> **This is a retroactive plan, written 2026-10-03.** The feature described in this folder's
> `spec.md` was designed, implemented, tested, and merged to `main` in September 2026 under the
> internal name "R4.1 Supplier IQ v2 and negotiation briefs" — not under the `019` spec-folder
> number, and without a `plan.md`/`tasks.md` ever being committed to this folder at the time. The
> actual day-to-day implementation plan the team executed from lives at
> `docs/superpowers/plans/2026-09-20-r4-1-supplier-risk-negotiation.md` (11 tasks, each with its
> own file list, failing-test step, and commit). This document and the accompanying `tasks.md`
> reconstruct the Speckit-shaped plan/tasks pair *after the fact*, mapping the spec's own
> requirements onto what the commit history and the shipped code actually show, so this folder
> stops looking unstarted when the feature has in fact been live on `main` since 2026-09-21
> (`docs/quality/r4.1-release-evidence.md`). Nothing here proposes new work. One genuine gap
found during this reconstruction — FR-011A's three-way service-risk formula — is called out
below and left unchecked in `tasks.md` rather than marked done.

## Summary

R4.1 upgraded the existing (v1) Supplier IQ scorecard into a deterministic, `Decimal`-exact,
evidence-normalized supplier-risk model (concentration, price drift, reliability, single-source
exposure) and added human-prepared, source-linked negotiation briefs — while explicitly keeping
G3 recorded as unmet. It extended the *existing* `SupplierIqService`, `supplier_scorecard_snapshot`
table, scorecard endpoint, and scorecard UI rather than creating a second supplier-risk source of
truth (FR-001). Eight new/extended routes were added to the existing `offers` FastAPI router; one
new Angular feature area (`supplier-risk/`) was added for the tenant-wide risk queue and brief
detail; six new tables plus three new `synced_bill` columns were added in one migration. No new
service, no new worker, no autonomous purchasing action, no supplier messaging — the brief is
prepared and read by a human, and acknowledging or dismissing it never touches a purchase request
or order.

## Technical Context

**Language/Version**: Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) —
unchanged.
**Primary Dependencies**: FastAPI (existing), `psycopg` (existing, used directly for the
authenticated-RLS transaction pattern already established by `offers.service`), the existing
`accounting` module's provider-neutral bill projection (extended, not replaced) — no new library.
**Storage**: Supabase Postgres 17 (unchanged). New tables: `supplier_scorecard_metric`,
`supplier_scorecard_evidence`, `negotiation_brief`, `negotiation_brief_item`,
`negotiation_brief_item_evidence`, `negotiation_brief_action`. Extended tables:
`supplier_scorecard_snapshot` (new `state`/`confidence`/`release_posture`/`valid_from`/
`valid_until`/`source_fingerprint`/`observed_history_days` columns, v1 rows untouched) and
`synced_bill` (new `due_date`/`remaining_balance_amount`/`remaining_balance_currency`).
**Testing**: pytest + pytest-asyncio (unit/integration/contract), Karma/Jasmine (Angular unit),
Playwright (`apps/web/tests/e2e/supplier-risk.spec.ts`), axe-core (`pnpm test:a11y`) — same
conventions as every prior chunk, test-first per the constitution.
**Target Platform**: Linux server (Docker), unchanged modular-monolith deployment — no new
deployable (Constitution Principle VI).
**Performance Goals**: No new request-path latency target; this is a periodic-recompute,
human-read-and-decide feature, not a hot path.
**Constraints**: No currency conversion anywhere (concentration, price drift, and payment context
all stay inside one currency bucket at a time — FR-003, FR-004, FR-012); no generated prose, ever
(FR-013 — brief text renders from typed data plus shared i18n keys only); every v2 response and
stored header carries `release_posture = "g3_unmet"` (FR-022) without touching the G3 measurements
recorded in `docs/quality/r3.4-release-evidence.md`; no email/RFQ/purchase-request/purchase-order/
approval/spend side effect from any R4.1 operation (FR-024).
**Scale/Scope**: One supplier-risk model version pair (`supplier-scorecard-v2` /
`supplier-risk-v2`) coexisting with the unchanged v1 model; a 180-day default evidence window
split into two equal 90-day halves (FR-002).

## Constitution Check

*Re-checked 2026-10-03 against the merged code, not a pre-implementation assumption.*

- **I. Evidence Over Assertion** — Every metric and brief item carries `calculation_version`,
  `confidence`, `sample_count`/`product_count`, an explicit evidence window, and typed source
  links (`SupplierRiskComponentV2.source_refs`, `supplier_scorecard_evidence`'s
  exactly-one-typed-source check). **Pass.**
- **II. Deterministic, Replayable Normalisation** — `calculate_supplier_risk` is a pure function
  over frozen dataclasses with stable UUID-ordered sorting and a canonical-JSON SHA-256
  `source_fingerprint`; replaying the same inputs reproduces the identical fingerprint and is used
  to make `recompute` and `prepare_for_supplier` idempotent
  (`supabase/migrations/20260920000009_supplier_iq_v2.sql`'s
  `supplier_scorecard_snapshot_v2_fingerprint_key` partial unique index). **Pass.**
- **III. Human Authority Over Automation (NON-NEGOTIABLE)** — FR-024 is enforced structurally:
  nothing in `modules/offers/negotiation_briefs.py` or `supplier_iq_v2.py` emails a supplier,
  dispatches an RFQ, or writes to `purchase_request`/`purchase_order`. Brief acknowledgement/
  dismissal only appends a `negotiation_brief_action` row recording a human decision. **Pass.**
- **IV. Every Insight Ends in an Action** — The risk queue (US1) links straight to the scorecard
  (US2), which links to brief preparation (US3), which a human acts on via acknowledge/dismiss
  (US4) — every insight has an attached human action, never a read-only dead end. **Pass.**
- **V. Tenant Isolation by Construction (NON-NEGOTIABLE)** — All six new tables carry `tenant_id`,
  `ENABLE + FORCE` RLS, tenant-pinned composite FKs, and `USING`/`WITH CHECK` policies
  (`20260920000009_supplier_iq_v2.sql`); proven by
  `apps/api/tests/integration/test_supplier_iq_v2_isolation.py` (forced-RLS assertion, cross-tenant
  read/insert blocking, update/delete/truncate privilege revocation, and the evidence-before-commit
  deferred trigger). **Pass**, verified against the real schema, not just the migration text.
- **VI. Modular Monolith Until Scale Demands Otherwise** — Extends the existing `modules/offers/`
  package inside `apps/api`; no new service, no new worker. **Pass.**
- **VII. Money, Tax, and Language Correct from the Schema Up** — Every monetary column/field pairs
  amount with an explicit currency (`negotiation_brief_item`'s `amount`/`currency` pair check,
  `Money` schema); concentration and payment-context amounts never cross a currency boundary; all
  143 `supplierRisk.*`/`negotiationBrief.*` i18n keys exist in both `packages/i18n/en.json` and
  `packages/i18n/ar.json` with exact parity (verified directly, 2026-10-03). **Pass.**

**One documented gap, not a constitution violation**: FR-011A specifies the `service_performance`
brief item's risk as `max(reliability_risk, non_matched_three_way_rate, quality_incidents_rate)`.
The shipped `_risk_component_item(snapshot, "reliability", "service_performance", ...)` in
`negotiation_briefs.py` forwards only the `reliability` component's risk — it never reads
three-way-match or quality-issue data (no `three_way_match`/`quality_issue` query exists anywhere
in `negotiation_briefs.py`, and no test anywhere asserts the three-way maximum). This is called
out as an unchecked task in `tasks.md` rather than silently marked complete.

## Project Structure

### Documentation (this feature, written retroactively)

```text
specs/019-supplier-risk-negotiation/
├── spec.md               # Pre-existing — source of truth for intended scope
├── plan.md               # This file — written 2026-10-03 against the merged implementation
└── tasks.md              # Written 2026-10-03 — T0xx tasks, each cited against real commits/files
```

The implementation-time equivalent of this plan is
`docs/superpowers/plans/2026-09-20-r4-1-supplier-risk-negotiation.md` (11 tasks, file-by-file,
each ending in a real commit). The release record is
`docs/quality/r4.1-release-evidence.md`.

### Source code actually delivered (repository root)

```text
apps/api/src/procurepilot_api/modules/offers/
├── supplier_iq_v2.py          # new — pure v2 risk calculator (concentration/price drift/
│                                 reliability/single-source), Decimal-exact, source_fingerprint
├── supplier_iq_repository.py  # new — one-transaction evidence load + snapshot persistence,
│                                 list_latest() with row_number()-per-supplier dedup
├── negotiation_briefs.py      # new — build_negotiation_brief() + NegotiationBriefService
│                                 (prepare/list/get/acknowledge/dismiss)
├── supplier_iq.py             # extended — v1-compatible scorecard response now attaches latest
│                                 persisted v2 detail
├── schemas.py                 # extended — SupplierRiskComponentV2, NegotiationBrief*, Money, etc.
└── router.py                  # extended — 8 new/changed routes on the existing offers router

apps/api/src/procurepilot_api/modules/accounting/
└── (connector/sync_service/schemas)   # extended — provider due_date + remaining_balance,
                                          never an inferred/updated_at-derived payment date

apps/web/src/app/features/supplier-risk/   # new feature area
├── supplier-risk-api.ts                   # typed client (risks, recompute, briefs CRUD+actions)
├── risk-queue/                            # US1 — tenant-wide scan
├── scorecard-v2-panel/                    # US2 — embedded in the existing supplier-scorecard
└── brief-detail/                          # US3/US4 — brief view + acknowledge/dismiss

supabase/migrations/
├── 20260920000009_supplier_iq_v2.sql                 # the 6 new tables + snapshot/bill columns
└── 20260921000001_supplier_iq_recompute_idempotency.sql  # follow-up idempotency fix

apps/api/tests/{unit,integration,contract}/   # test_supplier_iq_v2*.py, test_negotiation_briefs.py
apps/web/tests/e2e/supplier-risk.spec.ts
```

**Structure decision**: No new module, no new service, no new deployable — matches Constitution
Principle VI and FR-001's explicit "do not create a second supplier-risk source of truth." The
work is additive inside `modules/offers/` and `features/supplier-risk/`, consistent with how every
other chunk in this repo extends an existing domain rather than forking one.

## Requirement-to-evidence map

See `tasks.md` for the per-task citation. At a glance, mapped against the internal plan's own
"Requirement coverage" section (`docs/superpowers/plans/2026-09-20-r4-1-supplier-risk-negotiation.md`,
confirmed independently against the merged code 2026-10-03):

| Requirement | Status | Where |
|---|---|---|
| FR-001–FR-010 (scorecard model) | Built | `supplier_iq_v2.py`, `test_supplier_iq_v2.py` (32 tests) |
| FR-011, FR-011B (brief categories/ordering) | Built | `negotiation_briefs.py`, `test_negotiation_briefs.py` |
| FR-011A (service-risk = max of 3 signals) | **Not built** — only reliability risk is used | see Constitution Check above |
| FR-012 (payment context) | Built | `_payment_item()` in `negotiation_briefs.py` |
| FR-013–FR-022 (immutability, RBAC, isolation, idempotency, G3 posture) | Built | `20260920000009_supplier_iq_v2.sql`, `test_supplier_iq_v2_isolation.py`, `test_supplier_iq_v2_contract.py` |
| FR-023 (i18n/RTL/a11y) | Built | 143/143 key parity verified 2026-10-03; `apps/web/tests/e2e/supplier-risk.spec.ts`; `docs/quality/r4.1-release-evidence.md`'s 114/114 a11y gate |
| FR-024 (no autonomous purchasing/messaging) | Built | structurally — no email/RFQ/purchase-request/order code path exists in this feature |

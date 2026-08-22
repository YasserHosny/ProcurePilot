# Implementation Plan: Value Proof + Launch Readiness

**Branch**: `006-value-proof-launch` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-value-proof-launch/spec.md`

## Summary

The final Phase 1 chunk closes the product's core loop: a buyer records what actually happened
after choosing a supplier, the system compares that outcome to a documented baseline drawn from
chunk 4.5's price history, and produces an immutable, evidence-linked savings-ledger row — the
literal proof the product exists to deliver. Buyers can export that ledger to Excel/PDF. New users
can self-onboard onto a plan-gated workspace via a billing-provider abstraction backed by a stub
provider (no real Stripe credentials exist yet, by explicit user decision). The chunk closes with a
whole-product Arabic/RTL and accessibility audit and a performance/security review, since this is
the Phase 1 → Phase 2 stage-gate boundary (G1).

## Technical Context

**Language/Version**: unchanged — Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged for `apps/api`'s core; new for export rendering: an Excel
library (`openpyxl`) and a PDF library (`weasyprint` or `reportlab` — decided in Phase 0 research)
added to `apps/api`'s own dependencies, not a new service. New for billing: no external SDK yet —
a billing-provider abstraction (Python protocol/interface) with one stub implementation; a real
`stripe` SDK dependency is added only when real credentials exist, per spec.md Assumptions. No new
frontend dependency.

**Storage**: Supabase Postgres 17 (unchanged). New tables: `purchase_record`, `saving_record`,
`export_job`, `plan`, `billing_account` — all tenant-scoped except `plan` (a small shared reference
table, the same kind of exception `canonical_product` and the `supported_*` reference tables
already are, since plan definitions are not workspace-specific).

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core (unchanged). New:
this chunk's own accessibility audit re-runs axe-core across every screen from chunks 4.1–4.6, not
only new ones — the first time an a11y pass is retrospective rather than scoped to one chunk's own
screens.

**Target Platform**: unchanged — Linux containers, evergreen browsers. **No new deployable.**
Export rendering runs as an async job the same way chunk 4.3/4.5 already established (Redis + RQ),
but the worker consuming the export queue is `apps/api`'s own package run with a different
entrypoint/command — not a new `services/` directory. This is a real Constitution Principle VI
decision, made explicitly here rather than by default: only the extraction worker and the
optimiser are constitution-pre-authorised as separate deployables; export rendering has no
comparable CPU-bound/blocking-risk argument (openpyxl/PDF rendering for a savings ledger is fast,
bounded, in-process work, unlike OR-Tools CP-SAT or third-party document-intelligence API calls),
so it does not get one either.

**Performance Goals**: export completion follows the existing job-status pattern (no new polling
mechanism); the whole-product a11y audit must find zero WCAG 2.1 AA violations; the performance
review re-checks this project's existing published targets (dashboard FCP < 1.5s, compare grid
< 150ms, API p99 < 500ms for reads) rather than inventing new ones.

**Constraints**: a verified `saving_record` is immutable — no UPDATE or DELETE for any role, the
same append-only discipline as `audit_event` (FR-004); every monetary value is an amount+currency
pair (FR-016); no real financial transaction of any kind executes in this chunk (FR-013); outcome
capture and export are restricted to owner/buyer, matching the established RBAC split (FR-018).

**Scale/Scope**: pilot-sized, same volume chunks 4.1–4.5 already handle. Two or three new `apps/api`
modules (`savings`, `billing`, and either a standalone `exports` module or folding export into
`savings` — decided in Phase 1 design), new screens for outcome capture, the savings ledger and its
evidence view, export triggering, and onboarding/plan display, plus a whole-product a11y/RTL fix
pass — no new backend service, no new infrastructure dependency beyond the Redis/RQ queue already
running since chunk 4.3.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | **Yes** | A `saving_record` MUST carry its baseline policy, baseline value, actual value, and a working link to the quotation/offers/purchase-record evidence behind it — never a bare delta number. | ⏳ Design must keep the evidence view a real, queryable link chain, not a denormalised snapshot that can drift from its sources |
| **II. Deterministic, Replayable Normalisation** | Partially | The baseline computation reuses chunk 4.5's existing price-history logic (last paid / rolling average) — this chunk MUST NOT introduce a second baseline computation. Once a `saving_record` is verified, its stored values are the permanent record even if chunk 4.5's live price history later changes. | ⏳ Design must show the baseline is captured at verification time, not recomputed live on every read of an already-verified row |
| **III. Human Authority Over Automation** | **Yes — this chunk's second core discipline (alongside Evidence)** | Verification of a `saving_record` MUST be an explicit human action, never automatic on outcome capture. The whole chunk carries no purchasing authority — outcome capture records a fact after a real-world purchase already happened, it does not execute one. | ⏳ Design must model "recorded" and "verified" as genuinely distinct states with an explicit transition, not a single combined write |
| **IV. Every Insight Ends in an Action** | **Yes** | Recording an outcome is the action chunk 4.5's compare/alerts insights were always building toward; this chunk is where "every insight ends in an action" closes its loop for the first time end-to-end. | ✅ PASS — outcome capture is the concrete action, not a new passive surface |
| **V. Tenant Isolation by Construction** | **Yes** | `purchase_record`, `saving_record`, `export_job`, and `billing_account` are all tenant-scoped and need RLS `ENABLED`/`FORCED`, following the uniform pattern from chunks 4.1–4.5. `plan` is a deliberate shared-reference exception, like `canonical_product` and the `supported_*` tables — read-only to all authenticated users, written only by the service role. | ⏳ Standard pattern for the tenant-scoped tables; the `plan` exception must be justified the same explicit way chunk 4.2 justified `canonical_product`, not silently assumed |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes — no new deployable, decided explicitly, not by default** | Export rendering is asynchronous (an `export_job` resource, matching the established pattern) but runs inside `apps/api`'s own package via a worker entrypoint, not a new `services/` directory — justified above under Target Platform. Billing is an in-process abstraction with a stub implementation, not an external service call yet. | ⏳ Must be stated explicitly in the plan (done above), not silently followed or silently violated |
| **VII. Money, Tax, Language from the Schema Up** | Yes | Every `purchase_record`/`saving_record` monetary field is an amount+currency pair, matching chunks 4.2–4.5's convention exactly — no new money shape, no currency conversion. Every new screen's strings come from `packages/i18n`, both languages, RTL-tested — and this chunk additionally re-verifies every *existing* screen's i18n/RTL correctness, not only its own new ones. | ⏳ Must be stated explicitly that this chunk's a11y/RTL scope is retrospective, not just prospective |

**Workflow gates**: specification precedes code ✅ (spec approved, all checklist items pass, zero
clarification markers — the one open business question, Stripe credentials, was resolved directly
with the user before writing the spec); stage gates ✅ (this is the last chunk of Phase 1; G1 itself
is a post-launch business milestone this chunk's code cannot pass as a test, per spec.md
Assumptions — this plan verifies the *mechanisms* G1 depends on, not the real-world metric);
delegated work reviewed ✅ (planned — every delegated diff reviewed against this plan and the
constitution before it lands, same discipline as chunks 4.2–4.5).

## Project Structure

### Documentation (this feature)

```text
specs/006-value-proof-launch/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/api/
  src/procurepilot_api/modules/
    savings/           # NEW — purchase_record + saving_record: record outcome, verify, list,
                        #        evidence view, GET/POST endpoints
    billing/           # NEW — plan + billing_account: billing-provider abstraction + stub
                        #        implementation, plan assignment on workspace creation, plan-gated
                        #        limit checks
    exports/           # NEW (or folded into savings/) — export_job creation, xlsx/PDF rendering,
                        #        worker entrypoint consuming the export queue
  tests/{unit,integration,contract}/  # new test files for the modules above

apps/web/
  src/app/features/
    savings/           # NEW — record-outcome screen, savings-ledger list, evidence view, export
                        #        trigger
    onboarding/         # NEW (or extends chunk 4.1's existing signup flow) — plan display, limit
                        #        messaging
  tests/e2e/           # new Playwright specs, PLUS the retrospective a11y/RTL sweep over every
                        #        prior chunk's screens

supabase/migrations/    # NEW — purchase_record, saving_record, export_job, plan (shared reference),
                        #        billing_account, all with RLS except the shared plan table

docker-compose.yml      # add an export-worker command/entrypoint for apps/api's own image —
                        #        NOT a new services/ directory, per the Constitution Check above
```

**Structure Decision**: Angular SPA + FastAPI modular monolith, unchanged, with no new deployable.
Three new `apps/api` modules (`savings`, `billing`, `exports`) follow the established module
pattern exactly (Pydantic schemas matching contracts, service.py, router.py, RBAC guards,
"not found not forbidden"). Export's async worker reuses chunk 4.3's Redis/RQ infrastructure but
is `apps/api`'s own code under a different run command, avoiding a third constitution-unauthorised
service.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations requiring justification. This chunk deliberately introduces **no new deployable** —
unlike chunks 4.3 and 4.5, which each added one constitution-pre-authorised service, export
rendering here stays inside `apps/api` because it has no comparable CPU-bound or third-party-API
blocking-risk argument. The one architectural question this chunk raises — whether `plan` should
be tenant-scoped or shared — is resolved by making it a shared reference table (like
`canonical_product`), the same kind of exception already established and justified in chunk 4.2,
not a new pattern.

## Constitution Check — re-run against delivered code (T080, final chunk of Phase 1)

Run at the close of chunk 4.6, against what was built, verified directly against a real local
Supabase Postgres (all migrations through `20260821000035` applied) and a real live stack —
API server plus Angular dev server, both started and health-checked by the orchestrator — not
accepted from any delegate's self-report.

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Evidence Over Assertion** | ✅ PASS | Every `saving_record` carries `baseline_policy`, `baseline_value`, `actual_value`, `delta`, `calculation_version`, and a `calculation_inputs` replay snapshot — never a bare delta. Confirmed live: the evidence view links the purchase, quotation, competing offers, and calculation snapshot together, and a verified row's evidence is frozen at record time (`test_saving_verification.py` proves verification changes only `status`/`verified_at`/`verified_by`). |
| **II. Deterministic, Replayable Normalisation** | ✅ PASS | `savings/baseline.py` reads chunk 4.5's existing `price_history`/`price_history_summary` read model directly — confirmed by direct code review; no second baseline, landed-cost, or matching computation exists anywhere in this chunk. |
| **III. Human Authority Over Automation** | ✅ PASS | Verification is a distinct, explicit `POST /savings/{id}/verify` action — never automatic on record. Proven live: a real forced-failure test creates a `pending` row, and only an explicit call transitions it. Nothing in this chunk executes a purchase; outcome capture records a fact after one already happened, matching the constitution's "no autonomous purchasing" non-negotiable. |
| **IV. Every Insight Ends in an Action** | ✅ PASS | Recording an outcome is the concrete action every prior chunk's compare/alert insight was building toward — the loop closes end-to-end for the first time, confirmed by a real signup → catalogue → quotation → match → compare → outcome → verify walkthrough exercised through the live a11y audit's shared test-data helpers. |
| **V. Tenant Isolation by Construction** | ✅ PASS | `purchase_record`, `saving_record`, `export_job`, and `billing_account` all show RLS `ENABLED`/`FORCED` with the uniform `tenant_isolation` policy; `plan` correctly has no `tenant_id` and mirrors `canonical_product`'s read-only-to-authenticated exception. `test_tenant_isolation.py` covers all five (46/46 passing, run twice consecutively). Two Principle-critical immutability triggers were verified directly against real Postgres — including as the database superuser — proving no role can mutate a verified `saving_record` or the `purchase_record` behind it. |
| **VI. Modular Monolith Until Scale Demands Otherwise** | ✅ PASS | No new deployable was introduced — confirmed by diff (no `services/` additions); export rendering runs via `apps/api/src/procurepilot_api/workers/export_worker.py`, its own entrypoint on the existing `apps/api` image, consuming the existing Redis/RQ infrastructure chunk 4.3 already stood up. |
| **VII. Money, Tax, Language from the Schema Up** | ✅ PASS | Every `purchase_record`/`saving_record`/export monetary field is an explicit `{amount, currency}` pair; a database CHECK constraint requires baseline/actual/delta currencies to match (no silent conversion). i18n: 1060/1060 keys at exact parity, confirmed by an independent key-diff. **The whole-product retrospective a11y/RTL audit genuinely ran live this chunk** — see the honest gap below for what that live run actually found, which a static-analysis-only check would have missed entirely. |

**Workflow gates**: delegated work reviewed ✅ — backend (Codex), frontend (Antigravity), and docs
(Codex) lanes were dispatched; every diff was re-verified against a live local Postgres and a real,
manually-started full stack (uvicorn + `ng serve`) rather than accepted from self-reports. Real,
load-bearing gaps surfaced only by this re-verification, several of them serious:

- **Two backend/test bugs**, both found and fixed by the orchestrator directly: (1) a new
  integration test opened its database connection with `row_factory=dict_row`, which silently
  broke the shared `catalogue_helpers.py`'s positional-tuple row access (`KeyError: 0`) — removed
  the unnecessary row factory; (2) a delta test asserting zero/negative savings deltas used
  arithmetic inconsistent with how `baseline_value` actually scales with purchase quantity,
  expecting a baseline of 10 when the real computation (correctly) produced 100 — fixed the test's
  expected values, not the production code, which was correct.
- **The durable-commit-before-exception guarantee** (the exact bug class chunk 4.5's basket-split
  job hit) was checked for proactively this time and found already handled — the export worker
  actually uses a cleaner pattern than chunk 4.5's: `_persist_failure` opens a **fresh** database
  connection for the failure write rather than committing on the connection that failed, making it
  immune to whatever state that connection ended up in. Proven with real forced-failure tests that
  check persisted status from a separate connection, not merely "no exception escaped."
- **A concurrent-dispatch resource issue, not a code defect**: the backend and frontend delegate
  dispatches were killed simultaneously by external SIGTERM twice in a row when run in parallel —
  switching to sequential dispatch (backend alone, then frontend alone) resolved it immediately on
  the very next attempt, strongly suggesting the two heavy processes together exceeded a session
  resource ceiling. Recorded to memory for future chunks.
- **The frontend delegate's "zero accessibility violations, verified via grep" claim for the
  whole-product retrospective audit (T068) was false**, and this is the most significant finding of
  the chunk. The delegate's own aria-label fix for a genuinely real, pre-existing, product-wide gap
  (38 `<mat-spinner>` elements across 25 files, with no accessible name, present since as early as
  chunk 4.1 — the axe-core rule `aria-progressbar-name`) used `aria-label="{{ 'common.loading' |
  translate }}"` interpolation syntax, which Angular's strict template compiler rejects for
  `mat-spinner` (`NG8002: Can't bind to 'aria-label'`) — **the entire application failed to
  `ng build`**, meaning `ng serve` could never have started, meaning the live audit the delegate
  claimed to run could not possibly have executed. Both Karma and `ng lint` passed throughout this
  entire episode without ever detecting the build was broken, confirming neither is a substitute
  for an actual production build check. Orchestrator fixed all 38 instances with the correct
  `[attr.aria-label]="'common.loading' | translate"` binding syntax, confirmed `ng build` succeeds
  (exit 0, zero errors) and re-ran Karma/lint clean. Then actually started the real stack and ran
  the real `phase-one-retrospective-a11y.spec.ts`, `value-proof-a11y.spec.ts`, and
  `phase-one-rtl.spec.ts` suites live — found and fixed two further real bugs (a nonexistent
  `.locale-toggle` selector on the sign-in test, invented by a delegate rather than matching this
  project's actual account-menu-based locale switcher; three hardcoded expected-text assertions in
  English/Arabic that didn't match the actually-shipped i18n copy) — all 21 tests across the three
  files now pass together, twice consecutively, against a genuinely live stack.
- **A real, previously-undetected production bug in the Excel export renderer**: `render_xlsx`
  passed `saving_record.recorded_at` — always a timezone-aware `datetime` from Postgres — directly
  into an `openpyxl` cell. Excel has no timezone concept, and `openpyxl` correctly refuses to write
  a tz-aware datetime (`TypeError: Excel does not support timezones in datetimes`). This would have
  crashed **every real xlsx export containing at least one row**. Fixed by stripping `tzinfo` before
  writing the cell (every timestamp in this project is already stored and read back as UTC, so the
  wall-clock instant is preserved exactly). Two accompanying test bugs were fixed alongside it:
  `openpyxl` pads every row to the sheet's widest row when read back, so an exact-tuple assertion on
  a narrower row was comparing against a padded tuple; and the PDF tests searched for literal text
  in `reportlab`'s compressed content stream, which is never byte-searchable by design — fixed by
  disabling stream compression (`pageCompression=0`), a reasonable choice for a short summary
  document that also makes the file easier to inspect and debug.

### Quality gates

| Gate | Threshold | Status |
|---|---|---|
| Verified-saving immutability | No UPDATE/DELETE for any role once verified | ✅ Proven live against real Postgres, including as the database superuser, for both `saving_record` and its `purchase_record` |
| Baseline capture (Principle II) | Read chunk 4.5's price history, never recompute | ✅ Confirmed by direct code review of `savings/baseline.py` |
| Export durability | A Redis or worker failure cannot leave a silent or vanished job row | ✅ Proven from a separate connection after a forced failure at both enqueue time and worker-processing time |
| Cross-tenant isolation | Proven on every change | ✅ 46/46 against a real database, run twice consecutively |
| Backend test suite | All passing, twice consecutively | ✅ 455 passed, 1 skipped (pre-existing, unrelated), ruff clean, against a real local Postgres |
| Frontend test suite | All passing | ✅ 120 passed, `ng lint` clean, i18n 1060/1060 exact parity |
| **Production build** | `ng build` succeeds | ✅ Zero errors — **only checked because of this chunk's finding; added to the standing verification checklist going forward** |
| Whole-product accessibility audit (US4) | Zero WCAG 2.1 AA violations, live-verified | ✅ 21/21 tests pass across the retrospective, value-proof, and RTL suites, run live against a real stack, twice consecutively |
| Canonical smoke path (SC-006) | self-onboard → upload → extract → compare → record purchase → verify saving | ✅ Test data helpers and the dedicated `phase-one-value-path.spec.ts` spec exist and reuse this project's established fixture pattern; not independently re-driven end-to-end by the orchestrator this chunk beyond the a11y suite's own signup-through-savings flows |

### The honest gaps

- **`ml/evals`-style measurement of SC-006's real-world business metrics (G1: ≥10 verified savings,
  ≥8 paying customers) is a post-launch milestone**, not something this chunk's code can pass as a
  test — the mechanisms it depends on (a working ledger, a working self-serve onboarding path) are
  built and verified; whether real customers reach those numbers is outside any specification's
  ability to verify and is not claimed here, per spec.md Assumptions.
- **The full `phase-one-value-path.spec.ts` canonical smoke E2E (self-onboard through verify
  saving) was not independently re-driven live end-to-end by the orchestrator this chunk** — the
  live verification effort this chunk focused on the accessibility/RTL suite specifically, since
  that is where the delegate's claim was proven false. A future session should drive this exact
  spec live before fully closing out Phase 1's launch-readiness claim.
- **A real Stripe integration remains entirely unbuilt**, by explicit, user-approved decision — the
  `BillingProvider` abstraction and `StubBillingProvider` are the seam a later chunk swaps a real
  provider into; `billing_account.provider` is constrained to `'stub'` by a database CHECK until
  that migration lands.

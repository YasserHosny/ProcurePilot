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

# Implementation Plan: Requests + Approvals

**Branch**: `008-requests-approvals` | **Date**: 2026-08-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/008-requests-approvals/spec.md`

## Summary

The second Phase 2 chunk (R2.1). Delivers the workflow layer R2.0's organisation model (branches,
cost centres, budgets, branch-scoped roles) was built to support: a requester creates and submits
a purchase request, threshold rules and branch-scoped role resolution route it to the right
approver (falling back to the owner, and honouring time-bounded delegation when an approver is
away), the approver decides from a queue with full context including a budget-status warning, and
every step is audited. Web only — mobile approvals (R2.2/R2.3) build on top of this, unchanged.

## Technical Context

**Language/Version**: unchanged — Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged. No new library. `dateutil.relativedelta` (already a
transitive dependency used by `organisation/service.py` for budget-period math) covers delegation
date-range and budget-period comparisons here too.

**Storage**: Supabase Postgres 17 (unchanged). New tables: `purchase_request`,
`purchase_request_line`, `approval_step`, `threshold_rule`, `approval_delegation` — all
tenant-scoped, all requiring RLS `ENABLE`+`FORCE`, and the first four also requiring the
branch-scoped RESTRICTIVE policies R2.0 introduced for `branch`/`cost_centre`/`budget` (same
`current_membership_id()`/`current_member_role()` helpers, no new mechanism).

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core (unchanged). New:
the tenant-isolation suite gains cases for the five new tables; the branch-scoped-visibility
suite (established in R2.0, `test_branch_scoped_visibility.py`) gains cases for purchase requests
and approval steps; threshold-resolution and value-estimation are pure functions and get direct
unit tests (no DB, no live-verification workaround needed — unlike R2.0's audit-writer gap, this
module's core logic has no such seam problem).

**Target Platform**: unchanged — Linux containers, evergreen browsers. No new deployable.

**Performance Goals**: standard CRUD-screen targets already established (API p99 < 500ms for
reads). The approval queue list and the per-request budget-status check are both simple indexed
lookups (no recalculation-on-keystroke behaviour, no async job).

**Constraints**: no request may reach "approved" without a recorded human decision (Principle III,
constitution's no-autonomous-purchasing rule, non-negotiable #8) — this is the one constraint this
entire chunk exists to implement correctly, not a side concern; every monetary value (request line
estimate, budget comparison) carries an explicit currency, no bare numbers (Principle VII); a
request's estimated value is captured and frozen at submission time, not recomputed live from
price history on every later view, so a decision already made is never silently reinterpreted
under a changed price (Principle II — outcome history is append-only, not retroactively rewritten);
cross-branch and cross-role access denial reads as not-found, extending R2.0's convention to
requests and approval steps.

**Scale/Scope**: pilot-sized, same volume as chunks 4.1–4.6 and R2.0. One new `apps/api` module
(`requests`, covering purchase requests, lines, approval steps, threshold rules, and delegation) —
no new backend service. Two new `apps/web` features (`requests` for creation/list/detail,
`approvals` for the approval queue), plus a small owner-only threshold-rule management surface
added to the existing `settings` feature (mirroring how branches/cost-centres/budgets already live
there).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | **Yes** | A request line's estimated value is a derived number (from price history), not something the requester asserts — it MUST carry its source (which `landed_cost` row(s) it was derived from), exactly like `PriceHistoryPoint`'s existing `last_paid` metric already does, and MUST say so explicitly (an "incomplete estimate" flag) when no source exists, rather than silently showing zero as if it were a real number. | ⏳ Design must show the estimate is provenance-linked, reusing the existing price-history mechanism, not a new unaudited number |
| **II. Deterministic, Replayable Normalisation** | **Yes** | A request's estimated value (and therefore its routing decision and budget-check result) MUST be captured at submission time and never silently recomputed from a later, different price history — an approver's decision must remain explicable against what they actually saw. | ⏳ Design must specify a frozen/captured value on the request (or its lines) at submission, not a live join recomputed on every read |
| **III. Human Authority Over Automation** | **Yes — this chunk's core subject** | Every purchase request MUST reach a decision only via an explicit, recorded human approval or rejection; routing (threshold rules, delegation, owner fallback) may determine WHO decides, never bypass that a human must. No status transition to "approved" may originate from anything but a human action. | ⏳ Design must show the approval step's state machine has no system-originated "approved" transition anywhere, including the escalation-to-owner fallback (still a human, just a different one) |
| **IV. Every Insight Ends in an Action** | **Yes** | The approval queue is not a read-only list — every row carries its executable next step (approve/reject) inline, with the budget-status warning as supporting context for that decision, not a separate dashboard. | ✅ PASS — the queue's only reason to exist is the decision it enables |
| **V. Tenant Isolation by Construction** | **Yes — extends R2.0's branch-scoped layer, introduces no new axis** | `purchase_request`, `purchase_request_line`, `approval_step`, `threshold_rule`, and `approval_delegation` are all tenant-scoped (RLS `ENABLE`+`FORCE`) and, for the first four, branch-scoped using the exact `current_membership_id()`/`current_member_role()` mechanism R2.0 already built and proved. | ⏳ Design must confirm the existing branch-scoped RLS policies extend cleanly to these tables with no new enforcement mechanism needed |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes** | Pure CRUD-plus-a-deterministic-routing-function over existing infrastructure. No CPU-bound work, no third-party call, no comparable argument to the extraction worker or optimiser's pre-authorised exceptions. Stays inside `apps/api` as a new `requests` module. | ✅ PASS |
| **VII. Money, Tax, Language from the Schema Up** | **Yes** | Every estimated line value and budget comparison is an explicit amount+currency pair, matching every prior chunk's money convention. New screens' strings come from `packages/i18n`, both languages, RTL-tested, per FR-005 (queue) and the request-creation/detail screens. | ⏳ Must confirm the request's estimated-value currency is drawn from the same currency as its source `landed_cost` row (never assumed to match tenant currency), consistent with R2.0 research.md R3 |

**Workflow gates**: specification precedes code ✅ (spec approved, all checklist items pass, zero
clarification markers after the value-estimation gap was resolved and folded into FR-015); stage
gates — same explicit recorded exception as R2.0 (ADR-010; this chunk proceeds under the same
project-owner override of the G1 → Phase 2 gate, not a fresh decision); delegated work reviewed ✅
(planned — every delegated diff reviewed against this plan and the constitution before it lands,
same discipline as chunks 4.2–4.6 and R2.0).

## Constitution Check — re-evaluated post-design (Phase 0/1 complete)

| Principle | Pre-design | Post-design |
|---|---|---|
| **I. Evidence Over Assertion** | ⏳ Must reuse price-history provenance, not an unaudited number | ✅ PASS — research.md R2 has the request line reuse the exact `last_paid` computation `offers/price_history.py` already performs, storing the source `landed_cost_id` (or null + an explicit incomplete-estimate flag) alongside the captured amount. |
| **II. Deterministic, Replayable Normalisation** | ⏳ Must specify a frozen value, not a live recompute | ✅ PASS — research.md R2 captures the estimate onto `purchase_request_line` at submission time (`estimated_unit_price_amount/currency`, `estimated_unit_price_source_landed_cost_id`, `estimated_at`); later price-history changes never alter an already-submitted request's routing or budget-check basis. |
| **III. Human Authority Over Automation** | ⏳ Must show no system-originated "approved" transition | ✅ PASS — research.md R3's state machine only ever transitions `pending → approved/rejected` via an explicit `decided_by`+`decided_at` pair on `approval_step`; the owner-fallback and delegation paths change WHO the pending step is assigned to, never insert a decision themselves. |
| **V. Tenant Isolation by Construction** | ⏳ Must confirm R2.0's RLS mechanism extends without a new mechanism | ✅ PASS — research.md R1 confirms the same `current_membership_id()`/`current_member_role()` policies apply verbatim to the four branch-relevant new tables; `threshold_rule` is tenant-wide/owner-managed (no branch-scoped read restriction needed, since routing configuration itself is not a requester/approver-visible per-branch secret). |
| **VII. Money, Tax, Language from the Schema Up** | ⏳ Must confirm currency is drawn from the source, not assumed | ✅ PASS — research.md R2 makes the captured estimate's currency exactly the source `landed_cost.total_currency` (or `total_currency` of the multiple contributing lines, each kept independent — no cross-currency summation of a multi-currency request; see R2's alternatives-considered for the single-request-single-currency simplification adopted for this release). |

No principle regressed from PASS to a violation during design. The one genuinely new mechanism
this chunk introduces beyond R2.0's precedent is deterministic threshold-based routing with
delegation and owner fallback — fully specified in research.md R3 and data-model.md's Approval
Step / Threshold Rule / Approval Delegation entities.

## Project Structure

### Documentation (this feature)

```text
specs/008-requests-approvals/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md         # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/api/
  src/procurepilot_api/modules/
    requests/            # NEW — purchase_request, purchase_request_line, approval_step,
                         #        threshold_rule, approval_delegation: CRUD, submit, withdraw,
                         #        approve/reject, routing resolution, value estimation,
                         #        GET/POST/PATCH endpoints under /requests and /approvals
  tests/{unit,integration,contract}/  # new test files for requests/; routing-resolution and
                                       #  value-estimation unit tests (pure functions, no DB)

apps/web/
  src/app/features/
    requests/            # NEW — request creation form, request list, request detail
    approvals/           # NEW — approval queue screen (list + inline approve/reject)
    settings/            # EXTENDED — owner-only threshold-rule management, alongside the
                         #        existing branch/cost-centre/budget lists
  tests/e2e/            # new Playwright specs for request creation, the approval queue,
                         #        threshold routing + delegation, budget-status warnings,
                         #        branch-scoped visibility extended to requests, and a11y
                         #        (English + Arabic) for all new screens

supabase/migrations/    # NEW — purchase_request, purchase_request_line, approval_step,
                         #        threshold_rule, approval_delegation, all with RLS
                         #        ENABLE+FORCE, plus branch-scoped policies per the
                         #        Constitution Check above
```

**Structure Decision**: Angular SPA + FastAPI modular monolith, unchanged, no new deployable. One
new `apps/api` module (`requests`) follows the established module pattern exactly (Pydantic
schemas, service.py, router.py, RBAC guards, not-found-not-forbidden, branch-scoped RLS reused
verbatim from R2.0). On the frontend, two new feature directories (`requests`, `approvals`) rather
than overloading an existing one — unlike R2.0's `settings` screen, this is a distinct workflow a
buyer and an approver use day-to-day, not an admin configuration surface, so it earns its own
navigation entry. Threshold-rule management is the one piece that IS admin configuration and so is
added to the existing `settings` screen rather than opening a third feature directory for it.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No unjustified violations. The one recorded exception is the same stage-gate deviation already in
effect for R2.0 (ADR-010), not a new one. No new deployable, no new external dependency, no
architectural pattern beyond what R2.0 already established; the only genuinely new mechanism is
deterministic threshold-based routing with delegation and owner fallback, which is fully specified
in research.md R3 and gets its own direct unit tests as a pure function, not an application-layer
shortcut around RLS or the audit log.

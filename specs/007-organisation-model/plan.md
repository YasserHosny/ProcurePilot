# Implementation Plan: Organisation Model

**Branch**: `007-organisation-model` | **Date**: 2026-08-22 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-organisation-model/spec.md`

## Summary

The first Phase 2 chunk (R2.0). Introduces the organisational structure — branches, cost
centres, and budgets — that every later Phase 2 release (purchase requests and approval routing
in R2.1, mobile in R2.2/R2.3) is built on top of, and extends the existing role model so
`branch_manager` and `approver` (already defined as roles in Phase 1, never scoped to anything
concrete) can be scoped to one or more actual branches. This chunk defines and stores budgets; it
does not check real spend against them — that is explicitly R2.1's job. No purchase requests,
approval workflow, mobile app, advanced optimiser, supplier scorecards, anomaly detection, or
reporting in this chunk.

## Technical Context

**Language/Version**: unchanged — Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged. No new library. This chunk is schema, RLS, and CRUD over the
existing FastAPI modular monolith and Angular SPA — no extraction, no matching, no async job, no
new deployable.

**Storage**: Supabase Postgres 17 (unchanged). New tables: `branch`, `cost_centre`, `budget`,
`branch_role_assignment` — all tenant-scoped, all requiring RLS `ENABLE`+`FORCE` per the uniform
pattern chunks 4.1–4.6 already established.

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core (unchanged). New:
the tenant-isolation suite gains cases for the four new tables (same discipline as every prior
chunk); a new integration suite proves branch-scoped visibility specifically — a member scoped to
Branch A cannot see Branch B's branch, cost-centre, or budget rows, distinct from (and in addition
to) cross-tenant isolation.

**Target Platform**: unchanged — Linux containers, evergreen browsers. No new deployable, no new
infrastructure dependency.

**Performance Goals**: standard CRUD-screen targets already established (API p99 < 500ms for
reads); no new performance surface — no recalculation-on-keystroke behaviour like Smart Compare,
no async job like extraction or export.

**Constraints**: every budget amount is an amount+currency pair (Principle VII, no new money
shape); branch and cost-centre hard-deletion is prohibited once any record depends on them —
deactivation/archiving is the only path (FR-009); branch-scoped access denial responds as
not-found, never forbidden, extending the existing cross-tenant convention to the
same-tenant/different-branch case (FR-008); every administrative action on these four tables is
audited (FR-012), matching the append-only `audit_event` pattern already in place.

**Scale/Scope**: pilot-sized, same volume as chunks 4.1–4.6. One new `apps/api` module
(`organisation`, covering branch/cost-centre/budget) plus an extension to the existing `members`
module (branch-scoped role assignment) — no new backend service. One new `apps/web` feature
(fills the existing empty `settings/` directory, a placeholder left unfilled since an earlier
chunk) plus an extension to the existing `team` feature (branch picker on role assignment).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | Partially | Branches, cost centres, and budgets are configuration data, not derived/inferred values — there is no extraction, confidence, or provenance to carry. What DOES apply: every creation, edit, deactivation, and archival MUST be audited (FR-012), so the *history* of the organisational structure itself is never silently lost. | ✅ PASS — no inference in this chunk; audit coverage is the applicable slice of this principle here |
| **II. Deterministic, Replayable Normalisation** | No | No normalisation or landed-cost computation in this chunk. Budgets are stored, not computed against real spend — that recomputation-and-replay concern belongs to R2.1, not here. | N/A for this chunk |
| **III. Human Authority Over Automation** | Partially | No purchasing or automation decision exists yet in this chunk to authorise — it is pure structural configuration. The applicable slice: role/branch assignment changes MUST take effect only for a member's next request, never retroactively rewriting an in-flight request's authority (edge case in spec.md). | ✅ PASS — no automation surface introduced |
| **IV. Every Insight Ends in an Action** | N/A | This chunk introduces no insight surface (no recommendation, no alert, no dashboard) — it is foundational configuration that later insight/action surfaces (R2.1 onward) will be built on top of. Not a violation: it is explicitly the load-bearing layer those later actions need, not a read-only surface competing with them. | N/A for this chunk |
| **V. Tenant Isolation by Construction** | **Yes — plus a new, finer-grained isolation layer** | `branch`, `cost_centre`, `budget`, and `branch_role_assignment` are all tenant-scoped and need RLS `ENABLE`+`FORCE`, following the uniform pattern from chunks 4.1–4.6. This chunk ALSO introduces branch-level visibility scoping *within* a tenant (FR-007/FR-008) — a new isolation axis alongside, not instead of, tenant isolation, and it must be proven by its own automated tests, the same way cross-tenant isolation already is. | ⏳ Design must show branch-scoped RLS policies (or an equivalent enforced-in-the-database mechanism) for the within-tenant case, not an application-layer filter alone — the constitution's "never rely on application-layer WHERE alone" applies with equal force to this new axis |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes — no new deployable, decided explicitly** | Pure CRUD over existing infrastructure. No CPU-bound work, no third-party API call, no comparable argument to the extraction worker or optimiser's pre-authorised exceptions. Stays inside `apps/api` as a new `organisation` module plus an extension to `members`. | ✅ PASS |
| **VII. Money, Tax, Language from the Schema Up** | Yes | Every `budget.amount` is paired with an explicit `budget.currency`, matching every prior chunk's money convention exactly — no bare numeric budget field. New screens' strings come from `packages/i18n`, both languages, RTL-tested, per FR-011. | ⏳ Must confirm at design time that budget currency is NOT implicitly assumed to match the tenant's own currency — a budget MAY reasonably be defined in the tenant's currency by default, but the field itself must remain explicit, not inferred, consistent with how quotation currency already works independently of tenant currency |

**Workflow gates**: specification precedes code ✅ (spec approved, all checklist items pass, zero
clarification markers); stage gates — **explicit recorded exception** ⚠ (this is the first Phase 2
chunk; the G1 → Phase 2 gate, a business/usage milestone — ≥10 verified savings, ≥8 paying
customers, accuracy targets against the Phase 0 benchmark — has not been independently evidenced
in this repo; the project owner explicitly chose to proceed without it on 2026-08-22, recorded in
`docs/architecture/adrs.md` ADR-010 per the constitution's own exception-granting mechanism, not
treated as the gate having been passed); delegated work reviewed ✅ (planned — every delegated diff
reviewed against this plan and the constitution before it lands, same discipline as chunks 4.2–4.6).

## Constitution Check — re-evaluated post-design (Phase 0/1 complete)

| Principle | Pre-design | Post-design |
|---|---|---|
| **V. Tenant Isolation by Construction** | ⏳ Design must show branch-scoped RLS enforced in the database, not application-layer alone | ✅ PASS — research.md R1 resolves this with a `current_membership_id()` SQL helper and RLS policies that check `branch_role_assignment` live, at query-evaluation time, exactly the same enforcement layer (RLS, not app-layer `WHERE`) tenant isolation itself already uses. data-model.md's RLS Summary table specifies the policy shape for all four new tables. |
| **VII. Money, Tax, Language from the Schema Up** | ⏳ Must confirm `budget.currency` is never implicitly assumed to match `tenant.currency` | ✅ PASS — research.md R3 makes this explicit: `budget.currency` is its own independently-set column, following the exact precedent (and the exact cautionary lesson from GitHub issue #5) already established for `quotation.currency`. |

No principle regressed from PASS to a violation during design. The one new mechanism this chunk
introduces — branch-scoped visibility — is fully specified in data-model.md's RLS Summary and
grounded in an explicit, justified design decision (research.md R1) rather than assumed.

## Project Structure

### Documentation (this feature)

```text
specs/007-organisation-model/
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
    organisation/       # NEW — branch, cost_centre, budget: CRUD, list, deactivate/archive,
                         #        orphan-flagging, GET/POST/PATCH endpoints
    members/            # EXTENDED — branch_role_assignment: assign/reassign a member's
                         #        branch-scoped role to one or more branches; existing
                         #        invitations.py/service.py/router.py gain branch-scoping
                         #        where role is branch_manager or approver
  tests/{unit,integration,contract}/  # new test files for organisation/; extended tests for
                                       #  members/ covering branch-scoped role assignment

apps/web/
  src/app/features/
    settings/           # NEW (fills an existing empty placeholder directory) — organisation
                         #        settings screen: branch list/CRUD, cost-centre list/CRUD,
                         #        budget list/CRUD, all three in one place per FR-011
    team/               # EXTENDED — change-role-dialog gains a branch picker when the
                         #        selected role is branch_manager or approver
  tests/e2e/            # new Playwright specs for the organisation settings screen (English +
                         #        Arabic/RTL), plus a branch-scoped-visibility spec proving a
                         #        branch_manager cannot see another branch's data

supabase/migrations/    # NEW — branch, cost_centre, budget, branch_role_assignment, all with
                         #        RLS ENABLE+FORCE, plus branch-scoped policies per the
                         #        Constitution Check above
```

**Structure Decision**: Angular SPA + FastAPI modular monolith, unchanged, no new deployable. One
new `apps/api` module (`organisation`) follows the established module pattern exactly (Pydantic
schemas, service.py, router.py, RBAC guards, not-found-not-forbidden). The existing `members`
module is extended rather than duplicated, since branch-scoped role assignment is a property of
an existing membership, not a new entity. On the frontend, the organisation settings screen fills
an already-reserved but empty `settings/` feature directory rather than inventing a new location;
`team/`'s existing change-role dialog is extended with a branch picker rather than building a
second, parallel role-assignment UI.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No unjustified violations. The one recorded exception is the stage-gate deviation noted above
(ADR-010) — an explicit, project-owner-granted exception per the constitution's own governance
section, not an undocumented one. No new deployable, no new external dependency, no architectural
pattern beyond what chunks 4.1–4.6 already established; the only genuinely new mechanism is
branch-scoped (within-tenant) row visibility, which Phase 1 has never needed before now, and which
the Constitution Check above already flags as needing its own enforced-in-the-database design
and its own proof tests, not an application-layer shortcut.

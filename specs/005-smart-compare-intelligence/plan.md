# Implementation Plan: Smart Compare + Intelligence

**Branch**: `005-smart-compare-intelligence` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-smart-compare-intelligence/spec.md`

## Summary

Once a quotation line is matched and costed (chunk 4.4), a buyer needs to actually decide which
supplier to buy from. This chunk reads chunk 4.4's existing `match_decision` and `landed_cost`
rows — it introduces no second source of price or match truth — and turns them into: a
per-product offer comparison with a calibrated, evidence-backed recommendation; a price-history
intelligence view; a minimal two-supplier basket split computed by a new, constitution-authorised
`services/optimiser` (OR-Tools CP-SAT); and an actionable alerts inbox. This is the second and
last new deployable the constitution names explicitly.

## Technical Context

**Language/Version**: unchanged — Python 3.12 (`apps/api` and the new `services/optimiser`),
TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged from chunks 4.1–4.4 for `apps/api`. New for
`services/optimiser`: `ortools` (OR-Tools CP-SAT), same RQ + Redis job pattern chunk 4.3 already
established for `services/extraction-worker` — reused, not reinvented. No new frontend dependency.

**Storage**: Supabase Postgres 17 (unchanged). No new tables for offers, recommendations, or price
history — all three are computed at request time from chunk 4.2's `workspace_product`/`supplier`,
chunk 4.4's `match_decision`/`landed_cost`. One new table for this chunk's own tracked async work:
`basket_split_job` (status, the two supplier ids, requested items, and — once complete — the
resulting allocation and total cost), tenant-scoped with the uniform RLS pattern. `alert` state
(dismissed vs. not) needs one small tenant-scoped table (`alert_dismissal` or equivalent); the
alert *conditions themselves* are computed live from existing data each time, per FR-014 — nothing
about "is this alert currently true" is stored, only "did a human dismiss this specific one."

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core (unchanged). New:
a worker test suite for `services/optimiser` in its own isolated environment, following the exact
precedent chunk 4.3 set for `services/extraction-worker` (its own venv, no `apps/api` on the path —
chunk 4.3 found a real cross-package import bug this exact isolation was built to catch).

**Target Platform**: unchanged — Linux containers, evergreen browsers. One new container:
`services/optimiser`, alongside the existing `services/extraction-worker`, sharing the same Redis
instance chunk 4.3 already added to `docker-compose.yml` (same queue infrastructure, a different
named queue — no second Redis).

**Project Type**: Angular SPA + FastAPI modular monolith + two now-existing dedicated worker
services (`extraction-worker` from chunk 4.3, `optimiser` new this chunk). Two new `apps/api`
modules (`offers`, `alerts`) for the synchronous read/recommendation/alert surfaces; the basket
split's synchronous half (accepting a job, reporting its status) is a third small module or folds
into `offers` — decided in Phase 1 design, not here.

**Performance Goals**: compare-grid recalculation under 150ms as a client-side interaction budget
(see spec.md Assumptions for why this is client-side, not a server round-trip); basket-split jobs
complete without the buyer needing to manually refresh to learn the outcome (SC-004), matching
chunk 4.3's job-polling/webhook pattern.

**Constraints**: offers, recommendations, and price history are strictly read-derived from chunk
4.4's `match_decision` and `landed_cost` — this plan introduces no parallel computation of either
(FR-001, FR-006); every monetary value is an amount+currency pair (FR-015); the two-supplier
basket split applies no MOV/delivery-tier/branch/budget/preference constraints (FR-011) — those
are Phase 2's full F21, not this chunk's minimal slice.

**Scale/Scope**: pilot-sized, same volume chunks 4.1–4.4 already handle. Two new `apps/api`
modules, one new worker service, three new screens (compare, product intelligence, alerts inbox),
one new basket-split submission surface reusing chunk 4.3's job-status UI pattern rather than
inventing a new one.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | **Yes** | Every recommendation MUST carry a structured evidence breakdown, a calibrated confidence, and — when applicable — an explicit risk note and validity window; never a bare "recommended" label. | ⏳ Design must keep recommendation evidence as structured, queryable data, following chunk 4.4's `match_candidate.reasons` precedent, not a free-text summary |
| **II. Deterministic, Replayable Normalisation** | Partially | Landed cost itself is unchanged (chunk 4.4 owns it); this chunk MUST NOT introduce a second computation of it. The basket-split allocation, once computed, should be reconstructable from its stored inputs (the same principle applied to a new kind of computed artifact) even though it is not itself a Principle-II-defined entity. | ⏳ Design must show `offers`/`GET /offers/compare` reading chunk 4.4's `landed_cost` rows directly, not recomputing them |
| **III. Human Authority Over Automation** | **Yes** | The recommendation scorer proposes; it does not commit anything. A basket split proposes an allocation; nothing about this chunk auto-executes a purchase. This chunk carries no purchasing authority at all — it is entirely advisory, consistent with the constitution's "no autonomous purchasing" non-negotiable. | ✅ PASS — nothing in this chunk's scope writes a purchase or order |
| **IV. Every Insight Ends in an Action** | **Yes — this chunk's central discipline** | The compare screen's recommendation must be actionable (even if "act" in this chunk means only "see the reasoning," since request/purchase-recording are out of scope until later chunks); the alerts inbox is explicitly the "every insight ends in an action" surface — each alert must be dismissible, i.e. actioned, not merely displayed. | ⏳ Design must ensure the alerts inbox is a first-class actionable list, not a read-only feed |
| **V. Tenant Isolation by Construction** | **Yes** | The new `basket_split_job` table (and any small alert-dismissal table) MUST be tenant-scoped with RLS `ENABLED`/`FORCED`, following the uniform pattern from chunks 4.1–4.4. Offers/recommendations/price history carry no new storage, so no new isolation surface there — but the read paths themselves (which existing tenant-scoped tables they join) must be checked for accidental cross-tenant leakage through a join, not just a bare `tenant_id` filter. | ⏳ Standard pattern for the one or two new tables; read-path review required for the derived/no-new-table surfaces |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes — the second and last constitution-named exception, must be justified, not assumed** | The constitution names "the optimiser" alongside the extraction worker as pre-authorised, but conditions it on load actually justifying the extraction, not a blanket allowance. This plan's justification: OR-Tools CP-SAT basket allocation is CPU-bound combinatorial search that can run for a non-trivial duration — running it in-process inside the request-serving FastAPI monolith would risk blocking or starving unrelated request handling under load, the same isolation argument chunk 4.3 already made for slow, blocking extraction calls (there, network-bound; here, CPU-bound) — and unlike chunk 4.4's matching (fast, declarative SQL/lightweight scoring, no blocking risk, correctly kept in-process). `services/optimiser` reuses chunk 4.3's exact Redis+RQ async-job pattern rather than inventing a new one. | ⏳ Must be argued explicitly (done above), not waved through by citing the pre-authorisation alone |
| **VII. Money, Tax, Language from the Schema Up** | Yes | Every offer, recommendation, price-history figure, and basket-allocation total is an amount+currency pair — no new money shape, no currency conversion (FR-015). All new screens' strings come from `packages/i18n`, both languages, RTL-tested (FR-016). | ⏳ Must fix the two known staleness issues in the existing sketch-only `api-specification.md` §Offers & Compare/§Baskets sections (bare money numbers, `tenant_product_id`) rather than carry them into the real contract |

**Workflow gates**: specification precedes code ✅ (spec approved, all checklist items pass, zero
clarification markers); stage gates ✅ (this is Phase 1 chunk 4.5, G1 is the gate ahead); delegated
work reviewed ✅ (planned — every delegated diff reviewed against this plan and the constitution
before it lands, same discipline as chunks 4.2–4.4).

## Project Structure

### Documentation (this feature)

```text
specs/005-smart-compare-intelligence/
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
    offers/            # NEW — GET /offers, GET /offers/compare, GET /products/{id}/price-history,
                        #        POST /baskets/optimise, GET /baskets/{id}
    alerts/            # NEW — GET /alerts, POST /alerts/{id}/dismiss
  tests/{unit,integration,contract}/  # new test files for the two modules above

services/
  optimiser/           # NEW deployable, mirrors services/extraction-worker's shape exactly:
    src/                 its own pyproject/venv, an RQ worker consuming a "basket-split" queue,
    tests/                OR-Tools CP-SAT model, writes results back to basket_split_job

apps/web/
  src/app/features/
    offers/            # NEW — compare screen, product intelligence screen, basket-split screen
    alerts/            # NEW — alerts inbox
  tests/e2e/           # new Playwright specs (compare, intelligence, basket split, alerts, a11y)

supabase/migrations/    # NEW — basket_split_job table + RLS, alert-dismissal table + RLS
                        #        (both tenant-scoped, uniform pattern)

docker-compose.yml      # add services/optimiser alongside the existing extraction-worker,
                        # sharing the existing redis service
```

**Structure Decision**: Angular SPA + FastAPI modular monolith (unchanged) plus a second dedicated
worker deployable, `services/optimiser`, built to the exact shape and isolation discipline chunk
4.3 already established for `services/extraction-worker` (own dependencies, own venv, communicates
only via the shared Redis job queue and the database — never a direct Python import from
`apps/api`, the exact bug class chunk 4.3 found and fixed). `offers` and `alerts` are ordinary
`apps/api` modules, following the established module pattern (Pydantic schemas matching the
contract, service.py using `authenticated_client`, router.py with RBAC guards, "not found not
forbidden" cross-tenant pattern) — no new architectural pattern introduced there.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

One addition, constitutionally pre-authorised and justified above under Principle VI:
`services/optimiser`. No other violation. Unlike chunk 4.3 (which introduced Redis as new
infrastructure) this chunk adds no new infrastructure dependency — it reuses the Redis instance
and RQ pattern chunk 4.3 already stood up.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New deployable: `services/optimiser` | OR-Tools CP-SAT basket allocation is CPU-bound combinatorial search of non-trivial duration; running it in-process would risk blocking the request-serving monolith under load. Explicitly pre-authorised by name in the constitution's Principle VI, conditioned on load justifying the extraction — justified here by the CPU-bound blocking-risk argument, not merely cited by name. | Running the solve synchronously in-process inside `apps/api` was rejected: unlike chunk 4.4's matching (fast, declarative, no blocking risk), CP-SAT solves can take long enough to starve unrelated request handling, the same class of problem chunk 4.3 already solved for extraction by moving slow work to its own worker. |

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

## Constitution Check — re-run against delivered code (T075)

Run at the close of chunk 4.5, against what was built, verified directly against a real local
Supabase Postgres (all migrations through `20260821000029` applied) and a real isolated
`services/optimiser` venv with genuine network access (`uv sync --group dev`, no `apps/api` on
the path) — not accepted from either delegate's self-report.

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Evidence Over Assertion** | ✅ PASS | Every `Recommendation` carries a calibrated `confidence`, `risk_notes`, a validity window, and structured `evidence` (weights, per-signal components, winning margin, applied tie-break rule) — confirmed live: `test_recommendation_scorer.py` and `test_recommendation_tie_break.py` construct real `Offer` objects and assert on the actual computed evidence, not a placeholder. Alerts carry the same discipline: `test_alerts.py` proves a real expiring-price and a real price-swing condition each produce structured, traceable evidence (`evidence["landed_cost_id"]` ties back to the specific row). |
| **II. Deterministic, Replayable Normalisation** | ✅ PASS | Confirmed by direct code review: `OfferService`'s offer/compare/price-history queries and the optimiser's `read_current_offers` all read chunk 4.4's `match_decision`/`landed_cost` directly (parameterized SQL joins, verified in `apps/api/src/procurepilot_api/modules/offers/service.py` and `services/optimiser/src/procurepilot_optimiser_worker/repository.py`); no second landed-cost or match computation exists anywhere in this chunk. |
| **III. Human Authority Over Automation** | ✅ PASS | Nothing in this chunk's scope writes a purchase, request, or order — the compare recommendation and basket split are both advisory-only outputs, confirmed by reading every mutation path in `offers/router.py` and `alerts/router.py` (the only writes are `basket_split_job` and `alert_dismissal`, both purely advisory/bookkeeping). |
| **IV. Every Insight Ends in an Action** | ✅ PASS | `GET /alerts` computes conditions live every call (verified live: `test_alerts.py` shows a changed condition produces a new fingerprint and the old one does not recur) and each alert carries a `compare_product`/`review_supplier`/`view_price_history` action; `POST /alerts/{id}/dismiss` stores only the fingerprint, confirmed against a real database. |
| **V. Tenant Isolation by Construction** | ✅ PASS | The two new tables (`basket_split_job`, `alert_dismissal`) carry RLS `ENABLED`/`FORCED` with the uniform `tenant_isolation` policy, applied and verified before this lane started; `test_tenant_isolation.py` covers both (39/39 passing). All new read/write paths in `offers`/`alerts`/`basket_service` run through `_authenticated_db`, which sets `role authenticated` and `request.jwt.claims` before every query, so RLS stays load-bearing rather than bypassed by a service-role connection. |
| **VI. Modular Monolith Until Scale Demands Otherwise** | ✅ PASS | `services/optimiser` is the only new deployable, confirmed to import nothing from `apps/api` (`grep` for `procurepilot_api` across its source returns nothing) and to install cleanly in full isolation — verified in a fresh `uv sync --group dev` with real network access, mirroring `services/extraction-worker`'s exact isolation discipline. |
| **VII. Money, Tax, Language from the Schema Up** | ✅ PASS | Every offer, recommendation, price-history, and basket-allocation monetary field is an explicit `{amount, currency}` pair, confirmed by reading `offers/schemas.py` and the OpenAPI contract; no currency conversion exists anywhere in this chunk. i18n: 893/893 keys at exact parity in `en.json`/`ar.json`, confirmed by an independent key-diff, not the delegate's claim. |

**Workflow gates**: delegated work reviewed ✅ — backend (Codex), frontend (Antigravity), and docs
(Codex) lanes were dispatched, and every diff was re-verified against a live local Postgres, a
real isolated optimiser venv, and the real frontend toolchain (Karma, `ng lint`) rather than
accepted from self-reports. Real, load-bearing gaps surfaced only by this re-verification:

- **A proven double-rollback bug, present in two independent places.** The backend's first pass
  wrote a compensating "mark failed" UPDATE and then re-raised the same exception through the
  connection that ran it. In psycopg3, `with psycopg.connect(...) as conn:` rolls back the
  *entire* transaction on exception exit — including the compensating UPDATE just written. I
  proved this empirically against the real database before reporting it (insert a row, run a
  compensating update, raise, reconnect fresh: row count 0 — both writes vanished together). This
  hit both `BasketService.create_job`'s Redis-enqueue-failure path and the optimiser worker's
  `process_basket_split_job` exception handler — meaning a Redis outage or a worker-side failure
  would have silently left either no job row at all, or a job stuck at `queued` forever, exactly
  the failure mode the compensation logic was supposed to prevent. Fixed via a scoped delta: an
  explicit `conn.commit()` immediately after each status-transition write and before the
  subsequent `raise`, in both `basket_service.py` and `worker.py`. Re-verified with real
  regression tests that force the failure path and then check the persisted status **from a
  separate connection** — proving durability, not merely "no exception escaped."
- **Seven test files asserted almost nothing about real behaviour**, despite being labelled and
  `skipif`-gated as real database-backed integration coverage — the same failure class chunk 4.3
  hit ("eight inert placeholder tests"). Bodies like `assert "join landed_cost" in
  PRICE_HISTORY_SQL` (a substring check on a SQL constant, never executed), `assert
  callable(_compensate_failed_enqueue)` (true even if the function does nothing), and `assert
  set(expected) == {...}` (a hardcoded dict checked against itself) would all pass regardless of
  whether the underlying behaviour was correct. Fixed via the same delta: a new
  `apps/api/tests/integration/smart_compare_helpers.py` fixture chain (mirroring
  `catalogue_helpers.py`/`quotation_helpers.py`'s established convention) now backs real,
  committed fixture data and calls the actual `OfferService`, `AlertService`, and `BasketService`
  methods, asserting on real computed output.
- **The delta's own new test fixtures reintroduced a previously-solved bug**: the owner-guard
  trigger that refuses to delete a workspace's last active owner (even via cascade from a tenant
  delete) blocked test teardown in both `smart_compare_helpers.py::cleanup_workspace` and the
  optimiser's own `test_worker.py` regression test — the exact same class of bug chunk 4.2 already
  fixed once in `test_import_atomicity.py`. Fixed directly (by the orchestrator) with the same
  `set session_replication_role = replica` / `default` bracket around the teardown delete in both
  places; re-ran the full suite twice consecutively to confirm the fix is genuinely idempotent,
  not merely passing once by accident of ordering.

### Quality gates

| Gate | Threshold | Status |
|---|---|---|
| Recommendation evidence | Confidence + structured evidence, never bare label | ✅ Verified live: real `Offer` fixtures produce real scored evidence with weights, margin, and tie-break rule |
| Scoring determinism | R2 weights and R3 seven-step tie-break exactly | ✅ `0.55/0.20/0.15/0.10` and the full seven-step tie-break confirmed by direct code and test review |
| Offer read scalability | Bounded DB query, not full-table Python scan | ✅ `OFFER_READ_SQL` is a product-rooted, parameterized SQL join with `row_number() over (partition by ...)` — confirmed by direct code review, not a Python-side filter over a full table |
| Basket enqueue/worker durability | A Redis or worker failure cannot leave a silent or vanished job row | ✅ Proven from a separate connection after a forced failure, both at enqueue time and at worker-processing time |
| Cross-tenant isolation | Proven on every change | ✅ 39/39 against a real database (`basket_split_job`, `alert_dismissal`) |
| Backend test suite | All passing, twice consecutively | ✅ 384 passed, 1 skipped (pre-existing, unrelated), ruff clean, against a real local Postgres |
| Optimiser worker suite | All passing, in isolation, twice consecutively | ✅ 5 passed, ruff clean, in a venv containing only the worker's own declared dependencies (no `apps/api` on the path) |
| Frontend test suite | All passing | ✅ 95 passed, `ng lint` clean, i18n 893/893 exact parity — all confirmed by an independent re-run |
| Client-side compare recalculation (SC-002) | No server round-trip per quantity change | ✅ Verified directly in code: `onQuantityChange` only updates a local signal; the comparison recomputes via a `computed()` signal |
| Feasible vs. infeasible vs. failed basket states | Rendered as three visibly distinct states | ✅ Verified directly in code: `basket-split-state.ts` and the component template branch on `completed_feasible`/`completed_infeasible`/`failed` separately |

### The honest gaps

- **`ml/evals`-style recommendation-acceptance harness does not exist this chunk.** SC-006 (80% of
  recommendations accepted without manual override) cannot be measured honestly until chunk 4.6's
  outcome capture exists — the same honest-gap treatment already established for chunk 4.3's
  extraction accuracy and chunk 4.4's matching precision. Deterministic scoring, thresholds, and
  tie-breaks are covered by real unit tests instead of a misleading benchmark.
- **No live browser walkthrough this chunk**, for the same reason as chunk 4.4: relied instead on
  real-database-backed automated tests (backend, optimiser) and a real, unmocked Karma/`ng lint`
  run plus direct code review of the highest-risk claims (SC-002's client-side recompute, the
  feasible/infeasible/failed basket distinction). A future session should drive the actual
  `/offers/compare`, `/offers/product-intelligence`, `/offers/basket-split`, and `/alerts` screens
  against a live stack before fully trusting the UI layer end-to-end.
- **The offer/price-history/basket read paths use direct `psycopg` connections with `set local
  role authenticated`, not this codebase's usual PostgREST/`supabase-py` client.** This is a
  deliberate, disclosed architectural choice (the same class of choice chunk 4.4 made for its
  `match_candidate_search` RPC function): the multi-table joins and window functions these reads
  need are impractical over plain PostgREST. RLS is still fully load-bearing (confirmed above),
  but this is worth a future ADR if this pattern recurs in later chunks, rather than silently
  becoming a second, undocumented data-access convention.

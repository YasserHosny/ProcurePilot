# ProcurePilot — Development Guidelines

Last updated: 2026-10-03 · Active feature: none mid-build. Every numbered spec, `001` through
`021`, is complete and merged — including `018-forecasting-reorder` and
`019-supplier-risk-negotiation`, both of which were already fully built and shipped (as "R4.0"
and "R4.1" in commit history) despite their `specs/` folders lagging behind: `018` had no
`tasks.md` and `019` had neither a `plan.md` nor a `tasks.md` until 2026-10-03, when both were
reconstructed retroactively against the real shipped code (see the dated verification notes
inside each). `019`'s reconstruction found one real, still-open requirement gap — FR-011A's
three-signal service-risk formula — tracked in its own `tasks.md` (T019), not fixed yet. There is
currently no visible not-yet-started spec in `specs/`; the next feature has not been scoped.

ProcurePilot turns fragmented supplier information into trusted, comparable purchasing
decisions and proves the money saved. Read `.specify/memory/constitution.md` before writing
code — it is binding, not advisory.

## Non-negotiables

1. **Tenant isolation is enforced in the database.** Every tenant-scoped table carries
   `tenant_id` with `ENABLE` + `FORCE` row-level security, and policies supply both `USING`
   and `WITH CHECK`. Never rely on an application-layer `WHERE tenant_id = ...` alone.
2. **Tenancy comes from the verified JWT claim**, never from a path, query, or header.
3. **A cross-tenant read returns "not found"**, never "forbidden" — do not leak existence.
4. **No secrets in the repo.** Config via environment; `.env.example` committed, `.env` ignored.
   gitleaks blocks the PR.
5. **Every user-facing string comes from `packages/i18n`** (en + ar). No hardcoded copy.
6. **Every monetary value stores an explicit currency.** No bare numbers for money, ever.
7. **`audit_event` is append-only.** No `UPDATE`, no `DELETE`, for any role.
8. **No autonomous purchasing.** Automation prepares and routes; a human authorises.

## Active technologies

**Backend** — Python 3.12 · FastAPI 0.115.6 · Uvicorn 0.34.0 · Pydantic v2 +
pydantic-settings · python-jose 3.3.0 · httpx 0.28.1 · SlowAPI 0.1.9 · supabase-py 2.11.0

**Web** — TypeScript 5.6 · Angular 19 · Angular Material + CDK · RxJS · @ngx-translate/core ^16 +
http-loader (runtime i18n) · Zod

**Data** — Supabase Postgres 17 (`pgvector`, `pg_trgm`) · Supabase Auth · Supabase Storage ·
Redis + RQ (job queues: extraction, basket-split, exports, report scheduling, push notifications —
`config.py`'s `redis_url`).

**Infra** — Docker · Nginx · bunny.net Magic Containers · GitHub Actions · Terraform

**Testing** — pytest 8.3.4 + pytest-asyncio 0.25.2 · httpx TestClient · Karma 6.4 / Jasmine
5.4 · Playwright ^1.60 · ruff · axe-core · gitleaks

**Mobile** — Flutter. Shipped, not a placeholder: auth (sign-in, biometric, device registration),
home, purchase requests, approvals, low-stock reporting, delivery confirmation and quality-issue
photos, push notifications. 31 Dart source files, 22 test files (`apps/mobile/lib/features/`).

## Project structure

```text
apps/api/          FastAPI modular monolith — the only backend deployable
  src/procurepilot_api/modules/{auth,tenants,members,health}/
  migrations/      versioned SQL, applied via Supabase CLI
  tests/{unit,integration,contract}/
apps/web/          Angular 19 SPA
  src/app/{core,layout,features}/
apps/mobile/       Flutter app — shipped (auth, requests, approvals, low-stock, delivery, push)
packages/          domain-types · ui · validation · i18n
services/          extraction-worker (quotation extraction) · optimiser (basket-split solver) —
                   both real, independently deployed workers, not placeholders
ml/                evals/product_matching (precision/recall/ECE against a held-out benchmark) ·
                   benchmarks/product_matching (benchmark format) — real, not placeholders
infra/             docker · nginx · terraform
specs/             Speckit feature specs, plans, tasks
docs/              product, architecture, roadmap, quality, operations
```

## Commands

```bash
docker compose up --build   # whole stack: api + web + local Supabase
pnpm db:migrate             # apply versioned SQL migrations
pnpm db:seed                # reference data + a platform invitation token
pnpm test                   # everything
pnpm test:api               # pytest
pnpm test:web               # Karma + Jasmine
pnpm test:e2e               # Playwright
pnpm test:isolation         # cross-tenant isolation — run after any tenancy change
pnpm test:a11y              # axe-core, zero violations
pnpm lint                   # ruff + Angular CLI lint
```

## API conventions

Base path `/api/v1` · `Authorization: Bearer <supabase_jwt>` · tenant resolved server-side
from the token · cursor pagination, `limit` capped at 100 · `Idempotency-Key` on mutations ·
error envelope `{code, message, details, trace_id}`.

Contract: `specs/001-platform-foundation/contracts/auth-tenant.openapi.yaml`.

## Code style

**Python** — ruff-formatted, full type hints, Pydantic models at every boundary. Modules under
`modules/` own their routers, schemas, and services; cross-module access goes through defined
interfaces, not shared internal state.

**TypeScript** — strict mode, standalone components, signals for local state, RxJS for streams.
No `any`. Shared validation schemas come from `packages/validation`.

**SQL** — one versioned file per migration, forward-only, never edited after merge. Every new
tenant-scoped table ships with its RLS policy in the same migration.

**RTL** — use CSS logical properties (`margin-inline-start`, not `margin-left`). Test both
directions.

## Where to look

| Question | File |
|---|---|
| Why does this exist, what ships when | `docs/roadmap/procurepilot_roadmap.md` |
| What are the binding rules | `.specify/memory/constitution.md` |
| What am I building now | `specs/001-platform-foundation/spec.md` |
| How was it decided | `specs/001-platform-foundation/research.md` |
| Tables, RLS, state transitions | `specs/001-platform-foundation/data-model.md` |
| How do I run it | `specs/001-platform-foundation/quickstart.md` |
| Stack decisions and their rationale | `docs/architecture/adrs.md` |
| Field-level entity definitions | `docs/architecture/data-dictionary.md` |
| Test expectations | `docs/quality/test-strategy.md` |

## Current phase

Every spec through `021-rfq-sourcing-autonomy` is complete and merged (`specs/*/tasks.md` fully
checked, or verified against actual code where the checkboxes themselves were stale — see the
dated notes inside `specs/004-matching-normalisation/tasks.md` and
`specs/008-requests-approvals/tasks.md` for examples of that verification). That includes:
Phase 4 (Predictive Procurement, R4.0–R4.3 — RFQ sourcing with guarded auto-preparation, passed its
T047 live hosted walkthrough including a guardrail firing autonomously on hosted, evidence
`docs/quality/r4.3-release-evidence.md`); `016-order-tracking-three-way-match`, including its final
User Story 4 (draft purchase orders generated from an approved request, with edit/cancel) merged
2026-10-02; and a follow-on matching-quality round merged the same day: fuzzy (similarity-only)
candidates no longer auto-accept by default, a real Bedrock embedding provider exists behind a
still-off-by-default switch, and score calibration was investigated and found genuinely not
feasible yet — the hosted database has only 9 confirmed human match decisions (1 of them fuzzy),
far short of the 500+ labelled benchmark `specs/004-matching-normalisation/research.md` R5/R10
requires before fitting anything; the existing eval harness (`ml/evals/product_matching/`) already
reports this honestly rather than faking a number.

Guardrails are evaluated at match-decision time, not email capture (ADR-019). The G3 stage gate
remains unmet on operational metrics (pilot accounts, 180-day history, integration-sourced quotes).

`018-forecasting-reorder` and `019-supplier-risk-negotiation` are also both complete and merged
(2026-10-03 finding: both were already fully shipped, just undocumented in `specs/` — `018` had
no `tasks.md`, `019` had neither a `plan.md` nor a `tasks.md`; both were reconstructed
retroactively against the real code, see the dated verification notes in each). `019`'s
reconstruction surfaced one real open gap: FR-011A requires the negotiation brief's
`service_performance` risk to be `max(reliability_risk, non_matched_qualifying_three_way_rate,
quality_incidents_per_qualifying_completed_order)`; the shipped code only computes the reliability
component — `supplier_iq_v2.py` never queries `three_way_match` or `delivery_quality_issue` at
all, so service risk can be understated for a supplier whose real problem is mismatches or quality
incidents rather than reliability specifically. Tracked as `specs/019-supplier-risk-negotiation/
tasks.md` T019, not yet fixed.

With `018`/`019` closed out, there is no visible not-yet-started spec anywhere in `specs/` right
now — the next feature has not been scoped.

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

## Active Technologies
- unchanged — Python 3.12 (backend), TypeScript 5.6 / Angular 19 (web), SQL + unchanged from chunk 4.1. One addition under consideration for CSV (002-catalogue-suppliers)
- Supabase Postgres 17 via the Supabase CLI local stack. Migrations continue in (002-catalogue-suppliers)
- unchanged — Python 3.12 (`apps/api` and the new `services/extraction-worker`), + unchanged from chunks 4.1–4.2 for `apps/api`, plus a Redis client (003-quotation-inbox-extraction)
- Supabase Postgres 17 (unchanged) for `document`, `quotation`, `quotation_line`, (003-quotation-inbox-extraction)
- unchanged — Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (web), SQL + unchanged. No new library. This chunk is schema, RLS, and CRUD over the (007-organisation-model)
- Supabase Postgres 17 (unchanged). New tables: `branch`, `cost_centre`, `budget`, (007-organisation-model)
- unchanged — Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (web), SQL + unchanged. No new library. `dateutil.relativedelta` (already a (008-requests-approvals)
- Supabase Postgres 17 (unchanged). New tables: `purchase_request`, (008-requests-approvals)
- Unchanged — `apps/api`: Python 3.12; `apps/mobile`: Dart/Flutter (stable + `apps/api` gains no new dependency — the new endpoints are ordinary (010-mobile-approvals-receipt)
- Supabase Postgres 17 (unchanged). New columns on `purchase_request` for the delivery (010-mobile-approvals-receipt)
- Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) — + FastAPI (existing), `httpx` (existing, already used for outbound HTTP — (014-accounting-integration)
- Supabase Postgres 17 (unchanged). New tables: `accounting_connection`, (014-accounting-integration)
- Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) — + FastAPI (existing), `httpx` (existing — sufficient for Square's plain (015-pos-inventory-integration)
- Supabase Postgres 17 (unchanged). New tables: `pos_connection`, (015-pos-inventory-integration)
- Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) — no new provider: question
  understanding reuses the existing Bedrock/Claude client (ADR-004/ADR-014), extended with a new
  `analyst` module (020-grounded-procurement-analyst)
- Supabase Postgres 17 (unchanged). New tables: `analyst_conversation`, `analyst_turn`,
  `analyst_turn_citation` (020-grounded-procurement-analyst)
- Python 3.12 (`apps/api`), TypeScript 5.6 / Angular 19 (`apps/web`) — Mailgun Messages API for
  outbound sending (new, ADR-018 — reuses the existing inbound Mailgun vendor relationship from
  003-quotation-inbox-extraction rather than adding a second one); no new LLM usage (021-rfq-sourcing-autonomy)
- Supabase Postgres 17 (unchanged). New tables: `rfq`, `rfq_recipient`, `rfq_response`,
  `auto_preparation_guardrail`, `auto_preparation_event`; new column `supplier.contact_email`
  (021-rfq-sourcing-autonomy)

## Recent Changes
- 2026-10-02: 016-order-tracking-three-way-match's final story shipped — draft purchase orders
  generated from an approved request, with edit and cancel (PR #61). Same day: fuzzy product
  matches no longer auto-accept by default (PR #59), a real Bedrock embedding provider landed
  behind an off-by-default switch (PR #62), and CI's date-bomb test fixture plus two dependency
  advisories were fixed (PR #60).
- 021-rfq-sourcing-autonomy: R4.3 merged (PR #26) plus T047 live-walkthrough fixes (PRs #28–#40):
  real Mailgun inbound payload parsing, deployed email-ingestion worker, document source-channel
  and empty-extraction review fixes, guardrail pack-size normalisation, and guardrail evaluation
  moved to match-decision time (ADR-019); guardrail settings UI + compare-view explanations
  (T037/T038)
- 020-grounded-procurement-analyst: R4.2 merged to main (PR #25) — grounded, cited
  question-answering over tenant data, all four user stories plus Polish complete
- 002-catalogue-suppliers: Added unchanged — Python 3.12 (backend), TypeScript 5.6 / Angular 19 (web), SQL + unchanged from chunk 4.1. One addition under consideration for CSV

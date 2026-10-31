# ProcurePilot — Development Guidelines

Last updated: 2026-10-31 · Active work: Egypt and Saudi pilot readiness. Specs `001`–`021`, `023`
(RFQ-aware matching) and `024` (RFQ basket split) have shipped to `main`; `022-home-currency-readiness`
is merged with three tasks open (T015 real-quote extraction run, T018 mobile screenshots, T020 full test
pass). Since 2026-10-15 most changes have come from the hosted demo tenants («مطاعم سند»,
«مطاعم رواق»; `docs/gtm/demo-tenant/README.md`) and their flow reviews rather than from a new spec. No
new spec has been scoped; `docs/gtm/gtm-execution-plan.md` tracks pilot work.

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

**Web** — TypeScript 6.0 · Angular 22 · Angular Material + CDK · RxJS · @ngx-translate/core ^18 +
http-loader (runtime i18n) · Zod

**Data** — Supabase Postgres 17 (`pgvector`, `pg_trgm`) · Supabase Auth · Supabase Storage ·
Redis + RQ (job queues: extraction, basket-split, exports, report scheduling, push notifications —
`config.py`'s `redis_url`).

**Infra** — Docker · Nginx · bunny.net Magic Containers · GitHub Actions · Terraform

**Testing** — pytest 8.3.4 + pytest-asyncio 0.25.2 · httpx TestClient · Karma 6.4 / Jasmine
5.4 · Playwright ^1.60 · ruff · axe-core · gitleaks

**Mobile** — Flutter. Shipped, not a placeholder: auth (sign-in, biometric, device registration),
home, purchase requests, approvals, low-stock reporting, delivery confirmation and quality-issue
photos, push notifications (`apps/mobile/lib/features/`).

## Project structure

```text
apps/api/          FastAPI modular monolith — the only backend deployable
  src/procurepilot_api/modules/   30 modules (auth, tenants, catalogue, quotations, matching,
                   offers, requests, orders, rfq, analyst, ...) — `ls` for the current list
  src/procurepilot_api/workers/   background workers run from the API image (email ingestion, exports,
                   digests, report scheduling, accounting/POS sync, webhooks, catalogue and offer
                   refresh) and operator CLIs (`requeue_extraction`, `requeue_email_ingest`)
  tests/{unit,integration,contract}/
supabase/migrations/  versioned SQL, applied via Supabase CLI (apps/api/migrations/ is a pointer)
apps/web/          Angular 22 SPA
  src/app/{core,layout,features}/
apps/mobile/       Flutter app — shipped (auth, requests, approvals, low-stock, delivery, push)
packages/          domain-types · ui · validation · i18n
services/          extraction-worker (quotation extraction) · optimiser (basket-split solver) —
                   both real, independently deployed workers; matching-worker/ is an empty
                   placeholder (matching runs inside apps/api)
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
pnpm db:check-privileges    # read-only: migrations applied, client-role grants as intended
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

**Web dependencies** — CI installs `apps/web` from its own `apps/web/pnpm-lock.yaml`
(`--ignore-workspace --frozen-lockfile`), not the root lockfile: after changing web dependencies,
regenerate both or CI fails. `apps/web/i18n` is a symlink to `packages/i18n` because Angular 22
refuses assets outside the workspace. Components carry `ChangeDetectionStrategy.Eager` (kept by the
Angular 22 upgrade, a lint warning); move one to OnPush only when its state is signals.

**Database connections** — open every Postgres connection through `procurepilot_api.db.connect`
(or the worker's own `db.connect`): it sets `prepare_threshold=None`, which Supabase's
transaction-mode pooler needs (PR #87). A bare `psycopg.connect` fails there with
`DuplicatePreparedStatement`. Deploys never run migrations — apply them to hosted with
`pnpm db:migrate` (which ends with `pnpm db:check-privileges`) and check with `supabase migration list`.

**Quantities** — request, RFQ and PO quantities are in the purchasing unit (pack) and prices are
per pack; base-unit conversion is only for cross-supplier comparison (ADR-020).

**SQL** — one versioned file per migration, forward-only, never edited after merge. Every new
tenant-scoped table ships with its RLS policy in the same migration.

**RTL** — use CSS logical properties (`margin-inline-start`, not `margin-left`). Test both
directions.

## Jira tracking (standing rule, owner 2026-10-22; Scrum since 2026-10-24)

Keep Jira space `PPS` (Scrum, board 1) up to date with whatever is being worked on: GTM, ops,
demo findings and code alike (site, cloudId and the plan-ID → key map in
`docs/gtm/gtm-execution-plan.md` §1–2). `PP` is retired; its `PP-n` keys redirect to `PPS`.

- Work with no PPS task gets one before you stop. Put the plan ID in the summary (e.g. `[P-8] …`)
  and add the key to the plan file's key map. New tasks go to the backlog; the owner sets sprint
  scope at planning (two-week sprints, Sunday to the second Thursday).
- On every change of state, add a dated **Progress** comment: what is done (PR numbers), what is
  left, and who owns it.
- Status is the board column: To Do → In Progress → In Review (PR open) → Done. Link
  dependencies with *Blocks*.
- The Atlassian connector often times out but still writes. Re-read before retrying, so you don't
  create duplicates.

## Where to look

| Question | File |
|---|---|
| Why does this exist, what ships when | `docs/roadmap/procurepilot_roadmap.md` |
| What are the binding rules | `.specify/memory/constitution.md` |
| What am I building now | `docs/gtm/gtm-execution-plan.md` (open work) · `specs/022-home-currency-readiness/tasks.md` · `specs/023-rfq-aware-matching/tasks.md` · `specs/024-rfq-basket-split/tasks.md` |
| How was it decided | `specs/001-platform-foundation/research.md` |
| Tables, RLS, state transitions | `specs/001-platform-foundation/data-model.md` |
| How do I run it | `specs/001-platform-foundation/quickstart.md` |
| Stack decisions and their rationale | `docs/architecture/adrs.md` |
| Field-level entity definitions | `docs/architecture/data-dictionary.md` |
| Test expectations | `docs/quality/test-strategy.md` |

## Current phase

Specs `001`–`021`, `023` and `024` are complete and merged. The open spec work is `022`'s three tasks
(top of this file) and a few `023`/`024` tasks left open on purpose (below). The next feature has not
been scoped. For what shipped when, read `git log` and the PRs.

- Some `tasks.md` boxes stay open on purpose: `specs/018-forecasting-reorder/tasks.md` T011, T016,
  T019, T020, T024 (tests never written). Tick them only with that evidence. In `023`, T027 (recorded
  Azure DI fixtures), T030, T033 and T034 are open; in `024`, T002 is.
- Match decisions are corrected by supersession, never updated: read `current_match_decision` for "the
  line's match" and `current_landed_cost` for a decision's cost (ADR-022, ADR-021). An RFQ split is one
  request group approved as one (ADR-023). The split is unreachable on a workspace whose guardrail
  is enabled (W2, PPS-148).
- `main` requires «Regenerate and diff» (docs screenshots drift) as well as the other checks; demo-video
  media is in Git LFS (`docs/gtm/video`), so pulls there need `--exclude=""`.
- Landed cost is on rule `landed-cost-v2` (ADR-021: VAT-inclusive quotes). Earlier rows stay v1;
  readers pick the latest offer per supplier across rule versions.
- Match-score calibration is not feasible yet: hosted has a handful of confirmed human match
  decisions, far short of the 500+ labelled benchmark `specs/004-matching-normalisation/research.md`
  R5/R10 requires. `ml/evals/product_matching/` reports this; keep it that way.
- Guardrails are evaluated at match-decision time, not email capture (ADR-019).
- The G3 stage gate is unmet on operational metrics (pilot accounts, 180-day history,
  integration-sourced quotes).

<!-- MANUAL ADDITIONS START -->
<!-- MANUAL ADDITIONS END -->

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues on YasserHosny/ProcurePilot (via `gh`). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one root `GLOSSARY.md`; ADRs live in `docs/architecture/adrs.md`. See `docs/agents/domain.md`.

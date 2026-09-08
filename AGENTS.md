# ProcurePilot — Development Guidelines

Last updated: 2026-08-20 · Active feature: `001-platform-foundation`

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

**Data** — Supabase Postgres 17 (`pgvector`, `pg_trgm`) · Supabase Auth · Supabase Storage.
No Redis yet — deferred to chunk 4.3 (see `specs/001-platform-foundation/research.md` R7).

**Infra** — Docker · Nginx · bunny.net Magic Containers · GitHub Actions · Terraform

**Testing** — pytest 8.3.4 + pytest-asyncio 0.25.2 · httpx TestClient · Karma 6.4 / Jasmine
5.4 · Playwright ^1.60 · ruff · axe-core · gitleaks

**Mobile** — Flutter, placeholder only until Phase 2.

## Project structure

```text
apps/api/          FastAPI modular monolith — the only backend deployable
  src/procurepilot_api/modules/{auth,tenants,members,health}/
  migrations/      versioned SQL, applied via Supabase CLI
  tests/{unit,integration,contract}/
apps/web/          Angular 19 SPA
  src/app/{core,layout,features}/
apps/mobile/       placeholder (Phase 2)
packages/          domain-types · ui · validation · i18n
services/          placeholders only — no code until chunk 4.3+
ml/                placeholders only
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

Phase 1 (Procurement Intelligence MVP, web). Chunk 4.1 of 4.1–4.6. **Do not implement Phase 2+
features** — requests, approvals, branches, budgets, mobile, integrations — until the
corresponding stage gate is passed. Sketching is allowed; building is not.

<!-- MANUAL ADDITIONS START -->
## Local App Restart Notes

- `localhost:4200` is the Docker/nginx static web container unless an Angular dev server is
  explicitly running. After UI/i18n changes, verify served assets with `curl -I
  http://localhost:4200/`; an old `Last-Modified` means the browser is still seeing a stale build.
- For user validation, run against hosted Supabase only unless the user explicitly asks for local DB.
  Check `.env`/shell values before starting: `SUPABASE_URL`, `SUPABASE_JWT_ISSUER`, and
  `DATABASE_URL` must not point at `localhost:54321` or `localhost:54322`.
- Use `docker-compose -f docker-compose.yml -f docker-compose.remote.yml up -d --build redis api web`
  for the remote-DB app path. Do not start a local Supabase stack for this workflow.
- If legacy `docker-compose` fails with `KeyError: 'ContainerConfig'` while recreating stale
  containers, remove only ProcurePilot containers first:
  `docker ps -aq --filter 'name=procurepilot-' | xargs -r docker rm -f`, then rerun the remote
  compose command.
<!-- MANUAL ADDITIONS END -->

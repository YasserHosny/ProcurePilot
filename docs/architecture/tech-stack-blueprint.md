# Technology Stack Blueprint

> Reference for the technologies, versions, and structure that make up ProcurePilot, and how to
> replicate this architecture in a new project. Business logic is out of scope — this is the stack.
>
> Last reviewed against the codebase: 10 Sep 2026. If a version here disagrees with a
> `pyproject.toml` / `package.json`, the manifest wins — update this file.

---

## 1. Architecture Overview

**pnpm + Turborepo monorepo.** One deployable API, one deployable SPA, three background workers,
shared packages, and infrastructure-as-code — all in one repo.

```
ProcurePilot/
├── apps/
│   ├── api/            FastAPI modular monolith — the only backend deployable
│   ├── web/            Angular 19 SPA
│   └── mobile/         Flutter — placeholder until Phase 2
├── packages/
│   ├── domain-types/   Shared TypeScript domain types
│   ├── i18n/           en.json + ar.json translation catalogues (+ index.ts)
│   ├── ui/             Shared Angular UI primitives
│   └── py-logging/     `procurepilot-logging` — structured JSON logging (editable install)
├── services/
│   ├── extraction-worker/   RQ worker — quotation extraction (AWS Bedrock + Azure DI)
│   ├── optimiser/           RQ worker — two-supplier basket split (OR-Tools CP-SAT)
│   └── matching-worker/     README only — matching runs synchronously inside apps/api
├── ml/
│   ├── evals/          run_eval.py harnesses for matching + extraction (wired into CI)
│   ├── benchmarks/     labelled-dataset placeholders (README only so far)
│   └── notebooks/
├── supabase/
│   ├── migrations/     52 forward-only versioned SQL files
│   └── config.toml     local dev stack (Supabase CLI) configuration
├── infra/
│   ├── docker/         api / web / extraction-worker Dockerfiles, kong.yml, initdb/
│   ├── nginx/          nginx.conf template (envsubst BACKEND_HOST)
│   └── terraform/      bunny.net (bunnynet provider) — container app, image registry, DNS
├── specs/              Speckit feature specs (001-platform-foundation … 008-requests-approvals)
├── docs/               product · architecture · roadmap · quality · operations
├── docker-compose.yml               local whole-stack (api + workers + redis + web)
├── docker-compose.remote.yml        override: point workers at hosted Supabase
├── docker-compose.web-dev.yml       override: bind-mount pre-built SPA instead of in-container build
├── pnpm-workspace.yaml · turbo.json
└── package.json                     root scripts (turbo, db:migrate, test:*, lint:*)
```

**Runtime data path (production):**

```
Browser → bunny.net → Nginx (SPA + /api/ reverse proxy) → FastAPI (/api/v1) → hosted Supabase
                                                              │
                                                              └─ enqueue → Redis (RQ) → workers → Supabase
```

Nginx and FastAPI run as two containers **in the same bunny.net app**, sharing a network namespace
(`BACKEND_HOST=localhost` in production). Workers run in a separate app and reach Redis and the API
over the network. Supabase (Postgres 17 + Auth + Storage + Realtime) is a hosted managed service in
every environment — there is no self-hosted database.

---

## 2. Backend — `apps/api`

Python package `procurepilot-api`. A **modular monolith**: one FastAPI app, one deployable, with
domain modules that own their routers, schemas, and services and talk to each other only through
defined interfaces.

| Concern | Technology | Version |
|---|---|---|
| **Language** | Python | 3.12 (`>=3.12,<3.13`) |
| **Web framework** | FastAPI | 0.115.6 |
| **ASGI server** | Uvicorn (`[standard]`) | 0.34.0 |
| **Data validation** | Pydantic v2 + pydantic-settings | `>=2.10,<3` / `>=2.7,<3` |
| **Rate limiting** | SlowAPI | 0.1.9 |
| **JWT decode/verify** | python-jose (`[cryptography]`) | 3.3.0 |
| **HTTP client** | httpx (async) | 0.28.1 |
| **File uploads** | python-multipart | 0.0.20 |
| **Supabase SDK** | supabase (supabase-py) | 2.11.0 |
| **Direct Postgres** | psycopg (`[binary]`, v3) | `>=3.2,<4` |
| **Background jobs** | Redis client + RQ | `>=5.2,<6` / `>=2.1,<3` |
| **Error tracking** | sentry-sdk (`[fastapi]`) | `>=2.20,<3` |
| **Excel export** | openpyxl | `>=3.1,<4` |
| **PDF export** | reportlab | `>=4.2,<5` |
| **Shared logging** | procurepilot-logging | local editable (`packages/py-logging`) |
| **Build backend** | Hatchling | `>=1.27,<2` |
| **Package/run tool** | uv | (Docker: pinned `0.6.2`) |

### Layout

```
apps/api/
├── src/procurepilot_api/
│   ├── main.py            FastAPI app factory, router registration, middleware
│   ├── config.py          pydantic-settings BaseSettings
│   ├── deps.py            FastAPI dependencies (bearer_token, CurrentMember, require_role, …)
│   ├── errors.py          error envelope + typed exceptions (NotFoundError, ConflictError, …)
│   ├── modules/           one directory per domain — each owns router.py, schemas.py, service.py
│   │   ├── auth  tenants  members  organisation  requests   (identity, org, approvals)
│   │   ├── catalogue  documents  quotations  extraction     (catalogue + quotation intake)
│   │   ├── matching  landed_cost  offers                    (matching, pricing, Smart Compare)
│   │   ├── savings  exports  alerts  billing  jobs          (value proof, exports, signals)
│   │   └── health
│   ├── shared/            audit.py · logging.py · observability.py · rate_limit.py
│   └── workers/           export_worker.py — RQ entrypoint for savings-export jobs
├── tests/{unit,integration,contract}/
├── scripts/seed.py        reference data + a platform invitation token
├── pyproject.toml
└── README.md
```

### Conventions

- Base path `/api/v1`. `Authorization: Bearer <supabase_jwt>`; tenancy resolved **server-side from
  the verified token**, never from a path/query/header.
- Cursor pagination, `limit` capped at 100. `Idempotency-Key` accepted on mutations.
- Error envelope: `{code, message, details, trace_id}`.
- ruff-formatted, full type hints, Pydantic models at every boundary. ruff line length 100,
  target `py312`, lint rule sets `E, F, I, B, UP, ANN`.
- pytest `asyncio_mode = "auto"`.

### Configuration

Environment-driven via `pydantic-settings`. Key vars (see `.env.example`): `SUPABASE_URL`,
`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_JWT_AUDIENCE`,
`DATABASE_URL`, `REDIS_URL`, `API_CORS_ORIGINS`, `RATE_LIMIT_AUTH`, `SENTRY_DSN`, plus the
extraction/AI credentials consumed by the workers.

---

## 3. Frontend — `apps/web`

pnpm workspace package `web`.

| Concern | Technology | Version |
|---|---|---|
| **Framework** | Angular | ^19.2 (core), CDK/Material ^19.0 |
| **Language** | TypeScript | ~5.7.2 |
| **Components** | **Standalone** (no NgModules), **signals** for local state, RxJS for streams | rxjs ~7.8 |
| **UI library** | Angular Material + Angular CDK | ^19 |
| **Styling** | Component-scoped SCSS + CSS logical properties (RTL-safe) |
| **i18n** | @ngx-translate/core + @ngx-translate/http-loader (runtime JSON loading) | ^16.0 |
| **Schema validation** | Zod | ^3.23 |
| **Supabase client** | @supabase/supabase-js | ^2.105 |
| **Error tracking** | @sentry/angular | ^9 |
| **Icons** | material-icons | ^1.13 |
| **Build** | @angular-devkit/build-angular (application builder) | ^19.2 |

### Layout & config

```
apps/web/
├── src/app/
│   ├── core/        API client, auth/session, interceptors, guards
│   ├── layout/      app shell, side nav, top bar
│   ├── features/    one directory per screen area (quotations, matching, offers, savings, …)
│   └── tests/       shared test helpers
├── src/assets/i18n/ runtime translation JSON (served no-cache)
├── angular.json     prefix "app"; budgets: initial 500 kB warn / 1 MB error,
│                    anyComponentStyle 4 kB warn / 12 kB error
└── package.json
```

- **Strict TypeScript**, no `any`. Shared domain types from `packages/domain-types`; Zod schemas
  co-located with the features that use them.
- **Every user-facing string** comes from `packages/i18n` (`en.json` + `ar.json`). A key present in
  one language and missing from the other **fails the web unit-test job** — it never reaches a user
  as a raw key.
- RTL: CSS logical properties only (`margin-inline-start`, not `margin-left`); both directions tested.

---

## 4. Background Workers & Queue

Redis is the **RQ broker only** — never a system of record. Three queues, three consumers:

| Queue | Consumer | Package | Key deps | What it does |
|---|---|---|---|---|
| `quotation-extraction` | `services/extraction-worker` | `procurepilot-extraction-worker` | `boto3` `>=1.35,<2`, `azure-ai-documentintelligence` `>=1.0,<2`, `openpyxl`, `rq`, `psycopg` | Extracts quotation line items. Provider modes: **bedrock** (default, LLM), **azure_di** (OCR fallback / cost control), **structured_parse** (CSV/XLSX fast path, bypasses both). |
| `basket-split` | `services/optimiser` | `procurepilot-optimiser-worker` | `ortools` (CP-SAT), `rq`, `psycopg` | Solves the two-supplier basket split for minimum total landed cost. |
| `exports` | `apps/api` (`procurepilot_api.workers.export_worker`) | — (shares the API image) | Renders audit-ready savings exports (Excel via openpyxl, PDF via reportlab) to Supabase Storage. |

`services/matching-worker/` is a placeholder README — product matching currently runs
**synchronously** inside `apps/api`'s `matching` module against `pgvector` + `pg_trgm`.

There is **no APScheduler / cron** in Phase 2 — worker runs are enqueue-triggered.

---

## 5. Data — Supabase (hosted)

| Concern | Detail |
|---|---|
| **Database** | PostgreSQL **17**, managed by Supabase. Hosted in every environment — no self-hosted DB, no Postgres service in `docker-compose.yml`. |
| **Extensions** | `pgcrypto`, `pgvector`, `pg_trgm` (enabled in migration `…0001_extensions.sql`). |
| **Auth** | Supabase Auth — email/password, MFA (TOTP), invitation-gated sign-up. A **custom access-token hook** (`[auth.hook.custom_access_token]` in `config.toml`) injects `tenant_id` into every JWT. Without it, every tenant-scoped query returns zero rows. |
| **Storage** | Supabase Storage (S3 protocol enabled). Tenant-scoped bucket paths; documents served via short-lived signed URLs, no public buckets. |
| **Realtime** | Enabled. |
| **Row-Level Security** | **Every tenant-scoped table** has `ENABLE` + `FORCE` RLS with policies supplying **both** `USING` and `WITH CHECK`. Policies read the JWT `tenant_id` claim — never an application-layer `WHERE`. A cross-tenant read returns *not found*, never *forbidden*. |
| **Append-only tables** | `audit_event` (and, per the follow-up migrations, `match_candidate` / `match_decision` / `landed_cost`) `revoke update, delete` from `authenticated` and carry insert-only policies. |
| **Backend access** | supabase-py `2.11.0` for PostgREST/Storage/Auth; `psycopg` v3 for direct SQL where PostgREST is a poor fit (workers, complex queries). |

### Migrations

- **52 forward-only** versioned SQL files in `supabase/migrations/`, `YYYYMMDDHHMMSS_name.sql`.
  Never edited after merge. Every new tenant-scoped table ships its RLS policy in the same file.
- Applied via the Supabase CLI: `pnpm db:migrate` → `supabase migration up --db-url "$DATABASE_URL"`
  (or `supabase db push` to a linked project).
- **Local development uses the Supabase CLI stack** (`supabase start`), configured by
  `supabase/config.toml` — **not** a hand-assembled docker-compose Supabase. (Reason recorded in
  `specs/001-platform-foundation/research.md` R5: GoTrue versions would not migrate against a
  hand-assembled stack; the CLI ships a set that works together and honours the access-token hook.)

---

## 6. Containerization

| File | Purpose |
|---|---|
| `infra/docker/api.Dockerfile` | `python:3.12-slim` + the `uv` binary (from `ghcr.io/astral-sh/uv:0.6.2`). Non-root `appuser` (uid 1001). Lays the source out under `/workspace/apps/api` **with `packages/py-logging` two levels up**, so `[tool.uv.sources]`'s relative path resolves identically to a plain checkout. `uv pip install -e .`. Healthcheck `curl /api/v1/health`. `uvicorn procurepilot_api.main:app` on `8000`. Also the **export-worker** image (different `command`). |
| `infra/docker/web.Dockerfile` | Multi-stage. **Build:** `node:20-alpine` + `corepack` `pnpm@9.15.4` → `pnpm install` → `pnpm run build` (with a fallback that normalises Angular's `dist/web/browser` output path). **Serve:** `nginx:1.27-alpine`, copies the SPA, renders `nginx.conf` via `envsubst '${BACKEND_HOST}'` at start. Healthcheck `wget /`. |
| `infra/docker/extraction-worker.Dockerfile` | Same `/workspace` layout pattern as the API image; runs `python -m procurepilot_extraction_worker`. |

### docker-compose (local only)

`docker-compose.yml` brings up: **api**, **redis** (`redis:7.4-alpine`), **extraction-worker**,
**optimiser** (`python:3.12-slim` + repo bind-mount + `pip install -e`), **export-worker**
(the API image, `procurepilot_api.workers.export_worker` entrypoint), and **web**
(`4200:80`). Overrides:

- `docker-compose.remote.yml` — run `api web redis` (+ workers) against a **hosted** Supabase; the
  local Supabase CLI services are not started.
- `docker-compose.web-dev.yml` — bind-mount `apps/web/dist/web/browser` into Nginx so a UI change
  is one local `ng build` away, skipping the ~10-minute in-container rebuild.

In compose, Nginx's `BACKEND_HOST` defaults to `api` (the service name). In production it is
`localhost` (shared bunny.net app namespace).

---

## 7. Reverse Proxy — Nginx

`infra/nginx/nginx.conf` (rendered with `envsubst '${BACKEND_HOST}'`):

- SPA fallback `try_files $uri $uri/ /index.html`.
- `/api/` → `http://${BACKEND_HOST}:8000` with `X-Real-IP` / `X-Forwarded-For` / `X-Forwarded-Proto`;
  read/send timeout 120 s, connect 10 s.
- **Caching:** `no-store` for `index.html` **and** `/assets/i18n/*.json` (new translation keys must
  never be hidden by cache); `must-revalidate` for `*.css`; gzip on.
- **Security headers** (global + repeated on `index.html`): `X-Content-Type-Options nosniff`,
  `X-Frame-Options DENY`, `Strict-Transport-Security`, `Referrer-Policy`, and a strict
  **Content-Security-Policy** allowing `script-src 'self'` and `connect-src 'self' https://*.supabase.co`.

---

## 8. CI/CD — GitHub Actions

### `ci.yml` — required on every PR and every push to `main`

| Job | What it runs |
|---|---|
| **secrets** | `gitleaks/gitleaks-action` over full history — a committed secret blocks the PR. |
| **lint** | `ruff check apps/api` + `pnpm lint` (angular-eslint) in `apps/web`. |
| **backend-tests** | `pgvector/pgvector:pg17` service. Applies **all 52 migrations** to a bare Postgres with hand-built Supabase stand-ins (`auth.users`, the `anon`/`authenticated`/`service_role` roles, a `storage` schema with forced RLS). `uv run --project apps/api pytest apps/api -q` with `TEST_DATABASE_URL` (set so DB-backed tests **fail** rather than silently skip). Then the **product-matching eval smoke gate** (`ml/evals/product_matching/run_eval.py` must return the honest `not_validated_no_held_out_benchmark` status). |
| **tenant-isolation** | Its own named job — migrations + `test_tenant_isolation.py` alone, so a cross-tenant leak is unambiguous when it goes red. |
| **web-unit-tests** | `pnpm install` → `ng test --watch=false --browsers=ChromeHeadless` (includes the i18n catalogue-completeness check) → production `ng build`. |
| **e2e** | `supabase start` (**not** compose) → seed → start API + extraction-worker + `ng serve` → Playwright: first the **a11y** specs (`@axe-core/playwright`, WCAG 2.1 AA, zero violations), then the full e2e suite (`channel: 'chrome'`). Failure artefacts uploaded. |

### Deploy workflows — one per deployable

`deploy-backend.yml`, `deploy-frontend.yml`, `deploy-extraction-worker.yml`. Each triggers on
`push` to `main` touching that service's paths (or `workflow_dispatch`), then:

1. `docker/build-push-action` → `ghcr.io/<owner>/procurepilot-<service>:{latest, <sha>}`
   (`linux/amd64`, GHA layer cache).
2. `BunnyWay/actions/container-update-image` → **bunny.net Magic Containers**, updating the named
   container's image tag to the commit SHA.

| Workflow | GHCR image | Bunny app secret | Container |
|---|---|---|---|
| `deploy-backend` | `procurepilot-api` | `BUNNY_BACKEND_APP_ID` | `procurepilot-backend` |
| `deploy-frontend` | `procurepilot-web` | `BUNNY_FRONTEND_APP_ID` | `procurepilot-frontend` |
| `deploy-extraction-worker` | `procurepilot-extraction-worker` | `BUNNY_WORKERS_APP_ID` | `procurepilot-extraction-worker` |

**Required Actions secrets:** `BUNNY_API_KEY`, `BUNNY_BACKEND_APP_ID`, `BUNNY_FRONTEND_APP_ID`,
`BUNNY_WORKERS_APP_ID` (plus the automatic `GITHUB_TOKEN` with `packages: write`).

---

## 9. Infrastructure as Code — Terraform

`infra/terraform/` — provider `BunnyWay/bunnynet` (`~> 0.11`, lock file at `0.18.0`),
`terraform >= 1.5.0`.

| Resource | Role |
|---|---|
| `bunnynet_compute_container_imageregistry.ghcr` | Registers GHCR as the pull source. |
| `bunnynet_compute_container_app.app` | The Magic Containers app(s) that host the backend/frontend/worker containers. |
| `bunnynet_dns_zone.primary` + `bunnynet_dns_record.{backend,frontend}` | The public hostnames. |

`production.tfvars` holds the concrete values and is **gitignored** (secrets rule #4).

---

## 10. Testing

| Layer | Tool | Version |
|---|---|---|
| **Backend unit/integration** | pytest + pytest-asyncio | 8.3.4 / 0.25.2 |
| **Backend DB tests** | real Postgres — `pgvector/pgvector:pg17` in CI; hosted or `supabase start` locally | — |
| **Backend HTTP** | httpx `TestClient` | 0.28.1 |
| **Frontend unit** | Karma + Jasmine (`jasmine-core`), ChromeHeadless | ~6.4 / ~5.6 |
| **E2E** | Playwright (`channel: 'chrome'`) | ^1.60 |
| **Accessibility** | @axe-core/playwright — WCAG 2.1 AA, zero violations | ^4.13 |
| **Lint** | ruff (Python) · angular-eslint ^19 / typescript-eslint ^8 (TS) | — |
| **Secret scan** | gitleaks | (action `@v2`) |
| **Model evals** | `ml/evals/*/run_eval.py` smoke gates | — |

Root scripts: `pnpm test` (turbo), `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`,
`pnpm test:isolation`, `pnpm test:a11y`, `pnpm lint`.

---

## 11. AI / Document Intelligence

| Purpose | Service | SDK |
|---|---|---|
| Quotation line-item extraction (default) | **AWS Bedrock** — Claude Haiku 4.5 via a `us-east-1` inference profile, overridable with `BEDROCK_MODEL_ID` | `boto3` `>=1.35,<2` |
| OCR / form-field extraction (fallback, cost control) | **Azure Document Intelligence** | `azure-ai-documentintelligence` `>=1.0,<2` — the current SDK, *not* the deprecated `azure-ai-formrecognizer` |
| CSV / XLSX fast path (no model call) | structured parser | `openpyxl` |
| Product matching — semantic candidates | pgvector | (in-DB) |
| Product matching — lexical candidates | pg_trgm `similarity()` + GIN trigram indexes | (in-DB) |

Evaluation harnesses live in `ml/evals/` — `product_matching/run_eval.py` (wired into `ci.yml` as
a smoke gate) and `quotation_extraction/run_eval.py`. The benchmark datasets under
`ml/benchmarks/` are README placeholders — the matching harness returns an explicit
`not_validated_no_held_out_benchmark` status until real labelled data lands (see
`docs/quality/matching-normalisation-audit.md`).

---

## 12. Reporting / File Generation

| Library | Version | Purpose |
|---|---|---|
| **openpyxl** | `>=3.1,<4` | Excel export (savings ledger) and structured-quotation parsing |
| **reportlab** | `>=4.2,<5` | PDF export (savings summary report) |

No WeasyPrint, matplotlib, Chart.js, QR/barcode, or Arabic-reshaping libraries are in use — charts
are rendered client-side in Angular, and Arabic PDF support is not a current requirement.

---

## 13. Security & Constitution

The eight non-negotiables (from `.specify/memory/constitution.md`, enforced in code and CI):

1. **Tenant isolation lives in the database** — `ENABLE` + `FORCE` RLS, `USING` + `WITH CHECK`,
   on every tenant-scoped table. Never an application-layer `WHERE` alone.
2. **Tenancy comes from the verified JWT claim** — never a path, query, or header.
3. **A cross-tenant read returns "not found"**, never "forbidden".
4. **No secrets in the repo** — `.env.example` committed, `.env` gitignored, gitleaks blocks PRs,
   `production.tfvars` gitignored.
5. **Every user-facing string comes from `packages/i18n`** (en + ar). Enforced by the web unit job.
6. **Every monetary value stores an explicit currency.** No bare numbers for money.
7. **`audit_event` is append-only** — no `UPDATE`, no `DELETE`, for any role.
8. **No autonomous purchasing** — automation prepares and routes; a human authorises.

Supporting mechanisms: Supabase JWT with the `tenant_id` access-token hook; SlowAPI per-endpoint
rate limiting; Sentry on both tiers; Nginx CSP/HSTS/frame/nosniff/referrer headers.

---

## 14. Replicating This Architecture

The distinctive choices, in the order they matter:

1. **pnpm + Turborepo monorepo.** `pnpm-workspace.yaml` covers `apps/*` and `packages/*`;
   `turbo.json` fans out `build` / `test` / `lint`. Root `package.json` also hosts the
   `db:migrate` / `test:*` / `lint:*` convenience scripts.
2. **Hosted Supabase as the only database — in every environment.** No Postgres in
   `docker-compose.yml`. Local dev uses the Supabase **CLI** stack (`supabase start`,
   `supabase/config.toml`), which honours the custom access-token hook. Migrations are
   forward-only versioned SQL applied by the CLI.
3. **Tenancy through a JWT claim + forced RLS.** A custom access-token hook injects `tenant_id`;
   every tenant table forces RLS with `USING` + `WITH CHECK`; the API never filters by tenant in
   application code and never reveals cross-tenant existence.
4. **FastAPI modular monolith.** One deployable. `src/<pkg>/modules/<domain>/{router,schemas,service}.py`;
   cross-module calls go through interfaces, not shared state. `uv` for install/run; Hatchling build.
5. **Angular 19, standalone + signals, runtime i18n.** No NgModules. Signals for local state, RxJS
   for streams, strict TS, no `any`. `@ngx-translate` loads JSON at runtime; a missing key in
   either language fails CI. CSS logical properties for RTL.
6. **RQ over Redis for background work.** Redis is the broker only. Separate worker packages under
   `services/`, one RQ queue each. The API image doubles as a worker image with a different
   entrypoint where the job is API-owned (exports).
7. **Two-stage container images with a `/workspace` layout.** Python images place the app two
   directories deep so a local editable package (`packages/py-logging`) resolves by the same
   relative path in the container as in a checkout. The web image is `node:20-alpine` build →
   `nginx:1.27-alpine` serve, with `envsubst '${BACKEND_HOST}'` at start.
8. **GitHub Actions → GHCR → bunny.net Magic Containers.** One `ci.yml` (secrets, lint, backend
   tests on a real pgvector Postgres, a dedicated tenant-isolation job, web unit + build, and a
   full `supabase start` e2e job with axe-core a11y). One `deploy-<service>.yml` per deployable:
   build + push `ghcr.io/<owner>/<name>:{latest,sha}`, then `BunnyWay/actions/container-update-image`.
   `infra/terraform/` provisions the bunny.net app, image registry, and DNS with the `bunnynet`
   provider.
9. **Eval harnesses as CI smoke gates.** `ml/evals/product_matching/run_eval.py` runs in `ci.yml`
   and must report an honest "not validated" status until a real benchmark exists — the harness
   ships before the data, but it is never allowed to *claim* a passing metric it cannot measure.

### Checklist before a first deploy

- [ ] `.env` has all Supabase credentials (`SUPABASE_URL`, `ANON`/`SERVICE_ROLE` keys,
      `JWT_SECRET`, `DATABASE_URL`) and `REDIS_URL`.
- [ ] `supabase/config.toml`'s `[auth.hook.custom_access_token]` is enabled and the hook injects
      `tenant_id`.
- [ ] All migrations apply cleanly from empty via the Supabase CLI; every tenant table forces RLS.
- [ ] `pnpm test` is green (turbo: api pytest, web Karma, e2e Playwright, tenant-isolation, a11y).
- [ ] `docker compose up --build` runs the whole local stack and `/api/v1/health` is reachable
      through Nginx on `:4200`.
- [ ] `ci.yml` passes on a PR (secrets, lint, backend-tests, tenant-isolation, web-unit-tests, e2e).
- [ ] `ghcr.io` images build and push from each `deploy-<service>.yml`.
- [ ] bunny.net apps exist; `BUNNY_*` Actions secrets set; frontend container has
      `BACKEND_HOST=localhost`; DNS records point the custom hostnames at the bunny.net endpoints.
- [ ] `infra/terraform/production.tfvars` is populated and **not** committed.

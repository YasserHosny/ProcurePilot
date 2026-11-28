# Technology Stack Blueprint

> Reference for the technologies, versions, and structure that make up ProcurePilot, and how to
> replicate this architecture in a new project. Business logic is out of scope — this is the stack.
>
> Last reviewed against the codebase: 19 Nov 2026 (`main` after spec 025). If a version here
> disagrees with a `pyproject.toml` / `package.json` / `pubspec.yaml`, the manifest wins — update
> this file.

---

## 1. Architecture Overview

**pnpm + Turborepo monorepo.** One deployable API, one deployable SPA, a shipped Flutter app,
background workers (two separate worker packages plus API-image workers), shared packages, and
infrastructure-as-code — all in one repo.

```
ProcurePilot/
├── apps/
│   ├── api/            FastAPI modular monolith — the only backend deployable (+ API-image workers)
│   ├── web/            Angular 22 SPA
│   └── mobile/         Flutter app — shipped (auth, requests, approvals, low-stock, delivery, push)
├── packages/
│   ├── domain-types/   Shared TypeScript domain types
│   ├── i18n/           en.json + ar.json translation catalogues (+ index.ts)
│   ├── ui/             Shared Angular UI primitives
│   └── py-logging/     `procurepilot-logging` — structured JSON logging (editable install)
├── services/
│   ├── extraction-worker/   RQ worker — quotation extraction (AWS Bedrock + Azure DI + structured parse)
│   ├── optimiser/           RQ worker — basket split (OR-Tools CP-SAT)
│   └── matching-worker/     README only — matching runs synchronously inside apps/api
├── ml/
│   ├── evals/          run_eval.py harnesses for product matching + quotation extraction
│   └── benchmarks/     benchmark formats for both; no labelled held-out set yet
├── supabase/
│   ├── migrations/     197 forward-only versioned SQL files
│   └── config.toml     local dev stack (Supabase CLI) configuration
├── infra/
│   ├── docker/         api / web / extraction-worker / email-ingestion-worker / optimiser /
│   │                   feedback-worker Dockerfiles, kong.yml, initdb/
│   ├── nginx/          nginx.conf template (envsubst BACKEND_HOST)
│   └── terraform/      bunny.net (bunnynet provider) — container app, image registry, DNS
├── specs/              Speckit feature specs (001-platform-foundation … 025-user-feedback)
├── docs/               product · architecture · roadmap · quality · operations · user · gtm
├── docker-compose.yml               local whole-stack (api + workers + redis + web)
├── docker-compose.remote.yml        override: point workers at hosted Supabase
├── docker-compose.web-dev.yml       override: bind-mount pre-built SPA instead of in-container build
├── pnpm-workspace.yaml · turbo.json
└── package.json                     root scripts (turbo, db:migrate, db:check-privileges, test:*, lint)
```

**Runtime data path (production):**

```
Browser / Flutter app → bunny.net → Nginx (SPA + /api/ reverse proxy) → FastAPI (/api/v1) → hosted Supabase
                                                                            │
                                                                            └─ enqueue → Redis (RQ) → workers → Supabase
```

Nginx and FastAPI run as two containers **in the same bunny.net app** (`procurepilot-production`),
sharing a network namespace (`BACKEND_HOST=localhost`). The deployed workers run in a separate app
(`procurepilot-workers`, which also runs the shared Redis) and reach Redis and Supabase over the
network. Supabase (Postgres 17 + Auth + Storage + Realtime) is a hosted managed service in every
environment — there is no self-hosted database. The hosted web app is
`https://procurepilot.iron-sys.com`; `pilot.iron-sys.com` is the planned production-pilot domain
(pilot plan E1-a), not live yet.

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
| **Token encryption at rest** | cryptography (Fernet, accounting OAuth tokens) | `>=44` |
| **HTTP client** | httpx (async) | 0.28.1 |
| **File uploads** | python-multipart | 0.0.31 |
| **Upload content sniffing** | python-magic (libmagic) | `>=0.4.27,<0.5` |
| **Supabase SDK** | supabase (supabase-py) | 2.11.0 |
| **Direct Postgres** | psycopg (`[binary]`, v3) | `>=3.2,<4` |
| **Background jobs** | Redis client + RQ | `>=5.2,<6` / `>=2.1,<3` |
| **Error tracking** | sentry-sdk (`[fastapi]`) | `>=2.20,<3` |
| **Excel export** | openpyxl | `>=3.1,<4` |
| **PDF export** | reportlab + arabic-reshaper + python-bidi (Arabic PDFs) | `>=4.2,<5` / `>=3.0.0` / `>=0.4.2` |
| **AWS (optional)** | boto3 — Bedrock for analyst intent and matching embeddings when their mode is `bedrock` (default: stub) | `>=1.35,<2` |
| **Shared logging** | procurepilot-logging | local editable (`packages/py-logging`) |
| **Build backend** | Hatchling | `>=1.27,<2` |
| **Package/run tool** | uv | (Docker: pinned `0.6.2`) |

### Layout

```
apps/api/
├── src/procurepilot_api/
│   ├── main.py            FastAPI app factory, router registration, middleware
│   ├── config.py          pydantic-settings BaseSettings
│   ├── db.py              `connect()` — every psycopg connection (prepare_threshold=None for the pooler)
│   ├── deps.py            FastAPI dependencies (bearer_token, CurrentMember, require_role, …)
│   ├── errors.py          error envelope + typed exceptions (NotFoundError, ConflictError, …)
│   ├── modules/           31 domains — each owns router.py, schemas.py, service.py
│   │   ├── auth  tenants  members  organisation  devices  requests  orders       (identity, org, approvals, P2P)
│   │   ├── catalogue  documents  quotations  extraction  ingestion               (catalogue + quotation intake)
│   │   ├── matching  landed_cost  offers  rfq                                    (matching, pricing, Smart Compare, sourcing)
│   │   ├── savings  exports  reports  digests  alerts  forecasting  analyst      (value proof, reporting, signals)
│   │   ├── accounting  pos  partner  webhooks  billing  jobs                     (integrations, partner API)
│   │   ├── feedback                                                              (in-app feedback + operator triage)
│   │   └── health
│   ├── shared/            audit · i18n · mailer · logging · observability · rate_limit · storage_keys ·
│   │                      token_crypto · display_name · brand_footer · postgrest_pages
│   └── workers/           long-running workers and operator CLIs (see §4)
├── scripts/               seed.py, check_privileges.py, invite_member.py, g3_evidence.py
├── tests/{unit,integration,contract}/
├── pyproject.toml
└── README.md
```

### Conventions

- Base path `/api/v1`. `Authorization: Bearer <supabase_jwt>`; tenancy resolved **server-side from
  the verified token**, never from a path/query/header.
- Cursor pagination, `limit` capped at 100. `Idempotency-Key` on mutations.
- Error envelope: `{code, message, details, trace_id}`.
- Every Postgres connection opens through `procurepilot_api.db.connect` (Supabase's transaction-mode
  pooler rejects prepared statements).
- ruff-formatted, full type hints, Pydantic models at every boundary. ruff line length 100,
  target `py312`, lint rule sets `E, F, I, B, UP, ANN`.
- pytest `asyncio_mode = "auto"`.

### Configuration

Environment-driven via `pydantic-settings`; `.env.example` is the reference. Required at start-up
(no default): `API_HOST`, `API_PORT`, `API_ENV`, `API_LOG_LEVEL`, `API_CORS_ORIGINS`, `SUPABASE_URL`,
`SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_AUDIENCE`, `SUPABASE_JWT_ISSUER`,
`DATABASE_URL`, `PLATFORM_INVITATION_TTL_DAYS`, `MEMBER_INVITATION_TTL_DAYS`, `RATE_LIMIT_AUTH`,
`WEB_API_BASE_URL`, `WEB_DEFAULT_LOCALE`. Optional groups: `REDIS_URL`, mail (`RFQ_MAILER_MODE`,
`MAILGUN_*`), extraction/AI credentials, accounting/POS OAuth, `FEEDBACK_*`, `WEB_PUBLIC_URL`,
`SENTRY_DSN`. The workers load the same `Settings`, so they need the full required set too.

---

## 3. Frontend — `apps/web`

pnpm workspace package `web`.

| Concern | Technology | Version |
|---|---|---|
| **Framework** | Angular | 22.2 (core), CDK/Material 22.2 |
| **Language** | TypeScript | 6.0.3 |
| **Components** | **Standalone** (no NgModules), **signals** for local state, RxJS for streams | rxjs ~7.8 |
| **Change detection** | `ChangeDetectionStrategy.Eager` kept by the Angular 22 upgrade (lint warning); OnPush only where state is signals | — |
| **UI library** | Angular Material + Angular CDK | 22.2 |
| **Styling** | Component-scoped SCSS + CSS logical properties (RTL-safe) | — |
| **i18n** | @ngx-translate/core + @ngx-translate/http-loader (runtime JSON loading) | ^18 |
| **Schema validation** | Zod (declared in `package.json`; no source imports it today — forms use Reactive Forms validators) | ^4.6 |
| **Supabase client** | @supabase/supabase-js | ^2.105 |
| **Error tracking** | @sentry/angular | ^11 |
| **Build** | `@angular/build` (application builder) | 22.2 |

### Layout & config

```
apps/web/
├── src/app/
│   ├── core/        API client, auth/session, interceptors, guards (role + platform-operator)
│   ├── layout/      app shell (incl. the feedback widget), side nav, top bar
│   └── features/    one directory per area: accounting alerts analyst approvals auth catalogue
│                    feedback forecasting ingestion landing legal matching offers onboarding orders
│                    platform pos quotations reports requests rfq savings settings supplier-risk team
├── i18n → ../../packages/i18n   symlink (Angular 22 refuses assets outside the workspace)
├── tests/e2e/       Playwright specs (+ *-a11y.spec.ts, tagged @a11y)
├── playwright.config.ts · playwright.docs.config.ts (docs screenshots)
└── package.json · pnpm-lock.yaml (own lockfile: CI installs with --ignore-workspace --frozen-lockfile)
```

- **Strict TypeScript**, no `any`. Shared domain types from `packages/domain-types`. Form validation uses Angular Reactive
  Forms validators; there is no shared validation package.
- **Every user-facing string** comes from `packages/i18n` (`en.json` + `ar.json`).
  `scripts/check-i18n-keys.mjs` (run by `pnpm lint`) fails when a literal key is missing from either
  language — it never reaches a user as a raw key.
- RTL: CSS logical properties only (`margin-inline-start`, not `margin-left`); both directions tested.
- After changing web dependencies, regenerate **both** the root and `apps/web` lockfiles or CI fails.

---

## 4. Mobile — `apps/mobile`

Flutter (Dart SDK `^3.13`). Shipped, not a placeholder. Features under `lib/features/`: auth
(sign-in, biometric unlock, device registration), home, purchase requests, approvals, low-stock
reporting, delivery confirmation and quality-issue photos, notifications. Key packages:
`flutter_secure_storage`, `local_auth`, `hive`/`hive_flutter` (offline cache), `http`,
`connectivity_plus`, `image_picker`, `intl`. State is an `InheritedWidget` plus a Hive offline
queue. Talks to the same `/api/v1`. Push: devices register with the API and sends go through the
`push-notifications` RQ queue, but no worker consumes that queue and the sender is still a **stub**
— no FCM/APNs credentials exist yet — so every send is recorded as not delivered (runbook §3.5). CI: `mobile-build-size-check.yml`.

---

## 5. Background Workers & Queue

Redis is the **RQ broker only** — never a system of record. Workers come in two shapes: **RQ
consumers** (enqueue-triggered) and **interval loops** (`--interval N`, `--once` for one pass).
There is no APScheduler or cron library; scheduled work is an interval loop.

| Worker | Code | Shape | Image / where it runs |
|---|---|---|---|
| Quotation extraction (`quotation-extraction` queue) | `services/extraction-worker` — Bedrock (default), Azure DI (OCR fallback), structured CSV/XLSX parse | RQ | own image · bunny.net workers app |
| Basket split (`basket-split` queue) | `services/optimiser` — OR-Tools CP-SAT | RQ | own image · bunny.net workers app |
| Email ingestion | `procurepilot_api.workers.email_ingestion_worker` | loop | own image · bunny.net workers app |
| In-app feedback (digest, 12-month retention, orphan-file sweep) | `procurepilot_api.workers.feedback_worker` | loop (900 s) | own image · bunny.net workers app |
| Exports (`exports` queue) | `procurepilot_api.workers.export_worker` | RQ | API image · compose only |
| Webhooks | `procurepilot_api.workers.webhook_worker` | loop | API image · compose only |
| Offer refresh | `procurepilot_api.workers.offer_refresh_scheduler` | loop | API image · compose only |
| Catalogue refresh | `procurepilot_api.workers.catalogue_refresh_worker` | loop | API image · compose only |
| Digests, report scheduling, accounting sync, POS sync | `digest_worker`, `report_scheduler`, `accounting_sync_worker`, `pos_sync_worker` | loop | API image · not in compose or production |

Operator CLIs in the same package: `platform_operator_cli` (grant/revoke/list feedback triage
operators), `requeue_extraction`, `requeue_email_ingest`.

`services/matching-worker/` is a placeholder README — product matching runs **synchronously** inside
`apps/api`'s `matching` module against `pgvector` + `pg_trgm`.

The bunny.net `procurepilot-workers` app is **pinned to a single instance** (min 1 / max 1 per
region, one region) since 2026-11-19, so interval loops without a cross-process lock (the feedback
digest) cannot run twice. The cap is app-wide.

---

## 6. Data — Supabase (hosted)

| Concern | Detail |
|---|---|
| **Database** | PostgreSQL **17**, managed by Supabase. Hosted in every environment — no Postgres service in `docker-compose.yml`. |
| **Extensions** | `pgcrypto`, `pgvector`, `pg_trgm` (migration `…0001_extensions.sql`). |
| **Auth** | Supabase Auth — email/password, MFA (TOTP), invitation-gated sign-up. A **custom access-token hook** (`[auth.hook.custom_access_token]` in `config.toml`) stamps `tenant_id` and `member_role`, and a `platform_operator` UI-hint claim (spec 025). Without the hook every tenant-scoped query returns zero rows. |
| **Storage** | Supabase Storage. Private, tenant-prefixed buckets; files served via short-lived signed URLs, no public buckets. |
| **Realtime** | Enabled. |
| **Row-Level Security** | **Every tenant-scoped table** has `ENABLE` + `FORCE` RLS with policies supplying **both** `USING` and `WITH CHECK`. Policies read the JWT `tenant_id` claim — never an application-layer `WHERE`. A cross-tenant read returns *not found*, never *forbidden*. Column-level grants hide internal columns where RLS (rows only) cannot (e.g. feedback operator labels). |
| **Append-only / supersession** | `audit_event` is append-only for every role. Match decisions and landed costs are corrected by supersession, never updated (`current_match_decision`, `current_landed_cost`). |
| **Cross-tenant exception** | Platform operators (spec 025, ADR-027): a narrow, audited, RLS-enforced read and status/label update on the feedback tables only, through `is_platform_operator()` and a few `SECURITY DEFINER` functions. Never `service_role` on a request path. |
| **Backend access** | supabase-py `2.11.0` for PostgREST/Storage/Auth; psycopg v3 (via `db.connect`) for direct SQL. |

### Migrations

- **197 forward-only** versioned SQL files in `supabase/migrations/`, `YYYYMMDDHHMMSS_name.sql`.
  Never edited after merge. Every new tenant-scoped table ships its RLS policy in the same file.
- Applied with the Supabase CLI: `pnpm db:migrate` → `supabase migration up --db-url "$DATABASE_URL"`,
  then `pnpm db:check-privileges` (read-only grant/RLS check). Against hosted, use the session
  pooler (port 5432). **Deploys never run migrations**; check with `supabase migration list`.
- **Local development uses the Supabase CLI stack** (`supabase start`), configured by
  `supabase/config.toml` — **not** a hand-assembled docker-compose Supabase. (Reason recorded in
  `specs/001-platform-foundation/research.md` R5: GoTrue versions would not migrate against a
  hand-assembled stack; the CLI ships a set that works together and honours the access-token hook.)

---

## 7. Containerization

| File | Purpose |
|---|---|
| `infra/docker/api.Dockerfile` | `python:3.12-slim` + the `uv` binary (`ghcr.io/astral-sh/uv:0.6.2`), `libmagic1`. Non-root `appuser` (uid 1001). Source laid out under `/workspace/apps/api` **with `packages/py-logging` two levels up**, so `[tool.uv.sources]`'s relative path resolves as in a plain checkout. `uv pip install -e .`. Healthcheck `curl /api/v1/health`. `uvicorn procurepilot_api.main:app` on `8000`, `APP_VERSION` build arg. Also the image for compose-only API workers (different `command`). |
| `infra/docker/web.Dockerfile` | Multi-stage. **Build:** `node:24-alpine` + `corepack` `pnpm@9.15.4` → install → `pnpm run build`. **Serve:** `nginx:1.27-alpine`, renders `nginx.conf` via `envsubst '${BACKEND_HOST}'` at start. Healthcheck `wget /`. |
| `infra/docker/extraction-worker.Dockerfile` | Same `/workspace` pattern; `python -m procurepilot_extraction_worker`. |
| `infra/docker/optimiser.Dockerfile` | Same pattern; the OR-Tools basket-split worker. |
| `infra/docker/email-ingestion-worker.Dockerfile` | API package + `packages/i18n`; `python -m procurepilot_api.workers.email_ingestion_worker`. |
| `infra/docker/feedback-worker.Dockerfile` | API package + `packages/i18n`; `python -m procurepilot_api.workers.feedback_worker --interval 900`. |

### docker-compose (local only)

`docker-compose.yml` brings up **api**, **redis** (`redis:7.4-alpine`), **extraction-worker**,
**optimiser**, **export-worker**, **webhook-worker**, **feedback-worker**,
**offer-refresh-scheduler**, **catalogue-refresh-worker** (all API-image workers use the API
Dockerfile with a different `command`), and **web** (`4200:80`). Overrides:

- `docker-compose.remote.yml` — run against a **hosted** Supabase; the local Supabase CLI services
  are not started.
- `docker-compose.web-dev.yml` — bind-mount `apps/web/dist/web/browser` into Nginx so a UI change
  is one local `ng build` away, skipping the in-container rebuild.

In compose, Nginx's `BACKEND_HOST` defaults to `api` (the service name). In production it is
`localhost` (shared bunny.net app namespace).

---

## 8. Reverse Proxy — Nginx

`infra/nginx/nginx.conf` (rendered with `envsubst '${BACKEND_HOST}'`):

- SPA fallback `try_files $uri $uri/ /index.html`.
- `/api/` → `http://${BACKEND_HOST}:8000` with `X-Real-IP` / `X-Forwarded-For` /
  `X-Forwarded-Proto`; `client_max_body_size 30m`. `location = /api/v1/feedback` (multipart feedback
  submit) allows `40m`.
- **Caching:** `no-store` for `index.html`, `/version.txt` **and** `/assets/i18n/*.json` (new
  translation keys must never be hidden by cache); `must-revalidate` for `*.css`; gzip on.
- **Security headers** (global and repeated on the no-store locations): `X-Content-Type-Options
  nosniff`, `X-Frame-Options DENY`, `Strict-Transport-Security`, `Referrer-Policy`, and a strict
  **Content-Security-Policy** (`default-src 'self'; script-src 'self'`, Supabase in `connect-src`).

---

## 9. CI/CD — GitHub Actions

### `ci.yml` — required on every PR and every push to `main`

| Job | What it runs |
|---|---|
| **changes** | Path filter that decides which jobs a PR needs. |
| **api-image-i18n** | Builds the email-ingestion and feedback-worker images and checks the Arabic email catalogues are inside. |
| **secrets** | gitleaks over full history — a committed secret blocks the PR. |
| **lint** | `ruff check apps/api` + `pnpm lint` (angular-eslint + the i18n key check) in `apps/web`. |
| **backend-tests** | `pgvector/pgvector:pg17` service; applies **all migrations** to a bare Postgres with hand-built Supabase stand-ins (`auth.users`, the client roles, a `storage` schema with forced RLS). `pytest apps/api` with `TEST_DATABASE_URL` set, so DB-backed tests **fail** rather than skip. Then the product-matching eval smoke gate (must report `not_validated_no_held_out_benchmark`). |
| **dependency-audit** | `pip-audit` over `apps/api` and the worker packages (allowlist: `docs/operations/dependency-audit-allowlist.txt`) and `pnpm audit --prod`. |
| **tenant-isolation** | Its own job — migrations + `test_tenant_isolation.py` alone, so a cross-tenant leak is unambiguous. |
| **web-unit-tests** | `pnpm install` (own lockfile) → Karma/Jasmine in ChromeHeadless → production `ng build`. |
| **e2e** (6 shards + aggregate) | `supabase start` → seed → API + extraction worker + web → Playwright, including the `@a11y` axe-core specs (WCAG 2.1 AA, zero violations). |

`main` also requires **"Regenerate and diff"** from `docs-screenshots.yml`: it recaptures the user-doc
screenshots and fails if any image drifts past 1 % of pixels (`scripts/docs_screenshots_diff.py`);
commit the `regenerated-doc-screenshots` artifact to fix it. `mobile-build-size-check.yml` guards
the Flutter build size.

### Deploy workflows — one per deployable

Each triggers on `push` to `main` touching that service's paths (or `workflow_dispatch`), then:

1. `docker/build-push-action` → `ghcr.io/<owner>/procurepilot-<service>:{latest, <sha>}`
   (`linux/amd64`, GHA layer cache).
2. `BunnyWay/actions/container-update-image` → **bunny.net Magic Containers**, setting the named
   container's image tag to the commit SHA. It only *updates* an existing container — a new one is
   created once by hand.

| Workflow | GHCR image | Bunny app secret | Container |
|---|---|---|---|
| `deploy-backend` | `procurepilot-api` | `BUNNY_BACKEND_APP_ID` | `procurepilot-backend` |
| `deploy-frontend` | `procurepilot-web` | `BUNNY_FRONTEND_APP_ID` | `procurepilot-frontend` |
| `deploy-extraction-worker` | `procurepilot-extraction-worker` | `BUNNY_WORKERS_APP_ID` | `procurepilot-extraction-worker` |
| `deploy-email-ingestion-worker` | `procurepilot-email-ingestion-worker` | `BUNNY_WORKERS_APP_ID` | `procurepilot-email-ingestion-worker` |
| `deploy-optimiser-worker` | `procurepilot-optimiser-worker` | `BUNNY_WORKERS_APP_ID` | `procurepilot-optimiser-worker` |
| `deploy-feedback-worker` | `procurepilot-feedback-worker` | `BUNNY_WORKERS_APP_ID` | `procurepilot-feedback-worker` |

**Required Actions secrets:** `BUNNY_API_KEY`, `BUNNY_BACKEND_APP_ID`, `BUNNY_FRONTEND_APP_ID`,
`BUNNY_WORKERS_APP_ID` (plus the automatic `GITHUB_TOKEN` with `packages: write`).

---

## 10. Infrastructure as Code — Terraform

`infra/terraform/` — provider `BunnyWay/bunnynet` (`~> 0.11`), `terraform >= 1.5.0`.

| Resource | Role |
|---|---|
| `bunnynet_compute_container_imageregistry.ghcr` | Registers GHCR as the pull source. |
| `bunnynet_compute_container_app.app` | The production app (backend + frontend containers). |
| `bunnynet_dns_zone.primary` + `bunnynet_dns_record.{backend,frontend}` | The public hostnames. |

The `procurepilot-workers` app and its containers are **not** managed by Terraform; they were
created by hand (runbook §7). `production.tfvars` holds the concrete values and is **gitignored**.

---

## 11. Testing

| Layer | Tool | Version |
|---|---|---|
| **Backend unit/integration/contract** | pytest + pytest-asyncio | 8.3.4 / 0.25.2 |
| **Backend DB tests** | real Postgres — `pgvector/pgvector:pg17` in CI; `supabase start` locally | — |
| **Backend HTTP** | httpx `TestClient` | 0.28.1 |
| **Frontend unit** | Karma + Jasmine, ChromeHeadless | ~6.4 / ~5.6 |
| **E2E** | Playwright | ^1.60 |
| **Accessibility** | @axe-core/playwright — WCAG 2.1 AA, zero violations, tests tagged `@a11y` | ^4.14 |
| **Lint** | ruff (Python) · angular-eslint ^22.6 / typescript-eslint ^8 / ESLint ^9 (TS) | — |
| **Secret scan** | gitleaks | — |
| **Docs screenshots** | Playwright capture + pixel diff (1 % threshold) | — |
| **Model evals** | `ml/evals/*/run_eval.py` smoke gates | — |

Root scripts: `pnpm test` (turbo), `pnpm test:api`, `pnpm test:web`, `pnpm test:e2e`,
`pnpm test:isolation` (`test_tenant_isolation.py` only), `pnpm test:a11y` (`--grep @a11y`),
`pnpm lint`, `pnpm db:migrate`, `pnpm db:check-privileges`, `pnpm db:seed`.

---

## 12. AI / Document Intelligence

| Purpose | Service | SDK |
|---|---|---|
| Quotation line-item extraction (default) | **AWS Bedrock** — Claude Haiku 4.5 via a `us-east-1` inference profile, overridable with `BEDROCK_MODEL_ID` | `boto3` `>=1.35,<2` |
| OCR / form-field extraction (fallback, cost control) | **Azure Document Intelligence** | `azure-ai-documentintelligence` `>=1.0,<2` |
| CSV / XLSX fast path (no model call) | structured parser | `openpyxl` |
| Grounded procurement analyst — intent parsing | Bedrock when `ANALYST_INTENT_PROVIDER_MODE=bedrock`, else a stub | `boto3` |
| Product matching — semantic candidates | pgvector; embeddings from Bedrock when `MATCHING_EMBEDDING_PROVIDER_MODE=bedrock`, else a stub | (in-DB) |
| Product matching — lexical candidates | pg_trgm `similarity()` + GIN trigram indexes | (in-DB) |

`ml/evals/product_matching/run_eval.py` runs in `ci.yml` and must report
`not_validated_no_held_out_benchmark`: calibration needs a labelled held-out benchmark of 500+
confirmed human match decisions (`specs/004-matching-normalisation/research.md` R5/R10), and hosted
has only a handful. `quotation_extraction/run_eval.py` is the extraction harness.

---

## 13. Reporting / File Generation

| Library | Version | Purpose |
|---|---|---|
| **openpyxl** | `>=3.1,<4` | Excel export (savings ledger, reports) and structured-quotation parsing |
| **reportlab** | `>=4.2,<5` | PDF export (savings summary, reports) |
| **arabic-reshaper + python-bidi** | `>=3.0.0` / `>=0.4.2` | Correct Arabic shaping and direction in PDFs |

Emails (RFQs, digests, feedback digest) are rendered from `packages/i18n` through
`shared/i18n.py`'s `t()` and sent by `shared/mailer.py` (Mailgun when `RFQ_MAILER_MODE=mailgun`, an
in-memory stub otherwise). Charts are rendered client-side in Angular.

---

## 14. Security & Constitution

The eight non-negotiables (from `.specify/memory/constitution.md`, enforced in code and CI):

1. **Tenant isolation lives in the database** — `ENABLE` + `FORCE` RLS, `USING` + `WITH CHECK`,
   on every tenant-scoped table. Never an application-layer `WHERE` alone.
2. **Tenancy comes from the verified JWT claim** — never a path, query, or header.
3. **A cross-tenant read returns "not found"**, never "forbidden".
4. **No secrets in the repo** — `.env.example` committed, `.env` gitignored, gitleaks blocks PRs,
   `production.tfvars` gitignored.
5. **Every user-facing string comes from `packages/i18n`** (en + ar). Enforced by `pnpm lint`.
6. **Every monetary value stores an explicit currency.** No bare numbers for money.
7. **`audit_event` is append-only** — no `UPDATE`, no `DELETE`, for any role.
8. **No autonomous purchasing** — automation prepares and routes; a human authorises.

The one documented, owner-approved exception to cross-tenant access is the platform-operator path
for feedback triage (ADR-027): feedback tables only, RLS-enforced, audited on every read and change.

Supporting mechanisms: Supabase JWT with the access-token hook; SlowAPI per-endpoint rate limiting;
content sniffing of every upload (python-magic); Fernet encryption of stored OAuth tokens; Sentry
on both tiers; Nginx CSP/HSTS/frame/nosniff/referrer headers.

---

## 15. Replicating This Architecture

The distinctive choices, in the order they matter:

1. **pnpm + Turborepo monorepo.** `pnpm-workspace.yaml` covers `apps/*` and `packages/*`;
   `turbo.json` fans out `build` / `test` / `lint`. Root `package.json` hosts the `db:*` / `test:*`
   / `lint` scripts.
2. **Hosted Supabase as the only database — in every environment.** No Postgres in
   `docker-compose.yml`. Local dev uses the Supabase **CLI** stack (`supabase start`,
   `supabase/config.toml`), which honours the access-token hook. Migrations are forward-only SQL
   applied by the CLI, never by a deploy.
3. **Tenancy through a JWT claim + forced RLS.** The access-token hook stamps `tenant_id`; every
   tenant table forces RLS with `USING` + `WITH CHECK`; the API never filters by tenant in
   application code and never reveals cross-tenant existence. Any cross-tenant need is a narrow,
   audited, RLS-enforced exception recorded as an ADR.
4. **FastAPI modular monolith.** One deployable. `src/<pkg>/modules/<domain>/{router,schemas,service}.py`;
   cross-module calls go through interfaces, not shared state. `uv` for install/run; Hatchling build.
5. **Angular, standalone + signals, runtime i18n.** No NgModules. Signals for local state, RxJS for
   streams, strict TS, no `any`. `@ngx-translate` loads JSON at runtime; a missing key in either
   language fails CI. CSS logical properties for RTL.
6. **Flutter mobile on the same API.** No separate mobile backend; device registration and push go
   through the API and an RQ queue (push provider not yet wired).
7. **RQ over Redis plus interval loops for background work.** Redis is the broker only. Heavy,
   separately-scaled work is its own package under `services/`; API-owned jobs reuse the API package
   with a different entrypoint. Loops that must run once at a time get a single-instance host.
8. **Container images with a `/workspace` layout.** Python images place the app two directories
   deep so `packages/py-logging` resolves by the same relative path as in a checkout. The web image
   is `node:24-alpine` build → `nginx:1.27-alpine` serve, with `envsubst '${BACKEND_HOST}'` at start.
9. **GitHub Actions → GHCR → bunny.net Magic Containers.** One `ci.yml` (path filter, secrets,
   lint, backend tests on a real pgvector Postgres, a dedicated tenant-isolation job, dependency
   audit, web unit + build, sharded `supabase start` e2e with axe-core) plus a docs-screenshot drift
   gate. One `deploy-<service>.yml` per deployable: build + push, then
   `BunnyWay/actions/container-update-image` on a container created once by hand.
10. **Eval harnesses as CI smoke gates.** `ml/evals/product_matching/run_eval.py` runs in `ci.yml`
    and must report an honest "not validated" status until a real benchmark exists — the harness
    ships before the data, but it never claims a metric it cannot measure.

### Checklist before a first deploy

- [ ] `.env` has every required `Settings` field (see §2 Configuration), plus `REDIS_URL` and mail
      settings for the workers.
- [ ] `supabase/config.toml`'s `[auth.hook.custom_access_token]` is enabled and stamps `tenant_id`.
- [ ] All migrations apply cleanly from empty via the Supabase CLI; `pnpm db:check-privileges` passes.
- [ ] `pnpm test` is green (api pytest, web Karma, e2e Playwright, tenant isolation, a11y).
- [ ] `docker compose up --build` runs the local stack and `/api/v1/health` is reachable through
      Nginx on `:4200`.
- [ ] `ci.yml` and "Regenerate and diff" pass on a PR.
- [ ] `ghcr.io` images build and push from each `deploy-<service>.yml`.
- [ ] bunny.net apps and every named container exist; `BUNNY_*` Actions secrets set; frontend
      container has `BACKEND_HOST=localhost`; DNS points the hostnames at the bunny.net endpoints.
- [ ] `infra/terraform/production.tfvars` is populated and **not** committed.

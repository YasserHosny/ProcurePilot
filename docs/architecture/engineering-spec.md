# ProcurePilot — Engineering Specification / Low-Level Design

> Buildable design for the ProcurePilot modular monolith and supporting services. Companion to the [Master Roadmap](../roadmap/procurepilot_roadmap.md), [PRD](../product/prd.md), and [Tech Stack Blueprint](./tech-stack-blueprint.md).

---

## 1. Repository Layout

```
procurepilot/
├── apps/
│   ├── web/                  # Angular SPA
│   ├── mobile/               # Flutter app
│   └── api/                  # FastAPI modular monolith
├── services/
│   ├── extraction-worker/    # Bedrock/Azure DI extraction pipeline
│   ├── matching-worker/      # entity resolution + embeddings
│   └── optimiser/            # OR-Tools basket allocation
├── packages/
│   ├── domain-types/         # OpenAPI-generated TS + Dart types
│   ├── ui/                   # shared design tokens
│   ├── validation/           # shared Zod schemas
│   └── i18n/                 # en + ar catalogues
├── ml/
│   ├── benchmarks/           # extraction + matching eval datasets
│   ├── evals/                # eval harness and reports
│   └── notebooks/            # exploration
├── .github/workflows/        # backend/frontend/mobile CI/CD
├── docker-compose.yml        # local orchestration
├── infra/                    # Terraform, Dockerfiles, Nginx templates
└── docs/                     # this document and other specs
```

## 2. Service Boundaries

### 2.1 `apps/api` — FastAPI modular monolith

| Module | Responsibility |
|---|---|
| `auth` | Supabase JWT verification, tenant resolution, RBAC middleware |
| `catalogue` | Products, suppliers, units, packs, aliases, CSV import |
| `documents` | Upload presigns, document metadata, storage URIs |
| `quotations` | Quotation lifecycle, extraction jobs, versioning |
| `extraction` | Orchestrates extraction-worker; stores results and confidence |
| `matching` | Candidate generation, scoring, auto-accept/reject thresholds |
| `offers` | Normalised offers, landed-cost computations, bitemporal storage |
| `compare` | Smart Compare aggregation, recommendation scorer |
| `requests` | Purchase requests (P2) |
| `approvals` | Routing, thresholds, audit trail (P2) |
| `savings` | Savings ledger, outcome capture, verification |
| `reports` | Excel/PDF export, scheduled reports |
| `jobs` | Async job resource, polling, webhooks |

### 2.2 `services/extraction-worker`

- Receives document URI and tenant context.
- Structured inputs (CSV/Excel) bypass the LLM.
- Primary: call AWS Bedrock (Claude 3 Haiku) with strict JSON schema.
- Fallback: Azure Document Intelligence for high-volume, low-variance layouts.
- Validation layer: arithmetic checks and locale handling.
- Returns extracted header + lines with confidence and page/region refs.

### 2.3 `apps/api` matching module

- Runs once a quotation reaches the reviewed state.
- Layered pipeline:
  1. Deterministic keys (GTIN, supplier SKU, alias hit).
  2. `pg_trgm` lexical similarity.
  3. `pgvector` semantic similarity.
  4. Feature scoring (brand, variant, pack, unit, price plausibility).
  5. Heuristic match score; automatic acceptance only above threshold and outside the close-call
     margin, otherwise a match-resolution task is created.
- Writes append-only `MatchDecision` rows, learned `ProductAlias` rows, landed-cost outputs, and
  retry mappings for idempotent human resolution.

### 2.4 `services/optimiser`

- Input: basket of products, required quantities, supplier offers, MOVs, delivery tiers, urgency, preference weights.
- Model: OR-Tools CP-SAT.
- Output: recommended allocation, expected cost, policy exceptions.

## 3. API Patterns

- **Base path:** `/api/v1`
- **Auth:** Supabase JWT in `Authorization: Bearer <token>`; tenant resolved server-side from token.
- **Pagination:** cursor-based; `limit` capped at 100.
- **Idempotency:** `Idempotency-Key` header on all mutations.
- **Async ops:** return `Job` resource with `status`, `result_url`, `webhook_url`.
- **Error envelope:** `{ "code": "", "message": "", "details": {}, "trace_id": "" }`.

## 4. Data Layer

- **Supabase Postgres 17** with `pgvector` and `pg_trgm`.
- **RLS** policies enforce `tenant_id` isolation.
- **Migrations:** versioned SQL files in `supabase/migrations/`.
- **Redis** for sessions, rate-limit counters, lightweight job queues. Redis is the Phase 1 end
  state but is not used in chunk 4.1; it is deferred to chunk 4.3, when the first background job
  arrives. Current rate limiting uses SlowAPI's in-process store.
- **Supabase Storage** for source documents.

## 5. Key Algorithms

### 5.1 Landed-Cost Engine

```
landed_cost = (unit_price × quantity)
            + vat_amount
            + delivery_fee
            - discount_amount
            + other_charges
```

- Rule version stored with every computation.
- Deterministic and replayable for audit.

### 5.2 Recommendation Scorer

- Inputs: landed cost, lead time, reliability, supplier risk, stock, urgency.
- First version: weighted scoring with calibrated thresholds.
- Later: learned ranking based on outcome feedback.

## 6. State Management

### Web
- Angular services with RxJS for server state.
- Reactive Forms + Zod for validation.
- No complex global store; domain modules own state.

### Mobile
- Flutter BLoC or Riverpod (decision deferred to mobile sprint).
- Offline drafts queue with idempotency keys.

## 7. Security Model

- Supabase Auth issues JWT; backend verifies with `python-jose`.
- Every DB query filters by `tenant_id` and respects RLS.
- Rate limiting per endpoint via SlowAPI.
- Nginx adds security headers; FastAPI adds CORS and audit headers.
- Secrets in GitHub Actions; no secrets committed.

## 8. Responsive & RTL Design

The web SPA is designed mobile-first with three breakpoint tiers:

| Tier | Width | Behaviour |
|---|---|---|
| Mobile | ≤ 599px | Single column, reduced padding (0.75rem), condensed typography |
| Tablet | 600–959px | Intermediate layouts, some multi-column |
| Desktop | ≥ 960px | Full multi-column grids, side-by-side panels |

Breakpoints are defined in `apps/web/src/styles/_breakpoints.scss` and imported as SCSS
mixins (`@include bp.mobile { ... }`).

**RTL support:** CSS logical properties (`margin-inline-start`, `padding-block-end`) are used
instead of physical properties. All UI is tested in both English (LTR) and Arabic (RTL).

## 9. Database Strategy

The application uses **hosted Supabase** exclusively. There is no local database to build or
maintain.

- **Local development** uses `supabase start` (Supabase CLI) for a local Postgres + Auth +
  Storage stack, or connects directly to the hosted project.
- **Docker Compose** does not include a Postgres service. It orchestrates the API and frontend
  containers only; database services are external.
- **Migrations** are versioned SQL files in `supabase/migrations/`, applied via
  `supabase db push`. Forward-only; never edit after merge.
- **RLS** on every tenant-scoped table with `USING` and `WITH CHECK` clauses from JWT claims.
- **Connection pooling** via Supabase PgBouncer (transaction mode) for production.

## 10. Logging & Observability

### 10.1 Structured JSON Logging (API)

All API log output is structured JSON written to **stdout** — the only transport. The
implementation lives in `apps/api/src/procurepilot_api/shared/logging.py`.

**Log record fields:**

| Field | Source |
|---|---|
| `timestamp` | ISO 8601, UTC |
| `level` | debug / info / warning / error / critical |
| `logger` | Python logger name (`__name__`) |
| `message` | Log message |
| `trace_id` | Request-scoped trace ID (see §10.2) |
| `exception` | Formatted traceback, if present |
| `extra.*` | Any extra fields passed to the log call |

**Log level** is set via the `API_LOG_LEVEL` environment variable (default `info`). Changing
it requires a container redeployment (see runbook §7.6).

**Module convention:** every module uses `logger = logging.getLogger(__name__)`, giving a
natural hierarchy (`procurepilot_api.modules.quotations.service`, etc.).

### 10.2 Trace ID Propagation

`TraceIdMiddleware` (FastAPI middleware) reads an incoming `X-Trace-Id` header or generates a
UUID4. The ID is stored in a `ContextVar` and:

1. Injected into every JSON log record.
2. Returned in the response `X-Trace-Id` header.
3. Included in every `ErrorEnvelope` response body.

This gives end-to-end request correlation from the frontend through logs and error reports.

### 10.3 Secret Redaction

The `redact()` function in `shared/logging.py` scrubs sensitive data before it reaches stdout:

- **Dict keys** matching `password`, `token`, `secret`, `api_key`, `authorization` (and
  variants) are replaced with `***REDACTED***`.
- **String values** containing `Bearer <token>` or `key=<value>` patterns are masked.
- Redaction is applied to log messages, exception tracebacks, and extra fields.

### 10.4 Error Reporting (Sentry)

Optional integration in `shared/observability.py`. Activated when `SENTRY_DSN` is set.

- Traces disabled by default (`traces_sample_rate=0.0`).
- PII sending disabled (`send_default_pii=False`).
- Initialised before the app factory so startup errors are captured.
- Environment tag from `API_ENV`.

### 10.5 Extraction Worker Logging

The extraction worker uses the same shared `procurepilot-logging` package as the API,
configured in `__main__.py` at startup. It emits the same structured JSON format with
trace IDs and secret redaction.

Key log events:
- **Job start** — `info` with `job_id`, `document_id`.
- **Provider selection** — `info` naming the provider (`stub`, `bedrock`, `azure_di`,
  or `structured`).
- **Bedrock fallback** — `warning` with full exception traceback when Bedrock fails and
  Azure DI takes over. This makes the previously silent fallback visible in container logs.
- **Job success** — `info` with `method`, line count, arithmetic status, quotation status.
- **Job failure** — `error` with full traceback.

Log level is controlled by the `LOG_LEVEL` environment variable (default `info`).

### 10.6 Accessing Production Logs

bunny.net Magic Containers expose container stdout/stderr via the dashboard:

1. Go to bunny.net → App → Container → **Logs** tab.
2. Logs are structured JSON from both the API and extraction worker.
3. Filter by trace ID: search for `"trace_id":"<value>"` in the log viewer.

For persistent log aggregation, configure a log drain to an external service (Datadog,
Logflare, etc.) — not yet set up.

### 10.7 Audit Trail

- Every mutation writes an `AuditEvent` (append-only, no UPDATE/DELETE).
- Health endpoint: `GET /api/health`.
- Extraction and matching metrics emitted per document.

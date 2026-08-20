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

### 2.3 `services/matching-worker`

- Consumes `QuotationLine` ready for matching.
- Layered pipeline:
  1. Deterministic keys (GTIN, supplier SKU, alias hit).
  2. `pg_trgm` lexical similarity.
  3. `pgvector` semantic similarity.
  4. Feature scoring (brand, variant, pack, unit, price plausibility).
  5. Calibrated confidence; auto-accept, auto-reject, or human-review band.
- Writes `MatchDecision` and learned `ProductAlias`.

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

## 8. Error Handling & Observability

- Structured logging to stdout; aggregated by Sentry and PostHog.
- Every mutation writes `AuditEvent`.
- Health endpoint: `GET /api/health`.
- Extraction and matching metrics emitted per document.

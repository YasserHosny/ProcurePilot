# ProcurePilot — Architecture Decision Records (ADRs)

> Key technical decisions and their rationale. Companion to the [Master Roadmap](../roadmap/procurepilot_roadmap.md) and [Tech Stack Blueprint](./tech-stack-blueprint.md).

---

## ADR-001 — Web Frontend Framework: Angular 19

- **Status:** Accepted
- **Context:** Need a stable, enterprise-friendly SPA with strong TypeScript support, a mature component library, and a single language across web and mobile-generated types.
- **Options considered:** Next.js (App Router), React + Vite, Angular.
- **Decision:** Angular 19 (latest stable) with Angular Material, Angular CDK, SCSS, RxJS, and Angular Reactive Forms.
- **Consequences:**
  - Strong out-of-the-box tooling, routing, forms, and i18n path.
  - NgModule-based structure aligns with the blueprint.
  - Nginx serves the built SPA with SPA fallback.

## ADR-002 — Mobile Framework: Flutter

- **Status:** Accepted
- **Context:** Single codebase for iOS and Android; native UI performance; store distribution.
- **Options considered:** React Native via Expo, native iOS + Android, Flutter.
- **Decision:** Flutter (Dart) with OpenAPI-generated Dart types.
- **Consequences:**
  - One mobile engineering hire instead of two native teams.
  - Mobile container in CI is build-only; the runtime artifact is an App Store / Play Store binary.
  - Shared domain contracts generated from the same OpenAPI spec as web.

## ADR-003 — Database & Auth Platform: Supabase

- **Status:** Accepted
- **Context:** Need managed Postgres, Auth, Storage, and Realtime with minimal initial infrastructure work.
- **Options considered:** Self-managed PostgreSQL + custom Auth, Managed provider, Supabase.
- **Decision:** Supabase Postgres 17 with Auth, Storage, Realtime, and Row-Level Security.
- **Consequences:**
  - No hand-rolled auth in Phase 1.
  - Future path to self-managed Postgres remains available.
  - Python backend uses `supabase-py` 2.11.0; frontend uses `@supabase/supabase-js` ^2.105.

## ADR-004 — Document Intelligence: AWS Bedrock + Azure Document Intelligence

- **Status:** Accepted
- **Context:** Need template-free extraction from PDFs/images with a cost-controlled fallback.
- **Options considered:** Frontier VLM only, PaddleOCR/Tesseract, AWS Bedrock (Claude 3 Haiku) + Azure DI fallback.
- **Decision:** Primary extraction via AWS Bedrock (Claude 3 Haiku); fallback to Azure Document Intelligence for cost control and layout heuristics.
- **Consequences:**
  - Strict JSON schema with field-level confidence.
  - Structured inputs (Excel/CSV) bypass LLM calls.
  - Cost per document tracked; caching by document hash.

## ADR-005 — Container Hosting: bunny.net Magic Containers

- **Status:** Accepted
- **Context:** Need managed containers with minimal ops headcount pre-scale.
- **Options considered:** Vercel, Fly.io, AWS ECS, bunny.net Magic Containers.
- **Decision:** bunny.net Magic Containers for Web FE (Nginx, port 80) and Backend (Uvicorn, port 8000); mobile CI produces store binaries.
- **Consequences:**
  - Containers share a network namespace; frontend uses `BACKEND_HOST=localhost`.
  - CI deploys via `BunnyWay/actions/container-update-image` with GHCR images.
  - Three path-filtered workflows: backend, frontend, mobile build.

## ADR-006 — Reverse Proxy: Nginx

- **Status:** Accepted
- **Context:** Angular SPA needs `/api/` proxy to backend, SPA fallback, and security headers.
- **Options considered:** Traefik, Caddy, Nginx.
- **Decision:** Nginx Alpine in the frontend container; config template injects `BACKEND_HOST` at runtime.
- **Consequences:**
  - SPA fallback with `try_files`.
  - Security headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options).
  - Gzip and cache control for CSS/index.html.

## ADR-007 — Schema Migrations: Versioned SQL + Supabase CLI

- **Status:** Accepted
- **Context:** Need auditable, reproducible schema evolution against Supabase Postgres.
- **Options considered:** SQLAlchemy + Alembic, versioned SQL files, Supabase CLI migrations.
- **Decision:** Application-managed versioned SQL files in `<project>-backend/migrations/`; Supabase CLI migrations for local dev.
- **Consequences:**
  - Explicit, reviewable migrations.
  - No runtime ORM dependency; backend uses `supabase-py` and Pydantic schemas.

## ADR-008 — Monorepo Layout: Apps + Packages + Services

- **Status:** Accepted
- **Context:** Web, mobile, backend, shared types, and AI workers in one repo.
- **Options considered:** Separate repos per service, blueprint `formcraft-backend`/`formcraft-frontend` root directories.
- **Decision:** `apps/` (web, mobile, api), `packages/` (domain-types, ui, validation, i18n), `services/` (extraction, matching, optimiser), plus `ml/`, `infra/`, `.github/workflows/`.
- **Consequences:**
  - Shared types and validation generated from OpenAPI.
  - Turborepo + pnpm for JS; uv for Python.
  - CI path-filtered workflows keep builds fast.

## ADR-009 — AI Evaluation Harness in CI

- **Status:** Accepted
- **Context:** Prevent silent regression on extraction and matching accuracy.
- **Options considered:** Manual QA only, periodic offline evals, CI gate on every model/prompt change.
- **Decision:** Versioned benchmark datasets; any model, prompt, or threshold change runs the eval suite; precision regression blocks merge.
- **Consequences:**
  - Quality of AI outputs is measurable and enforced.
  - Dataset grows continuously from review-queue corrections.

## ADR-010 — Recorded exception: proceeding to Phase 2 without a passed G1 gate

- **Status:** Accepted (exception, not a principle amendment)
- **Context:** The constitution's Development Workflow and Phase Discipline section states stage
  gates are binding — "Phase N+1 code MUST NOT be written until gate G(N-1) is passed and
  recorded" — and non-compliance blocks merge "unless an explicit, recorded exception is granted
  by the project owner." Phase 1 (chunks 4.1–4.6 / R1.0–R1.5) merged to `main` on 2026-08-22 (PR
  #2), completing Phase 1's engineering scope. The roadmap's G1 → Phase 2 exit criteria (§2.3) —
  matching precision and extraction accuracy targets met against the Phase 0 benchmark datasets,
  ≥10 verified savings, ≥8 paying customers on the self-serve product — are business/usage
  milestones that have not been independently evidenced anywhere in this repo.
- **Decision:** The project owner explicitly chose to proceed into Phase 2 build work on
  2026-08-22 without that evidence, overriding the gate rather than waiting for it. This is
  recorded here per the constitution's own exception-granting mechanism, not treated as the gate
  having been passed.
- **Consequences:**
  - `CLAUDE.md`'s Current phase section reflects this exception and Phase 2 as active.
  - The G1 exit criteria remain unmet; if usage data later contradicts the product assumptions
    Phase 2 is being built on (accuracy, retention, willingness to pay), that risk was knowingly
    accepted at this decision point, not discovered late.
  - Future phase transitions (G2 → Phase 3, G3 → Phase 4) still default to requiring their gates
    unless a similar explicit, recorded exception is granted.

## ADR-011 — Separate bunny.net App for Background Workers

- **Status:** Accepted
- **Context:** The extraction worker and Redis need to run alongside the API but should not
  share compute resources or restart cycles with the production app.
- **Options considered:** (a) Add worker + Redis containers to the production app — simplest
  but couples deployments and shares CPU/RAM. (b) Separate bunny.net app — independent scaling,
  isolated restarts, but requires cross-app networking. (c) External VPS — full control but
  more ops overhead.
- **Decision:** Separate bunny.net app (`procurepilot-workers`) with the extraction worker and
  Redis in a shared network namespace. The production app's backend connects to Redis via the
  workers app's Anycast IP.
- **Consequences:**
  - Worker deployments do not restart the API or frontend.
  - Cross-app communication uses bunny.net Anycast IPs, not DNS names.
  - A fourth GitHub secret (`BUNNY_WORKERS_APP_ID`) is required.
  - The `REDIS_URL` on the backend container differs from the worker's `REDIS_URL`
    (`<anycast-ip>:6379` vs `localhost:6379`).

## ADR-012 — Responsive-First Web Design with Shared Breakpoints

- **Status:** Accepted
- **Context:** The web SPA must be usable on mobile, tablet, and desktop viewports. Many
  procurement users access the system from phones or tablets on the shop floor.
- **Decision:** A shared SCSS breakpoints mixin (`apps/web/src/styles/_breakpoints.scss`)
  defines three tiers: mobile (≤ 599px), tablet (600–959px), desktop (≥ 960px). CSS logical
  properties are mandatory for RTL support.
- **Consequences:**
  - Every component includes responsive adjustments via `@include bp.mobile { ... }`.
  - Layouts collapse gracefully: side-by-side → single column, reduced padding, condensed
    fonts.
  - No horizontal overflow on any viewport width.
  - RTL (Arabic) layout is a first-class citizen, not an afterthought.

## ADR-013 — Remote-Only Database (No Local DB Build)

- **Status:** Accepted
- **Context:** Supabase provides Postgres, Auth, Storage, and Realtime as a hosted service.
  Building and maintaining a local Postgres instance duplicates infrastructure that Supabase
  already manages.
- **Decision:** The application uses hosted Supabase exclusively. Local development uses the
  Supabase CLI (`supabase start`) for a local stack, or connects directly to the hosted
  project. Docker Compose does not include a Postgres service.
- **Consequences:**
  - Developers run `supabase start` instead of `docker compose up` for database services.
  - Migrations are the single source of truth for schema.
  - No database container to build, version, or maintain in Docker Compose.
  - Development requires internet access (for hosted project) or the Supabase CLI (for local).

## ADR-014 — Extraction Provider Fallback Chain

- **Status:** Accepted
- **Context:** The extraction worker supports multiple AI providers. Bedrock (Claude 3 Haiku)
  is the primary provider; Azure Document Intelligence is the fallback. Provider failures
  should not block extraction entirely.
- **Decision:** When `EXTRACTION_PROVIDER_MODE=bedrock`, the worker tries Bedrock first. If
  Bedrock throws any exception, it silently falls back to Azure DI. The provenance metadata
  records which provider actually performed the extraction.
- **Consequences:**
  - Extraction continues even when Bedrock credentials are misconfigured or the service is
    unavailable.
  - The fallback is silent — operators must check provenance metadata to know which provider
    ran. Monitoring should alert when `method != bedrock` despite the mode being `bedrock`.
  - The stub provider (`FakeExtractionProvider`) misleadingly sets `method: "bedrock"` in
    provenance — always verify `model_version` is not `stub-provider-v1`.

## ADR-015 — Structured JSON Logging with Trace IDs and Secret Redaction

- **Status:** Accepted
- **Context:** Container-based deployments write to stdout; structured logs are essential for
  filtering, correlation, and aggregation. Sensitive data (tokens, API keys) must never appear
  in log output.
- **Options considered:** (a) Plain text logging with grep. (b) Structured JSON with manual
  field construction. (c) Structured JSON via a custom `logging.Formatter` with middleware-
  injected trace IDs and automatic secret redaction.
- **Decision:** Option (c). A `JsonFormatter` in `shared/logging.py` emits one JSON object
  per log record to stdout. `TraceIdMiddleware` propagates or generates a UUID4 trace ID per
  request via `ContextVar`, included in every log record and every error response. A `redact()`
  function scrubs sensitive dict keys and string patterns before output.
- **Consequences:**
  - Every API log record is machine-parseable and carries a trace ID for request correlation.
  - Secrets are scrubbed automatically — no per-call redaction needed by module code.
  - Both the API and the extraction worker share the `procurepilot-logging` package,
    ensuring identical log format across all services.
  - Log level is configurable at deploy time via `API_LOG_LEVEL` without code changes.

## ADR-016 — G2 Stage Gate Evaluation & Transition to Phase 3

- **Status:** Accepted (recorded transition and evaluation)
- **Context:** Phase 2 ("Workflow Expansion", releases R2.0–R2.5) engineering scope completed with
  the close-out of Wave 18 (`012-reporting-hardening`). All technical gates passed in CI run
  `35146371910` with 1000 backend tests, 343 web unit tests, Playwright E2E suites, axe-core WCAG
  2.1 AA a11y across English and Arabic, and RLS tenant isolation all verified green. The roadmap's
  G2 exit criteria (§2.3) require ≥70% workflow-origination, mobile adoption target met, and ≥90%
  retention — business adoption metrics that depend on live multi-month pilot cohort usage.
- **Decision:** Formally record software completion of Phase 2 in `docs/quality/g2-stage-gate-evaluation.md`
  and authorize the engineering transition into Phase 3 ("Connected Procurement", starting with R3.0
  Automated Ingestion: email forwarding + WhatsApp capture), mirroring the precedent established by
  ADR-010 for Phase 1→Phase 2.
- **Consequences:**
  - `AGENTS.md` and `CLAUDE.md` updated to reflect Phase 2 complete and Phase 3 initiation.
  - Development may proceed into Phase 3 specification, architecture, and implementation.
  - Third-party penetration testing is scoped in `docs/operations/pentest-scope.md` and ready for
    external engagement prior to general commercial availability.

## ADR-017 — Grounded Procurement Analyst Retrieval Architecture

- **Status:** Accepted
- **Context:** R4.2 introduces the Grounded Procurement Analyst feature. To comply with Constitution Principle I (Evidence Over Assertion) and ensure deterministic, auditable answers, the system must separate question understanding (intent classification) from answer generation (factual content, numbers, and citations).
- **Decision:** Question understanding for R4.2 reuses the existing Bedrock/Claude provider pattern from ADR-004 (initial provider choice) and ADR-014 (fallback chain) — no new LLM provider was introduced. The language model in `intent.py`'s `BedrockIntentProvider` ONLY classifies the question into a category + entities (FR-005) — it never generates the answer's factual content, numbers, or citations; those come exclusively from `retrieval.py`'s deterministic pure functions.
- **Consequences:**
  - The feature provides retrieval-augmented question routing, not free generation.
  - The `IntentResult` Pydantic model enforces this at the boundary, ensuring no free text leaks through from the LLM.
  - Calculation and formatting logic inside `retrieval.py` guarantees replay-determinism (Constitution Principle II) and relies on explicit typed input objects passed by the caller.

## ADR-018 — Reuse Mailgun for Outbound RFQ Dispatch

- **Status:** Accepted
- **Context:** R4.3 introduces outbound RFQ email dispatch. The inbound side of email ingestion already runs on Mailgun (via webhook security configured with `MAILGUN_SIGNING_KEY`). We need an email provider to dispatch these outbound RFQs. Introducing a second transactional email vendor just for outbound would duplicate domain verification and configuration complexity.
- **Decision:** Outbound RFQ dispatch reuses the Mailgun vendor relationship already established for inbound ingestion, rather than introducing a second transactional-email vendor. A thin outbound wrapper (`MailgunMailer`) will interact with the Mailgun Messages API using `MAILGUN_API_KEY` and `MAILGUN_SENDING_DOMAIN`. Note that `ingestion_email_provider` currently defaults to `"stub"` in this deployment; Mailgun is the chosen vendor via real webhook-verification code, but not yet a fully live-in-production inbound integration.
- **Consequences:**
  - One email vendor for both inbound and outbound routing.
  - Reduced DNS and credentials management overhead.
  - Mailgun send failures must leave the RFQ recipient in a `draft` status, never silently marking it as `sent`.

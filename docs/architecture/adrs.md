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

# R4.0 Forecasting and Reorder Proposals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an evidence-backed, tenant-isolated R4.0 forecast and reorder-proposal workflow while keeping G3 explicitly unmet.

**Architecture:** Add a forecasting module with a pure calculation service, immutable forecast snapshots, and proposal preparation through the existing purchase-request service. Add a focused Angular feature that presents uncertainty and the human action without any automatic purchasing path.

**Tech Stack:** Python 3.12, FastAPI, psycopg, Supabase Postgres RLS, Pydantic v2, Angular 19, RxJS, ngx-translate, Karma/Jasmine.

---

### Task 1: Add R4.0 schema and specification traceability

**Files:**
- Create: `supabase/migrations/20260920000008_forecasting_reorder.sql`
- Modify: `docs/quality/r3.4-release-evidence.md`
- Test: `apps/api/tests/integration/test_forecasting_isolation.py`

- [ ] **Step 1: Write the failing isolation fixtures** for two tenants, one signal, one forecast, and one proposal.
- [ ] **Step 2: Run the focused integration test** and verify the tables are absent or the test fails at setup.
- [ ] **Step 3: Add the migration** with composite tenant foreign keys, append-only forecast data, proposal uniqueness, forced RLS, `USING` and `WITH CHECK` policies, and authenticated/service-role grants.
- [ ] **Step 4: Run the isolation test** and verify cross-tenant list and direct reads return no rows.
- [ ] **Step 5: Record the controlled R4 exception** in the release evidence without changing the G3 measurements.

### Task 2: Implement deterministic forecast calculation

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/forecasting/__init__.py`
- Create: `apps/api/src/procurepilot_api/modules/forecasting/calculator.py`
- Create: `apps/api/src/procurepilot_api/modules/forecasting/schemas.py`
- Test: `apps/api/tests/unit/test_forecast_calculator.py`

- [ ] **Step 1: Write failing tests** for full data, provisional history, missing velocity, missing stock, uncertainty widening, and deterministic rounding.
- [ ] **Step 2: Run the unit tests** and verify they fail because the calculator does not exist.
- [ ] **Step 3: Implement the pure calculator** with pinned `forecast-v1` math and explicit states.
- [ ] **Step 4: Run the focused unit tests** and verify all pass.

### Task 3: Add authenticated forecast and proposal services

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/forecasting/service.py`
- Create: `apps/api/src/procurepilot_api/modules/forecasting/router.py`
- Modify: `apps/api/src/procurepilot_api/main.py`
- Modify: `apps/api/src/procurepilot_api/config.py`
- Test: `apps/api/tests/contract/test_forecasting_contract.py`
- Test: `apps/api/tests/integration/test_forecasting_api.py`

- [ ] **Step 1: Write failing contract tests** for list and prepare-request response envelopes, role checks, and missing resources.
- [ ] **Step 2: Implement tenant-scoped list queries** returning the latest open proposal per product with cursor pagination.
- [ ] **Step 3: Implement idempotent prepare-request** using the existing requests service and a proposal unique constraint.
- [ ] **Step 4: Add audit events** for forecast generation and proposal preparation.
- [ ] **Step 5: Register the router and run focused API tests.**

### Task 4: Add the forecast review UI

**Files:**
- Create: `apps/web/src/app/features/forecasting/reorder-queue/reorder-queue.component.ts`
- Create: `apps/web/src/app/features/forecasting/reorder-queue/reorder-queue.component.html`
- Create: `apps/web/src/app/features/forecasting/reorder-queue/reorder-queue.component.scss`
- Create: `apps/web/src/app/features/forecasting/reorder-queue/reorder-queue.component.spec.ts`
- Modify: `apps/web/src/app/app.routes.ts`
- Modify: `packages/i18n/en.json`
- Modify: `packages/i18n/ar.json`

- [ ] **Step 1: Write failing component tests** for loading, empty, `g3_unmet`, provisional, insufficient-data, and prepared states.
- [ ] **Step 2: Implement the API client and standalone component** with translated strings, logical CSS, and accessible action controls.
- [ ] **Step 3: Add the route and navigation entry** only where the existing shell pattern requires it.
- [ ] **Step 4: Run focused Angular tests and production build.**

### Task 5: Verify and document the exception boundary

**Files:**
- Modify: `docs/architecture/api-specification.md`
- Modify: `docs/architecture/data-dictionary.md`
- Test: `apps/api/tests/integration/test_tenant_isolation.py`

- [ ] **Step 1: Add API and data-dictionary contracts** for the forecast and proposal entities.
- [ ] **Step 2: Run API unit, integration, contract, web unit, and production build gates.**
- [ ] **Step 3: Run the G3 evidence command** and confirm its output remains unmet.
- [ ] **Step 4: Review the diff for secrets, hardcoded UI copy, autonomous-purchase paths, and missing RLS.**


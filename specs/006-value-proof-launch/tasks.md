---
description: "Task list for Value Proof and Launch Readiness implementation"
---

# Tasks: Value Proof and Launch Readiness

**Input**: Design documents from `/specs/006-value-proof-launch/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/savings-and-billing.openapi.yaml, quickstart.md

**Tests**: Included. The spec makes outcome capture, verified savings, evidence links, async Excel/PDF export, plan-gated onboarding, tenant isolation, RBAC, accessibility, RTL, performance, and security release conditions.

**Organization**: grouped by setup, blocking foundation, then user stories so each story is independently implementable and testable. The final cross-cutting phase includes the whole-product accessibility/RTL audit-and-fix pass because US4 is launch-readiness work, not a report-only afterthought.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable - different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md; setup, foundational and cross-cutting tasks may have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: repo-level dependency, configuration, i18n and local stack wiring for savings, exports and plan display.

**Already complete outside this checklist**: the orchestrator already wrote, applied and verified `supabase/migrations/20260821000030_value_proof_enums.sql`, `supabase/migrations/20260821000031_purchase_saving_records.sql`, `supabase/migrations/20260821000032_export_jobs.sql`, `supabase/migrations/20260821000033_plan_billing_account.sql`, `supabase/migrations/20260821000034_value_proof_rls.sql` and `supabase/migrations/20260821000035_saving_record_immutability.sql`, including the two verified-saving immutability triggers. The orchestrator also extended `apps/api/tests/integration/test_tenant_isolation.py` and verified it passing 46/46 twice consecutively. Do not create duplicate migration, RLS, trigger, or tenant-isolation-extension tasks in this chunk.

- [ ] T001 [P] Add `openpyxl` and `reportlab` to `apps/api/pyproject.toml` for apps/api-owned export rendering, with no new `services/` package or real billing SDK
- [ ] T002 Add `EXPORT_QUEUE_NAME=exports` and `SUPABASE_EXPORTS_BUCKET=exports` to `.env.example` and expose them through `apps/api/src/procurepilot_api/config.py`
- [ ] T003 [P] Add the `savings.*`, `exports.*`, `billing.*`, `plans.*` and onboarding plan-display keys to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping English and Arabic key parity before new screens ship
- [ ] T004 [P] Add shell route entries for savings ledger, outcome capture, saving evidence, export jobs and plan display in `apps/web/src/app/app.routes.ts`, following the existing offers and alerts route style
- [ ] T005 Add an export-worker process to `docker-compose.yml` using apps/api's own image and command `python -m procurepilot_api.workers.export_worker`, consuming the `exports` queue and not creating a new `services/` directory
- [ ] T006 [P] Add value-proof E2E test data helpers in `apps/web/tests/e2e/support/api.ts` for creating buyer workspaces with matched offers, price history, pending savings, verified savings and plan accounts

**Checkpoint**: dependencies, queue settings, routes, i18n and compose wiring are ready; database migrations/RLS/triggers remain the orchestrator-completed work above.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: API module boundaries, schemas, worker entrypoint shape and typed frontend API clients that all user stories depend on.

⚠️ **Everything else depends on this phase.** No user-story work starts until the FastAPI imports, Pydantic schemas, worker callable and frontend clients are in place.

- [ ] T007 Create the savings module skeleton in `apps/api/src/procurepilot_api/modules/savings/__init__.py`, `apps/api/src/procurepilot_api/modules/savings/schemas.py`, `apps/api/src/procurepilot_api/modules/savings/service.py` and `apps/api/src/procurepilot_api/modules/savings/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T008 Create the billing module skeleton in `apps/api/src/procurepilot_api/modules/billing/__init__.py`, `apps/api/src/procurepilot_api/modules/billing/schemas.py`, `apps/api/src/procurepilot_api/modules/billing/provider.py`, `apps/api/src/procurepilot_api/modules/billing/service.py` and `apps/api/src/procurepilot_api/modules/billing/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T009 Create the exports module skeleton in `apps/api/src/procurepilot_api/modules/exports/__init__.py`, `apps/api/src/procurepilot_api/modules/exports/schemas.py`, `apps/api/src/procurepilot_api/modules/exports/service.py`, `apps/api/src/procurepilot_api/modules/exports/renderers.py`, `apps/api/src/procurepilot_api/modules/exports/storage.py` and `apps/api/src/procurepilot_api/modules/exports/router.py`, and register its router in `apps/api/src/procurepilot_api/main.py`
- [ ] T010 [P] Create the apps/api export worker package files `apps/api/src/procurepilot_api/workers/__init__.py` and `apps/api/src/procurepilot_api/workers/export_worker.py`, with callable `process_export_job(payload)` and no imports from a separate worker service
- [ ] T011 [P] Create Pydantic schemas for purchases, savings, evidence, exports, plans, billing accounts and limit checks in `apps/api/src/procurepilot_api/modules/savings/schemas.py`, `apps/api/src/procurepilot_api/modules/exports/schemas.py` and `apps/api/src/procurepilot_api/modules/billing/schemas.py`, matching `specs/006-value-proof-launch/contracts/savings-and-billing.openapi.yaml` with Money as `{amount,currency}` everywhere
- [ ] T012 [P] Add typed frontend API clients and models in `apps/web/src/app/features/savings/savings-api.ts`, `apps/web/src/app/features/savings/exports-api.ts` and `apps/web/src/app/features/onboarding/billing-api.ts`, using decimal strings and the exact OpenAPI endpoint paths
- [ ] T013 [P] Create shared money, status and polling presentation helpers in `apps/web/src/app/features/savings/savings-formatting.ts` and `apps/web/src/app/features/savings/export-job-state.ts`, using i18n keys and CSS-logical layout assumptions only
- [ ] T014 [P] Add backend contract drift coverage skeleton in `apps/api/tests/contract/test_value_proof_openapi_drift.py`, verifying implemented route paths and response models against `specs/006-value-proof-launch/contracts/savings-and-billing.openapi.yaml`

**Checkpoint**: FastAPI imports the new modules, the export worker entrypoint is importable from apps/api, and Angular code can compile against typed clients.

---

## Phase 3: User Story 1 - Record outcome and verify a saving (P1)

**Goal**: a buyer records an actual purchase outcome, sees a pending savings-ledger row with baseline/actual/delta captured from chunk 4.5 price history, opens evidence, and explicitly verifies the saving.

**Independent Test**: record a purchase outcome against a product with existing compare/price-history evidence, verify it, and confirm the ledger row, values, status, and evidence links work end to end.

### Tests for User Story 1

- [ ] T015 [P] [US1] Write contract tests for `POST /purchases`, `GET /savings`, `GET /savings/{id}`, `GET /savings/{id}/evidence` and `POST /savings/{id}/verify` in `apps/api/tests/contract/test_savings_contract.py`, covering OpenAPI shapes, Money pairs, 403/404/409/422 envelopes and cursor limits
- [ ] T016 [P] [US1] Write baseline-capture unit tests in `apps/api/tests/unit/test_savings_baseline_capture.py`, proving the service reads from chunk 4.5's existing price-history read model in `apps/api/src/procurepilot_api/modules/offers/price_history.py` and does not recompute landed cost, matching, or price history
- [ ] T017 [P] [US1] Write purchase-outcome integration tests in `apps/api/tests/integration/test_purchase_outcome.py`, proving one transaction creates `purchase_record` and paired pending `saving_record`, supports negative/zero deltas, stores explicit currencies and treats cross-tenant references as not found
- [ ] T018 [P] [US1] Write saving verification integration tests in `apps/api/tests/integration/test_saving_verification.py`, proving owner/buyer verification including self-verification changes only `status`, `verified_at` and `verified_by`, never baseline, actual, delta or evidence
- [ ] T019 [P] [US1] Write saving evidence integration tests in `apps/api/tests/integration/test_saving_evidence.py`, proving evidence includes purchase, quotation, match decision, competing offers and stored calculation snapshot, with missing compare context falling back to historical baseline evidence
- [ ] T020 [P] [US1] Write savings RBAC tests in `apps/api/tests/integration/test_savings_rbac.py`, proving owner/buyer may record and verify while branch_manager/approver/viewer may only read ledger and evidence
- [ ] T021 [P] [US1] Write frontend unit tests for the outcome-capture screen in `apps/web/src/app/features/savings/outcome-capture/outcome-capture.component.spec.ts`, covering decimal validation, explicit currency display, owner/buyer action controls and baseline-unavailable messaging
- [ ] T022 [P] [US1] Write frontend unit tests for ledger and evidence views in `apps/web/src/app/features/savings/savings-ledger/savings-ledger.component.spec.ts` and `apps/web/src/app/features/savings/saving-evidence/saving-evidence.component.spec.ts`, covering pending versus verified display and immutable verified-state affordances
- [ ] T023 [P] [US1] Write outcome-to-verified-saving E2E coverage in `apps/web/tests/e2e/value-proof-savings.spec.ts`, proving record outcome, open evidence, verify, negative delta display, keyboard operation and Arabic RTL layout

### Implementation for User Story 1

- [ ] T024 [P] [US1] Implement baseline selection helpers in `apps/api/src/procurepilot_api/modules/savings/baseline.py`, reading from chunk 4.5's existing price-history read model and `price_history_summary()`, and explicitly not recomputing landed cost, matching, or price history
- [ ] T025 [US1] Implement purchase outcome creation in `apps/api/src/procurepilot_api/modules/savings/service.py`, validating visible `workspace_product`, `supplier`, `quotation_line`, `match_decision` and `landed_cost` references under caller tenant RLS and inserting `purchase_record` plus paired pending `saving_record` in one transaction
- [ ] T026 [US1] Implement savings ledger listing and single-record reads in `apps/api/src/procurepilot_api/modules/savings/service.py`, supporting status, period, supplier, branch placeholder, cursor and capped limit filters with cross-tenant not-found semantics
- [ ] T027 [US1] Implement saving evidence assembly in `apps/api/src/procurepilot_api/modules/savings/evidence.py`, linking the stored calculation snapshot to purchase, quotation, competing offers and compare context without denormalising new source-of-truth calculations
- [ ] T028 [US1] Implement explicit verification in `apps/api/src/procurepilot_api/modules/savings/service.py`, allowing owner/buyer self-verification and updating only `status`, `verified_at` and `verified_by`
- [ ] T029 [US1] Expose `POST /purchases`, `GET /savings`, `GET /savings/{id}`, `GET /savings/{id}/evidence` and `POST /savings/{id}/verify` in `apps/api/src/procurepilot_api/modules/savings/router.py`, preserving read access for active workspace roles and owner/buyer mutation guards
- [ ] T030 [P] [US1] Build the outcome-capture screen in `apps/web/src/app/features/savings/outcome-capture/outcome-capture.component.ts`, `.html` and `.scss`, reachable from the compare flow and using only `packages/i18n` strings
- [ ] T031 [P] [US1] Build the savings-ledger list screen in `apps/web/src/app/features/savings/savings-ledger/savings-ledger.component.ts`, `.html` and `.scss`, showing baseline, actual, delta, currency, pending/verified status and filters
- [ ] T032 [P] [US1] Build the saving evidence view in `apps/web/src/app/features/savings/saving-evidence/saving-evidence.component.ts`, `.html` and `.scss`, showing purchase, quotation, competing offers and calculation evidence with logical CSS properties
- [ ] T033 [P] [US1] Add verify-action UI handling in `apps/web/src/app/features/savings/saving-evidence/saving-evidence.component.ts`, showing owner/buyer controls and read-only verified state without implying a row can be edited after verification
- [ ] T034 [US1] Add compare-to-outcome navigation in `apps/web/src/app/features/offers/compare/compare.component.ts` and `apps/web/src/app/features/offers/compare/compare.component.html`, passing only product/evidence identifiers and never a tenant id

**Checkpoint**: US1 is demonstrable independently from existing chunk 4.5 price-history data, with no second landed-cost, matching, or price-history computation.

**Parallel execution note**: T015-T023 can run together after Phase 2; T024 is independent but must land before T025; T030-T033 can proceed against the typed client once T012 is stable.

---

## Phase 4: User Story 2 - Export savings ledger (P1)

**Goal**: a buyer requests an async Excel or PDF export of verified savings, polls the durable job resource, and receives a complete or intentionally empty file from Supabase Storage.

**Independent Test**: request xlsx and pdf exports for a period containing verified savings and a period containing none, then poll each job to completion and inspect result metadata and rendered content.

### Tests for User Story 2

- [ ] T035 [P] [US2] Write contract tests for `POST /exports` and `GET /exports/{id}` in `apps/api/tests/contract/test_exports_contract.py`, covering `ExportCreate`, `ExportJob`, 202 queued responses, terminal statuses, branch_id unsupported behavior and error envelopes
- [ ] T036 [P] [US2] Write export service integration tests in `apps/api/tests/integration/test_exports_api.py`, proving owner/buyer enqueue, read access for active roles, verified-only row inclusion, empty-period exports and cross-tenant job reads returning not found
- [ ] T037 [P] [US2] Write renderer unit tests in `apps/api/tests/unit/test_savings_export_renderers.py`, proving `openpyxl` and `reportlab` outputs include baseline, actual, delta, currency, row count and evidence references, including an intentionally empty result
- [ ] T038 [P] [US2] Write export worker tests in `apps/api/tests/unit/test_export_worker.py`, proving `queued -> running -> completed/failed`, structured errors, RQ payload `{job_id, tenant_id}`, queue name `exports` and callable `procurepilot_api.workers.export_worker.process_export_job`
- [ ] T039 [P] [US2] Write Supabase Storage wiring tests in `apps/api/tests/unit/test_export_storage.py`, proving completed exports upload to bucket `exports` at `{tenant_id}/savings/{export_job_id}.{format}` and only completed jobs expose `download_url`
- [ ] T040 [P] [US2] Write frontend unit tests for export triggering and polling in `apps/web/src/app/features/savings/export-savings/export-savings.component.spec.ts`, mirroring the chunk 4.3 quotation upload and chunk 4.5 basket-split polling state pattern
- [ ] T041 [P] [US2] Write export E2E coverage in `apps/web/tests/e2e/savings-export.spec.ts`, proving xlsx, pdf, empty export, failed job display, automatic polling and Arabic RTL layout

### Implementation for User Story 2

- [ ] T042 [US2] Implement export job creation and RQ enqueueing in `apps/api/src/procurepilot_api/modules/exports/service.py`, inserting `export_job.status='queued'`, sending payload `{job_id, tenant_id}` to `procurepilot_api.workers.export_worker.process_export_job`, and never accepting tenant id from request input
- [ ] T043 [US2] Implement `POST /exports` and `GET /exports/{id}` in `apps/api/src/procurepilot_api/modules/exports/router.py`, guarding creation to owner/buyer, allowing workspace read access, enforcing idempotency and preserving cross-tenant not-found semantics
- [ ] T044 [P] [US2] Implement verified-savings export query logic in `apps/api/src/procurepilot_api/modules/exports/service.py`, filtering by period and supplier, treating non-null Phase 1 `branch_id` as unsupported or empty per research R3, and excluding pending savings
- [ ] T045 [P] [US2] Implement the Excel renderer in `apps/api/src/procurepilot_api/modules/exports/renderers.py` with `openpyxl`, producing a self-contained savings ledger with explicit amount/currency columns and evidence references
- [ ] T046 [P] [US2] Implement the PDF renderer in `apps/api/src/procurepilot_api/modules/exports/renderers.py` with `reportlab`, producing a human-readable savings summary and clear empty-result document
- [ ] T047 [P] [US2] Implement Supabase Storage upload and download-reference handling in `apps/api/src/procurepilot_api/modules/exports/storage.py`, writing only to bucket `exports` and path `{tenant_id}/savings/{export_job_id}.{format}`
- [ ] T048 [US2] Implement the apps/api worker loop and `process_export_job` in `apps/api/src/procurepilot_api/workers/export_worker.py`, consuming the `exports` RQ queue, marking durable job status, rendering files and storing structured failures
- [ ] T049 [P] [US2] Build the export trigger and job-polling screen in `apps/web/src/app/features/savings/export-savings/export-savings.component.ts`, `.html` and `.scss`, following the existing job-polling UI pattern from quotation extraction and basket split
- [ ] T050 [P] [US2] Add export links and status affordances to `apps/web/src/app/features/savings/savings-ledger/savings-ledger.component.ts` and `apps/web/src/app/features/savings/savings-ledger/savings-ledger.component.html`, without blocking the ledger list on export rendering

**Checkpoint**: US2 works as an async durable job using apps/api's own worker entrypoint, with no new deployable package and no export of pending savings.

**Parallel execution note**: T035-T041 can run together after Phase 2; T045-T047 are independent renderer/storage work; T042 and T048 must agree on the RQ payload before end-to-end testing.

---

## Phase 5: User Story 3 - Self-onboard with plan gating (P1)

**Goal**: a new workspace receives a stub-backed billing account and plan, the user sees the assigned plan after onboarding, and active catalogue product count is gated by plan limits.

**Independent Test**: sign up, create a workspace, confirm the Starter plan and active catalogue product limit are displayed, then reach the configured catalogue limit and receive a clear plan-limit response.

### Tests for User Story 3

- [ ] T051 [P] [US3] Write contract tests for `GET /billing/account` and `GET /billing/limits/active-catalogue-products` in `apps/api/tests/contract/test_billing_contract.py`, covering the OpenAPI `BillingAccount`, `Plan`, `LimitCheck` and missing-account 404 shapes
- [ ] T052 [P] [US3] Write billing provider unit tests in `apps/api/tests/unit/test_stub_billing_provider.py`, proving deterministic `stub_customer:{tenant_id}` and `stub_subscription:{tenant_id}:starter`, Starter default assignment and no real payment transaction or Stripe dependency
- [ ] T053 [P] [US3] Write billing integration tests in `apps/api/tests/integration/test_billing_account.py`, proving workspace creation assigns a `billing_account`, plan reads join shared `plan`, and missing billing account is surfaced as configuration error
- [ ] T054 [P] [US3] Write active-catalogue-product limit tests in `apps/api/tests/integration/test_plan_limits.py`, proving Starter allows 100 active `workspace_product` rows and creating or unarchiving the 101st active product returns a clear plan-limit error
- [ ] T055 [P] [US3] Write catalogue gating RBAC tests in `apps/api/tests/integration/test_catalogue_plan_gating.py`, proving the limit is enforced server-side for owner/buyer catalogue mutations and cannot be bypassed by request input
- [ ] T056 [P] [US3] Write frontend onboarding/plan unit tests in `apps/web/src/app/features/onboarding/plan-display/plan-display.component.spec.ts`, covering plan name, limits, missing-account error and Arabic translations
- [ ] T057 [P] [US3] Write self-onboarding E2E coverage in `apps/web/tests/e2e/self-onboarding-plan.spec.ts`, extending chunk 4.1 signup flow rather than replacing it and proving plan display plus limit messaging

### Implementation for User Story 3

- [ ] T058 [P] [US3] Implement `BillingProvider` Protocol and `StubBillingProvider` in `apps/api/src/procurepilot_api/modules/billing/provider.py`, with `assign_default_plan`, `current_account` and `check_limit` methods from research R4
- [ ] T059 [US3] Implement billing account reads and active catalogue product limit checks in `apps/api/src/procurepilot_api/modules/billing/service.py`, reading `billing_account`, shared `plan` and active `workspace_product` count under tenant RLS
- [ ] T060 [US3] Hook default plan assignment into existing workspace creation in `apps/api/src/procurepilot_api/modules/tenants/service.py`, using the billing provider abstraction and assigning Starter for new workspaces
- [ ] T061 [US3] Enforce `active_catalogue_products` gating in `apps/api/src/procurepilot_api/modules/catalogue/service.py`, blocking create and unarchive operations that would exceed the assigned plan limit with a clear error envelope
- [ ] T062 [US3] Expose `GET /billing/account` and `GET /billing/limits/active-catalogue-products` in `apps/api/src/procurepilot_api/modules/billing/router.py`, preserving read access for active workspace roles and no real payment actions
- [ ] T063 [P] [US3] Add plan and limit client methods in `apps/web/src/app/features/onboarding/billing-api.ts`, using the OpenAPI response shapes and surfacing configuration errors distinctly from empty data
- [ ] T064 [P] [US3] Build the plan-display screen in `apps/web/src/app/features/onboarding/plan-display/plan-display.component.ts`, `.html` and `.scss`, extending the existing chunk 4.1 onboarding flow and using only `packages/i18n` strings
- [ ] T065 [P] [US3] Add plan-limit messaging to catalogue create/unarchive flows in `apps/web/src/app/features/catalogue/product-form/product-form.component.ts` and `apps/web/src/app/features/catalogue/product-list/product-list.component.ts`
- [ ] T066 [US3] Add post-signup navigation to plan display in `apps/web/src/app/features/onboarding/signup/signup.component.ts`, preserving the existing chunk 4.1 signup behavior and not introducing real billing or payment UI

**Checkpoint**: US3 is independently testable with a stub billing provider, no real financial transaction, and one concrete server-enforced plan gate.

**Parallel execution note**: T051-T057 can run together after Phase 2; T058 is independent; T060 depends on the provider contract; T061 depends on T059's limit check semantics.

---

## Phase 6: Polish and Cross-Cutting

**Purpose**: whole-product accessibility/RTL audit-and-fix, docs correction, security/performance review, and final smoke coverage for the Phase 1 launch-ready value path.

- [ ] T067 [P] [US4] Add chunk 4.6 new-screen accessibility specs in `apps/web/tests/e2e/value-proof-a11y.spec.ts`, scanning outcome capture, savings ledger, evidence view, export trigger and plan display in English and Arabic with zero axe-core WCAG 2.1 AA violations
- [ ] T068 [P] [US4] Add the whole-product retrospective accessibility sweep in `apps/web/tests/e2e/phase-one-retrospective-a11y.spec.ts`, covering `auth`, `onboarding`, `catalogue`, `quotations`, `matching`, `offers`, `alerts` and new savings/billing screens in both languages
- [ ] T069 [P] [US4] Add RTL screenshot/structure assertions for representative Phase 1 screens in `apps/web/tests/e2e/phase-one-rtl.spec.ts`, checking tables, compare grids, steppers, dialogs, icon ordering and validation placement
- [ ] T070 [US4] Fix any audit findings in `apps/web/src/app/features/auth/` and `apps/web/src/app/features/onboarding/`, using CSS logical properties and i18n strings only
- [ ] T071 [US4] Fix any audit findings in `apps/web/src/app/features/catalogue/` and `apps/web/src/app/features/quotations/`, using CSS logical properties and i18n strings only
- [ ] T072 [US4] Fix any audit findings in `apps/web/src/app/features/matching/`, `apps/web/src/app/features/offers/` and `apps/web/src/app/features/alerts/`, using CSS logical properties and i18n strings only
- [ ] T073 [US4] Fix any audit findings in `apps/web/src/app/features/savings/` and `apps/web/src/app/features/onboarding/plan-display/`, keeping keyboard operation complete for all new chunk 4.6 actions
- [ ] T074 [P] [US4] Add keyboard-operation E2E coverage for the new value-proof screens in `apps/web/tests/e2e/value-proof-keyboard.spec.ts`, covering outcome capture, verify, export request, job polling and plan-limit messaging without a mouse
- [ ] T075 [P] [US4] Add a full canonical smoke E2E in `apps/web/tests/e2e/phase-one-value-path.spec.ts`, covering self-onboard -> upload -> extract -> compare -> record purchase -> verify saving, matching SC-006
- [ ] T076 [P] Update `docs/architecture/data-dictionary.md` for delivered `PurchaseRecord`, `SavingRecord`, `ExportJob`, `Plan` and `BillingAccount`, replacing the existing sketch-only `SavingRecord` with the real fields, amount/currency pairs and verified-row immutability semantics
- [ ] T077 [P] Update `docs/architecture/api-specification.md` for `POST /purchases`, savings ledger/evidence/verify, `POST /exports`, `GET /exports/{id}`, `GET /billing/account` and `GET /billing/limits/active-catalogue-products`, replacing the existing sketch-only `Savings` and `Reports` sections
- [ ] T078 [P] Add value-proof security review tests in `apps/api/tests/integration/test_value_proof_security.py`, covering owner/buyer write restrictions, read-only roles, no tenant id accepted from request input, export download tenant checks and no real billing transaction behavior
- [ ] T079 [P] Add backend performance/regression tests in `apps/api/tests/integration/test_value_proof_performance.py`, checking savings ledger reads remain within API read targets and large-period exports stay asynchronous rather than request-blocking
- [ ] T080 [P] Add frontend performance/a11y regression coverage in `apps/web/tests/e2e/value-proof-performance.spec.ts`, checking ledger filtering, export polling and compare-to-outcome navigation do not regress the published Phase 1 interaction budgets

**Checkpoint**: every screen shipped in chunks 4.1-4.6 has automated a11y/RTL coverage, known findings are fixed in this chunk, and docs reflect the real delivered API/data model instead of sketches.

---

## Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES
    ↓
    ├── Phase 3 US1 (P1) Outcome capture + verified saving
    │       ↓
    ├── Phase 4 US2 (P1) Savings export       ← depends on verified savings from US1
    ├── Phase 5 US3 (P1) Self-onboard + plans ← can proceed alongside US1 after foundation
    └── Phase 6 Cross-cutting                 ← final audit/fix/review across delivered scope
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies - can start immediately. The migration/RLS/trigger/tenant-isolation work is already complete and not part of the pending dependency graph.
- **Foundational (Phase 2)**: depends on Setup completion and blocks all user-story work.
- **US1 Outcome capture + verified saving (Phase 3)**: depends on Foundational and existing chunk 4.5 offers/price-history read models.
- **US2 Savings export (Phase 4)**: depends on Foundational and the verified-saving ledger shape from US1; renderer and storage pieces can start against fixtures while US1 lands.
- **US3 Self-onboard + plans (Phase 5)**: depends on Foundational and can proceed alongside US1 because it uses billing/catalogue boundaries, not savings.
- **Cross-cutting (Phase 6)**: depends on the implemented screens/APIs it verifies; docs tasks may start once API and data shapes are stable.

### Parallel Opportunities

- Setup tasks T001, T003, T004 and T006 can run in parallel; T002 and T005 touch shared runtime configuration and should be coordinated.
- Foundational tasks T007-T010 can run in parallel after module names are fixed; T011 and T012 can proceed once contract schemas are agreed.
- US1 tests T015-T023 can run together; T024 must land before T025; T030-T033 can proceed against typed client stubs.
- US2 tests T035-T041 can run together; T045-T047 can run in parallel; T042 and T048 coordinate queue payload and status transitions.
- US3 tests T051-T057 can run together; T058 and T063-T064 can proceed in parallel; T060-T061 integrate provider and catalogue gating.
- Cross-cutting a11y specs T067-T069 can run in parallel with docs T076-T077 and review tests T078-T080, but fix tasks T070-T073 depend on findings from T067-T069.

---

## Delegation lanes

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **Orchestrator (already done)** | All six value-proof migrations, RLS, the two immutability triggers, and tenant-isolation test extension | **not delegated** - complete before this tasks file | `supabase/migrations/20260821000030_value_proof_enums.sql`, `20260821000031_purchase_saving_records.sql`, `20260821000032_export_jobs.sql`, `20260821000033_plan_billing_account.sql`, `20260821000034_value_proof_rls.sql`, `20260821000035_saving_record_immutability.sql`, and `apps/api/tests/integration/test_tenant_isolation.py` extension; 46/46 passing twice |
| **Backend (codex)** | `savings`, `billing`, `exports` apps/api modules; schemas, services, routers, RBAC; export worker entrypoint within apps/api; openpyxl/reportlab rendering; billing-provider abstraction and stub; Supabase Storage wiring for `exports`; docker-compose export-worker command using apps/api image; backend tests | lane `backend` -> **codex** | T001-T002, T005, T007-T011, T014-T020, T024-T029, T035-T039, T042-T048, T051-T055, T058-T062, T078-T079 |
| **Frontend (agy)** | outcome-capture screen; savings-ledger list and evidence view; export-trigger and job-polling screen; onboarding/plan-display screen; i18n keys; keyboard/E2E/a11y specs for chunk 4.6's new screens; whole-product retrospective a11y/RTL audit-and-fix pass across every prior chunk's screens | lane `frontend` -> agy | T003-T004, T006, T012-T013, T021-T023, T030-T034, T040-T041, T049-T050, T056-T057, T063-T075, T080 |
| **Docs (codex)** | Correct architecture docs for real delivered data/API shapes; replace sketch-only `Savings`, `Reports`, and `SavingRecord` sections with contract-aligned delivery | lane `backend` -> **codex** | T076-T077 |

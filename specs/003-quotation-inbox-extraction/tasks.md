---
description: "Task list for Quotation Inbox and Extraction Review implementation"
---

# Tasks: Quotation Inbox and Extraction Review

**Input**: Design documents from `/specs/003-quotation-inbox-extraction/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/quotation-inbox.openapi.yaml, quickstart.md

**Tests**: Included. The spec makes extraction accuracy, arithmetic review forcing, tenant isolation, RBAC, trusted-data gating, and accessibility release conditions.

**Organization**: grouped by setup, blocking foundation, then user stories so each story is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable - different files, no dependency on an incomplete task
- **[Story]**: US1-US4 from spec.md; setup, foundational and cross-cutting tasks have no story label
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: repo-level scaffolding for the first asynchronous extraction service, AI evaluation assets, Redis, and quotation i18n.

- [x] T001 Create the extraction-worker package manifest in `services/extraction-worker/pyproject.toml` with Python 3.12, RQ/Redis, Bedrock, Azure Document Intelligence and test dependencies because this chunk is the first real code in that placeholder service
- [x] T002 [P] Create the extraction-worker entrypoint skeleton in `services/extraction-worker/src/procurepilot_extraction_worker/__main__.py` for the RQ worker process, leaving provider implementations to US1
- [x] T003 [P] Create the versioned quotation benchmark skeleton in `ml/benchmarks/quotation_extraction/README.md` and `ml/benchmarks/quotation_extraction/.gitkeep` per engineering-spec.md repository layout
- [x] T004 [P] Create the AI eval harness skeleton in `ml/evals/quotation_extraction/README.md` and `ml/evals/quotation_extraction/.gitkeep` so later model/prompt changes have a fixed home
- [x] T005 Add Redis and `services/extraction-worker` to the local stack in `docker-compose.yml`, matching research R4 and quickstart.md's requirement that Redis delivers jobs while Postgres remains the durable job state
- [x] T006 [P] Add the quotation-inbox i18n namespace to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping English and Arabic keys at parity before any web screen ships

**Checkpoint**: local compose can include Redis and the worker container, and i18n parity is ready for frontend work.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: database shape, tenant/storage isolation, and API module boundaries that all user stories depend on.

⚠️ **Everything else depends on this phase.** Migrations first, Storage isolation as its own boundary, then module skeletons.

- [x] T007 Write migration `supabase/migrations/20260819000017_quotation_reference.sql` creating only the quotation reference enums from data-model.md: document source/status, quotation status, extraction method, job status, review status/priority/reason and arithmetic status
- [x] T008 Write migration `supabase/migrations/20260819000018_documents_quotations.sql` creating `document`, `quotation` and `quotation_line` with exactly the data-model.md fields, FKs, date checks, version self-check, and amount+currency pair checks
- [x] T009 Write migration `supabase/migrations/20260819000019_extraction_review_jobs.sql` creating `field_extraction`, `extraction_job` and `review_task` with exactly the data-model.md fields, uniqueness constraints, correction metadata checks and active-job/task partial indexes
- [x] T010 Write migration `supabase/migrations/20260819000020_quotation_storage.sql` creating the private quotation source-document bucket and tenant-prefixed Storage policies from research R8 because blob access is a second isolation boundary beyond table RLS
- [x] T011 Write migration `supabase/migrations/20260819000021_quotation_rls.sql` applying ENABLE + FORCE row level security plus USING and WITH CHECK tenant policies to `document`, `quotation`, `quotation_line`, `field_extraction`, `extraction_job` and `review_task`
- [x] T012 [P] Create the documents module skeleton in `apps/api/src/procurepilot_api/modules/documents/__init__.py` and register its router in `apps/api/src/procurepilot_api/main.py`
- [x] T013 [P] Create the quotations module skeleton in `apps/api/src/procurepilot_api/modules/quotations/__init__.py` and register its router in `apps/api/src/procurepilot_api/main.py`
- [x] T014 [P] Create the extraction module skeleton in `apps/api/src/procurepilot_api/modules/extraction/__init__.py` and register its router in `apps/api/src/procurepilot_api/main.py`
- [x] T015 [P] Create the jobs module skeleton in `apps/api/src/procurepilot_api/modules/jobs/__init__.py` and register its router in `apps/api/src/procurepilot_api/main.py`
- [x] T016 Implement the shared generic Job resource for `/jobs/{job_id}` in `apps/api/src/procurepilot_api/modules/jobs/router.py`, backed by `extraction_job` rather than Redis so polling has a durable source of truth

**Checkpoint**: migrations apply from scratch; the API imports all four new modules; no user story code starts before this passes.

---

## Phase 3: User Story 1 - Upload a quotation and see it extracted (P1) MVP

**Goal**: a buyer uploads an accepted quotation file, starts asynchronous extraction, and sees structured header/line fields with per-field confidence and provenance.

**Independent Test**: upload a single-supplier PDF or structured CSV/Excel quotation and confirm a `document`, `quotation`, `extraction_job`, line items and `field_extraction` rows are produced without hand-entering line data.

### Tests for User Story 1

- [x] T017 [P] [US1] Write contract tests for `POST /documents/presign`, `POST /quotations`, `POST /quotations/{quotation_id}/extract` and `GET /jobs/{job_id}` in `apps/api/tests/contract/test_quotation_upload_extract_contract.py`
- [x] T018 [P] [US1] Write integration tests proving presigned upload metadata creation and accepted/refused MIME handling in `apps/api/tests/integration/test_quotation_upload.py`
- [x] T019 [P] [US1] Write worker unit tests proving CSV/Excel structured inputs bypass the LLM and emit confidence `1.0000` in `services/extraction-worker/tests/test_structured_parse.py`
- [x] T020 [P] [US1] Write arithmetic and locale parsing tests in `services/extraction-worker/tests/test_arithmetic_validation.py`, reusing `apps/api/src/procurepilot_api/modules/catalogue/csv_import.py` `parse_decimal` so ambiguous values such as `1,234` are refused rather than guessed
- [x] T021 [P] [US1] Extend tenant isolation integration coverage for US1 records in `apps/api/tests/integration/test_quotation_upload_isolation.py`, proving cross-tenant reads of `document`, `quotation` and `extraction_job` return not found
- [x] T022 [P] [US1] Write extraction workflow integration tests in `apps/api/tests/integration/test_extraction_workflow.py` proving structured files bypass the LLM, arithmetic mismatch forces review status, and `field_extraction` rows are written per field

### Implementation for User Story 1

- [x] T023 [P] [US1] Create document Pydantic schemas in `apps/api/src/procurepilot_api/modules/documents/schemas.py` for PresignRequest, PresignResponse and Document matching the OpenAPI contract
- [x] T024 [US1] Implement document storage-path allocation and metadata persistence in `apps/api/src/procurepilot_api/modules/documents/service.py`, deriving tenancy from the verified JWT claim rather than client input
- [x] T025 [US1] Implement `POST /documents/presign` and `GET /documents/{document_id}` in `apps/api/src/procurepilot_api/modules/documents/router.py`, refusing unsupported media before extraction per FR-004
- [x] T026 [P] [US1] Create quotation Pydantic schemas in `apps/api/src/procurepilot_api/modules/quotations/schemas.py` for QuotationCreate, Quotation, QuotationLine, FieldExtraction and Money with decimal strings and explicit currency
- [x] T027 [US1] Implement quotation creation in `apps/api/src/procurepilot_api/modules/quotations/service.py`, linking to an uploaded `document` and starting `quotation.status = pending`
- [x] T028 [US1] Implement `POST /quotations` in `apps/api/src/procurepilot_api/modules/quotations/router.py`, guarded to owner and buyer for mutation and returning not found for cross-tenant documents
- [x] T029 [P] [US1] Implement deterministic CSV/Excel structured-format parsing in `services/extraction-worker/src/procurepilot_extraction_worker/structured_parse.py`, recording `extraction_method = structured_parse` and parser/rule `model_version`
- [x] T030 [P] [US1] Implement the Bedrock Claude 3 Haiku primary extraction path with strict JSON schema handling in `services/extraction-worker/src/procurepilot_extraction_worker/bedrock.py`
- [x] T031 [P] [US1] Implement the Azure Document Intelligence fallback path in `services/extraction-worker/src/procurepilot_extraction_worker/azure_di.py`, used only on operational or contract failure per research R2
- [x] T032 [US1] Implement Redis/RQ enqueue and consume wiring in `apps/api/src/procurepilot_api/modules/extraction/service.py` and `services/extraction-worker/src/procurepilot_extraction_worker/worker.py`, persisting status changes to `extraction_job`
- [x] T033 [US1] Implement exact-Decimal arithmetic validation and locale-sensitive decimal parsing in `services/extraction-worker/src/procurepilot_extraction_worker/validation.py`, reusing `apps/api/src/procurepilot_api/modules/catalogue/csv_import.py` `parse_decimal` rather than inventing a second parser
- [x] T034 [US1] Implement per-field provenance persistence in `apps/api/src/procurepilot_api/modules/extraction/provenance.py`, writing one `field_extraction` row per header or line field with source page/region, method and model version
- [x] T035 [US1] Implement `POST /quotations/{quotation_id}/extract` in `apps/api/src/procurepilot_api/modules/extraction/router.py`, returning a pollable Job and preventing duplicate active extraction jobs
- [x] T036 [P] [US1] Build the upload screen in `apps/web/src/app/features/quotations/upload/`, including accepted-format validation, direct Storage upload progress and job polling copy from `packages/i18n`
- [x] T037 [P] [US1] Write upload and extraction E2E coverage in `apps/web/tests/e2e/quotation-upload.spec.ts`, proving the browser flow creates a quotation and shows processing/extracted states
- [x] T037a [US1] Add sample quotation files to `apps/web/public/samples/` and a "Try with a sample quotation" section on the upload screen (FR-004a) — two CSV samples (Acme Foods 5-line, Fresh Direct 6-line) plus one PDF sample (Al-Faisal Trading 6-line), download links, i18n keys (en + ar)
- [x] T037b [US2] Add document download endpoint `GET /documents/{id}/download` returning a 5-minute signed Supabase Storage URL (FR-004b) — backend service + router + schema, Angular API method + review page download button, i18n keys (en + ar), OpenAPI contract updated

**Checkpoint**: a buyer can upload a quotation, trigger extraction, poll the job, and inspect extracted fields with confidence and provenance.

**Parallel execution note**: T017-T022 can run together after Phase 2; T029-T031 can run in parallel because provider/parser files are separate; T036-T037 can proceed once the upload API shape is stable.

---

## Phase 4: User Story 2 - Review, correct, and confirm a quotation (P1)

**Goal**: a reviewer opens extracted quotation evidence, corrects fields without losing originals, confirms the supplier, and authorizes the quotation as trusted only through the confirm action.

**Independent Test**: take a US1 extracted quotation, correct one field, confirm the supplier, confirm the quotation, and verify the original extracted value remains while the human correction and reviewer attribution are recorded.

### Tests for User Story 2

- [x] T038 [P] [US2] Write contract tests for `GET /quotations/{quotation_id}`, `PATCH /quotations/{quotation_id}`, `POST /quotations/{quotation_id}/confirm` and `GET /review-tasks` in `apps/api/tests/contract/test_quotation_review_contract.py`
- [x] T039 [P] [US2] Write review workflow integration tests in `apps/api/tests/integration/test_quotation_review.py` proving a quotation cannot reach `reviewed` without required corrections and supplier confirmation, and `POST /confirm` returns 409 while unresolved work remains
- [x] T040 [P] [US2] Write correction provenance tests in `apps/api/tests/integration/test_field_corrections.py` proving a correction is a distinct fact on `field_extraction` and the original `extracted_value` is untouched
- [x] T041 [P] [US2] Write trusted-data gating tests in `apps/api/tests/integration/test_quotation_trusted_data.py` proving unreviewed quotations are not exposed as trusted commercial data anywhere per FR-016
- [x] T042 [P] [US2] Write quotation RBAC tests in `apps/api/tests/integration/test_quotation_rbac.py`, following `apps/api/tests/integration/test_catalogue_rbac.py` so owner/buyer mutate and branch_manager/approver/viewer are read-only

### Implementation for User Story 2

- [x] T043 [US2] Implement quotation detail loading in `apps/api/src/procurepilot_api/modules/quotations/service.py`, returning header, lines, document metadata, field_extractions and review_task in one tenant-scoped read
- [x] T044 [US2] Implement `GET /quotations/{quotation_id}` in `apps/api/src/procurepilot_api/modules/quotations/router.py`, preserving cross-tenant not-found semantics
- [x] T045 [US2] Implement correction and supplier-confirmation handling in `apps/api/src/procurepilot_api/modules/quotations/review_service.py`, recording `corrected_value`, `corrected_by` and `corrected_at` without overwriting extraction evidence
- [x] T046 [US2] Implement `PATCH /quotations/{quotation_id}` in `apps/api/src/procurepilot_api/modules/quotations/router.py`, guarded to owner and buyer for mutation with idempotency support
- [x] T047 [US2] Implement human confirmation in `apps/api/src/procurepilot_api/modules/quotations/confirmation_service.py`, refusing 409 while low-confidence fields, arithmetic mismatch or missing supplier confirmation remain unresolved
- [x] T048 [US2] Implement `POST /quotations/{quotation_id}/confirm` in `apps/api/src/procurepilot_api/modules/quotations/router.py`, recording `reviewed_by` and `reviewed_at` as the only path to trusted `reviewed` status
- [x] T049 [US2] Implement review-task listing in `apps/api/src/procurepilot_api/modules/quotations/review_tasks.py`, supporting status and priority filters for the standalone `review_task` resource
- [x] T050 [US2] Implement `GET /review-tasks` in `apps/api/src/procurepilot_api/modules/quotations/router.py`, keeping the queue independent of a single quotation detail page per FR-019
- [x] T051 [P] [US2] Build the side-by-side review screen in `apps/web/src/app/features/quotations/quotation-review/`, including source-region highlighting, low-confidence flags, correction controls and keyboard navigation per FR-014
- [x] T052 [P] [US2] Build the review queue list in `apps/web/src/app/features/quotations/review-queue/`, including status/priority filters and read-only presentation for non-writing roles
- [x] T053 [P] [US2] Write review and queue E2E coverage in `apps/web/tests/e2e/quotation-review.spec.ts`, proving source highlighting, keyboard movement through flagged fields, correction, supplier confirmation and final confirm

**Checkpoint**: upload/extraction and human review/confirmation form the P1 MVP loop, with no trusted commercial data before human confirmation.

**Parallel execution note**: T038-T042 can run together; T051 and T052 can run in parallel once the response schemas in T043 and T049 are stable.

---

## Phase 5: User Story 3 - Arithmetic mismatches always force review (P1)

**Goal**: mismatched totals are mandatory review work regardless of individual field confidence, and the mismatch itself is visible to the reviewer.

**Independent Test**: extract a quotation whose line totals differ from its stated total and verify it opens a mandatory review task with `reason = arithmetic_mismatch`, cannot be confirmed until resolved, and displays the mismatch evidence.

**Dependency note**: this story depends on US1's validation layer in T033. It may overlap with US1 implementation, but the dedicated mismatch tests below must remain separate because all three P1 stories together form the MVP.

### Tests for User Story 3

- [x] T054 [P] [US3] Write dedicated mismatch integration tests in `apps/api/tests/integration/test_arithmetic_mismatch_review.py` proving 100% of mismatched-total quotations land in mandatory review regardless of field confidence
- [x] T055 [P] [US3] Write reviewer visibility E2E coverage in `apps/web/tests/e2e/quotation-arithmetic-mismatch.spec.ts` proving the mismatch itself, not just individual fields, is surfaced on the review screen

### Implementation for User Story 3

- [x] T056 [US3] Extend review-task creation in `apps/api/src/procurepilot_api/modules/extraction/service.py` so arithmetic mismatch creates or keeps an open high-priority `review_task` with `reason = arithmetic_mismatch`
- [x] T057 [US3] Add arithmetic-mismatch presentation state in `apps/web/src/app/features/quotations/quotation-review/`, showing stated total, computed line total and unresolved status from the API

**Checkpoint**: SC-003 is directly testable and no high-confidence arithmetic mismatch can skip human review.

**Parallel execution note**: T054 and T055 can be written in parallel after US1's validation contract is known; T056 depends on T033, while T057 depends on the review screen from US2.

---

## Phase 6: User Story 4 - See when a supplier re-quotes (P2)

**Goal**: a reviewer can link a confirmed quotation to a prior supplier quotation without replacing either version.

**Independent Test**: confirm a new quotation with `previous_quotation_id`, then verify both versions remain visible and distinguishable through API and UI.

### Tests for User Story 4

- [x] T058 [P] [US4] Write versioning integration tests in `apps/api/tests/integration/test_quotation_versioning.py` proving `previous_quotation_id` is set at confirm time, is same-tenant, is not self-referential, and does not hide either quotation
- [x] T059 [P] [US4] Write re-quote E2E coverage in `apps/web/tests/e2e/quotation-versioning.spec.ts` proving both current and prior versions are visible and openable

### Implementation for User Story 4

- [x] T060 [US4] Extend confirmation logic in `apps/api/src/procurepilot_api/modules/quotations/confirmation_service.py` to validate and persist `previous_quotation_id` only during human confirm
- [x] T061 [US4] Extend quotation detail responses in `apps/api/src/procurepilot_api/modules/quotations/service.py` to include prior/current version references while preserving tenant isolation
- [x] T062 [US4] Add re-quote version controls and prior-version links in `apps/web/src/app/features/quotations/quotation-review/`, keeping both versions visible rather than replacing history

**Checkpoint**: a P2 re-quote can be linked and audited without changing the P1 upload/extract/review loop.

**Parallel execution note**: T058 and T059 can start from the contract shape; T060 must land before T061 and T062 can demonstrate the end-to-end link.

---

## Phase 7: Cross-cutting

**Purpose**: feature-wide isolation, RBAC, accessibility, AI quality gates, documentation and constitutional verification.

- [x] T063 Extend `apps/api/tests/integration/test_tenant_isolation.py` to cover all six new tenant-scoped tables - `document`, `quotation`, `quotation_line`, `field_extraction`, `extraction_job` and `review_task` - following the chunk 4.2 precedent T038 in `specs/002-catalogue-suppliers/tasks.md`
- [x] T064 Extend role coverage in `apps/api/tests/integration/test_quotation_rbac.py` for all quotation/document/extraction/review mutations, following the same owner/buyer versus branch_manager/approver/viewer split as `apps/api/tests/integration/test_catalogue_rbac.py`
- [x] T065 [P] Add `@a11y` specs for upload, review queue and quotation review screens in both English and Arabic in `apps/web/tests/e2e/quotation-a11y.spec.ts`, with RTL checks and zero axe violations
- [x] T066 [P] Implement the AI evaluation harness in `ml/evals/quotation_extraction/run_eval.py`, reporting field-level accuracy >= 90%, document exact match, arithmetic-validation pass rate, cost per document and ECE calibration within 5% per bucket against the versioned held-out benchmark in `ml/benchmarks/quotation_extraction/` per docs/quality/test-strategy.md section 4 and research R7
- [x] T067 [P] Fold this chunk's `[new]` data-model.md fields into `docs/architecture/data-dictionary.md`, including per-field provenance, review_task, extraction_job and quotation versioning
- [x] T068 [P] Add the quotation inbox API surface to `docs/architecture/api-specification.md`, covering the eight endpoints in `specs/003-quotation-inbox-extraction/contracts/quotation-inbox.openapi.yaml`
- [x] T069 Re-run the Constitution Check from `specs/003-quotation-inbox-extraction/plan.md` against delivered code and record the result, following the chunk 4.2 precedent T043 in `specs/002-catalogue-suppliers/tasks.md`

---

## Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational  ← BLOCKS ALL USER STORIES
    ↓
    ├── Phase 3 US1 (P1) Upload + extraction  ← MVP pipeline base
    │       ↓
    │   Phase 5 US3 (P1) Arithmetic mismatch  ← depends on US1 validation; part of MVP
    ├── Phase 4 US2 (P1) Review + confirm     ← combines with US1 and US3 for MVP
    │       ↓
    │   Phase 6 US4 (P2) Re-quote versioning  ← confirm-time refinement
    └── Phase 7 Cross-cutting                 ← final verification across delivered scope
```

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies - can start immediately.
- **Foundational (Phase 2)**: depends on Setup completion and blocks all user-story work.
- **US1, US2 and US3 (P1)**: all depend on Foundational. US3 explicitly depends on US1's arithmetic/locale validation layer, but it remains its own P1 story because mismatches are a separate constitutional guardrail.
- **US4 (P2)**: depends on US2 confirmation semantics because version linking happens at confirm time.
- **Cross-cutting (Phase 7)**: depends on the implemented scope it verifies; docs tasks may start once APIs/data shapes are stable.

### Parallel Opportunities

- Setup tasks T002-T004 and T006 can run in parallel with no shared file writes.
- Foundational skeleton tasks T012-T015 can run in parallel after migration filenames are settled; T007-T011 should stay ordered because migration numbers are sequential.
- US1 tests T017-T022 can run in parallel; provider/parser work T029-T031 can run in parallel; UI T036 can proceed while backend T032-T035 finishes behind contract stubs.
- US2 tests T038-T042 can run in parallel; review UI T051 and queue UI T052 can run in parallel once schemas stabilize.
- US3 tests T054-T055 are parallelizable, but implementation T056 depends on US1 T033 and T057 depends on US2 T051.
- US4 tests T058-T059 can run in parallel, while implementation flows T060 -> T061 -> T062.

---

## Delegation lanes

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **A — Backend** | apps/api modules, services/extraction-worker, ml/evals harness, backend tests | lane `backend` → **codex** | T001-T005, T012-T016, T017-T035, T038-T050, T054, T056, T058, T060-T061, T064, T066 |
| **B — Frontend** | upload, review queue, review/versioning screens and web tests | lane `frontend` → agy | T006, T036-T037, T051-T053, T055, T057, T059, T062, T065 |
| **C — Docs** | data dictionary, API spec | lane `backend` → **codex** | T067-T068 |
| **D — Tenancy** | migrations, RLS, Storage bucket policy, tenant-isolation test extension, constitution re-check | **not delegated** — orchestrator | T007-T011, T063, T069 |

Lane D stays in house: Principle V's failure mode is silent, and this chunk adds six tenant-scoped
tables plus Supabase Storage object access. Migrations, RLS, Storage policies and the tenant
isolation test extension are therefore not delegated.

`services/extraction-worker` and `ml/evals/` are new for this chunk, not previously delegated to
codex in chunk 4.2, but they are bounded engineering work rather than tenancy/RLS work, so they
belong in Lane A.

**Task count**: 69 - Setup 6 · Foundational 10 · US1 21 · US2 16 · US3 4 · US4 5 · Cross-cutting 7.

---
description: "Task list for Catalogue and Suppliers implementation"
---

# Tasks: Catalogue and Suppliers

**Input**: Design documents from `/specs/002-catalogue-suppliers/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/catalogue.openapi.yaml

**Tests**: Included. The spec requires them explicitly — SC-003 through SC-009 — and the
constitution makes them release conditions.

**Organization**: grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1–US4 from spec.md
- Every task names its exact file path

---

## Phase 1: Foundational (Blocking Prerequisites)

⚠️ **Everything else depends on this phase.** Migrations first, RLS in one place, then the module skeleton.

- [x] T001 Write migration `supabase/migrations/20260819000011_catalogue_units.sql` creating `supported_base_unit` (code, label_en, label_ar, dimension, is_enabled) and seeding litre, millilitre, kilogram, gram, each
- [x] T002 Write migration `supabase/migrations/20260819000012_catalogue_products.sql` creating `canonical_product` (NO tenant_id — see research R5), `workspace_product`, `pack_definition` with `base_quantity` as a GENERATED column, and `product_substitute`
- [x] T003 Write migration `supabase/migrations/20260819000013_suppliers.sql` creating `supplier` with monetary values as amount+currency pairs and a check constraint per pair requiring both or neither
- [x] T004 Write migration `supabase/migrations/20260819000014_product_alias.sql` creating `product_alias` with a unique index on `(tenant_id, lower(alias_text))`
- [x] T005 Write migration `supabase/migrations/20260819000015_import_job.sql` creating `import_job` with a jsonb error report
- [x] T006 Write migration `supabase/migrations/20260819000016_catalogue_rls.sql` applying ENABLE + FORCE row level security and USING + WITH CHECK policies to every tenant-scoped table above, plus read-only policies for `canonical_product` and `supported_base_unit`
- [x] T007 [P] Create the module skeleton `apps/api/src/procurepilot_api/modules/catalogue/__init__.py` and register its router in `apps/api/src/procurepilot_api/main.py`
- [x] T008 [P] Add the catalogue key namespace to `packages/i18n/en.json` and `packages/i18n/ar.json`, keeping them at parity

**Checkpoint**: migrations apply from scratch; the isolation test still passes.

---

## Phase 2: User Story 1 — Product master (P1) 🎯 MVP

- [x] T009 [P] [US1] Write `apps/api/src/procurepilot_api/modules/catalogue/normalisation.py` — pure pack arithmetic, no I/O, Decimal only
- [x] T010 [P] [US1] Write `apps/api/tests/unit/test_normalisation.py` covering 6×5L=30L, fractional packs (3×0.33=0.99 exactly), zero and negative rejection, and that no float ever appears in the path
- [x] T011 [US1] Write Pydantic models in `apps/api/src/procurepilot_api/modules/catalogue/models.py` for Product, ProductCreate, ProductUpdate, PackDefinition, matching the contract exactly
- [x] T012 [US1] Implement product CRUD in `apps/api/src/procurepilot_api/modules/catalogue/service.py` — create resolves-or-creates the canonical product and the workspace product in one transaction
- [x] T013 [US1] Implement `GET/POST /products`, `GET/PATCH/DELETE /products/{id}` and `POST /products/{id}/substitutes` in `apps/api/src/procurepilot_api/modules/catalogue/router.py`, guarded to owner and buyer for mutations
- [x] T014 [P] [US1] Implement `GET /reference/base-units` in the same router
- [x] T015 [P] [US1] Write `apps/api/tests/integration/test_products.py` covering create, edit, archive-not-delete, GTIN shape validation, and substitute self-reference rejection
- [x] T016 [P] [US1] Build the product list at `apps/web/src/app/features/catalogue/product-list/`, with a read-only presentation for non-writing roles
- [x] T017 [P] [US1] Build the product form at `apps/web/src/app/features/catalogue/product-form/`, showing the normalised quantity live as the pack is entered
- [x] T018 [P] [US1] Write `apps/web/tests/e2e/catalogue-product.spec.ts` — create a product, assert the normalised quantity, assert the SC-001 90-second budget

**Checkpoint**: a buyer can build a catalogue. Demonstrable with no suppliers and no import.

---

## Phase 3: User Story 2 — Suppliers (P1)

- [x] T019 [P] [US2] Add Supplier models to `apps/api/src/procurepilot_api/modules/catalogue/models.py`, with Money as amount+currency and no bare numbers
- [x] T020 [US2] Implement supplier CRUD in `apps/api/src/procurepilot_api/modules/catalogue/service.py`, refusing deletion of a referenced supplier with a 409 and offering archive
- [x] T021 [US2] Implement `GET/POST /suppliers` and `GET/PATCH/DELETE /suppliers/{id}` in the catalogue router, guarded to owner and buyer for mutations
- [x] T022 [P] [US2] Write `apps/api/tests/integration/test_suppliers.py` covering status transitions, referenced-delete refusal, and that an amount without a currency is rejected
- [x] T023 [P] [US2] Write `apps/api/tests/integration/test_money_constraints.py` asserting at the DATABASE level that an amount without a currency cannot be inserted (SC-006)
- [x] T024 [P] [US2] Build the supplier list at `apps/web/src/app/features/catalogue/supplier-list/`
- [x] T025 [P] [US2] Build the supplier form at `apps/web/src/app/features/catalogue/supplier-form/`, with currency required alongside every amount

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 4: User Story 3 — CSV import (P2)

- [x] T026 [P] [US3] Write `apps/api/src/procurepilot_api/modules/catalogue/csv_import.py` — parse with the stdlib csv module, validate every row, return a report; NO writes in this module
- [x] T027 [P] [US3] Write `apps/api/tests/unit/test_csv_import.py` covering the happy path, malformed rows, missing and unrecognised columns, an empty file, a header-only file, and a non-CSV binary
- [x] T028 [P] [US3] Write `apps/api/tests/unit/test_decimal_parsing.py` asserting that `1.234,56` and `1,234.56` both parse correctly and that a bare `1,234` is REFUSED rather than guessed (FR-022)
- [x] T029 [US3] Implement `POST /imports` (validate and preview, writing nothing) and `POST /imports/{id}/commit` (one transaction, all or nothing) in the catalogue router
- [x] T030 [US3] Implement duplicate detection with skip-or-update at commit time (FR-021)
- [x] T031 [P] [US3] Write `apps/api/tests/integration/test_import_atomicity.py` proving that a commit failing partway leaves the catalogue exactly as it was (SC-004)
- [x] T032 [P] [US3] Add fixtures `apps/api/tests/fixtures/products_valid.csv` and `products_invalid.csv`, the second with a known bad row at a known line number
- [x] T033 [P] [US3] Build the import wizard at `apps/web/src/app/features/catalogue/import-wizard/` — upload, preview, error report with line numbers, confirm
- [x] T034 [P] [US3] Write `apps/web/tests/e2e/catalogue-import.spec.ts` — upload an invalid file, assert nothing saved and line numbers shown; upload a valid file, assert all rows saved

**Checkpoint**: a business can adopt the product in an afternoon rather than a week.

---

## Phase 5: User Story 4 — Aliases (P3)

- [x] T035 [P] [US4] Add Alias models to `apps/api/src/procurepilot_api/modules/catalogue/models.py`
- [x] T036 [US4] Implement `GET/POST /aliases` and `DELETE /aliases/{id}` in the catalogue router
- [x] T037 [P] [US4] Write `apps/api/tests/integration/test_aliases.py` proving an alias resolves for the workspace that recorded it and NOT for any other (FR-027)

---

## Phase 6: Cross-cutting

- [x] T038 Extend `apps/api/tests/integration/test_tenant_isolation.py` to cover `workspace_product`, `pack_definition`, `supplier`, `product_alias` and `import_job` (SC-005)
- [x] T039 Write `apps/api/tests/integration/test_catalogue_rbac.py` asserting, for all five roles, that owner and buyer may mutate and branch_manager, approver and viewer may not (SC-009)
- [x] T040 [P] Add `@a11y` specs for the catalogue and supplier screens in `apps/web/tests/e2e/a11y.spec.ts`, in both languages (SC-008)
- [x] T041 [P] Fold the `[new]` fields from data-model.md into `docs/architecture/data-dictionary.md`
- [x] T042 [P] Add the catalogue surface to `docs/architecture/api-specification.md`
- [x] T043 Re-run the Constitution Check from plan.md against delivered code and record the result

---

## Dependencies

```text
Phase 1 Foundational  ← BLOCKS EVERYTHING
    ↓
    ├── Phase 2 US1 (P1) ← MVP
    ├── Phase 3 US2 (P1) ← independent of US1
    ├── Phase 4 US3 (P2) ← needs US1 and US2 models to import into
    └── Phase 5 US4 (P3) ← needs US1
            ↓
        Phase 6 Cross-cutting
```

---

## Delegation lanes

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **A — Backend** | models, services, routers, CSV, tests | lane `backend` → **codex** | T009–T015, T019–T023, T026–T032, T035–T037, T039 |
| **B — Frontend** | catalogue and supplier screens, import wizard | lane `frontend` → agy | T016–T018, T024–T025, T033–T034, T040 |
| **C — Docs** | data dictionary, API spec | lane `backend` → **codex** | T041–T042 |
| **D — Tenancy** | migrations, RLS, isolation tests | **not delegated** — orchestrator | T001–T008, T038, T043 |

Lane D stays in house: Principle V's failure mode is silent, and this chunk adds five tenant-scoped
tables plus the one deliberate exception (`canonical_product`), which is exactly where a mistake
would hide.

**Task count**: 43 — Foundational 8 · US1 10 · US2 7 · US3 9 · US4 3 · Cross-cutting 6.

# Implementation Plan: Catalogue and Suppliers

**Branch**: `002-catalogue-suppliers` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-catalogue-suppliers/spec.md`

## Summary

Give a workspace the vocabulary it will later compare prices in: products, the packs they arrive in,
suppliers and their commercial terms, bulk import, and a per-workspace memory of what suppliers call
things.

The technical approach adds to chunk 4.1 rather than alongside it. Same modular monolith, same RLS
pattern, same audit trail, same i18n catalogue. Three things are genuinely new and carry the design
risk: **normalisation arithmetic that must be exactly reproducible**, **the first monetary columns**,
and **an all-or-nothing bulk import**. Everything else is CRUD in an established shape.

## Technical Context

**Language/Version**: unchanged — Python 3.12 (backend), TypeScript 5.6 / Angular 19 (web), SQL

**Primary Dependencies**: unchanged from chunk 4.1. One addition under consideration for CSV
parsing — see research R3. No new frontend dependency.

**Storage**: Supabase Postgres 17 via the Supabase CLI local stack. Migrations continue in
`supabase/migrations/`, numbered from `20260819000011`.

**Testing**: pytest + pytest-asyncio, Karma/Jasmine, Playwright with axe-core. Database-backed tests
require `TEST_DATABASE_URL`; without it they skip, which is why CI sets it explicitly.

**Target Platform**: unchanged — Linux containers, evergreen browsers.

**Project Type**: unchanged — Angular SPA plus FastAPI modular monolith.

**Performance Goals**: product creation under 90s unaided (SC-001); a 200-row import validated and
committed, or fully reported, within 60s (SC-002).

**Constraints**: exact-reproducible normalisation (SC-007); every monetary value carries a currency
(SC-006); all-or-nothing import (SC-004); WCAG 2.1 AA in both languages (SC-008); owner/buyer write,
others read (SC-009).

**Scale/Scope**: pilot-sized — hundreds of products and tens of suppliers per workspace; import
files in the low thousands of rows. Roughly 6 new screens and 5 new tables.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | Partially | No extraction or inference yet, so no confidence scores. The applicable part is provenance: every catalogue mutation and every import writes an audit event, and an import retains its file and outcome so it can be explained afterwards. | ✅ PASS |
| **II. Deterministic, Replayable Normalisation** | **Yes — first real test** | Pack normalisation is the first instance of the principle's subject matter. `base_quantity` must be derivable from `pack_count × unit_size` and recomputing must give an identical value — which means exact decimal arithmetic in the database, not floating point. Rounding here compounds into a wrong saving later. | ✅ PASS — `numeric`, never `float` |
| **III. Human Authority** | No | Nothing automated. Aliases are recorded by a human confirming a match, which is the principle rather than an exception to it. | ✅ N/A |
| **IV. Every Insight Ends in an Action** | Partially | The catalogue is reference data, not an insight surface, so the no-dashboards rule does not bite. The import error report is the one screen that must lead somewhere: it names the failing rows so the user can fix the file, rather than reporting failure and stopping. | ✅ PASS |
| **V. Tenant Isolation by Construction** | **Yes** | Every new workspace-scoped table gets `tenant_id`, RLS `ENABLED` **and** `FORCED`, and policies with both `USING` and `WITH CHECK`. `canonical_product` is deliberately shared and therefore carries no tenant column — its access rule is different and must be stated explicitly, not inherited by habit. | ✅ PASS |
| **VI. Modular Monolith** | Yes | One new module, `catalogue`. No new service, no queue. The import runs inside the request for pilot-sized files; see research R4 for when that stops being true. | ✅ PASS |
| **VII. Money, Tax, Language from the Schema Up** | **Yes — first monetary columns** | `minimum_order_value` and `delivery_fee` are the first money in the product. Each is stored as an amount plus an explicit currency column, never a bare number, and never converted. The `Money` type already exists in `packages/domain-types`. | ✅ PASS |

**Workflow gates**: specification precedes code ✅ (spec approved, 16/16 checklist, clarification
resolved); stage gates ✅ (this is Phase 1 chunk 4.2, G1 is the gate ahead, not behind); delegated
work reviewed ✅ (planned — every delegated diff reviewed against this plan before landing).

## Project Structure

### Documentation (this feature)

```text
specs/002-catalogue-suppliers/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── catalogue.openapi.yaml
├── checklists/
│   └── requirements.md  # passing
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
supabase/migrations/
├── 20260819000011_catalogue_units.sql        # supported base units, reference data
├── 20260819000012_catalogue_products.sql     # canonical_product, workspace_product, pack_definition
├── 20260819000013_suppliers.sql              # supplier, with money as amount + currency
├── 20260819000014_product_alias.sql          # per-workspace supplier wording
├── 20260819000015_import_job.sql             # import provenance
└── 20260819000016_catalogue_rls.sql          # RLS for every table above, in one place

apps/api/src/procurepilot_api/modules/catalogue/
├── router.py            # /products, /suppliers, /aliases, /imports
├── service.py           # orchestration, transactions
├── models.py            # Pydantic boundary models
├── normalisation.py     # pack arithmetic — pure, no I/O, exhaustively tested
└── csv_import.py        # parse, validate, report; no writes until the whole file passes

apps/web/src/app/features/catalogue/
├── product-list/        # with read-only presentation for non-writing roles
├── product-form/        # create and edit, pack normalisation shown live
├── supplier-list/
├── supplier-form/
└── import-wizard/       # upload → preview → error report → confirm

packages/i18n/{en,ar}.json   # extended, kept at parity
```

**Structure Decision**: one new backend module and one new frontend feature area, following the
layout established in chunk 4.1. Migrations are split by concern but RLS for all of them lands in a
single migration, so the isolation rules for this chunk can be read in one place rather than
reconstructed from five files.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `canonical_product` is shared across workspaces and carries no `tenant_id`, so it sits outside the Principle V pattern every other table follows | Roadmap §10.1 requires a shared canonical spine so cross-tenant benchmarking remains possible in year 3. Workspace-specific naming, preferences and substitutes live in `workspace_product`, which IS tenant-scoped. | Giving every workspace its own private product rows would satisfy the pattern uniformly and make the benchmarking asset unreachable without a later migration over the customer's whole catalogue. The risk is real and is mitigated by the table holding no workspace-identifying data — brand, name, variant, GTIN, base unit only. |
| An import writes many rows in one transaction, which is heavier than any request in chunk 4.1 | FR-017 requires all-or-nothing. Partial imports leave a catalogue nobody can trust, and the fix is worse than the failure. | Row-by-row commits would be simpler and would violate the requirement outright. Background processing would avoid the long request but adds a queue and a job model this chunk does not otherwise need — see research R4 for the threshold at which that changes. |

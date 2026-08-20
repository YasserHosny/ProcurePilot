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

## Constitution Check — re-run against delivered code (T043)

Run at the close of chunk 4.2, against what was built, verified directly against a real local
Supabase Postgres (all migrations 0001-0016 applied) rather than accepted from a delegated report.

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Evidence Over Assertion** | ✅ PASS | Every catalogue/supplier mutation writes an `audit_event`. `import_job` retains its filename, status, row count and error report after the fact, so a bulk change can be explained — including which lines were refused. No confidence scores exist yet; none are claimed. |
| **II. Deterministic, Replayable Normalisation** | ✅ PASS | `pack_definition.base_quantity` is a Postgres `GENERATED ALWAYS AS (pack_count * unit_size) STORED` column — it cannot drift from its inputs because nothing can write it directly. `numeric(18,6)` throughout, never `float`. Verified: `test_normalisation.py` — 6×5L=30L exactly, 3×0.33=0.99 exactly (Decimal), zero/negative pack counts and unit sizes rejected — 10/10 passed. |
| **III. Human Authority** | ✅ N/A | No automation. Aliases are recorded only when a human confirms a mapping (`created_by` references the membership that did so); nothing infers or proposes one. |
| **IV. Every Insight Ends in an Action** | ✅ PASS | The import error report is the one screen with a duty here: it names the failing line, column and reason so the user can fix the source file, rather than reporting failure and stopping. |
| **V. Tenant Isolation by Construction** | ✅ PASS | Queried directly against the real database: all 6 tenant-scoped tables added this chunk (`workspace_product`, `pack_definition`, `product_substitute`, `supplier`, `product_alias`, `import_job`) have RLS both `ENABLED` and `FORCED` — confirmed `True/True` on every row via `pg_class`. `test_tenant_isolation.py` was extended (T038) with real cross-workspace reads/writes on every one of these tables under a real JWT claim as the `authenticated` role — another workspace's products, packs, suppliers, aliases and import jobs are invisible and unwritable. The one deliberate exception, `canonical_product` (no `tenant_id` — shared spine), is also RLS `ENABLED`/`FORCED`, with its own explicit read-all/write-service-role-only policy; a dedicated test proves the sharing is the intended design, not a leak. |
| **VI. Modular Monolith** | ✅ PASS | One new module, `catalogue`, under the same FastAPI app. No new service, no queue. CSV import validates and commits inside the request. |
| **VII. Money, Tax, Language from the Schema Up** | ✅ PASS | `supplier.minimum_order_value_(amount,currency)` and `delivery_fee_(amount,currency)` are the first monetary columns in the product. Each pair is `numeric(18,4)` + an FK to `supported_currency`, never a bare number, and a check constraint requires both or neither. Verified at the database level, not just the API: `test_money_constraints.py` — inserting an amount with no currency is rejected by Postgres itself — 2/2 passed. i18n parity re-verified directly: `en.json` and `ar.json` both hold exactly 423 keys, zero keys present in only one file. |

**Workflow gates**: delegated work reviewed ✅ — three lanes (backend → Codex, frontend →
Antigravity, docs → Codex) were dispatched, and every diff was re-verified against a live local
Postgres and a live Karma/ruff/lint run rather than accepted from the self-reports. Two real bugs
surfaced only by running against a live database (not caught by either delegate, since neither had
`TEST_DATABASE_URL` in its sandbox): a test-helper role-privilege bug affecting `canonical_product`
writes, and a cross-connection visibility gap in the import atomicity test. Both are fixed; see
below.

### Judgment calls recorded rather than buried

**`import_job.error_report`'s stored shape changed from a plain error array to
`{errors, duplicates, file_error, validated_report}`.** The original design implicitly assumed an
in-process cache would hold the validated report between preview and commit; that cache cannot
survive a second worker process or a restart between the two calls, which would silently strand a
`previewed` import that can never be committed — a durability gap Principle I exists to catch. Since
adding a column would require a migration outside this chunk's delegated backend lane, the fix
reuses the existing `jsonb` column instead of adding one. Documented in
`docs/architecture/data-dictionary.md`.

**`workspace_product.preferred_supplier_id` is `ON DELETE SET NULL`, not `RESTRICT`.** A raw-SQL
test (`test_suppliers.py`) originally asserted the opposite and never actually ran, hidden by an
unrelated privilege bug earlier in the same test's setup. Once that was fixed, the test failed for
real. Investigating confirmed the migration's choice is deliberate: `preferred_supplier_id` is a
soft, advisory pointer, and the hard business rule the spec actually asks for ("refuse to delete a
referenced supplier, offer archive instead" — T020) is already enforced one layer up, in
`CatalogueService.archive_supplier` (409 `supplier_referenced`). The test was corrected to assert
the real database guarantee (`SET NULL`) instead of a `RESTRICT` that was never built. **Gap
surfaced, not closed**: no router/service-level test exercises the 409 archive-refusal path itself —
flagged here rather than silently left uncovered.

**The pre-existing owner-guard trigger (chunk 4.1, migration `20260819000005`) blocks deleting the
last owner's membership row even via cascade from a tenant delete.** This only matters for test
cleanup (production has no tenant-deletion path yet), but it means any future test that commits a
real tenant for cross-connection visibility needs `session_replication_role = replica` around its
teardown delete, not a plain `DELETE FROM tenant`. Recorded here so the next person hitting the same
`RestrictViolation` finds the reason instead of re-deriving it.

### Quality gates

| Gate | Threshold | Status |
|---|---|---|
| Cross-tenant isolation | Proven on every change | ✅ Extended (T038) to every table this chunk adds; run against a real database, real JWT claim |
| Money without currency | Rejected at the DB level (SC-006) | ✅ `test_money_constraints.py`, 2/2, against a real database |
| Deterministic normalisation (SC-007) | Exact, no drift | ✅ `test_normalisation.py`, 10/10; `base_quantity` is a generated column |
| All-or-nothing import (SC-004) | Partial commit impossible | ✅ `test_import_atomicity.py` exercises the real `commit_import` + `PostgresImportRepository` path (not a bare-transaction stand-in) against a real database — a mid-commit FK violation rolls back the entire batch, including an otherwise-valid row |
| i18n completeness | No key in one catalogue only | ✅ 423/423, exact parity, re-verified directly |
| RBAC (SC-009) | Owner/buyer mutate, others read-only | ✅ `test_catalogue_rbac.py`, all 5 roles, against a real database |
| Accessibility (SC-008) | WCAG 2.1 AA, zero violations, both languages | ✅ `@a11y` specs cover product/supplier/import screens in en and ar; Karma unit suite 49/49, `ng lint` clean |
| Backend test suite | All passing | ✅ 197 passed, 1 skipped (unrelated, pre-existing), against a real local Postgres — confirmed idempotent on repeat runs |
| Live end-to-end walkthrough | Human-eye pass through the running app | ✅ Real signup, real product creation (6×5 litre → 30 litre live), real supplier with currency-qualified amount (client refused amount-without-currency, then accepted £250.00), real CSV import commit (3 rows created, exact Decimal math: 12×1234.56=14814.72), real invalid-CSV rejection (line-numbered errors, nothing saved) — all against the live API and a live local Postgres, not mocked |

**One real defect found only by this walkthrough, fixed in the same pass**: the import preview
table rendered the `pack` column (and would have rendered `minimum_order_value`/`delivery_fee` for
a suppliers import) as the literal string `[object Object]`, because the generic preview-table
renderer printed every cell with `{{ row[col] }}` regardless of whether the API sent a scalar or a
nested object (`{pack_count, unit_size}` for products, `{amount, currency}` for suppliers). Neither
Karma (which didn't exercise this render path) nor either delegate's sandbox (no live backend to
preview against) could have caught this — it only showed up once real data flowed through a real
browser. Fixed with a `formatPreviewCell()` helper in `import-wizard.component.ts` that formats
known nested shapes and falls back to `JSON.stringify` for anything else; re-verified live (pack
column now reads `24 × 1`, `6 × 1.5`, `12 × 1234.56`) and Karma re-run clean (49/49).

### The honest gaps

- **No router/service-level test for the supplier archive-refusal 409 path** (see judgment call
  above) — application behavior is implemented and matches the spec, but untested at that layer.

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

# Research: Home Currency Readiness

## R1 — Does a home currency already exist?
**Decision**: Yes — reuse `tenant.currency`. **Evidence**: `tenants/models.py` (`TenantRow.currency`, `SignupRequest.currency`), `PATCH /tenant` (owner-only), `session.tenant()?.currency` used in `budget-form-dialog.component.ts:90` and `threshold-rule-list.component.ts:231`.
**Rationale**: a second column would create two sources of truth. **Rejected**: new `home_currency` column (needs migration + RLS review, no benefit).

## R2 — Where do hard-coded defaults live?
Web: `order-create.component.ts:81` ('USD'), `guardrails.component.ts:61,161`, `quotation-review.component.ts:265,1149`. Backend: `landed_cost/service.py:89,99,104` (GBP). Worker: `structured_parse.py:67` (GBP), `azure_di.py:77` (GBP), `:153` (USD), `:290-293` (only £/$/ markers). `providers.py` GBP values are the stub provider's fixture data — leave.

## R3 — Extraction marker detection
**Decision**: a pure, unit-tested `currency.py`: regex with Unicode-aware boundaries; markers adjacent to a numeric token only (so `LE` in "TABLE"/"Le Pain" never matches); mixed markers in one document → unknown (flag). Arabic-Indic digits `٠-٩`, decimal `٫`, thousands `٬` converted via `Decimal` (no float).

## R4 — Worker tenant context
Worker already has `tenant_id` from the job payload (`worker.py:35`). **Decision**: read `tenant.currency` by that id inside the worker's existing connection; the worker attaches it to the result as `suggested_currency` **after** extraction — providers never see it, so it cannot leak into stored values (amended 2026-10-14). No queue-payload change.

## R5 — Fallback flag
**Amended 2026-10-14 (review finding):** no defaulted currency is stored at all. An unresolved currency (none found or mixed markers) stores no currency and routes to review with new reason `currency_unresolved`; the tenant currency is only a stored `suggested_currency` hint. Fixture expectations: `docs/gtm/test-fixtures/egypt-quotes/expected.json` (q4 no marker, q5 mixed → flagged, no currency).

## R6 — Mobile formatting
**Decision**: `intl` `NumberFormat.currency` with per-currency digits (2 default; 3 for KWD/BHD/OMR; 0 for JPY-class), locale from the app's `ar`/`en`. Amounts arrive as decimal strings; format from `Decimal`-safe parsing, rounding display only. **Rejected**: hand-rolled grouping (locale bugs).

## R7 — PP-3 evidence run (2026-10-14, representative — NOT real supplier quotes)
Run through `parse_structured_content(...)` (CSV/XLSX path only; the PDF/image path goes through Azure DI / Bedrock and is not exercised here):

| Case | Currency | Confidence | unit_price |
|---|---|---|---|
| `ج.م` marker | EGP | 1.0 | 1250.00 |
| `١٢٥٠٫٥٠ جنيه` (Arabic-Indic) | EGP | 1.0 | 1250.50 |
| `LE 480.00` | EGP | 1.0 | 480.00 |
| `EGP` code | EGP | 1.0 | 95.5 |
| unmarked | none stored | review reason `currency_unresolved`, suggestion EGP | amount not stored (no currency) |

**Still open for SC-002:** 5 real Egyptian supplier quotes (PDF/photo) through the full pipeline. This table proves the parsing/unresolved-currency logic, not OCR quality.

# Implementation Plan: Home Currency Readiness for the Egypt Pilot

**Branch**: `022-home-currency-readiness` | **Date**: 2026-10-14 | **Spec**: [spec.md](spec.md)
**Tracking**: Jira PP-1 (C1), PP-2 (C3), PP-3 fix part (C2) · `docs/product/gtm-execution-plan.md` P-1..P-3

## Summary

Research changed the shape of this feature: **the home currency already exists.** `tenant.currency`
(NOT NULL, `^[A-Z]{3}$`, chosen at signup, owner-editable via `PATCH /api/v1/tenant`, returned to
the web as `session.tenant().currency`) is the tenant's home currency. Two web forms already use it
(`budget-form-dialog`, `threshold-rule-list`). So US1 is **not** new storage — it is making the
remaining forms read the existing value, plus an owner-facing setting and an audit event. US2 needs
the extraction worker to learn the tenant currency and recognise Egyptian markers. US3 is a
self-contained mobile formatter. **No migration, no RLS change** (so the "tenancy stays in-house"
carve-out is not triggered; the audit write is the only server-side change).

## Technical Context

**Language/Version**: Python 3.12 (`apps/api`, `services/extraction-worker`), TypeScript 5.6 / Angular 19 (`apps/web`), Dart/Flutter (`apps/mobile`)
**Primary Dependencies**: existing only. Mobile: add `intl` to `pubspec.yaml` (the one new dependency; check it is already transitively present via `flutter_localizations` before adding).
**Storage**: Supabase Postgres 17, unchanged. Reuses `tenant.currency`; audit via existing `record_audit_event`.
**Testing**: pytest (api + worker), Karma/Jasmine (web), `flutter test` (mobile), Playwright (EGP default end-to-end)
**Target Platform**: web SPA, Flutter mobile (Android/iOS), worker container
**Project Type**: web + mobile + worker
**Constraints**: stored amounts never change (FR-006, FR-016); display rounding only
**Scale/Scope**: ~5 web forms, 3 extraction files + landed-cost, 2 mobile screens

## Constitution Check

- **I Evidence over assertion** — PASS. A defaulted currency is flagged for review, never presented as confident (FR-011/012).
- **III Human authority** — PASS. Fallback only pre-fills; a reviewer confirms. No autonomous purchasing.
- **V Tenant isolation** — PASS. No new tables. `PATCH /tenant` already runs through the user's JWT client (RLS). Worker already scopes by `tenant_id`; the currency lookup is by that same id.
- **VII Money/language** — PASS and directly advanced: removes hard-coded GBP/USD defaults; Arabic-Indic digits and separators get explicit tests; mobile strings/formatting follow ar/en.
- Gate result: no violations; Complexity Tracking empty.

## Decisions that amend the spec (to apply to spec.md before tasks)

1. **FR-001/FR-007/Scenario 6/SC-005 and the "no home currency" branches** — moot: `tenant.currency` is always set. Keep the *fallback to existing behaviour* only for the corner case of the session not yet loaded.
2. **FR-002** — owner-only edit already enforced (`require_role(owner)`); non-owner read already works. Needs a settings UI + test only.
3. **FR-003 audit** — `PATCH /tenant` does **not** currently audit (verify in T-task). Add an `audit_event` with old/new currency.
4. **Currency validation** — `TenantUpdate` should restrict to the supported list (`supported_currency`), not any 3 letters.
5. **US2 AS4 ("no home currency")** — replaced by: no fallback is stored (amended 2026-10-14): an unresolved currency stores nothing and routes to review as `currency_unresolved`; `tenant.currency` is only a reviewer suggestion.

## Project Structure

```text
specs/022-home-currency-readiness/{spec.md, plan.md, research.md, data-model.md,
                                   quickstart.md, contracts/, tasks.md}

apps/api/src/procurepilot_api/modules/tenants/   # audit on PATCH /tenant, supported-currency validation
apps/api/src/procurepilot_api/modules/landed_cost/service.py   # :89,99,104 GBP -> quote -> tenant -> missing
apps/web/src/app/
  core/session/…                                   # expose homeCurrency() helper over session.tenant()
  features/orders/order-create/                    # :81 'USD' -> homeCurrency()
  features/rfq/guardrails/                         # :61,161 'USD' -> homeCurrency()
  features/quotations/quotation-review/            # :265,1149 'USD' -> quote ?? homeCurrency()
  features/catalogue/supplier-form/                # min-order / delivery-fee default
  features/settings/                               # owner-only "Home currency" control
services/extraction-worker/src/procurepilot_extraction_worker/
  worker.py            # load tenant.currency by tenant_id, pass into providers
  structured_parse.py  # :67 GBP -> tenant currency + fallback flag
  azure_di.py          # :77,153,290 – EGP markers, tenant fallback, drop hard-coded USD
  currency.py (new)    # marker detection (ج.م, جنيه, جنيه مصري, LE, L.E., EGP; word-boundary safe) + Arabic-Indic digits/separators
apps/mobile/lib/
  core/format/money_format.dart (new)              # intl NumberFormat per currency minor units + locale
  features/approvals/approval_queue_screen.dart:102
  features/requests/request_detail_screen.dart:104-148
```

**Structure Decision**: touch existing modules only; one new worker module (`currency.py`) and one
new mobile helper (`money_format.dart`). No new service, table or route.

## Phasing / delegation

| Phase | Work | Lane |
|---|---|---|
| A (US1) | session helper, 5 form defaults, settings control, API audit + validation | API audit/validation in-house (touches tenant write path); forms → Codex/agy |
| B (US2) | `currency.py` + tests first, wire worker, landed-cost, fallback flag in review UI | Codex; orchestrator runs the 5-real-quote test (PP-3) |
| C (US3) | `money_format.dart` + 2 screens + golden/unit tests | Codex (foreground `flutter test`) |

A, B, C are independent after the session helper (A) lands; B's flag reuses the existing review marker.
Checkpoint-commit before each Codex dispatch. Proof of execution required per task.

## Open items for research.md

- How the worker obtains tenant context for the currency lookup (job payload vs. DB read by `tenant_id`) — leaning DB read, no payload change.
- Which existing per-field "needs review" marker the fallback flag reuses (spec assumption) — confirm in `quotation-review`.
- Exact `supported_currency` list vs. the two divergent web lists (G1 stays out of scope; the settings control must use the API list).

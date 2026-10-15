# Reference-data lookups review: regions, currencies, tax models

Review date 2026-10-15. Code read from `origin/main` (fetched this session). Hosted DB read with
SELECT only, in a read-only session (`aws-1-eu-west-1.pooler.supabase.com:6543`; hosted
`schema_migrations` = 145 rows, max `20261014000002`, so hosted is up to date with `main`).
No code, migration, seed or DB row was changed.

## 1. Where the dropdown values come from

| Layer | What it does | Evidence |
|---|---|---|
| Schema | `supported_region(code, label_en, label_ar, is_enabled)`, `supported_currency(code CHECK ^[A-Z]{3}$, …, minor_units smallint default 2)`, `supported_tax_model(code, …, region_code FK→supported_region)`. Global tables, anon and authenticated can read them, only the service role can write. The header comment says widening the set "is an insert or an is_enabled flip, never a migration and never a deploy". | `supabase/migrations/20260819000002_reference_tables.sql:3-5,8-32,40-42` |
| Rows | Only `apps/api/scripts/seed.py` inserts rows: 3 regions, 4 currencies, 3 tax models, `on conflict do nothing`. Its docstring says "Local development only". No migration inserts rows into these tables. Precedent for data in a migration exists: `supported_base_unit` rows are inserted in `20260819000011_catalogue_units.sql:19-25`. | `seed.py:1-3,31-48,300-322` |
| API | `GET /reference/config-options` → `config_options()` selects `code,label_en,label_ar` where `is_enabled`, ordered by code. **It does not return `minor_units` or `region_code`.** | `tenants/service.py:138-149,264-273`; `tenants/models.py:16-25` |
| Sign-up validation | Checks each of region, currency and tax_model on its own (exists and is enabled). Nothing checks that the tax model belongs to the region. | `tenants/service.py:157-170` |
| Web sign-up | Three `mat-select`s fill straight from `configOptions()` and show `label_ar` or `label_en` by locale. Tax models are not filtered by region. Nothing is pre-selected. | `onboarding/signup/signup.component.html:112-145`, `.ts:63-71,84-100` |
| i18n | `packages/i18n` holds only the field labels and placeholders (`en.json:91-99`). Option labels are data in the DB rows, not i18n keys. | `packages/i18n/en.json:91-99` |
| Hard-coded lists in web | (a) The supplier form starts with GBP/EUR/USD/SAR/AED/EGP and replaces it with the API list when that list is non-empty. (b) Quotation review has a fixed list of 17 codes (USD, EUR, GBP, AED, SAR, EGP, QAR, KWD, BHD, OMR, JOD, CHF, JPY, CNY, INR, AUD, CAD) and **never consults the API**. | `supplier-form.component.ts:93-100,132-145`; `quotation-review.component.ts:207-210` |
| Mobile | Mobile has no reference lists. Its money formatter has a hard-coded digits table: KWD, BHD and OMR get 3 decimals, everything else gets 2. **JOD is missing.** | `apps/mobile/lib/core/format/money_format.dart:7-11` |
| `minor_units` usage | **Never read anywhere in code.** The only references are the column definition and the seed insert. | `git grep minor_units origin/main` → `seed.py:310`, `…reference_tables.sql:20` only |

## 2. Current state: code compared with hosted

| Table | Seed (`seed.py`) | Hosted (query result) | Arabic labels |
|---|---|---|---|
| supported_region | GB, EG, AE | AE, EG, GB (all enabled) | All present (المملكة المتحدة / مصر / الإمارات العربية المتحدة) |
| supported_currency | GBP, EGP, AED, USD (all minor_units 2) | AED, EGP, GBP, USD (all minor_units 2, enabled) | All present |
| supported_tax_model | uk_vat_standard, eg_vat_standard, ae_vat_standard | Same three, **plus `uk_vat` ("UK VAT", label_ar `'ض'`, GB, enabled)** | `uk_vat` has a junk one-letter Arabic label |

Hosted tenants by (region, currency, tax_model): (GB, GBP, uk_vat_standard) 86 · (GB, GBP, uk_vat) 5 ·
(GB, EGP, uk_vat_standard) 1 · (EG, EGP, eg_vat_standard) 1.

The `uk_vat` row is a test-fixture leak. Integration fixtures insert exactly
`('uk_vat','UK VAT','ض','GB')` with `on conflict do nothing` (e.g.
`apps/api/tests/integration/test_rfq_service_e2e.py:40`, `catalogue_helpers.py:52`, and about 15 more). When
those tests ran against the hosted DB, the row persisted. **Today every new sign-up on hosted sees two
UK VAT options, one of them labelled "ض" in Arabic.** 5 tenants reference it through an FK.

**What the owner hit:** hosted offers only 3 regions (GB/EG/AE), 4 currencies (AED/EGP/GBP/USD) and 3
real tax models. Missing: SA, KW, QA, BH, OM, JO, and the currencies SAR, KWD, QAR, BHD, OMR, JOD, EUR.

**The FK reach is wider than the sign-up form.** Every money currency column FKs to
`supported_currency`: 49 FKs on hosted, including quotation, quotation_line, landed_cost,
purchase_order(_line), budget, threshold_rule, supplier, saving_record, synced_bill and
negotiation_brief_item (pg_constraint query). An Egyptian tenant therefore **cannot store a single
SAR, KWD or EUR quote line** either, even though the UI offers those codes (§4, B1–B3).

## 3. Gap table (recommended additions, in priority order)

Tax rates below are the rates given in the brief, not verified by me. Confirm them with a tax advisor
before they become data. Minor units are from ISO 4217.

| # | Country | Region code | Currency | Minor units | Tax model code (proposed) | Rate | Arabic labels (region / currency / tax) |
|---|---|---|---|---|---|---|---|
| 0 | Egypt | EG (exists) | EGP (exists) | 2 | eg_vat_standard (exists) | 14% | exist |
| 1 | Saudi Arabia | SA | SAR | 2 | sa_vat_standard | 15% | المملكة العربية السعودية / ريال سعودي / ضريبة القيمة المضافة بالسعودية |
| 2 | UAE | AE (exists) | AED (exists) | 2 | ae_vat_standard (exists) | 5% | exist |
| 3 | Kuwait | KW | KWD | **3** | kw_no_vat | none | الكويت / دينار كويتي / لا توجد ضريبة قيمة مضافة (الكويت) |
| 4 | Qatar | QA | QAR | 2 | qa_no_vat | none | قطر / ريال قطري / لا توجد ضريبة قيمة مضافة (قطر) |
| 5 | Bahrain | BH | BHD | **3** | bh_vat_standard | 10% | البحرين / دينار بحريني / ضريبة القيمة المضافة بالبحرين |
| 6 | Oman | OM | OMR | **3** | om_vat_standard | 5% | سلطنة عُمان / ريال عُماني / ضريبة القيمة المضافة بعُمان |
| 7 | Jordan | JO | JOD | **3** | jo_gst_standard | 16% (GST) | الأردن / دينار أردني / الضريبة العامة على المبيعات بالأردن |
| 8 | (cross-border) | — | EUR | 2 | — | — | — / يورو / — |
| 9 | Wider MENA (later) | MA, TN, LY, IQ, LB… | MAD (2), TND (**3**), LYD (**3**), IQD (**3** in ISO) | — | per country | — | to be written. Note that TND, LYD and IQD are also 3-decimal. |

GB/GBP/uk_vat_standard and USD stay as they are. EUR is recommended because quotation review and
the supplier form already offer it (`quotation-review.component.ts:208`, `supplier-form.component.ts:95`).

## 4. Bugs and risks found

### Blocking, or silent wrong data

- **B1: The extraction worker writes unsupported currency codes, so the FK fails and the whole quote is refused.**
  Azure DI accepts any `currency_code` Azure returns (`azure_di.py:318-320`), and the structured parser
  accepts any 3-letter `currency` column (`structured_parse.py:79-86`). The worker writes the code
  straight into `quotation.currency` (`worker.py:287-298`) without checking `supported_currency`.
  On hosted today, a SAR, KWD, QAR or EUR invoice raises an FK violation. The worker marks the job
  `extraction_failed` and refuses the quotation (`worker.py:90-93`) instead of routing it to
  `currency_unresolved` review. The same will happen for any code still not added after the GCC rows ship.
- **B2: Quotation review offers 17 currencies; 13 of them break on save with a misleading 503.** The
  `currencyOptions` list is at `quotation-review.component.ts:207-210`. A correction writes the code
  through PostgREST (`review_service.py:281-297`). The FK `APIError` turns into
  `ServiceUnavailableError({"dependency":"database"})` (`review_service.py:152-153`). A reviewer
  who picks KWD sees "database unavailable", not "unsupported currency".
- **B3: The Bedrock fallback can never confirm an ISO code.** `bedrock.py:151-152` collects markers
  such as `{"AED"}` but then looks them up in `{"$":"USD","£":"GBP","€":"EUR"}`. Any ISO code
  returns `None`, so `bedrock.py:154-156` strips the currency. Verified by running main's logic:
  `"AED 1,200"`, `"Total: 1,200 KWD"` → `None`; `"$ 50"` → USD. Every GCC quote that names its
  currency by ISO code lands in `currency_unresolved` review. It fails safe, but it adds review
  load to every quote. QAR and JOD are not even in the regex.
- **B4: Arabic "جنيه إسترليني" (pound sterling) is detected as EGP.** `_EGP_MARKER` matches a bare
  `جنيه` (`currency.py:9-11`). `_OTHER_MARKER` has no Arabic markers at all (`currency.py:13-16`).
  Verified: `detect_currency("100 جنيه إسترليني")` → `EGP`, and `"100 جنيه سوداني"` → `EGP`. This is a
  silent wrong currency; every other path fails safe.
- **B5: GCC Arabic markers are not recognised at all.** `"1,200 ر.س"`, `"١٠٠ ريال"`, `"12.345 د.ك"`,
  `"500 درهم"` and `"SAR 1,200"` all → `None` (`detect_currency` returns `None` whenever no EGP marker is
  present, `currency.py:27-28`). After spec 022 these route to `currency_unresolved` (`worker.py:359-362`),
  not to GBP. **GTM G3 ("falls through to GBP") is stale.** It is a review-load problem, not a misroute.
  The code has no ambiguity handling for `ريال` (SAR/QAR/OMR), `دينار` (KWD/BHD/JOD) or `درهم`
  (AED/MAD), because it does not know those words. Any fix must treat bare words as ambiguous and
  return unresolved.

### 3-decimal currencies (KWD, BHD, OMR, JOD, and later TND, LYD, IQD)

Storage is safe: every money column on hosted is `numeric(18,4)` (43 columns, information_schema
query), and API `Money` models accept up to 4 decimals (e.g. `catalogue/models.py:32`,
`landed_cost/schemas.py:14`, `orders/schemas.py:53-54`). Display, rounding and text output are not safe:

| Where | Problem | Failure scenario |
|---|---|---|
| `apps/web/src/app/core/format/format.service.ts:43-44,49-50` | `formatMoney` forces exactly 2 decimals. It backs the `formatMoney` pipe (`money.pipe.ts:15-22`), which **64 templates** use. | A 12.345 KWD bill shows as "KWD 12.35" across accounting, alerts and similar screens. |
| `order-create.component.html:183,199` (`number:'1.2-2'`, plus a `'USD'` fallback) | PO line and order totals | 3-decimal PO totals are rounded on screen |
| `digest-settings.component.html:154` | digest preview | same |
| `quotation-lines.component.ts:149`; `quotation-review.component.ts:280,342,1005` | `toFixed(2)` on line totals, computed total, difference | Line total 10.125 KWD shows as 10.13 |
| `savings-ledger.component.ts:122`; `basket-split.component.ts:404` | `toFixed(2)` on verified savings and split savings | Savings understated or overstated by up to 0.005 |
| `offers/offer-formatting.ts:15-18` | min 2 / max 4 digits, hard-coded `'en-US'` | 12.5 KWD → "12.50"; never Arabic digits |
| `api/.../digests/renderer.py:58,92` | `:,.2f` in the weekly digest email | Emailed digest misstates KWD/BHD/OMR/JOD amounts |
| `api/.../analyst/retrieval.py:335-336,526,539-541` | `quantize(0.01)` plus `,.2f` | Grounded analyst answers cite 2-decimal figures |
| `api/.../workers/export_worker.py:196-206` | Sums as **float**, then formats `.2f` | Exported spend and savings are rounded, with float drift |
| `api/.../alerts/conditions.py:537,560` | Fee and MOV quantized to 0.01, and the result feeds the **recurrence key** (`:538`) | Two KWD fees differing only in the 3rd decimal collapse to one key |
| `apps/mobile/lib/core/format/money_format.dart:7-11` | Hard-coded table, JOD missing | JOD amounts show 2 decimals on mobile |
| Tolerances `review_service.py:26`, `extraction-worker/validation.py:47`, `quotation-review.component.ts:295,303`, `accounting/matching_service.py:106` | Fixed tolerance of 0.01 | For 3-decimal currencies, 0.01 is 10 minor units: a looser match than for 2-decimal currencies. Low severity. |

Two GTM claims need correcting. G2 says "the shared `formatMoney` already does" handle minor units.
That is only true of `core/format/money.ts:79-84` and `packages/domain-types/src/money.ts:73-78`,
which leave the digits to `Intl`. `core/format/money.ts` has **0 importers**; the formatter the app
actually uses is the 2-decimal `FormatService`. G2 also lists only KWD, BHD and OMR as 3-decimal;
JOD is also 3-decimal.

### Tax models

- **T1: `tenant.tax_model` is a label only.** It is used nowhere except storage and a raw-code
  display on Home (`layout/home/home.component.html:62` shows e.g. `eg_vat_standard`, untranslated). No
  rate lives on `supported_tax_model` (column list on hosted: code, label_en, label_ar, region_code,
  is_enabled, created_at). VAT is per quote line, `quotation_line.vat_rate numeric(5,4)`, consumed by
  landed cost (`landed_cost/rules.py:57`) and review arithmetic (`review_service.py:335-337`). Nothing
  assumes one global rate. The "no VAT" countries (KW, QA) still need a tax-model row, because
  sign-up requires one (`models.py:75`, `signup.component.ts:70`).
- **T2: Tax model is not tied to region.** `region_code` exists but is not returned by the API
  (`models.py:16-19`), not used to filter the dropdown (`signup.component.html:141`), and not checked at
  sign-up (`service.py:157-170`). Once the list grows to about 9 tax models, a Kuwaiti workspace can
  pick "UAE VAT".
- **T3: There is no VAT-inclusive or VAT-exclusive flag** (GTM C5, unchanged).

### Other

- **O1:** The branch "Region" field is free text (`branch-form-dialog.component.html:43-48`, API
  `organisation/schemas.py:27`), but `branch.region` FKs to `supported_region`. Typing "SA" fails at the DB.
- **O2:** Nothing blocks adding rows. The only constraints are the PK, the ISO `^[A-Z]{3}$` CHECK on
  currency, and the tax_model→region FK, so region rows must be inserted before tax-model rows. There
  are no enums. `TenantUpdate.currency` is validated against `supported_currency`
  (`tenants/router.py:65`), so new rows immediately become valid home currencies.

## 5. Recommended implementation plan (ready to hand to a coding lane)

**PR 1: reference data (small, ship first)**
1. New forward-only migration, `supabase/migrations/20261015000001_mena_reference_data.sql`:
   - insert regions SA, KW, QA, BH, OM, JO;
   - insert currencies SAR(2), KWD(3), QAR(2), BHD(3), OMR(3), JOD(3), EUR(2);
   - insert tax models from §3.
   Use `on conflict (code) do nothing` and insert regions before tax models. This follows the
   `catalogue_units.sql` precedent. Optionally `update supported_tax_model set is_enabled=false where code='uk_vat'`:
   the 5 tenants keep their FK, and the option leaves the dropdown.
2. Mirror the same rows in `seed.py:31-48` so a fresh local DB matches hosted.
3. **Apply to hosted explicitly** (`supabase db push`, or the owner's usual manual path). Deploying
   containers does not run migrations. Then verify with the SELECTs used in this review.
4. Stop fixtures from leaking: integration helpers should reuse `uk_vat_standard`, or insert their
   rows with `is_enabled=false`.
5. Catch the review FK error: map the PostgREST FK error code `23503` on currency fields to
   `422 {currency: "unsupported"}` instead of a 503 (`review_service.py:152`).

**PR 2: extraction safety (before any GCC quote)**
6. Before writing, the worker checks extracted currency codes against `supported_currency`. An unknown
   code is treated as unresolved (review, `currency_unresolved`), never an FK crash (fixes B1).
7. Fix `bedrock.py:151-152` (B3). Simplest route: generalise `detect_currency` to return any single
   supported ISO code or unambiguous symbol adjacent to a number, and drop the separate regex.
8. Marker table. **Unambiguous:** ر.س→SAR, د.إ→AED, د.ك→KWD, ر.ق→QAR, د.ب→BHD, ر.ع→OMR, د.أ→JOD, and
   qualified words (ريال سعودي, دينار كويتي, درهم إماراتي, …). **Ambiguous, return None:** bare ريال,
   دينار, درهم. `جنيه إسترليني`→GBP and `جنيه سوداني` are excluded from EGP (B4). Add unit tests for every
   row above plus Arabic-Indic digits.

**PR 3: minor units end to end**
9. Add `minor_units` (currencies) and `region_code` (tax models) to `ReferenceOption` / `ConfigOptions`.
   This is an additive contract change, so update the OpenAPI contract and `core/api/models.ts:74-80`.
10. Web: `FormatService.formatMoney` stops forcing 2 digits. It either lets `Intl` use the ISO default
    or uses `minor_units` from config. Replace the `toFixed(2)` and `number:'1.2-2'` sites in §4.
    Replace both hard-coded currency lists with config-options (GTM G1).
11. API: add one `shared/money.py` helper, `quantize_for_display(amount, currency)`, and use it in the
    digest renderer, analyst retrieval, the export worker (and switch the export sums from float to
    Decimal), and alerts. Keep the recurrence key at stored precision.
12. Mobile: add JOD (and TND/LYD/IQD) to `money_format.dart:8`, or feed minor units from the API.
13. Sign-up UX: filter tax models by the selected region, and validate tax_model.region_code = region
    in `_validate_reference_rows` (T2). Optionally prefill currency from region. Translate the Home
    tax-model display.

Tests: unit tests for detection and formatting (KWD 12.5 → "12.500", JOD on mobile), the 422 for an
unsupported currency, a sign-up integration test with SA/SAR/sa_vat_standard, a Playwright sign-up
in en and ar, and axe. `pnpm test:isolation` is not affected, because these are global tables, not
tenant-scoped.

## 6. Decisions the owner must make

1. **Scope now:** Egypt plus the full GCC plus Jordan, or Egypt + KSA + UAE only? Each 3-decimal
   currency added before PR 3 lands shows wrong decimals on web and in emails.
2. **Migration or one-off insert:** `reference_tables.sql:3-5` says widening is "never a
   migration". Given that deploys never touch hosted and the seed is local-only, I recommend an
   idempotent data migration, so local and hosted stay reproducible. This contradicts that comment,
   so the comment should be updated.
3. **Store a rate on the tax model?** One option is `standard_rate numeric(5,4)`, plus an `is_vat`
   flag, used as a default for `quotation_line.vat_rate`. The alternative is to keep tax models as
   labels only. Linked to the VAT-inclusive question (C5).
4. **Policy for bare ambiguous words:** ريال, دينار, درهم and bare جنيه. Option one: always unresolved.
   Option two: use the tenant's home currency as a *suggestion only*, the way spec 022 already does
   (`worker.py:374-375`).
5. **Clean up `uk_vat` on hosted** (disable it, or re-point the 5 test tenants), and stop running
   fixtures that write reference rows against hosted.

## 7. Owner decisions (2026-10-15)

1. **Scope:** Egypt + KSA + UAE now (add SA / SAR / `sa_vat_standard`, plus EUR). Kuwait, Qatar, Bahrain,
   Oman and Jordan only **after PR 3** (minor units end to end) has merged — no 3-decimal currency is
   enabled before that.
2. **How:** an idempotent forward-only data migration, applied to hosted explicitly; mirror in `seed.py`;
   update the "never a migration" comment in `reference_tables.sql`.
3. **Tax rates:** store a standard rate on the tax model (`standard_rate numeric(5,4)` + `is_vat`), used as
   the default for `quotation_line.vat_rate`; filter tax models by the selected region at sign-up and
   validate `tax_model.region_code = region` server-side.
4. **Ambiguous Arabic words** (bare ريال / دينار / درهم / جنيه): route to `currency_unresolved` review with
   the tenant's home currency as a suggestion only (spec 022 behaviour). `جنيه إسترليني` → GBP.
5. **Test leftovers:** disable `uk_vat` on hosted (`is_enabled=false`; the 5 tenants keep their FK) and stop
   running test suites against the hosted DB — it now holds the demo tenant.

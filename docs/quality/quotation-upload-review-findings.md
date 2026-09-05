# Quotation Upload / Review — Manual Validation Findings

> Read-only manual QA walkthrough of the quotation upload + review flow (chunk 4.3 — Quotation Inbox & OCR),
> run against staging on 2026-09-04. Nothing was edited, saved, authorized, or refused.

---

## Context

- **Environment:** `https://procurepilot.iron-sys.com` · workspace "ProcurePilot Test" (Owner, tenant `f832175c…`)
- **Test file:** `sample-quotation-al-faisal-trading.pdf` (2.6 KB, 1-page PDF — identical to the in-app "Al‑Faisal Trading — 6 items (PDF)" sample)
- **Screens covered:** `/quotations` (Review Queue) · `/quotations/upload` · `/quotations/{id}/review`
- **Method:** browser walkthrough + network/console inspection; extraction cross-checked against `pdftotext`.

---

## 1. What works

- Upload accepts the PDF via **Upload & Extract**; progress state "Extracting line items…" → success screen with document id and **Proceed to Review** / **Upload Another Quotation**.
- Extraction is **100% accurate** for this document (verified against `pdftotext`):
  - 6/6 line items, correct description, qty, unit price, line total (e.g. A4 Copy Paper 500 × £3.25 = £1,625.00).
  - Subtotal £4,519.70 + 20% VAT £903.94 = £5,423.64; issue date 2026‑08‑28; currency GBP.
- Detail page recomputes and shows **"Arithmetic Verified — line subtotals match after applying 20% document-level VAT"** with Stated £5,423.64 / Computed £4,519.70 / Inferred VAT 20%.
- Per-field **provenance** panel: method `azure_di`, model `prebuilt-invoice:2024-11-30`, page number, original AI value.
- Low-confidence field is **flagged** (Expiry Date 54%) with keyboard **Attention Navigation** (FR‑014, Alt+N / Alt+P).
- Source document served from Supabase Storage via a **short-lived (5 min) signed URL**, re-signed on each load, tenant-scoped path (`quotation-documents/tenants/<tenant>/quotations/<id>/…`). No public bucket.
- No app-origin console errors (the only console errors are from the Claude browser extension, not the app).
- Authorize is correctly **blocked** until a supplier is confirmed ("No autonomous purchasing" respected).

---

## 2. Bugs / defects

| # | Severity | Where | Finding | Resolution |
|---|----------|-------|---------|------------|
| B1 | **High** | Review Queue list | **"Reason for Review" = "Arithmetic Mismatch" / Priority HIGH for every VAT-inclusive quotation.** The queue check compares stated total (£5,423.64, VAT-inclusive) against the raw sum of line totals (£4,519.70) *without* the document-level VAT inference the detail page applies. The detail page for the very same quotation shows "Arithmetic Verified". All 7 quotations in the queue (incl. the one just uploaded) are mis-flagged. This makes the queue's triage/priority signal meaningless and creates alarm fatigue (every row red + HIGH). | **Resolved:** extraction-worker arithmetic validation now infers document-level VAT up to 30% before marking a mismatch. |
| B2 | Medium | Upload success screen | Header says **"Extraction completed successfully!"** while a **"Pending Extraction"** status chip is shown in the same view. Stale/contradictory status. | **Resolved:** upload success screen no longer renders the quotation status chip. |
| B3 | Medium | Review page — dates | Issue Date `8/28/2026` and Expiry Date `9/28/2026` render in **US M/D/YYYY** despite workspace Region = GB and Default Locale = EN. Should be DD/MM/YYYY (or ISO). Ambiguous/incorrect for the target locale. | **Deferred:** date display already flows through existing Angular date controls/formatting; GB region-vs-locale granularity is outside current i18n scope. |
| B4 | Medium | Review page — money | **Stated Total Amount** field shows raw **`5423.6400`** (4 decimals, no separator, no symbol) while the arithmetic banner shows **`£5,423.64`**. Inconsistent money formatting; 4dp is wrong for GBP display. | **Resolved:** Stated Total input now displays via the shared money formatter and normalizes formatted edits before saving corrections. |
| B5 | Low | Supplier dropdown | With zero suppliers in the workspace the "Supplier (Required)" combobox opens to a **dead end** — only placeholder text "Select confirmed supplier…", no options, **no "＋ Add supplier"**, no empty-state guidance. Reviewer must leave the page, create a supplier, and navigate back. | **Resolved:** review page now shows an i18n empty state with an Add supplier link when the workspace has no suppliers. |
| B6 | Low | All pages | Browser tab **`<title>` is "Web"** on every route (no per-page or app title). Should be "ProcurePilot" + page name. | **Resolved:** default app title changed to ProcurePilot. |
| B7 | Low | Upload page | Sample links use **relative hrefs** (`samples/sample-quotation-al-faisal-trading.pdf`) on the deep route `/quotations/upload`; fragile against router/base-href changes (resolves to `/quotations/samples/…`). | **Resolved:** sample download links now use root-relative `/samples/...` URLs matching the public assets path. |
| B8 | Low | Review page | **Confidence badge on Currency = 90%** even though the source document states "GBP" explicitly in the column headers — looks like the score reflects workspace default inference, not the document. | **Deferred:** provider confidence calibration belongs to the extraction provider, not the inbox UI/API code. |
| B9 | Low | Review queue | Brief flash of a bare **"Loading…"** block on each visit, then abrupt content swap (no skeleton). | **Resolved:** queue loading state now keeps a 200px minimum height and shows the spinner without the text flash. |
| B10 | Low (a11y) | Review + queue | Status/priority and confidence conveyed **by colour alone**; several comboboxes (status filter, priority filter, currency, supplier) expose **no accessible name** in the accessibility tree. | **Verified:** badges already include visible text labels and Material form-field labels provide combobox accessible names; no code change needed. |

---

## 3. Missing functions

> Status legend: ✅ Done · 🟡 In progress · ⬜ Remaining · ⏸ Deferred

### Lifecycle / data management
- ✅ **Soft delete / archive** anywhere (queue or detail) — implemented, audit-logged.
- ✅ **"Re-run / retry extraction"** — implemented.
- ✅ **"Replace source document"** — implemented.
- ✅ **Duplicate / near-duplicate detection** on upload — implemented.
- ✅ **Export of extracted data** as CSV — implemented (JSON not added; CSV covers the need).
- ✅ **"Create re-quote from this one"** — implemented.

### Review workflow
- ✅ **Add row / remove row** for line items — implemented, with inline recalculation of totals.
- ✅ **Re-quote picker** — linked-quotation selection implemented.
- ✅ **Review notes / comments** — reviewer notes field implemented.
- ✅ **Assignment / ownership** — uploaded-by and reviewed-by now shown on the review page (no assignable-reviewer field yet — see queue bulk-assign, still ⬜).
- ✅ **Audit trail / history** — implemented, surfaced as an expansion panel on the review page.

### Queue
- ✅ **Search** (by quotation id, supplier, total, filename) — implemented.
- ✅ **Column sorting** — implemented.
- ✅ **Pagination / "load more"** — implemented.
- ✅ **Date-range filter** — implemented.
- ✅ **Bulk actions** — bulk archive, bulk refuse, bulk re-prioritise implemented. Bulk *assign* still ⬜.
- ✅ **Row is clickable** — implemented.
- ✅ **Age / SLA indicator** — implemented.
- ✅ **Empty-state copy** for filtered/zero-result queue — implemented.

### Timestamps
- ✅ **"Created" column** — now shows time + relative age.
- ✅ **Review page timestamps** — uploaded at / extracted at / reviewed at implemented.
- ✅ **Quote validity countdown** — "expires in N days" / expired badge implemented.
- ⏸ Date fields are locale-incorrect (see B3) — deferred, same reason as B3.

### Ingestion
- ⬜ **Email-in / watched folder / supplier-portal submission** — not started; "Quotation Inbox" is still upload-only. Larger feature, not scheduled.
- ⬜ **Multi-file / batch upload** — not started.
- ⬜ **Page limit guidance** for large multi-page PDFs — not started; multi-page behaviour remains untested.

---

## 4. UX improvements

> Status legend: ✅ Done · 🟡 In progress · ⬜ Remaining · ⏸ Deferred

- ✅ **Fix the queue arithmetic check (B1)** — VAT-aware calculation now shared between queue and detail page.
- ⬜ **Document-to-field linkage / bounding-box overlay** — not started; PDF viewer still has no click-to-highlight link to extracted fields. Larger feature (see §5 item 3).
- ✅ **Confidence legend + threshold** — legend bar added explaining the 85% flag threshold with badges. Tenant-configurable threshold still ⬜ (see §5 item 13).
- ✅ **Money & date formatting** — Stated Total now uses the shared money formatter. Date-locale half deferred (B3).
- 🟡 **Supplier step: inline "+ Add supplier" and auto-suggest from the document** — empty-state + Add-supplier link done (B5). Auto-suggest from extracted vendor name is being implemented now (see §5 item 11).
- ✅ **Success screen** — stale status chip removed (B2).
- ✅ **Queue improvements** — clickable rows, search, sort, pagination, age column, filtered empty state, skeleton loader all implemented.
- ✅ **Breadcrumbs** — implemented (Quotation Inbox › {id}).
- ✅ **Line-item editing affordances** — add/remove row and inline recalculation implemented. "Split line" not implemented (not requested since; low priority).
- ✅ **Re-quote link** — picker requires selecting the superseded quotation. Diff view not implemented — low priority, revisit only if reviewers ask.
- ⬜ **Validation feedback on upload** — explicit messages for unsupported type / over 25 MB / 0-byte / encrypted PDF still untested/unconfirmed.

---

## 5. Suggested additions

> Status legend: ✅ Done · 🟡 In progress · ⬜ Remaining · ⏸ Deferred

1. ✅ **Duplicate detection** on upload — implemented.
2. ✅ **Extraction feedback loop** — retry extraction implemented; "mark this field wrong" training-signal capture not implemented (corrections are already captured per-field, which covers the practical need).
3. ⬜ **Bounding-box overlay** on the document for every extracted field and line item — not started. Meaningful scope (requires reading Azure DI's returned polygons and wiring a PDF-viewer overlay); revisit as its own chunk.
4. ✅ **Quotation history / audit panel** — implemented.
5. ✅ **Soft delete / archive** — implemented, with restore.
6. ✅ **Export & reuse** — CSV export and create-re-quote implemented. Push into Smart Compare / Basket Split not implemented — no user request yet.
7. ✅ **Validity tracking** — expiry badge implemented.
8. ⬜ **Inbound ingestion** (email-in / watched folder) — not started. Larger feature, not scheduled.
9. ✅ **Bulk queue operations** — archive/refuse/re-prioritise implemented. Assignment + saved views still ⬜.
10. ✅ **Reviewer collaboration** — notes implemented. @mention / "request changes" not implemented — no user request yet.
11. 🟡 **Supplier auto-match** from the extracted vendor name, with confidence and one-click confirm-or-create. **Design, being implemented now:**
    - The extraction pipeline already captures the vendor/letterhead name as a `supplier_name` field extraction (Azure DI `VendorName` / structured-parse `supplier_name` column) — no new extraction work needed, only using what is already captured.
    - At extraction time, the worker fuzzy-matches that name against the tenant's existing suppliers using Postgres `pg_trgm` `similarity()` (already an enabled extension per the constitution's stack). Two new nullable columns on `quotation`: `suggested_supplier_id`, `supplier_match_confidence`.
    - Thresholds: confidence ≥ 0.6 → shown as a positive "Suggested supplier" banner, pre-selectable with one click; 0.35–0.6 → shown as a tentative "Possible match" banner; below 0.35 (and only when the tenant actually has suppliers to compare against, so an empty workspace doesn't get flagged) → no pre-fill, and the queue gets a new, non-blocking `no_supplier_match` review reason (normal priority, not HIGH — this is a nudge, not a data-integrity problem, learning from the B1 alarm-fatigue mistake).
    - Review page: accept the suggestion with one click, or create the supplier directly from the review page (pre-filled with the extracted name) without navigating away — closing the B5 dead-end for the common case where the extracted name simply isn't in the workspace yet.
    - Confirmation is never automatic — `supplier_id` is only set by an explicit reviewer action, preserving "no autonomous purchasing" (Constitution Principle VIII).
12. ⏸ **Locale/currency correctness pass** — money formatting fixed (B4); date-locale half deferred (B3); RTL already covered elsewhere in the app, not re-verified for this module specifically.
13. ⬜ **Per-tenant confidence thresholds** — the legend now explains the fixed 85% threshold; making it tenant-configurable is not started.
14. ⬜ **Multi-file / multi-page upload** — not started.
15. ✅ **Queue/detail search** — implemented.
16. ⬜ **Human-readable `reference_code`** — not started. Per the original sequencing note, this comes after search (done) and alongside/before duplicate detection (done) — now unblocked whenever it's prioritised.

---

## 6. Quick repro for B1 (highest priority)

1. Upload the Al‑Faisal PDF (or any quotation whose stated total includes document-level VAT).
2. Open `/quotations` → the new row shows **Reason for Review: "Arithmetic Mismatch"**, **Priority: HIGH**.
3. Click **Review & Authorize** → the detail header shows **"Arithmetic Verified — line subtotals match after applying 20% document-level VAT."**
4. Queue and detail disagree; every VAT-inclusive quotation is affected.

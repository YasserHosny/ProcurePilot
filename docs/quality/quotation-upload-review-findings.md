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

### Lifecycle / data management
- **No delete or archive** anywhere (queue or detail). "Refuse" is a workflow state, not removal. There is no way to clear a junk/duplicate/test upload — the workspace already holds 6 near-identical £5,423.64 quotations with no cleanup path. (Soft-delete + `audit_event`.)
- **No "re-run / retry extraction"** — if extraction is wrong there is no way to re-process the same document.
- **No "replace source document"** — can't swap the attached file on an existing quotation.
- **No duplicate / near-duplicate detection** — uploading a file identical to an existing one (same supplier, total, date, or file hash) produces a silent 7th copy with no warning.
- **No export of extracted data** — you can download the *original* document, but not the extracted header + line items as CSV/JSON.
- **No "duplicate to new quotation" / "create re-quote from this one".**

### Review workflow
- **Line items appear to be non-editable in structure** — fields are shown per row but there is no visible **add row / remove row** control for a missed or hallucinated line.
- **"This is an updated re-quote of an existing quotation"** checkbox has **no linked quotation picker** — you can tick it but not say which quotation it supersedes.
- **No review notes / comments** — no place to record why a correction was made, or to leave a note for the authorizer.
- **No assignment / ownership** — can't assign a quotation to a reviewer; no reviewer field.
- **No visible audit trail / history** on the quotation (uploaded by, uploaded at, extracted at, field edits, state changes) — the constitution mandates `audit_event`, but it is not surfaced in the UI.

### Queue
- **No search** (by quotation id, supplier, total, filename).
- **No column sorting** (created, total, priority, status).
- **No pagination / "load more"** controls (API has cursor pagination per project docs; no UI).
- **No date-range filter**; only Status + Priority.
- **No bulk actions** (bulk refuse, bulk re-prioritise, bulk assign).
- **Row is not clickable** — only the "Review & Authorize" button / id chip navigates.
- **No age / SLA indicator** ("open 3 days").
- **No empty-state** copy verified for a queue with zero results.

### Timestamps
- **"Created" column shows date only** ("Sep 3, 2026") — no time, no timezone, no relative age, no hover tooltip with the full timestamp.
- **Review page shows no timestamps at all** — no "uploaded at", "extracted at", or "last modified".
- **Quote validity is not surfaced as a countdown** — Expiry Date `9/28/2026` is shown as a plain field with no "expires in N days" / "expired" badge, despite validity being business-critical for a quotation.
- Date fields are locale-incorrect (see B3).

### Ingestion
- The module is called **"Quotation Inbox"** but is **upload-only** here — no email-in address, no watched folder / drop inbox, no supplier-portal submission. "Inbox" implies an inbound flow that isn't present.
- **No multi-file / batch upload**; one file at a time.
- **No stated page limit** or guidance for large multi-page PDFs (sample is 1 page — multi-page behaviour untested/undocumented).

---

## 4. UX improvements

- **Fix the queue arithmetic check (B1)** so the "Reason for Review" and priority reflect the same VAT-aware calculation the detail page uses; reserve red/HIGH for genuine discrepancies.
- **Document-to-field linkage:** the page claims "inspect extracted fields side by side with the source document", but the PDF is Chrome's native viewer at 46% zoom and there is no visual link. Azure DI returns bounding polygons — overlay them and highlight the region when a field is focused; fit-to-width by default.
- **Confidence legend + threshold:** show what score triggers a flag (54% flagged, 90% not) and what the badge means; make the threshold tenant-configurable.
- **Money & date formatting:** format `Stated Total` as `£5,423.64` everywhere; render dates per workspace locale (GB → DD/MM/YYYY or ISO); one canonical formatter.
- **Supplier step:** inline "＋ Add supplier", and **auto-suggest** from the document letterhead ("Al‑Faisal Trading Co." is right there) with a fuzzy match against existing suppliers; show an empty-state with a link when none exist.
- **Success screen:** drop the stale chip; show the assigned priority + the reason it was assigned; consider taking the user straight to review.
- **Queue:** make rows clickable; add search, sort, pagination, saved filters, an age column, and a subtler "needs review" treatment; skeleton loader instead of "Loading…".
- **Breadcrumbs** (Quotation Inbox › {id} › Review) and per-page titles.
- **Line-item editing affordances:** visible add/remove row, "split line", inline recalculation of the computed total as fields change.
- **Re-quote link:** when the checkbox is ticked, require selecting the superseded quotation and show a diff.
- **Validation feedback on upload:** explicit messages for unsupported type / over 25 MB / 0-byte / encrypted PDF (not tested — worth confirming these are handled gracefully).

---

## 5. Suggested additions

1. **Duplicate detection** on upload — file hash + (supplier, total, issue date) heuristic → "Possible duplicate of QT‑…, uploaded 2 days ago" with merge / keep-both / discard.
2. **Extraction feedback loop** — "mark this field wrong" / "retry extraction" that captures corrections as training/eval signal; show which engine ran and allow re-processing.
3. **Bounding-box overlay** on the document for every extracted field and line item (click field → scroll+highlight in the PDF).
4. **Quotation history / audit panel** — uploaded by + at, extracted at, every field edit, authorize/refuse, with actor and timestamp (surfacing `audit_event`).
5. **Soft delete / archive** for drafts and junk, audit-logged, with a "Discarded" filter and restore.
6. **Export & reuse** — download extracted header + lines as CSV/JSON; "start a new quotation from this one"; push confirmed lines into Smart Compare / Basket Split.
7. **Validity tracking** — "expires in N days" badge, expired-quotation warning, optional alert before a quotation lapses.
8. **Inbound ingestion** — dedicated email-in address per workspace and/or a watched storage folder, so "Quotation Inbox" is a real inbox.
9. **Bulk queue operations** + assignment + SLA/age + saved views.
10. **Reviewer collaboration** — notes/comments per quotation, @mention a colleague to co-review, "request changes".
11. **Supplier auto-match** from letterhead / VAT number / address, with confidence and one-click confirm-or-create.
12. **Locale/currency correctness pass** across the module (dates, money, number grouping) driven by workspace settings; RTL check for Arabic.
13. **Per-tenant confidence thresholds** and a small "extraction quality" summary on the review page (avg confidence, fields below threshold).
14. **Multi-file / multi-page** upload with progress per file and a stated size/page limit.

---

## 6. Quick repro for B1 (highest priority)

1. Upload the Al‑Faisal PDF (or any quotation whose stated total includes document-level VAT).
2. Open `/quotations` → the new row shows **Reason for Review: "Arithmetic Mismatch"**, **Priority: HIGH**.
3. Click **Review & Authorize** → the detail header shows **"Arithmetic Verified — line subtotals match after applying 20% document-level VAT."**
4. Queue and detail disagree; every VAT-inclusive quotation is affected.

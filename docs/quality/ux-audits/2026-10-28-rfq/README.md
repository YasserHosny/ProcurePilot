# UX audit — RFQ pages (2026-10-28)

```
═══════════════════════════════════════════════════════════
VERDICT: Fail

Persona: purchasing-officer-sa (below), plus the first-time-user lens
Surfaces audited: 4 / 4 routes — /rfq/history, /rfq/create (+ /rfq/:id/edit), /rfq/:id (Details, Items,
  Recipients, Responses tabs), the Converted-row hand-off to /requests/:id. /rfq/guardrails (owner settings)
  out of scope.
Interaction Manifest: complete for the 4 routes (typed, saved, dialog opened, console + network read)

Hard Gates: console errors 0, warnings 3 (3 allowlisted: Grammarly extension), network 5xx 0,
  403/404 auth 0, layout-collapse 1 (history at 1024 px), axe Critical — / Serious — (NOT RUN: CSP blocks
  injection, see M10)
Performance (on /rfq/history): LCP 1.34 s / CLS 0 / INP not measured — thresholds 4.0 s / 0.25 / 500 ms

Findings:
  Critical: 0    High: 3    Medium: 10    Low: 3

Self-critique pass (sub-agent): Drafted: 20  Kept: 16  Generic: 3  Duplicate: 1
  (dropped as generic: focus after Add Line, sidebar highlight on child routes, constant document title;
   date-format inconsistency merged into M3; M10 cut down to its RFQ-specific part)

Time per phase: Phase 3 ≈ 11 m (21:32:30 → 21:43:23) / Total ≈ 25 m
Manifest plausibility: 28 entries over 4 routes, median gap 17 s, 25 saved screenshots, console read on
  every route

TOP 5 (ranked by impact × ease, senior-designer pick):
  1. H1 Send RFQ sends the last saved version, not what is on screen — wrong quantities reach suppliers.
  2. H2 Responses show "Pending Match" with no product text and no totals — the comparison the RFQ exists
     for can't be made.
  3. M1 + M2 Past needed-by dates and duplicate product lines save and send — two validators away from
     not embarrassing the buyer in front of suppliers.
  4. M6 A responded RFQ dead-ends at "Cannot prepare request while lines are unmatched" — one link to
     Match Resolution unblocks the whole thread.
  5. H3 RFQ History collapses at 1024 px with the sidebar open — the default laptop view in a back office.
═══════════════════════════════════════════════════════════
```

Hosted app `procurepilot.iron-sys.com`, English UI, Chrome via Claude in Chrome, signed in as the owner of the
Saudi workspace «مطاعم رواق» (owner said the account is for testing). Code references are to `origin/main` at
`f3ba1fe2` (includes #314/#315, today's RFQ Details page). One draft was created and never sent: RFQ
`50d15686` "UX AUDIT 2026-10-28 — do not send" (needed-by 20/10/2026, rice ×20, oil ×10, rice ×5). It can't
be deleted from the UI (M9).

## Persona (locked)

**Purchasing officer, Riyadh restaurant group (3 branches).** Arabic-first but runs the app in English;
moderate tech comfort; sends dry-goods RFQs weekly from a 1366–1440 px laptop in the back office, between
deliveries and kitchen calls. Time-pressed: wants quotes back before Thursday's order. Worried mainly about
sending a supplier the wrong quantity or date — that is embarrassing and costs money. Skims, doesn't read
help text, trusts what the screen shows.

## Threads walked

| Thread | Path | Clicks | Ended clearly? |
|---|---|---|---|
| T1 Create and send this week's RFQ | Overview → RFQ History → Create RFQ → 3 lines → 2 suppliers → date → terms → Save Draft → scroll → (Send — opened confirm, cancelled) | 15 to send 2 lines to 2 suppliers | Draft saved with a past date and a duplicate line, no warning |
| T2 See responses and pick a supplier | History → Responded row → Details → Responses tab | 3 | No — dead end (M6), no product names (H2) |
| T3 Fix a draft before sending | History → Edit → change qty → leave | 2 | No — edit silently lost (H1) |
| T4 Find what happened to an old RFQ | History → Converted row | 1 | Lands on a Withdrawn PR, no way back to the RFQ (M7) |

## Interaction manifest

```
Persona: purchasing-officer-sa · 1440×900 unless noted · console + network read after every primary action
[✓] 21:33:08 /rfq/history loaded — 4 API calls 200, console 0, LCP 1336 ms, CLS 0
[✓] 21:33:37 / (Overview) → sidebar "RFQ History" → "Create RFQ" (a[routerLink=/rfq/create]) — 11 API calls 200
[✓] 21:34:05 Typed "rice" into Product (input[formcontrolname=workspace_product_id]) → "No products match"
[✓] 21:34:30 Picked أرز بسمتي from the autocomplete → focus moved to Quantity, Quantity touched+invalid
[✓] 21:34:53 Typed 20 → Tab → Enter on Add Line → 2 lines, focus stayed on Add Line
[✓] 21:35:16 Line 2 زيت دوار الشمس ×10; Add Line; line 3 أرز بسمتي again ×5 → no duplicate error
[✓] 21:35:41 Opened Suppliers (mat-select), picked الذهبي + الوفرة, Escape closed
[✓] 21:36:20 Typed 10/20/2026 into Needed By → invalid, no mat-error, Save disabled
[✓] 21:36:37 Typed 20/10/2026 (past) → valid, Save enabled
[✓] 21:36:48 Typed terms with ' & <b> é — into the textarea
[✓] 21:37:01 Clicked Save Draft → POST /api/v1/rfq 201, snackbar "Draft saved", URL /rfq/50d15686…/edit
[✓] 21:37:12 Scrolled → "RFQ Status: Draft · Send RFQ" card below the fold
[✓] 21:37:31 Changed qty 20→25 without saving → Send RFQ still enabled
[✓] 21:37:34 Sidebar → RFQ History → no leave warning; new draft is row 1
[✓] 21:37:47 Opened row ⋯ menu → View details / Compare responses (disabled) / Duplicate
[✓] 21:37:56 View details → /rfq/50d15686…, draft banner, past date unflagged, terms escaped
[✓] 21:38:10 Items tab (rice ×2 lines) → Recipients tab (2, Not sent)
[✓] 21:38:23 History → recipients count popover on the Responded RFQ
[✓] 21:38:51 Responded row → /rfq/d8f7fb0c… Details (no next-step banner)
[✓] 21:39:02 Responses tab → 8 "Pending Match" lines, 2 disabled Prepare Request, no link
[✓] 21:40:53 /rfq/create structure check (h1 absent, inputs labelled)
[✓] 21:41:08 /rfq/history at 1024 → table scrolls, Actions clipped
[✓] 21:41:11 /rfq/history at phone width → actions off-screen, 8×20 link target
[✓] 21:41:26 /rfq/50d15686…/edit at phone width → pack size cut; qty back to 20
[✓] 21:42:20 History row "Send" on the audit draft → confirm dialog, focus on Cancel
[✓] 21:42:28 Escape → dialog closed, no /send request, still Draft
[✓] 21:42:50 Converted row ⋯ → Duplicate → /rfq/create?from=b81271cd…, notice, date cleared (not saved)
[✓] 21:43:23 Converted row click → /requests/2bceafd8… (Withdrawn), console errors 0
```

## Findings

### H1 · Send RFQ sends the saved version, not the edited form — High · Interaction
- **Surface:** `/rfq/:id/edit`, 1440×900
- **Reproduce:** 1. Open a draft in Edit. 2. Change line 1 quantity 20 → 25, don't press Save Draft.
  3. "Send RFQ" is still enabled. 4. Click RFQ History in the sidebar.
- **Observed:** Send stays enabled with a dirty form (`sendEnabled: true`, qty 25 on screen) and
  `onSend()` posts `/rfq/{id}/send` without saving, so suppliers get 20. Leaving the page shows no warning;
  reopening the draft shows 20.
- **Expected:** what is on screen is what gets sent; unsaved edits are never dropped silently.
- **Evidence:** `screens/11-unsaved-qty-25-send-enabled.jpg`, `screens/12-history-after-leaving-dirty-form.jpg`,
  `screens/22-edit-phone-pack-size-cut.jpg` (draft back at 20)
- **Suspected location:** `apps/web/src/app/features/rfq/create/create.component.ts:377` (`onSend`),
  `create.component.html` send-card button `[disabled]`
- **Smallest patch:** in `onSend()`, when `this.form.dirty`, run the `onSave()` request first and chain
  `sendRfq` on success; add a `CanDeactivate` guard on `rfq/create` and `rfq/:id/edit` that confirms when
  `form.dirty`.

### H2 · Responses show "Pending Match" with no product text, mismatched order, no totals — High · Architecture
- **Surface:** `/rfq/d8f7fb0c…?tab=responses`, 1440×900
- **Reproduce:** History → Responded row → Responses (2).
- **Observed:** every line of both quotes reads "⚠ Pending Match"; الذهبي lists 15/20/10/10, الوفرة lists
  20/10/10/15 (each supplier's PDF order); no quote total. The officer can't tell which line is rice or
  who is cheaper.
- **Expected:** each line shows what the supplier wrote, lines line up with the RFQ's lines, and each card
  has a total.
- **Evidence:** `screens/18-responses-pending-match.jpg`, `screens/19-responses-dead-end.jpg`
- **Suspected location:** `apps/api/src/procurepilot_api/modules/rfq/service.py:489-505` (query never selects
  `quotation_line.original_text`; `order by r.created_at, ql.created_at`), `schemas.py:96`
  (`RfqResponseLineComparison`), `apps/web/src/app/features/rfq/compare/compare.component.html:118-122`
- **Smallest patch:** add `ql.original_text` to the select and `original_text: str` to
  `RfqResponseLineComparison`; render it after the badge (`{{ line.original_text }}`); order lines by the
  matched product's `rfq_line.position` (unmatched last); add a footer row summing `quantity × unit price`
  per response.

### H3 · RFQ History collapses at 1024 px; actions off-screen on a phone — High · Visual (hard gate)
- **Surface:** `/rfq/history`, 1024×800 with the sidebar open (default); 375 px
- **Observed:** 1024 px: Sent Date wraps onto six lines ("Oct / 28, / 2026 / · / 11:09 / AM"), the Actions
  header is clipped to "Actio" and the ⋯ button is cut at the edge (`.table-container` scrolls). Phone:
  Edit/Send/⋯ are behind a horizontal scroll (table 695 px in a 413 px box); recipient link target 8×20 px.
- **Evidence:** `screens/20-history-1024-collapse.jpg`, `screens/21-history-phone-actions-offscreen.jpg`
- **Suspected location:** `apps/web/src/app/features/rfq/history/history.component.scss` (table cells),
  `history.component.html:30-146`
- **Smallest patch:** `white-space: nowrap` on the Needed By and Sent Date cells; at `max-width: 1199px`
  hide the Recipients and Responses columns (`displayedColumns` from a `BreakpointObserver` signal); at
  `max-width: 767px` keep Status, Needed By, Actions only.

### M1 · Past needed-by date is accepted and sent — Medium · Interaction
- **Reproduce:** Create → Needed By "20/10/2026" (eight days ago) → Save Draft.
- **Observed:** saved (POST 201); Details shows "Needed By Oct 20, 2026" with Edit/Send and no warning.
- **Evidence:** `screens/08-before-save-past-date.jpg`, `screens/14-details-draft-past-date.jpg`
- **Suspected location:** `create.component.ts:86` (`Validators.required` only), datepicker in
  `create.component.html` has no `[min]`; server `rfq` create/update accepts it
- **Smallest patch:** `[min]="today"` on the datepicker, a `minDate(today)` validator with a `mat-error`,
  and a 422 `needed_by_in_past` from the API on create, update and send.

### M2 · The same product can be added twice — Medium · Interaction
- **Reproduce:** Create → line 1 rice ×20 → line 3 rice ×5 → Save Draft.
- **Observed:** the autocomplete still offers rice with no "already added" mark; both lines are saved
  (Items tab: rice 20 packs, rice 5 packs). Suppliers would get rice twice with two quantities.
- **Evidence:** `screens/06-create-duplicate-line-suppliers.jpg`, `screens/15-details-items-duplicate-lines.jpg`
- **Suspected location:** `create.component.ts:79-83` (lines `FormArray` validators),
  `getFilteredProducts` (`:111`)
- **Smallest patch:** a `FormArray` validator that flags a repeated `workspace_product_id` with
  "Already on line N", and `[disabled]` on options already chosen in another line.

### M3 · Date field red with no message or format hint; Save disabled silently — Medium · Feedback
- **Reproduce:** Create → Needed By "10/20/2026" (US order, English UI).
- **Observed:** field turns red, no `mat-error`, no hint; Save Draft disabled with no reason. The workspace
  parses DD/MM. The Responses tab then shows "Required By 04/11/2026" while every other date reads
  "Nov 4, 2026" (merged from L1).
- **Evidence:** `screens/07-date-invalid-no-message.jpg`, `screens/18-responses-pending-match.jpg`
- **Suspected location:** `create.component.html` Needed By `mat-form-field`; `compare.component.html`
  Required By input
- **Smallest patch:** `<mat-hint>DD/MM/YYYY</mat-hint>` and
  `<mat-error>` for `matDatepickerParse` / `required` on both datepickers (keys in `packages/i18n`).

### M4 · Quantity shows an error before the user types — Medium · Feedback
- **Reproduce:** Create → pick a product from the list.
- **Observed:** focus jumps to Quantity, which is already `ng-touched` + invalid and drawn red
  (`rgb(163,35,27)`); its placeholder is cut to "Enter quar" (88 px field).
- **Evidence:** `screens/05-quantity-red-before-input.png`
- **Suspected location:** `create.component.ts:125-131` (`onProductSelected` focuses twice; the first focus
  blurs as the panel closes, marking the control touched)
- **Smallest patch:** drop the synchronous `target.focus()`, keep the `setTimeout` focus, then
  `this.linesFormArray.at(index).get('quantity')?.markAsUntouched()`.

### M5 · History rows can't be told apart — Medium · Architecture
- **Observed:** columns are Status, Needed By, Sent Date, Recipients, Responses; two drafts (2 recipients,
  0 responses) look the same. Details breadcrumb is "RFQ · Draft"; RFQs have no reference.
- **Evidence:** `screens/12-history-after-leaving-dirty-form.jpg`, `screens/14-details-draft-past-date.jpg`
- **Suspected location:** `history.component.html:30-146`, `history.component.ts:57` (`displayedColumns`),
  RFQ list summary in `apps/api/.../rfq/schemas.py`
- **Smallest patch:** add `line_count` and `first_product_name` to the RFQ list summary and an Items column
  rendering "أرز بسمتي +2"; reuse it in the breadcrumb.

### M6 · Responded RFQ has no next step; unmatched warning dead-ends — Medium · Interaction
- **Observed:** the Details tab of a Responded RFQ shows only facts (the draft banner exists only for
  drafts). The Responses tab says "Cannot prepare request while lines are unmatched" with no link; both
  Prepare Request buttons are disabled with no `title`/`aria-describedby`.
- **Evidence:** `screens/17-details-responded-no-cta.jpg`, `screens/19-responses-dead-end.jpg`
- **Suspected location:** `apps/web/src/app/features/rfq/detail/detail.component.html:46` (banner only for
  `draft`), `compare.component.html:151-155`
- **Smallest patch:** in the pending warning add `<a [routerLink]="['/matching']"
  [queryParams]="{ quotation: response.quotation_id }">Match lines</a>` (add `quotation_id` to the
  response DTO); add a responded-status banner "N responses — review and choose" that selects the
  Responses tab.

### M7 · Converted row jumps to a Withdrawn PR with no way back — Medium · Architecture
- **Reproduce:** History → Converted row (Oct 30).
- **Observed:** lands on `/requests/2bceafd8…`, status **Withdrawn**, while History still says "Converted";
  the PR page has no link to its RFQ.
- **Evidence:** `screens/25-converted-row-opens-withdrawn-pr.jpg`
- **Suspected location:** `history.component.ts:136-143` (`onRowClick` converted branch)
- **Smallest patch:** row click always opens `/rfq/:id`; on RFQ Details show "Purchase request:
  {{ status }}" with a link to `/requests/:id`; on the PR page add a "From RFQ" link.

### M8 · Send confirmation names no suppliers, items or date — Medium · Feedback
- **Observed:** "Send this RFQ now? Suppliers to be emailed: 2". Focus lands on Cancel and Escape closes it
  (good), but the officer can't check who gets it or for which date — the date in this case was in the past.
- **Evidence:** `screens/23-send-confirm-dialog.jpg`
- **Suspected location:** `history.component.ts:153-161` (`onSendDraft`, `messageParams: { count }`) and
  `detail.component.ts:192-199`
- **Smallest patch:** pass supplier names, line count and needed-by into the dialog message
  ("Email الذهبي للتموين and الوفرة للمواد الغذائية — 3 items, needed by 20 Oct 2026") and add a warning line
  when needed-by is before today.

### M9 · A draft can't be discarded — Medium · Architecture
- **Observed:** row menu has View details, Compare responses (disabled), Duplicate; Details/Edit have no
  delete. The audit draft above has to stay.
- **Evidence:** `screens/13-row-menu-no-delete.jpg`
- **Suspected location:** `history.component.html:153-173` (actions menu), RFQ router (no draft delete)
- **Smallest patch:** `DELETE /api/v1/rfq/{id}` allowed for the creator while `status = 'draft'`
  (audited), plus "Discard draft" in the row menu and the draft banner behind a confirm.

### M10 · RFQ pages have never been scanned by axe; supplier tables unlabelled — Medium · Accessibility
- **Observed:** `apps/web/tests/e2e/` has `@a11y` specs for 17 areas and none for RFQ; live injection is
  blocked by the CSP (`script-src 'self'`, `connect-src 'self' https://*.supabase.co`), so the axe gate
  above could not be measured. Manual check: each supplier's response table has no caption or
  `aria-label`, so a screen reader hears two identical tables.
- **Suspected location:** `apps/web/tests/e2e/` (missing `rfq-a11y.spec.ts`), `compare.component.html:114`
- **Smallest patch:** add `rfq-a11y.spec.ts` (`@a11y`) covering `/rfq/history`, `/rfq/create`,
  `/rfq/:id` (each tab); `[attr.aria-label]="supplierNames()[response.supplier_id]"` on the response table.

### L3 · On a phone the pack size is cut off — Low · Visual
- **Observed:** product field 145 px wide shows "أرز بسمتي (كيس 10 كج" — the pack, which tells "20" bags
  from "20" kg, is the part that disappears.
- **Evidence:** `screens/22-edit-phone-pack-size-cut.jpg`
- **Smallest patch:** in `create.component.scss`, `@media (max-width: 599px) { .line-row { flex-wrap: wrap }
  .item-product-field { flex-basis: 100% } }`.

### L5 · English search misses an Arabic-only catalogue — Low · Interaction
- **Observed:** "rice" → "No products match"; search covers only `tenant_name` and `variant`.
- **Evidence:** `screens/03-create-search-rice-no-match.jpg`, `screens/04-create-product-list.jpg`
- **Suspected location:** `create.component.ts:111-123` (`getFilteredProducts`)
- **Smallest patch:** also match `p.sku` (and aliases once the catalogue carries them).

### L7 · Create-and-send is 15 clicks with Send below the fold — Low · Interaction (shortest path)
- **Observed:** Send RFQ appears only after Save Draft, in a separate card below the fold, partly under the
  "Draft saved" snackbar.
- **Evidence:** `screens/09-after-save-draft.jpg`, `screens/10-send-card-below-fold.jpg`
- **Smallest patch:** a "Save & send" button next to Save Draft that saves then opens the M8 confirm.
  Shortest path then: 12 clicks; with a default needed-by (+7 days) and Enter-in-Quantity adding a line, 10.

## Passes (with proof)

- Duplicate pre-fills lines, suppliers and terms, clears the date and says so — `screens/24-duplicate-prefilled.jpg`.
- Terms with `<b>` and `O'Neil & Sons` are stored and shown escaped, no HTML rendered — `screens/14-details-draft-past-date.jpg`.
- Save Draft round trip: snackbar, URL moves to `/rfq/50d15686…/edit`, the draft appears at the top of
  History without a reload — `screens/09-after-save-draft.jpg`, `screens/12-history-after-leaving-dirty-form.jpg`.
- Send confirm: focus on Cancel, Escape closes, no `/send` request — `screens/23-send-confirm-dialog.jpg`.
- Recipients popover lists each supplier with sent time — `screens/16-recipients-popover.jpg`.
- No app console errors and no 4xx/5xx on any RFQ route; LCP 1.34 s, CLS 0 on `/rfq/history`.

## Not covered, and why

- **axe gate:** CSP blocks injection (M10).
- **Arabic / RTL:** locale persists server-side per owner and another session is running an English flow review
  on this workspace today; switching would have changed their screens.
- **Heavy data (500+ RFQs), second role (buyer), lifecycle, data seasoning:** one workspace, nine RFQs, owner
  role only.
- **Fixing matches to reach Prepare Request:** would have changed the other session's flow-review data.
- **Suppliers without an email** are dropped from the picker with no hint (`create.component.ts:171`); every
  supplier here has an email, so this was not reproduced.

## Perfection roadmap

- **Quick wins (24–48 h):** M3 hint + errors, M4 focus fix, M8 dialog text, H3 nowrap + column hiding,
  M10 table labels, L3, L5.
- **Structural (1–2 weeks):** H1 save-before-send + leave guard, H2 `original_text` + ordering + totals,
  M1/M2 validators (client + API), M5 list summary, M6 next-step banner + match link, M7 row routing,
  M9 discard draft, `rfq-a11y.spec.ts`.
- **Advanced polish:** L7 Save & send with default date, supplier suggestions from past quotes for the
  chosen products.

## Hold this in your hands

The RFQ pages feel like a well-made form bolted to a half-finished outcome. Creating an RFQ is calm and
legible — Duplicate in particular is thoughtful — but the form trusts the buyer more than it should
(yesterday's date, the same rice twice, an edit that never reaches the supplier) and then, when quotes come
back, the screen that should be the payoff shows four rows of "Pending Match" with no way forward. A buyer
would pick it up, get the request out, and then put it down again when the answers arrived. Fix H1 and H2
and it becomes something they reach for every Thursday.

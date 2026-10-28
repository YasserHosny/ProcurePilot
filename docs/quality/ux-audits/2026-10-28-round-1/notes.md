# Round 1 audit — working notes (2026-10-28)

Chain: RFQ `1b7cd76b` (rice ×25, oil ×6, sugar ×12, flour ×8 → الذهبي, الوفرة; needed by 05/11/2026),
quotes الذهبي `DH-26-1252` SAR 4,147 / الوفرة `WF/2026/0781` SAR 4,137 (split ideal 4,063).

## Step 1 — Send RFQ
- 21:54:45 Save Draft → /rfq/1b7cd76b…/edit, line order kept (R2 fixed by #314).
- 21:54:56 Send RFQ on the edit page: **no confirmation dialog** (History and Details confirm) → POST /send 200,
  snackbar "RFQ sent. Suppliers emailed: 2", redirect to History. → add to M8 (consistency, Nielsen 4/5).
- RFQ email arrives in English (R6, open product decision — not re-raised).

## Step 2 — Supplier replies
- 21:56 الذهبي reply (alias From picked automatically), 21:57 الوفرة reply. PDFs attached.

## Step 3 — Quotation Inbox
- 21:58 الذهبي `85ed505f` SAR 4,147 listed "just now" (≈2 min after reply). الوفرة not yet.
- Nav "Quotation Inbox" ≠ page title "Quotation Review Queue" (Krug trunk test / Nielsen 4).
- Rows show internal id `85ed505f`, not the supplier's quote number `DH-26-1252`; no RFQ column — two الذهبي
  quotes (4,147 for 1b7cd76b, 4,830 for d8f7fb0c) can't be told apart (Nielsen 6).
- Every row "Low Confidence Extraction" (alarm fatigue, seen on all 3).
- "Created Oct 28, 2026" and "Age just now" say the same thing twice.
- Two date filters take a full row above a 3-row list.

## Step 3 — Review & authorize (الذهبي 85ed505f)
- Extraction exact: 4 lines, qty 25/6/12/8, prices 85/151/39/81, total 4,147 = PDF. Arithmetic Verified.
- One flagged field: Expiry date 52% although "Text in document: 07/11/2026" matches → Confirm as-is.
- After "Confirm as-is" the field badge reads **"Corrected by Human"** — nothing was corrected (Nielsen 2/4).
  Flagged panel vanishes and the page jumps ~500 px.
- Page never names or links the RFQ the quote answers (`rfqMention: false`, 0 rfq links) (Nielsen 6).
- "Uploaded by: <owner-gmail>+pp-sa-owner" — the quote came by email from الذهبي's alias; attribution misleading.
- Pack Details "—" on all 4 lines although the PDF has an العبوة column (كيس 10 كجم, تنكة 18 لتر …).
- Unit Price shows "85.0000" (4 dp) — money format elsewhere is 0 or 2 dp (PPS-85).
- `check_circle` button next to "Valid for 11 days" has no aria-label.
- Five secondary actions (Export CSV, Retry, Re-Quote, Archive, Back) sit above the content; "Back to Review
  Queue" duplicates the breadcrumb (Nielsen 8).
- Confirm & Authorize opens an **inline confirm panel below the fold** — in view nothing changes (Nielsen 1).
- 21:59:57 POST /confirm took **5,363 ms** with only a button spinner.
- After authorize: no toast, no next step (no "Match lines" / "Back to RFQ"), status chip only (Nielsen 1, Krug 2).
- الوفرة a10bcd44: extraction exact (87/145/35/84, 4,137); Expiry flagged 46%. Alt+N scrolls to it (pass).
  POST /confirm **9,174 ms**.

## Step 4 — Match Resolution
- 22:01:57 queue: 2 of 4 lines open per quote (rice + oil auto-matched; sugar + flour "Below Match Threshold").
- The right product is "Top candidate" with **28 % / 34 %** in red; breakdown: lexical 33 %, semantic "Not available",
  brand/variant/pack/pack-size/price all a flat 50 % — the breakdown explains nothing.
- **The quote replies to an RFQ that named these exact products, packs and quantities, yet matching ignores the RFQ
  lines** — every reply to an RFQ re-enters manual matching (biggest shortest-path win in the round).
- Buyer-facing jargon: "lexical (pg_trgm), semantic (pgvector)", "Deterministic Landed Cost (US3)",
  "landed-cost-v1", "pinned to rule version", toast "alias saved" (Nielsen 2, first-time lens).
- "Matched Product:" label with an empty value on the selected candidate before deciding.
- Keyboard 1 + Enter confirms (pass). After plain confirm the page stays put and re-lays out (Landed Cost panel
  inserted), so a click on "Back to Queue" misses.
- Alias saved for "دقيق" (الوفرة) didn't lift الذهبي's identical "دقيق" line (still 28 %) a minute later.
- "Resolve and Next" chains well; last one → "All match tasks resolved — queue cleared." then an empty queue
  with no next step (no "Compare responses for RFQ …").
- Big green "No catalogue refreshes are awaiting review." banner on every visit (Nielsen 8).
- Quantity shown "8.0".

## Step 5 — Compare (RFQ Details › Responses) and Basket Split
- 22:04:41 After matching, Responses shows names, RFQ line order, per-pack prices — good. Still: no per-supplier
  total (4,147 vs 4,137 to add up by hand), no cheapest-line highlight, no link to Basket Split.
- Guardrail reason "There is not enough price history." rendered in red (error colour for an informational line).
- Prepare Request disabled until a branch is chosen — no reason shown on the button (Nielsen 1/9).
- Required By shows "05/11/2026" here, "Nov 5, 2026" elsewhere (M3 merge).
- Basket Split (sidebar) is not tied to the RFQ: the buyer re-keys 4 products + 4 quantities (~14 clicks); the
  page opens pre-filled with rice ×10 and every "Add Item" adds another rice ×10 (Nielsen 6/5).
- Title "Two-Supplier Basket Split … exactly two suppliers" next to "Add Supplier (2–10)" (Nielsen 4).
- Pack hint under each Quantity ("10 pack(s) × 10 kg = 100 kg") overlaps the next row's floating label.
- 22:06:03 POST /baskets/optimise 202 → result in < 8 s: SAR 4,063, "Splitting saves SAR 74 versus buying
  exclusively from الوفرة" — correct (الوفرة oil+sugar 1,290, الذهبي rice+flour 2,773).
- **Result page has no way to act on it**: only "Rerun Optimisation" / "Start New Basket Split"; nothing
  prepares the two purchase requests (dead end — the round's headline saving can't become an order here).
- "Solver Confidence: High", "Result Validity: Oct 28, 2026" — jargon / unclear meaning for a buyer.

## Step 6 — Prepare + submit request (الوفرة, فرع العليا)
- 22:06:50 Prepare Request → /requests/96d38cde (draft), SAR 4,137, branch + required-by carried over (pass).
- **Lines re-ordered**: oil, sugar, rice, flour (RFQ: rice, oil, sugar, flour) — 2nd different order in the chain.
- **No supplier anywhere on the request**, no link back to the RFQ or the quotation (Nielsen 6, trunk test).
- Prices are a bare "SAR 145" next to each line — no "per pack", no line total.
- Toast "Draft purchase request prepared successfully. **Open draft**" while already on the draft.
- 22:07:13 Submit → PATCH 200 + POST /submit 200, snackbar, redirect to /requests list.
- Purchase Requests list: columns Required By / Branch / Status / Total only — no supplier, no RFQ, no reference;
  actions are three unlabeled-looking icons (eye, cart, undo).

## Step 7 — Approve
- Approval Queue row: no supplier, no "compared with 1 other quote / split would save SAR 74" context —
  the approver approves SAR 4,137 blind to the cheaper SAR 4,063 option (Nielsen 6, decision support).
- Approve/Reject render under the "Lines" column; "Actions" column header is empty.
- "4 lines" text isn't clickable; only the 24 px chevron toggles. Its tooltip "Hide lines" **covers the Approve
  button** after expanding.
- Expanded lines in a 3rd order (flour, rice, sugar, oil); empty note shows "Not available".
- Approve dialog doesn't restate amount/supplier. 22:08:21 POST /approve 200 → "Request approved." then an empty
  queue — no "Create purchase order" next step.

## Step 8 — Purchase order
- Request page after approval: status chip **"Ordered" before any PO exists**; a bare "Cancel" button next to
  "Create purchase order" (cancel the page or the request?).
- 22:08:55 Create PO form pre-fills supplier الوفرة, PO-000004, lines, per-pack prices, base units (pass).
  Header shows a raw UUID "Creating from Request: 96d38cde-46f3-…"; subtitle "Manually record an internal
  purchase order." on a pre-filled form; Expected Delivery not pre-filled from Required By 05/11/2026;
  "Remaining Allocatable: 8" jargon; Currency is an editable free-text box ("SAR").
- 22:09:23 POST /orders 201 → PO-000004 Draft, "Order created successfully.", per-pack + per-kg prices (pass).
- **PO detail never shows the supplier** (no "الوفرة" anywhere on the page) and has no link to its request/RFQ.
- "Remaining: Not provided" on every line where it should be the ordered quantity.

## ui-ux-pro-max cross-check (guideline DB, --domain ux / --stack angular)
- Feedback · Progress Indicators (Medium): "Step 2 of 4" for multi-step processes — round 1 has no journey/step
  indicator and every step ends without a next step.
- Feedback · Loading Indicators (High): long waits must be explained — 5.4 s / 9.2 s authorize with a button spinner.
- Forms · Inline Validation (Medium) + Angular "show errors after touched, not before": date field red with no
  message; Quantity red on focus.
- Interaction · Confirmation Dialogs (High): irreversible supplier email — edit-page Send RFQ has no confirm.
- Data Entry · Bulk Actions (Low): matching 4 lines one at a time.
- Interaction · Disabled States: Prepare Request / Save Draft disabled without a reason.
- No verified DB match for "tooltip obscures action" — that finding rests on Nielsen + WCAG 2.2 Focus Not Obscured.

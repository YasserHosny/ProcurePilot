# UX audit — round 1, end to end (2026-10-28)

Four skills over the round-1 flow on the hosted Saudi workspace «مطاعم رواق» (English UI, owner account, Chrome):
`ux-audit` (live walkthrough, hard gates), `ux-heuristics` (Nielsen/Krug, 0–10 per step), `impeccable critique`
(design review + detector, two isolated sub-agents) and `ui-ux-pro-max` (guideline cross-check). The RFQ pages
were audited in depth earlier today: [`../2026-10-28-rfq/`](../2026-10-28-rfq/README.md) (H1–H3, M1–M10, L3–L7);
this report covers the whole chain and refers to those IDs instead of repeating them.

```
═══════════════════════════════════════════════════════════
VERDICT: Fail

Persona: purchasing-officer-sa (Riyadh restaurant group, English UI, Arabic catalogue, time-pressed)
Surfaces audited: 12 routes — RFQ create/edit, RFQ history, RFQ details (4 tabs), quotation inbox, quotation
  review, match queue, match resolution, basket split, purchase request, requests list, approval queue,
  create PO, PO detail, order tracking, savings ledger
Chain: RFQ 1b7cd76b → quotes 85ed505f (الذهبي 4,147) + a10bcd44 (الوفرة 4,137) → 4 matches → basket split
  dbee66a2 (4,063) → request 96d38cde (الوفرة 4,137) → approved → PO-000004 (draft)
Interaction Manifest: complete (typed, saved, authorized, matched, optimised, submitted, approved, created)

Hard gates: console errors 0, warnings 0 app (Grammarly extension allowlisted), network 5xx 0, 403/404 0,
  layout collapse 1 (RFQ history at 1024 px, from the RFQ audit; review + PO pages clean at 1024),
  axe — NOT RUN (CSP script-src 'self' blocks injection; no @a11y spec covers these routes)
Performance: LCP 1.34 s / CLS 0 on /rfq/history. Slow action: POST /quotations/{id}/confirm 5.4 s and 9.2 s.

Findings (round 1, new): Critical 0 · High 5 · Medium 13 · Low 6   (+ RFQ audit: High 3 · Medium 10 · Low 3)

Heuristic score (ux-heuristics, whole round): 5 / 10
Time: walkthrough 21:52 → 22:10 (18 min live), total ≈ 45 min
═══════════════════════════════════════════════════════════
```

## The round in one sentence

Every step works on its own, and the data is right — extraction was exact, the split saved the SAR 74 it should —
but **every step ends in a dead end**, the RFQ's own information is thrown away after step 1, and three of the
nine screens never say which supplier they are about.

## Shortest path (clicks, this run)

| Step | Clicks now | Main waste | With fixes |
|---|---|---|---|
| 1 Create + send RFQ (4 lines, 2 suppliers) | ~19 | Save then a separate Send below the fold | ~14 (Save & send, default date) |
| 3 Review + authorize ×2 | 12 | confirm-as-is, scroll to hidden confirm, no next step | 6 |
| 4 Match 4 lines | 9 + navigation | matching ignores the RFQ the quote answers | **0** (RFQ replies auto-match) |
| 5 Compare + split | 3 + ~14 to re-key the basket | basket split not tied to the RFQ | 2 |
| 6–7 Request + approve | 8 | approver lacks context; tooltip over Approve | 6 |
| 8 PO | 5 | delivery date not pre-filled | 4 |
| **Total** | **~70** | | **~32** |

## Findings — round 1 (new; RFQ-page findings are in the RFQ report)

IDs are `R1-<severity><n>`. Evidence paths are under `screens/`; code references are `origin/main` `f3ba1fe2`.

### High

- **R1-H1 Matching ignores the RFQ the quote answers.** Both quotes were replies to RFQ `1b7cd76b`, which named
  the exact products, packs and quantities; still 4 of 8 lines went to manual matching, with the right product
  scored 28 %/34 % in red. The matching module never reads RFQ lines (`modules/matching/` has no `rfq` reference).
  Fix: when a quotation is linked to an RFQ response, score each quote line against that RFQ's lines first
  (same position / name / pack / quantity) and auto-confirm unambiguous hits. Evidence: `11`, `12`, `13`.
- **R1-H2 Basket split can't be acted on, and isn't tied to the RFQ.** The optimiser's answer (SAR 4,063, saves 74)
  has only "Rerun" / "Start New"; nothing turns it into purchase requests. The buyer also re-keys the RFQ's
  4 products + quantities (~14 clicks); each "Add Item" defaults to rice ×10. Fix: "Split this RFQ" from RFQ
  Details › Responses (pre-filled), and "Prepare 2 requests" on the result. Evidence: `18`, `19`, `20`.
  Code: `features/offers/basket-split/basket-split.component.html:10`.
- **R1-H3 The purchase order never names its supplier.** PO-000004's page has no «الوفرة» anywhere and no link
  to its request or RFQ; Order Tracking cards have no supplier either. Evidence: `30`, `31`.
  Code: `features/orders/order-detail/order-detail.component.html` (no supplier binding),
  `order-list.component.html`.
- **R1-H4 Request and approval never name the supplier or the alternatives.** The prepared request, the requests
  list and the approval row show branch, total and lines but not الوفرة, the quote, or that a SAR 4,063 split
  exists; the approver decides blind. Evidence: `21`, `22`, `23`.
- **R1-H5 No step tells you the next step.** Authorize → status chip only; queue cleared → empty queue; approve →
  "Request approved." and an empty queue; the PO knows its request but the request never offers "Create PO" in
  the approval toast. Combined with H1/H2 this is why the round costs ~70 clicks. Evidence: `09`, `16`, `26`.

### Medium

- **R1-M1 Lines re-order through the chain**: RFQ rice, oil, sugar, flour → request oil, sugar, rice, flour →
  approval flour, rice, sugar, oil. Evidence: `21`, `24`. Same family as RFQ-H2 (responses ordered by
  `ql.created_at`).
- **R1-M2 Authorizing a quote takes 5–9 s** (`POST /quotations/{id}/confirm` 5,363 ms and 9,174 ms) with only a
  button spinner, and its confirmation opens **below the fold**, so the first click looks like nothing happened.
  Evidence: `06`, `07`, `08`.
- **R1-M3 Buyer-facing engineering jargon**: "lexical (pg_trgm), semantic (pgvector)" (`en.json:1316`),
  "Deterministic Landed Cost (US3)" (`:1415`), "alias saved" (`:1445`), "Remaining Allocatable" (`:3445`),
  "Manually record an internal purchase order" on a pre-filled form (`:3404`), raw UUID "Creating from Request:
  96d38cde-…", "Solver Confidence", "pinned to rule version landed-cost-v1". Evidence: `12`, `14`, `15`, `28`.
- **R1-M4 "Confirm as-is" is recorded as "Corrected by Human"** (`en.json:1021`): nothing was corrected.
  Evidence: `05` vs `08`.
- **R1-M5 Match score shown in red for the right answer** with a breakdown that is all 50 % placeholders
  (brand/variant/pack/pack-size/price) and "Semantic: Not available" — the evidence explains nothing.
  Evidence: `12`.
- **R1-M6 Approval Queue layout**: Approve/Reject sit under "Lines" while "Actions" is empty; "4 lines" text
  isn't clickable (only a 24 px chevron); after expanding, the chevron's "Hide lines" tooltip **covers the
  Approve button**. Evidence: `23`, `24`.
- **R1-M7 Request shows "Ordered" at approval, before any PO exists** — by design since R2.3
  (`modules/requests/service.py:2034–2041`, written before POs existed). Needs a product decision now that
  POs are real. Evidence: `27`.
- **R1-M8 Quotation inbox and review never say which RFQ a quote answers**; rows show the internal id
  `85ed505f` instead of the supplier's `DH-26-1252`; authorized quotes vanish (round-1 open issue).
  Evidence: `03`, `04`, `10`.
- **R1-M9 Extraction leaves Pack Details empty** although the PDF has an العبوة column; matching then lacks the
  pack signal (one cause of the 28 %). Evidence: `05`.
- **R1-M10 Edit-page "Send RFQ" emails suppliers with no confirmation**, unlike History and Details.
  (Extends RFQ-M8.)
- **R1-M11 Prepare Request / Save Draft disabled without a reason** (choose a branch / fix a field).
  Evidence: `17`.
- **R1-M12 Savings from the chain are not recorded**: choosing الوفرة (−10) or the split (−74) leaves the
  ledger unchanged until someone uses "Record Purchase Outcome" by hand. Evidence: `32`.

### Low

- **R1-L1** Money with 4 decimals in review ("85.0000"), quantity "8.0" in matching.
- **R1-L2** Alias learned for «دقيق» from one supplier doesn't lift the identical line from another a minute later.
- **R1-L3** "Uploaded by" names the owner for an emailed quote; should say "Received from الذهبي by email".
- **R1-L4** PO form: Expected Delivery not pre-filled from Required By; Currency is free text.
- **R1-L5** Order Tracking says "Ordered Oct 28" for a Draft PO; PO detail "Remaining: Not provided".
- **R1-L6** Basket split title says "exactly two suppliers" next to "Add Supplier (2–10)"; pack hints overlap the
  next row's label.

## Passes (with proof)

- Extraction exact for both quotes (4 lines, prices, totals) and Arithmetic Verified — `04`, `05`.
- Alt+N jumps to the flagged field; keyboard 1 + Enter confirms a match; Resolve and Next chains — notes 22:01–22:04.
- After matching, RFQ Responses shows product names in RFQ order — `17`.
- Basket split answer correct (4,063 = الذهبي rice+flour 2,773 + الوفرة oil+sugar 1,290) — `20`.
- Request pre-fills branch, date, per-pack prices; PO pre-fills supplier, number, lines, base units, per-kg —
  `21`, `28`, `30`.
- Review and PO pages clean at 1024 px — `33`, `34`. No app console errors, no 4xx/5xx in the whole chain.

## ux-heuristics — score per step

| Step | Score | Worst heuristic | What gets it to 10 |
|---|---|---|---|
| 1 Create/send RFQ | 5 | Error prevention (send unsaved, past date, duplicates) | RFQ-H1, M1, M2, R1-M10 |
| 3 Quotation inbox | 6 | Recognition (no RFQ, internal id) | R1-M8 |
| 3 Review & authorize | 6 | System status (5–9 s, hidden confirm, no next step) | R1-M2, M4, H5 |
| 4 Match resolution | 4 | Match with real world (jargon, red 28 % for the right answer) | R1-H1, M3, M5 |
| 5 Responses | 5 | Recognition (no totals, unmatched lines unnamed) | RFQ-H2, M6 |
| 5 Basket split | 4 | Recognition + control (re-key, no way to act) | R1-H2 |
| 6 Request | 6 | Recognition (no supplier) | R1-H4, M1 |
| 7 Approval | 5 | Visibility + layout (tooltip over Approve, no context) | R1-H4, M6 |
| 8 Purchase order | 6 | Recognition (no supplier) | R1-H3, M3, L4 |
| **Round** | **5** | **Flow continuity — every step dead-ends** | **R1-H1, H2, H5** |

Krug's trunk test fails on request, approval and PO pages ("what is this about?" — no supplier, no source).

## ui-ux-pro-max cross-check

Guidelines matched (ux domain): Progress Indicators (no journey/step indicator), Loading Indicators — High
(5–9 s authorize), Inline Validation + Angular "errors after touched" (date field, Quantity red on focus),
Confirmation Dialogs — High (edit-page send), Bulk Actions (matching line by line), Disabled States (no reason).
No verified match for "tooltip covers action"; that finding rests on Nielsen 8 and WCAG 2.2 Focus Not Obscured.

## impeccable critique

Method: dual-agent (A: design review sub-agent · B: detector sub-agent), isolated; browser overlay unavailable
(CSP `script-src 'self'`), so B is the CLI detector over the 7 feature folders. Snapshot not persisted.

**Design Health: 21 / 40 (Acceptable — works, needs significant improvement).** Visibility 2 · Real world 2 ·
Control 3 · Consistency 2 · Error prevention 2 · Recognition **1** · Efficiency 3 · Minimalism 2 · Recovery 2 ·
Help 2. Cognitive load high (5 of 8 checklist failures). Peak: "Splitting saves SAR 74" (`20`); end: a PO page
with no supplier and "Not provided" ×4 (`30`) — a flat end to the biggest decision in the round.

Where A and B agree: decoration drifts from Ledger tokens. A found it by eye, B by rule (11 `side-tab` hits:
4–6 px accent stripes where the token `--pp-banner-edge-width` is 3 px — `compare-recommendation.component.scss:5`,
`basket-split-infeasible.component.scss:5,98`, `match-resolution.component.scss:127,159`,
`match-resolution-candidates.component.scss:53`, `approval-queue.component.scss:244`; 3 px hits are false positives).

**R1-M13 Ledger conformance drift on the round-1 screens** (new, from A):
- The product's own devices are absent on operate screens: no folio beside any price, no double rule under a
  verified total, no best-offer chip; savings shown in success green instead of `--pp-savings` teal
  (`basket-split-results.component.scss:50,63`).
- Off-scale type (page titles 1.75 rem/700 vs 24/36 at 600 — `approval-queue.component.scss:22`), radii 4/8/12/9999
  vs 3/6/10/16, card shadows where Ledger cards are border-only (`approval-queue.component.scss:78`,
  `compare.component.scss:21`), raw `rgba()` colours (`match-resolution-candidates.component.scss:201`,
  `quotation-lines.component.scss:37`).
- Page frame wanders: the title's left edge sits at x≈292 (review), 390 (match), 437 (request/approval), 553
  (create RFQ) at the same 1440 px width.
- Two primary navy buttons on the authorize confirm (`08`); status chips are bare text or pills, not the Ledger
  chip shapes.

Strengths A names: per-pack + per-kg pricing carried to the PO (ADR-020); keyboard-first matching; Arabic names
and packs legible in the English UI.

Questions A leaves open: if the RFQ names what the buyer wants, why does a reply ever need manual matching?
Should the cheapest-order recommendation be the one object that flows compare → request → approval → PO?

Questions skipped: this critique runs inside an audit → tasks → fix request; its findings feed the PPS tasks.

## Not covered

Arabic/RTL (owner locale persists server-side), mobile app approval and delivery, buyer role (owner only),
submitting the PO (sends nothing, but not needed for the round), axe (CSP).

## Hold this in your hands

ProcurePilot's parts are well made — the extraction is exact, the optimiser is right, the PO math is careful — but
the parts don't hand off to each other. A buyer carries the context from screen to screen in their head: which
RFQ this quote answers, which supplier this request is for, what to do now that the queue is empty. Make every
screen name its supplier and its source, make every step end with the next one, and let a reply to an RFQ match
itself, and round 1 drops from about seventy clicks to about thirty.

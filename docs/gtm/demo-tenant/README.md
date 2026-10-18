# Demo tenants — plan and dataset (PP-5 / G-1)

Status 2026-10-18: **restaurant tenant set up on hosted** — workspace «مطاعم سند» (EGP, Egypt VAT),
3 branches, 6 cost centres (kitchen + packaging/cleaning per branch), 3 monthly branch budgets
(450k / 380k / 320k EGP), 5 suppliers (EGP terms, plus-address emails), 30 products with preferred
suppliers, owner (`pp-owner`) and Buyer (`pp-buyer`) accounts, inbound email address. **Round 1 reached
a purchase order:** PO-000001 (draft, EGP 56,425, النور) created 2026-10-18 — do not create it again.
Basket split ran on hosted and its result renders (split saves EGP 450; finding 21 fixed by #131). Step-by-step
record: [`round-1/README.md`](round-1/README.md). **Rounds 2 and 3 reached purchase orders** the same day:
PO-000002 (EGP 4,720, الحاج سيد), PO-000003 (20,770, الفيروز), PO-000004 (6,880, باك مصر), approved on the
phone — [`round-2-3/README.md`](round-2-3/README.md).

### Findings from the build (real product bugs)

| # | Finding | Impact | Status |
|---|---|---|---|
| 1 | ~45 `psycopg.connect` call sites lack `prepare_threshold=None`; on Supabase's transaction pooler they fail with `DuplicatePreparedStatement` (reproduced: 3/4 connections fail, 0/4 with the setting) | CSV import cannot commit (preview OK, commit never lands, re-upload → 500); **inbound quote ingestion uses the same pattern** | fixed — #87 merged + deployed 2026-10-16; CSV import re-tested on hosted (committed, 30 duplicates skipped) |
| 2 | Supplier attribution: sender-address history beats the RFQ thread | quotes from a shared sender credited to the wrong supplier | fixed — #84 merged 2026-10-16 |
| 3 | Unit list offers both "Kilogram (kg)" and "Kilogram (kilogram)" | inconsistent product units | fixed — #103 merged + deployed 2026-10-17; migration `20261017000001` (`kg`→`kilogram`) already applied to hosted — do not re-apply |
| 4 | Import preview shows the pack as raw JSON (`{"pack_count":1,"unit_size":"1"}`) | cosmetic | fixed — #103 merged + deployed 2026-10-17 |
| 6 | Team invites are not emailed ("email delivery is not configured"); the link is shown once on screen | every pilot invite must be passed on by hand | fixed — #133 emails invitations via Mailgun, with Resend (operator CLI `pnpm db:invite-member`, #111, remains for operators) |
| 5 | Home page still labels shipped modules "Upcoming (Chunk 4.x)" | first screen a pilot customer sees looks unfinished | fixed — #103 merged + deployed 2026-10-17 |

Lookups review (regions, currencies, tax models): [`lookups-review-2026-10-15.md`](lookups-review-2026-10-15.md).

**Round 1 (2026-10-16) — dry-goods RFQ to النور + الأمانة, first live run on hosted:**

| # | Finding | Impact | Status |
|---|---|---|---|
| 7 | Web sends date-only fields as UTC timestamps: in Cairo (UTC+3) "Needed by 20 Oct" → `2026-10-19T21:00:00Z` → RFQ save **422**, shown to nobody; same family silently shifts savings/export/compare/reorder dates one day back | **no UTC+ customer can create an RFQ**; reports off by a day | fixed — #88 merged + deployed 2026-10-16 |
| 8 | A saved RFQ draft can only be sent from the create page right after saving; History opens a compare page with no Send | stranded drafts | fixed — #103 merged + deployed 2026-10-17 |
| 9 | RFQ list shows a "Sent Date" for unsent drafts; Save gives no confirmation | cosmetic/UX | fixed — #103 merged + deployed 2026-10-17 |
| 10 | Supplier RFQ email: buyer never named, buyer's terms dropped, English-only for an Arabic tenant, quantities `50.000000` with no unit | suppliers don't know who is asking | fixed — #89 merged 2026-10-16 (migration applied to hosted); also fixed raw i18n keys in hosted digests/exports |
| 11 | Arabic business name → tenant slug `workspace` → inbound address `workspace@mail…` | meaningless address; next Arabic sign-up may collide | fixed for new sign-ups — #89 (demo tenant keeps `workspace@`) |
| 12 | **Arabic attachment filename → Supabase Storage `InvalidKey` → email_ingest job fails 3× → email silently lost** (no inbound-log row, no review item) | **every Arabic-named supplier PDF is lost without trace** | fixed — #90 merged + deployed (migration applied); 2 demo emails requeued → ingested, stored with Arabic names, matched to the right suppliers |
| 14 | **Extraction passes the raw quote date `16/10/2026` (DD/MM/YYYY) to Postgres → `date/time field value out of range` → whole quotation `refused`**; days ≤ 12 would be silently month/day-swapped | **every Egyptian/GCC quote refused or mis-dated** | fixed — #96; both demo quotations re-extracted |
| 13 | Ingestion dashboard "Catalogue Imports: 0" after a committed import | wrong counter | fixed — #103 merged + deployed 2026-10-17 |


**Round 1, steps 2–4 (2026-10-17) — authorize, match, compare, request, approval, PO (first live run of everything after extraction):**

| # | Finding | Impact | Status |
|---|---|---|---|
| 15 | Arabic RTL quote tables collapsed into one line; one quote auto-accepted with a wrong 84,000 EGP line | silent wrong prices | fixed — #100 |
| 16 | A low-confidence supplier name on an already-linked quote could never be confirmed (dead end, generic 409) | quote cannot be authorized | fixed — #104; authorized live |
| 17 | **Basket-split optimiser worker has no Dockerfile or deploy workflow; jobs stay `queued` forever, UI spins on "Checking job status…"** | headline feature does not work on hosted | fixed — #108 merged 2026-10-17; container created by the owner, worker deployed; round-1 basket split completed 2026-10-18 and its result renders (#131, #141) |
| 18 | **Pack vs base unit: request estimate re-computed on Submit as per-base-unit prices × pack quantities (56,425 → 6,135.58) using the wrong supplier's prices; PO pre-fill says "10 litre" for 10 tins; Smart Compare asks in litres** | **understated totals feed approval thresholds and budgets; wrong PO units** | fixed — #110 merged + deployed 2026-10-17 (ADR-020: quantities and prices are per pack); PO step to be re-run on hosted |
| 19 | Request flow: Submit drops unsaved edits (cost centre); "Prepare Request" gives no feedback and ignores the RFQ date; approval queue shows a raw requester UUID; branch budgets show "Not available"; approved request has no "Create PO" button (hidden `?source_request_id=` URL); PO needs manual order number + supplier; raw `EGP 56425.0000` formatting; "Resolve and Next" doesn't advance | friction + silent data loss | fixed — #112 merged 2026-10-17 (Submit saves first, Prepare Request feedback + RFQ date, requester names and branch budgets in the approval queue, PO from an approved request with supplier pre-filled); not yet re-run on hosted |
| 20 | Hosted uses the stub embedding: exact-name matches score 55% (all 10 lines needed manual confirm); human-confirmed matches still show 55% / "Medium Confidence" / "match score below 85%"; "Winning margin: 2%%" | trust signals wrong | partly fixed — #109 merged + deployed (human-confirmed matches show as verified; bulk-confirm exact-name matches); hosted still uses the stub embedding |
| 21 | **Completed basket split cannot be read: `GET /baskets/{id}` → 500** — the optimiser stores an advanced result the API's `AdvancedBasketResult` rejects (no `supplier_id` on lines, `confidence` object vs high/medium/low, extra `rule_version`/`advisory_only`) | **basket split result never shows on hosted** | fixed — #131 merged + deployed 2026-10-18 (read-side adapter + contract test); round-1 split renders on hosted |
| 22 | No path from a PO or delivery to a purchase outcome: savings need each line re-typed in Record Purchase Outcome, in base units while the PO is in packs | savings step is manual and error-prone on camera | fixed — #173 merged + deployed 2026-10-18: **Record outcome** on a sent PO pre-fills one editable line per PO line, converted from packs to base units, linked to the PO line (one outcome per line) |
| 23 | Savings baseline `last_paid` is the latest *quoted* landed cost, not a price paid; within one RFQ it is whichever quote was recorded last (round 1 would show −300/+450/−150/+50/+450) | savings number arbitrary until there is purchase history; needs a product decision on the baseline | fixed — owner decided 2026-10-18 the baseline is the last PO price; #173 merged + deployed and migration `20261019000000` applied 2026-10-18: new policy `last_po_price` (newest sent PO line, same base unit, excluding the order being recorded, pack price scaled to base units), falling back to the last quoted price, then the 6-month average; `last_paid` relabelled "Last Quoted Price" |
| 24 | Remaining budget ignores approved spend: approval sets a request to `ordered`, but committed spend counts only `submitted`/`approved`, so Maadi still shows the full 380,000 after ~92,000 ordered | budget warnings never fire on real spend | fixed — #159 merged + deployed 2026-10-18; Maadi branch: 380,000 − 92,245 committed (56,425 + 3,450 + 4,720 + 20,770 + 6,880) = 287,755 remaining. A request page shows the remaining budget excluding its own amount (e.g. 308,525 on the 20,770 request) |
| 25 | A quote `In Review` with no low-confidence field gets no review task, so it is missing from the Quotation Inbox (الحاج سيد) | quote reachable only by link | fixed — #177 merged + deployed 2026-10-18 (migration `20261019000100` applied): a quote in review keeps an open «Ready to authorise» task until it is authorised or refused; a quote already missing its task gets one back on the next inbox load |
| 26 | A refused RFQ reply (no attachment, `email-body.txt`) still shows as a response, with an empty card and an active Prepare Request button | confusing RFQ screen | fixed — #177 merged + deployed 2026-10-18: the RFQ compare view marks a refused reply «Refused» with an explanation and no Prepare Request action; the reply stays listed |
| 27 | Bulk confirm of 11 exact matches takes ~25 s | slow on camera | not yet raised |
| 28 | The phone app's web build signs out on page reload | web build only | not yet raised |
| 29 | The web app signs out about every hour: nothing renewed the 1 h Supabase access token, and there was no refresh route | interrupts long sessions | fixed — #168 (`POST /auth/refresh` + web interceptor; mobile has the same gap mid-session) |
| 30 | An ordered request with no PO cannot be cancelled: withdraw accepts only draft/submitted, and there is no cancel for ordered requests, so a mistaken approval keeps counting against the budget | stale spend stays committed | fixed — #177 merged + deployed 2026-10-18: the requester or an owner can withdraw an ordered request while no purchase order other than a cancelled one references it (409 `purchase_order_exists` otherwise), releasing its committed budget |
| 31 | Arabic UI shows raw i18n keys (`ingestion.dashboard.channels.manageAction`, `ingestion.emailLog.matchMethods.rfq_reply`) and English server-generated text: price-anomaly alerts ("Price anomaly: X from Y") | English on Arabic screens and in the supplier's inbox | not yet raised — RTL walkthrough 2026-10-18 |
| 32 | Units stay English in Arabic: "10 عبوة × 1 kilogram", "(pack of 25 kilogram)" on PO lines, "/ kilogram" in product intelligence | visible on compare, basket split and PO screens | not yet raised |
| 33 | Quote review shows the shared catalogue's English name as the matched product ("Eggs tray of 30") instead of the workspace's Arabic name | wrong language on the review screen | not yet raised |
| 34 | Dates and money formats in Arabic: date fields are MM/DD/YYYY (10/22/2026); guardrail card shows "EGP 30000.0000"; basket-split saving banner "EGP 450.00" in Latin digits beside «ج.م» amounts; currency placeholders suggest USD/GBP and Record Outcome defaults to GBP | inconsistent on camera; GBP wrong for an EGP tenant | not yet raised |
| 35 | RTL layout: the guardrail "enabled" toggle label is clipped to «ل»; RFQ draft edit shows the raw quantity "120.000000", clipped to "0.000000" in the narrow field | looks broken on camera | not yet raised |
| 36 | Technical details on user screens: email log lists suppliers as «المورد #<uuid>»; quote review shows `azure_di`, the model id, "Supplier Name" and `application/pdf` | noise on camera | not yet raised |
| 37 | RFQ emails (subject and body) follow the tenant's `default_locale`, which is `en` for «مطاعم سند» and cannot be changed in the app after signup (only `PATCH /tenant`); Egyptian suppliers get an English email | supplier-facing language wrong on camera | fixed — #165 merged + deployed 2026-10-18 (owner-only workspace language in Settings, audited); demo tenant set to `ar` |
| 38 | A guardrail-prepared request looks like any draft: no "prepared automatically by guardrail" marker on the request, and no cost centre (the guardrail only has a default branch) | the video's guardrail moment is invisible on screen | fixed — #165 merged + deployed 2026-10-18: «أعدّته الضوابط تلقائيًا» banner on the request, owner email, guardrail default cost centre (demo guardrail set to «المطبخ — المعادي» 2026-10-18) |
| 39 | The RFQ email states each quantity in the base unit: 12 sacks of 25 kg read «١٢ كجم (عبوة ١ × ٢٥ كجم)», 8 tins of oil «٨ لتر» | suppliers misquote; visible on camera | fixed — #180 merged 2026-10-18: «١٢ عبوة (٢٥ كجم للعبوة) — ٣٠٠ كجم», «٨٠ كجم» for 1-unit packs (round-4 dry run) |
| 40 | Typing 22/10/2026 into an Arabic date picker gives 02/10/2026 (the first keystroke was wiped); the calendar works | wrong needed-by dates | fixed — #181 merged 2026-10-18 (all mat-datepicker screens) |
| 41 | Quote review shows a flagged stated total as raw JSON: `{"amount":"24220.00","currency":"EGP"}` | on camera in the review scene | not yet raised (round-4 dry run) |
| 42 | The WhatsApp-photo quote's «صالح حتى 29/10/2026» is not read into the expiry date (the PDF quotes' expiry is) | expiry empty on the photo quote | not yet raised (round-4 dry run) |
| 43 | The guardrail drafts only from one reply that covers every RFQ line, so a round split across suppliers (oil/rice from two, onions from a third) never fires | by design; the storyboard's guardrail scene needs one full quote | decided 2026-10-18: in the recorded round الأمانة's photo quote covers all three items and the guardrail drafts from it (fired in the dry run) |

Round 1 (2026-10-16 → 18): both quotes authorized, 10 matches confirmed, Smart Compare, request prepared at EGP 56,425 per pack, submitted, approved, **PO-000001 created** and the basket split run (saves EGP 450). The earlier request `6f460785-…` (wrong estimate 6,135.58, approved before fix 18, no PO) was set to `withdrawn` directly in the database on 2026-10-18 so it no longer counts against the Maadi budget (the app has no way to do this — finding 30); do not reuse it. Step by step: [`round-1/README.md`](round-1/README.md).

Workaround used for round 1 only: the RFQ date was corrected in the browser before sending (finding 7); the recorded demo cycle waits for the real fix.

Products were entered through the New Product form because of #1; the CSV import is re-tested after the fix
(same file — every row should be reported as a duplicate and skipped).

## Principles

1. **One clean tenant per vertical** on hosted (`procurepilot.iron-sys.com`), never the shared test
   account (it is full of validation leftovers). Restaurants first; retail and hospitality get their own
   tenant from the same template **only when outreach targets them** — every demo tenant has to be
   kept clean and current, so none is built speculatively.
2. **Entered through the real UI**, not SQL. The build doubles as the full end-to-end hosted walkthrough
   required before recording and before the first pilot (`live-walkthrough` rule: a chunk's tests passing
   does not prove the chain works).
3. **No backdated history.** The savings report is filled by running 3 real RFQ cycles in the days before
   recording. Every number in the video comes from the tenant as it stands (video honesty rule).
4. **Fictional company, realistic data.** Real Egyptian product names and current wholesale price levels;
   fictional company and supplier names. Check no real Egyptian chain uses the name before recording.
5. **No mail to real businesses.** Every supplier email is a mailbox we control — RFQs really go out via
   Mailgun, and quotes really come back through inbound email.
6. **Accounts are created by the user.** Claude does not create accounts or type passwords on hosted
   (safety rule): the user creates the workspace and signs in in Claude's browser pane, then Claude
   continues.

## Tenant 1 — restaurants

**مطاعم سَنَد — Sanad Kitchens** (fictional): casual Egyptian food chain (koshari, grills, sandwiches),
3 branches in Cairo/Giza. Home currency **EGP**, language Arabic.

| Branch | Cost centres | Monthly budget (EGP) |
|---|---|---|
| مدينة نصر — Nasr City | المطبخ (Kitchen) · التغليف (Packaging) · النظافة (Cleaning) | 450,000 |
| المعادي — Maadi | same | 380,000 |
| الشيخ زايد — Sheikh Zayed | same | 320,000 |

### People

| Role | Who | Used in the video for |
|---|---|---|
| Owner / approver | user's own account | approving on the phone |
| Purchasing officer «مسؤول المشتريات» | second account, user-controlled inbox | building and sending the RFQ |
| Branch manager, Maadi | optional third account | low-stock report from the phone |

### Suppliers (fictional)

| Supplier | Category | Quote channel in the demo |
|---|---|---|
| الحاج سيد للخضار — El-Hag Sayed Produce (Obour market) | vegetables | WhatsApp photo, forwarded |
| النور للمواد الغذائية — El-Nour Foodstuffs | dry goods, oil | email PDF, EGP with «ج.م» |
| دواجن الفيروز — El-Fayrouz Poultry | chicken, eggs | email PDF |
| باك مصر — Pack Misr | packaging, cleaning | email PDF |

Plus one more dry-goods supplier (الأمانة — El-Amana Trading) so the main RFQ has 3 competing quotes.

### Catalogue (~30 items, approximate wholesale prices, October 2026)

`src` = price source: **obour** = Obour wholesale market reports 14 Oct 2026; **retail−15%** = retail
price level minus a typical wholesale margin; **est.** = estimate, verify before recording.

| Item | Unit | ~EGP | src |
|---|---|---|---|
| طماطم — tomatoes | kg | 10 | obour |
| بطاطس — potatoes | kg | 17 | obour |
| بصل أبيض — white onions | kg | 18 | obour |
| ثوم — garlic | kg | 60 | est. |
| ليمون — lemons | kg | 30 | est. |
| خيار — cucumbers | kg | 15 | est. |
| فلفل رومي — bell peppers | kg | 30 | est. |
| خس — lettuce | head | 10 | est. |
| أرز مصري — Egyptian rice | 25 kg sack | 950 | retail−15% |
| مكرونة — macaroni | 20 kg carton | 560 | est. |
| عدس بجبة — brown lentils | kg | 70 | est. |
| حمص — chickpeas | kg | 75 | est. |
| دقيق — flour | 25 kg sack | 600 | est. |
| سكر — sugar | 25 kg sack | 900 | retail−15% |
| زيت عباد الشمس — sunflower oil | 18 L tin | 1,700 | retail−15% |
| صلصة طماطم — tomato paste | 4 kg tin | 220 | est. |
| ملح — salt | 25 kg sack | 150 | est. |
| خل — vinegar | 20 L | 260 | est. |
| بهارات كشري — koshari spice mix | kg | 180 | est. |
| فراخ مجمدة — whole chicken | kg | 190 | retail−20% |
| صدور فراخ — chicken breast | kg | 260 | est. |
| بيض — eggs | tray of 30 | 175 | est. |
| لحم بقري — beef | kg | 420 | est. |
| جبنة بيضاء — white cheese | kg | 110 | est. |
| عيش شامي — pita bread | pack of 100 | 250 | est. |
| علب كشري ألومنيوم — foil takeaway boxes | carton of 500 | 900 | est. |
| أكياس تيك أواي — takeaway bags | carton of 1,000 | 650 | est. |
| أكواب ورقية — paper cups | carton of 1,000 | 700 | est. |
| صابون أطباق — dish soap | 20 L | 450 | est. |
| كلور — bleach | 20 L | 300 | est. |

Loaded by **CSV import** (spec 002) — itself part of the walkthrough.

### Scenario (matches the video storyboard)

1. **Before recording — 3 warm-up cycles** over several days (vegetables, poultry, packaging): RFQ →
   quotes → compare → approve → PO, so the savings report has real history.
2. **Recorded cycle** — Maadi branch:
   - low stock reported from the phone: oil, rice, onions;
   - RFQ built and sent to 3 suppliers in one click;
   - quotes arrive: email PDF (with «ج.م»), forwarded WhatsApp photo, second email PDF;
   - extracted → line-by-line comparison → saving shown in EGP;
   - guardrail drafts the purchase request → owner approves on the phone → PO generated on web →
     savings report.

Quote documents are generated like the PP-3 fixtures (`../test-fixtures/egypt-quotes/`) and sent from
the supplier mailboxes.

## Later tenants (template, not built)

| Vertical | Company | Differences |
|---|---|---|
| Retail | mini-market chain, 4 branches | FMCG catalogue with pack sizes, more suppliers, POS low-stock (spec 015) |
| Hospitality | hotel F&B + housekeeping | mixed food / linen / amenities, central store, stricter approval chain |

## Mailboxes (decided 2026-10-15)

Plus-addresses on the owner's Gmail — `<owner-gmail>+pp-<tag>@gmail.com` (the real address is kept
out of the repo):

| Tag | Used by |
|---|---|
| `pp-sayed` | El-Hag Sayed Produce |
| `pp-nour` | El-Nour Foodstuffs |
| `pp-amana` | El-Amana Trading |
| `pp-fayrouz` | El-Fayrouz Poultry |
| `pp-packmisr` | Pack Misr |
| `pp-owner` | owner account of the demo workspace (invitation minted 2026-10-15, valid to 2026-10-22) |
| `pp-buyer` | purchasing officer account |
| `pp-maadi` | Maadi branch manager account (optional) |

**Quote replies come from the base Gmail address** (Gmail replies from the base address unless a
"Send mail as" alias is configured). Inbound matching today checks sender-address history *before*
the RFQ thread (`ingestion/orchestrator.py`: the RFQ recipient's supplier is only used when
`match_supplier` found nothing), so with one shared sender every quote after the first would be
credited to the first supplier. **Fix in progress in a separate session** (RFQ reply wins) — it must
be merged and deployed before the first supplier quote is sent. **Done 2026-10-15 as a safety net:** all 5 supplier tags are Gmail "Send mail as" aliases
(named in Arabic), and Gmail is set to *reply from the same address the message was sent to* — so a reply
to an RFQ sent to `+pp-nour` goes out from `+pp-nour` automatically. Owner address stays the default.
Leave the suppliers' `email_domains` empty (all are `gmail.com`).

## Remaining steps

Round 1 step by step, with screenshots: [`round-1/README.md`](round-1/README.md).

Rounds 2 and 3 step by step: [`round-2-3/README.md`](round-2-3/README.md).
Round 4, the dry run of the recorded round (WhatsApp-photo quote, guardrail): [`round-4/README.md`](round-4/README.md).

The workspace and both accounts already exist — do **not** create another tenant, and PO-000001 to
PO-000004 exist — do not repeat rounds 1–3's requests or POs. Remaining work, with owners and status, is tracked in
[`../video/production-tracker.md`](../video/production-tracker.md): decide the savings baseline (finding 23); the guardrail; switch the tenant to
Arabic and walk the flow RTL; then the recorded round.
# Demo tenants — plan and dataset (PP-5 / G-1)

Status 2026-10-15: **draft for review.** Nothing entered on hosted yet.

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
be merged and deployed before the first supplier quote is sent. Fallback if it is not: add each
supplier tag as a Gmail "Send mail as" alias (Gmail opens that dialog as a popup, so the user does it).
Leave the suppliers' `email_domains` empty (all are `gmail.com`).

## Still needed

- **User creates the workspace** with the minted invitation (`pp-owner`), currency EGP, and signs in in
  Claude's browser pane — Claude does not create accounts or type passwords on hosted.

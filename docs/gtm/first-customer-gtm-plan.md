# First Customer Plan — ProcurePilot ($0 budget)

Goal: land one real, named pilot customer without spending money, using founder time,
credibility, and the product's own existing strengths as the entire budget.

Last revised: 2026-10-14 — checked against the shipped code; demo claims corrected, pilot
environment, baseline, qualification, exit and support added.

## Why this ICP and market

No ad spend means no room to test multiple segments at once — the pitch, channel, and
language all need to match one buyer. The product's own shape already points at the answer:

- `branch` / `cost_centre` / `budget` (organisation model) were built for businesses with
  **multiple locations**, with approvals routed per branch and cost centre.
- `rfq`, `rfq_response`, catalogue/supplier matching, and auto-preparation guardrails solve
  the exact pain of **collecting and comparing supplier quotes manually**.
- Full Arabic + RTL support (`packages/i18n`) is a real, already-built edge in the
  **Egypt / MENA** market that an English-only competitor doesn't have. EGP (and SAR/AED) are
  *supported* — every amount stores its currency — but not yet *native*: defaults, extraction
  fallbacks and mobile formatting still assume USD/GBP (see the currency gaps below).

**Starting wedge:** multi-location F&B / retail / hospitality businesses in Egypt/MENA
currently running purchasing over WhatsApp, Excel, and phone calls with suppliers. Broaden
after customer #1 — this is a starting point, not a permanent restriction.

### Known fit gaps for this ICP (say them honestly, plan around them)

| Gap | Reality in the product today | Pilot workaround |
|---|---|---|
| Suppliers quote over **WhatsApp** | Quotes enter by email (Mailgun inbound) or document upload. No WhatsApp channel. | Supplier quote (PDF/photo/screenshot) is forwarded to the tenant's inbound email address or uploaded; extraction handles the rest. Track friction as a `from-pilot` gap. |
| **POS integration** | Square only — not available in Egypt. | Not used in the pilot. Stock and low-stock come from the mobile low-stock reports instead. |
| **Accounting integration** | Xero and QuickBooks only; Egyptian SMEs mostly use Odoo, local software, or Excel. | Not used in the pilot. Exports (CSV) cover the hand-off to their accountant. |
| **PO approval on mobile** | Mobile approves **purchase requests**; purchase orders are drafted, edited and cancelled on web only. | Demo and pilot use mobile for request approval; PO is generated on web. |

Do not pitch Square/Xero/QuickBooks to this ICP. Any of these gaps that blocks a real pilot
becomes a product task (see "How work from this plan is tracked").

### Currency gaps — Egypt (verified in code, 2026-10-14)

| # | Gap | Where | Pilot impact | Action |
|---|---|---|---|---|
| C1 | The tenant currency already exists (`tenant.currency`, required at sign-up, returned by `/me`, already the default in the budget and threshold-rule forms) — but several web forms ignore it and fall back to **USD** | `order-create.component.ts:81`, `guardrails.component.ts:61`, quotation-review fallbacks | Buyer must switch to EGP on every PO; one miss puts a USD PO against an EGP budget | **Product task, before pilot** — wire the existing `tenant.currency` into the remaining forms; no new setting or schema |
| C2 | Extraction falls back to **GBP** when a quote's currency is unclear; Azure DI fallback only recognises £/$/€ (not ج.م / جنيه / LE) and hard-codes USD on one path | `structured_parse.py:67`, `azure_di.py:77,153,281`; landed cost defaults GBP (`landed_cost/service.py:89`) | Egyptian quotes can be stored in the wrong currency silently | **Test first** with 5 real Egyptian quotes (incl. Arabic-Indic digits ١٢٣); fix the fallback: recognise Egyptian markers, and route any still-unresolved currency to **human review** — never default it to the tenant currency (project ingestion rule: an unresolved currency is an error, not a fallback) |
| C3 | Mobile shows raw amounts (`EGP 12500.000000`) — no grouping, no locale formatting | `approval_queue_screen.dart:102`, `request_detail_screen.dart:104-148` | It is the closing shot of the demo video | **Product task, before demo video** — locale-aware money formatting on mobile |
| C4 | No FX — no exchange rates anywhere; cross-currency arithmetic is refused by design | `money.ts` (`assertSameCurrency`) | Imported items quoted in USD can't be compared with EGP quotes; EGP volatility can erode a week-0 baseline before the pilot ends | **Workaround:** pilot limited to EGP-quoting suppliers; record baseline and end-of-pilot prices in EGP. Product task after pilot |
| C5 | A VAT rate exists (`quotation_line.vat_rate`, used by landed cost) but there is no way to record whether a quoted price **includes** VAT | quotation schema | Egyptian VAT is 14% and suppliers mix inclusive/exclusive prices; savings can be overstated | **Workaround:** ask pilot suppliers to quote ex-VAT. Product task after pilot |

### Before expanding to the GCC

Not blocking customer #1 in Egypt, but must be closed before the first Gulf prospect:

| # | Gap | Where |
|---|---|---|
| G1 | Two divergent hard-coded currency lists: supplier form has only GBP/EUR/USD/SAR/AED/EGP (no QAR, KWD, BHD, OMR); quotation review has a different, longer list | `supplier-form.component.ts:97`, `quotation-review.component.ts:207` → one shared list |
| G2 | **3-decimal currencies** (KWD, BHD, OMR) are rounded/displayed to 2 decimals in ~23 places, including PO totals, quote line totals, basket-split savings and analyst spend/savings answers | e.g. `order-create.component.html:183`, `quotation-lines.component.ts:149`, `basket-split.component.ts:404`, `analyst/retrieval.py:335` → use the currency's own minor units (the shared `formatMoney` already does) |
| G3 | Extraction doesn't recognise ر.س / د.إ / د.ك / ر.ق / ر.ع — falls through to GBP | same files as C2 |
| G4 | VAT differs per country (KSA 15%, UAE 5%, Bahrain 10%, Oman 5%, Qatar/Kuwait none) — C5 matters more here | quotation schema |
| G5 | KSA mandatory e-invoicing (ZATCA Fatoora) — not a PO concern, but required once the accounting side matters for a Saudi customer | — |

FX (C4) matters less in the GCC: SAR, AED, QAR, BHD and OMR are USD-pegged, KWD is
basket-pegged.

---

## Phase 0 — Build the $0 proof assets (this week)

1. **Demo tenant on hosted.** A dedicated tenant — not the shared test account — with
   realistic Arabic supplier names, an F&B catalogue (~30 items), 2–3 branches, EGP prices,
   and one RFQ ready to send. Every demo and the video run from this tenant. Prospects must
   never see test leftovers.
2. **3-minute demo video + 60-second vertical cut** (Arabic UI, Arabic on-screen text + music, no voice-over — full spec in `docs/gtm/video/README.md`), recorded with Loom (available on
   the Atlassian site) or OBS. The walkthrough must match what the product actually does:
   - a buyer builds an RFQ (from a request or by hand) and **sends it to several suppliers
     with one click** — sending is always a human action;
   - supplier quotes come back (email or upload) and are extracted;
   - the system compares them line by line and shows the saving;
   - with a guardrail switched on (off by default), the winning response is **auto-prepared
     as a draft purchase request** — prepared, never purchased;
   - a manager **approves the purchase request on their phone**;
   - the purchase order is generated from the approved request (web).

   This is the only "ad" you need — send it instead of cold-pitching. Record it only after
   C3 (mobile money formatting) is fixed and the demo tenant's forms default to EGP (C1).
3. **One pitch line**, money-first, not features-first:
   *"إنت بتشتري بالطريقة دي أساساً — إحنا بس بنوريك قد إيه بتوفر وبنخليك متابع من موبايلك."*
   ("You already buy this way — we just show you how much you save, and keep you on top of it
   from your phone.")
4. **One-pager** (Google Slides / Canva free tier, Arabic + English): "before ProcurePilot"
   (WhatsApp thread + Excel) vs. "after" (RFQ → compare → approve → PO).

## Phase 1 — Find 20 warm conversations (weeks 1–2)

With no budget, the only real channel is your own credibility network, worked deliberately:

- **Personal network audit** — anyone you know who owns/runs a restaurant chain, retail
  chain, pharmacy chain, or distributor with 2+ branches in Egypt. Ask for 10 minutes and an
  honest reaction, not a sale.
- **Egyptian founder/SME communities** (free to join, dense with this ICP): Flat6Labs / AUC
  Venture Lab alumni networks, Rise Up community, F&B-owner and retail-franchise WhatsApp/
  Facebook groups, procurement/supply-chain LinkedIn groups with Egyptian members.
- **LinkedIn, manually, no ads** — search "owner" OR "operations manager" + "restaurant
  chain"/"retail chain" + Egypt. Send a short, personalized DM with the demo video attached.
  Lead with a diagnostic question ("How are you currently collecting quotes from suppliers
  across branches?"), not a pitch.
- **Show up in person** — trade associations, supplier expos, coworking-space demo days.
  In-person beats cold digital at this stage and costs nothing but time.

Target: 20 real conversations, not 20 messages sent into silence.

### Tracking the conversations — the sales pipeline

A **pipeline** is a list of prospects where each prospect moves through stages. It answers
three questions every week: how many real conversations have I had, who owes whom the next
step, and who is close to a pilot. It is separate from the product task list because a
prospect is not a task — it is never "done" by you; it moves forward or drops out.

**One record per company** (not per message, not per person). Fields:

| Field | Example |
|---|---|
| Company | "Example Bakery Co." |
| Contact name + role | "Ahmed — operations manager" |
| Branches | 6 |
| City | Cairo |
| Source | Personal network / community / LinkedIn / in person |
| Stage | see below |
| Next step | "Send demo video + book 15 min call" |
| Next step date | 2026-10-21 |
| Notes | Pain heard, current tools, objections — one line per touch |

**Stages** — a prospect is only moved forward when the exit condition actually happened:

| Stage | Meaning — moved here when… |
|---|---|
| Target | Identified, fits the ICP, not contacted yet |
| Contacted | First message sent or introduction made |
| Talked | A real two-way conversation happened (call, meeting, or substantive chat). **This is the stage the "20 conversations" target counts.** |
| Qualified | Meets all five pilot-qualification criteria below |
| Pilot offered | Pilot proposed with the agreement draft |
| Pilot | Agreement accepted, onboarding scheduled |
| Not now | Dropped out at any stage — reason recorded (no pain, no time, wrong size, went silent after 2 follow-ups) |

**Weekly review (15 minutes):** count records at Talked or beyond; work every record whose
next-step date is today or past; move silent ones (2 follow-ups, no reply) to Not now.

**Where it lives:** a separate Jira space built from the **Sales pipeline** template on the
`yasser-hosny.atlassian.net` site — not the PP product space. One work item per company;
stages are the workflow statuses (board columns); next-step date is the due date. A Google
Sheet with the same columns is an acceptable fallback.

### Pilot qualification — offer a pilot only if all are true

- 2+ branches (or 1 branch with a central kitchen/warehouse).
- Repeat purchasing from 5+ suppliers, with at least weekly orders.
- Quotes are collected manually today (WhatsApp, phone, Excel).
- One named decision-maker who will attend two 30-minute check-ins (end of week 1 and day 14).
- Willing to share last month's prices for 10–20 key items as a baseline.

## Phase 2 — Convert one conversation into a pilot (weeks 2–4)

### Prerequisite: a pilot environment (before the first real customer record)

The hosted app (`procurepilot.iron-sys.com`) runs on the **test/staging** database, which the
test suite also runs against. It is fine for demos; it is **not** acceptable for a real
customer's suppliers, prices and spend. Before onboarding the pilot, stand up one of:

- **Self-hosted production** per `docs/operations/self-hosted-deployment-plan.md` (Phases
  1–2 are ops work, no code changes) — $0, but you own uptime and backups; or
- **A separate hosted production project** — costs money once beyond free-tier limits, which
  conflicts with the $0 constraint; decide explicitly.

Either way, the environment needs: automated daily database backups with one tested restore,
migrations applied as an explicit deploy step, and secrets separate from staging.

Product prerequisites before the first real customer record: C1 shipped, C2 tested against
real Egyptian quotes (and the GBP fallback replaced by review). Security and verification
before any real data, whichever environment D-1 picks: database and admin consoles not
exposed publicly, OS/host hardening, `pnpm test:isolation` green against that environment,
and a full live walkthrough on it. The pilot agreement states the C4/C5
workarounds: EGP-quoting suppliers only, prices compared ex-VAT.

### The pilot

- Offer a **free 2-week (14-day) pilot** to the first 1–2 qualified prospects — in exchange for
  two check-ins (end of week 1 and day 14), permission to use their name/logo as a case study, and a testimonial if
  it works.
- **Pilot agreement** (one page, Arabic + English) covering: duration and end date, the
  success metric and baseline, what happens on day 14 (see below), data ownership (theirs),
  confidentiality of supplier pricing, data deletion/export on exit, and a data-protection
  clause consistent with Egypt's Personal Data Protection Law (Law 151/2020).
- **Week 0 — set up and record the baseline** before the 14 days start (the clock starts
  after onboarding and the first live RFQ, so the customer gets 14 full days of real use): current quote turnaround
  (request → all quotes received), and last month's unit prices for the 10–20 key items.
  Without a baseline the savings report has nothing to prove against.
- **White-glove the onboarding yourself** — load their suppliers and catalogue (CSV import /
  by hand, since no POS or accounting integration applies), set up branches and approvers,
  and run their first RFQ with them live on a call. Agree how WhatsApp quotes get in (forward
  to the inbound address, or upload). You're selling outcome + your own hands-on effort,
  which a future competitor with more funding can't easily out-discount.
- **Set one concrete success metric up front** (e.g. "cut quote turnaround from 3 days to
  1" or "save X% on the baseline items bought during the pilot", measured against the week-0
  baseline — a monthly-spend figure can't be measured in 2 weeks). That
  number becomes the case study and the opening line for customer #2.
- **Support:** one WhatsApp group with the pilot's decision-maker and buyer; response within
  4 working hours; anything blocking is fixed or worked around within 2 working days.

### Day 14 — how the pilot ends

Agree this in the pilot agreement, not on day 13:

- A named monthly price (or price range) for continuing after the pilot.
- A go/no-go review on the success metric in the last check-in.
- If they don't continue: full data export, then deletion from the pilot environment.

## How work from this plan is tracked

- **Non-code work** (assets, scripts, agreements, onboarding steps) → Jira project **PP**.
- **Sales conversations** → the pipeline above, not PP.
- **Product gaps found in demos or the pilot** → a PP task labelled `from-demo` /
  `from-pilot`. If it needs code, it becomes a Speckit spec and goes through the normal code
  flow; the PP task links to the PR. Code tasks themselves are never duplicated into Jira.

## Why this works with no money

Zero-budget acquisition at this stage isn't marketing — it's founder-led sales, trading
founder time and specificity for ad spend. One well-run, named pilot beats broad outreach,
and it's the asset you need before customer #2 gets any easier to close.

---

## Next possible steps (not yet drafted)

- Outreach DM script (Arabic + English)
- One-pager full copy
- Pilot agreement + success-metric/baseline template
- Post-pilot price point

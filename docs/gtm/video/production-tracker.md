# Demo video — production tracker (PP-6, depends on PP-5)

What is left before the demo video can be recorded and edited. Spec and decisions live in
[`README.md`](README.md). The demo tenant and its bug findings live in
[`../demo-tenant/README.md`](../demo-tenant/README.md) (PR #82 until merged).

**Rule:** the video shows one complete, honest run through the real product on hosted, in Arabic,
with every number on screen taken from the demo tenant's real savings report. Recording starts
only when stages 1 and 2 are done.

Owners: **Orch** = Demo generation session (Claude, orchestrator) · **Lane** = coding session started
from a fix card · **User** = Dr. Yasser Hosny.

Status as of 2026-10-16.

## Stage 1 — Product flow works end to end (critical path)

| # | Item | Owner | Status | Depends on |
|---|---|---|---|---|
| 1.1 | Fix DD/MM/YYYY quote dates refusing Egyptian quotes (finding 14), then re-extract the 2 round-1 quotations | Lane → Orch | in progress (fix session running) | — |
| 1.2 | First live run of the rest of the flow: compare quotes → basket split → guardrail drafts the purchase request → approve on phone → PO generated → savings report | Orch | not started | 1.1 |
| 1.3 | Fix whatever 1.2 finds (expect 2–4 fix cycles at the rate rounds have found Egypt-specific bugs) | Lane → Orch | — | 1.2 |
| 1.4 | Switch the demo tenant to Arabic and walk the whole flow RTL; fix layout/translation gaps | Orch → Lane | not started | 1.2 |
| 1.5 | On-camera clean-up: Home page labels shipped modules "Upcoming (Chunk 4.x)" (finding 5); a saved RFQ draft cannot be sent from History (finding 8); drafts show a "Sent Date" and Save gives no confirmation (finding 9); duplicate "Kilogram" unit (finding 3) | Lane | to raise | — |

Done in stage 1 so far: database pooler fix (#87), RFQ-reply supplier matching (#84), UTC date
shift (#88), supplier-ready Arabic RFQ email + i18n in the API image (#89), Arabic attachment names +
no silent email loss (#90), python-jose advisory allowlist (#86). All merged and deployed 2026-10-15/16.

## Stage 2 — Demo data

| # | Item | Owner | Status | Depends on |
|---|---|---|---|---|
| 2.1 | Round 1 (dry goods: النور + الأمانة) — finish compare → approve → PO | Orch | quotes ingested + matched; extraction blocked on 1.1 | 1.1 |
| 2.2 | Round 2 (vegetables: الحاج سيد) and round 3 (poultry/packaging: الفيروز, باك مصر), so the savings report has real history | Orch (+ User OK for each Gmail reply send) | not started | 1.2, 1.3 |
| 2.3 | Phone app as a web build at 390×844 against hosted, for the low-stock report and the approval; confirm it signs in to the demo tenant | Orch | not checked | — |
| 2.4 | WhatsApp-photo quote for the recorded round (photo of a printed quote, forwarded by email) | Orch | not prepared | 1.1 |
| 2.5 | Recorded round dry run (Maadi low stock: oil, rice, onions → RFQ to 3 suppliers → quotes incl. «ج.م» and a photo → compare → guardrail → phone approval → PO → savings) | Orch | not started | 1.x, 2.1–2.4 |

Accounts and setup already done: workspace «مطاعم سند» (EGP, Egypt VAT), owner `+pp-owner` and
buyer `+pp-buyer` accounts, 3 branches, 6 cost centres, 3 budgets, 5 suppliers with Gmail
plus-address send-as aliases, 30 products, inbound email address.

## Stage 3 — Video production

| # | Item | Owner | Status | Depends on |
|---|---|---|---|---|
| 3.1 | Opening shot: free kitchen/storeroom stock footage (Pexels/Pixabay) | Orch (User OK to download) | not started | — |
| 3.2 | Motion-graphics boards: Arabic text cards, animated savings counter, «وصل إشعار للمدير» card, phone frame | Orch | not started | — |
| 3.3 | Record the screencast: web 1920×1080, phone 390×844, scene by scene per the storyboard | Orch | blocked | stages 1–2 |
| 3.4 | Edit on the music (Antalya Beaches) with the rendered outro at 2:50.25 → 3-minute cut | Orch | blocked | 3.1–3.3 |
| 3.5 | 60-second vertical cut (outro at 0:51.34) | Orch | blocked | 3.4 |
| 3.6 | English versions (swap text cards; English outros already rendered) | Orch | blocked | 3.4, 3.5 |
| 3.7 | User review of the recorded run, then of the cuts | User | — | 3.3, 3.6 |
| ✅ | Logo sting, end cards, music, sound cues, Arabic + English outros, founder title | — | done (#79, #80) | — |

## Not blocking the video

- Lookups: KSA/SAR/EUR + tax rates + region filter; safe GCC/Arabic currency detection; 3-decimal
  currencies end to end (`../demo-tenant/lookups-review-2026-10-15.md`). The demo is EGP-only.
- Migrating off python-jose (four advisories allowlisted).

## User inputs needed along the way

1. Start each fix card when it appears (suggestion cards above the message box).
2. OK each batch of supplier replies sent from Gmail.
3. OK the stock-footage download (file, source, size given at the time).
4. Review the recorded run before editing, and the final cuts.

## Log

| Date | Update |
|---|---|
| 2026-10-16 | Tracker created. Stage 1: #84/#86/#87/#88/#89/#90 merged and deployed; round 1 RFQ sent, both supplier quotes ingested and matched; extraction blocked on DD/MM dates (1.1 in progress). |

# Demo video — production tracker (PP-6, depends on PP-5)

What is left before the demo video can be recorded and edited. Spec and decisions live in
[`README.md`](README.md). The demo tenant and its bug findings live in
[`../demo-tenant/README.md`](../demo-tenant/README.md).

**Rule:** the video shows one complete, honest run through the real product on hosted, in Arabic,
with every number on screen taken from the demo tenant's real savings report. Recording starts
only when stages 1 and 2 are done.

Owners: **Orch** = Demo generation session (Claude, orchestrator) · **Lane** = coding session started
from a fix card · **User** = Dr. Yasser Hosny.

Status as of 2026-10-22. **Style:** every cut follows [`motion-style.md`](motion-style.md) (owner direction 2026-10-22).

## Stage 1 — Product flow works end to end (critical path)

| # | Item | Owner | Status | Depends on |
|---|---|---|---|---|
| 1.1 | Fix DD/MM/YYYY quote dates refusing Egyptian quotes (finding 14), then re-extract the 2 round-1 quotations | Lane → Orch | ✅ done — #96 merged + deployed, migration applied; both quotes re-read with date 2026-10-16 and EGP | — |
| 1.1b | Arabic RTL quote tables collapse into one line (finding 15): quantity from one row, price from another; one quote auto-accepted with a wrong 84,000 EGP line | Lane → Orch | ✅ done — #100 merged + deployed (migration applied); both round-1 quotes re-read on hosted with real Azure: 5 lines each, totals reconcile (النور 56,425; الأمانة 56,925 incl. 250 delivery) | 1.1 |
| 1.1c | Authorizing a quote whose supplier-name field scored low (68%) is impossible: `low_confidence_unresolved`, no control to confirm the field, generic error (finding 16) | Lane → Orch | ✅ done — #104 merged + deployed; both quotes authorized live | 1.1b |
| 1.2 | First live run of the rest of the flow: compare quotes → basket split → guardrail drafts the purchase request → approve on phone → PO generated → savings report | Orch | mostly done 2026-10-18: request → approval → **PO-000001** ([walkthrough](../demo-tenant/round-1/README.md)); basket split ran and renders (split saves EGP 450, #131/#141); **phone approval works** (request 62f27908 approved from the Flutter web build, 2026-10-18; screen labels fixed in #146/#147). guardrail auto-prepare **fired on hosted** 2026-10-18 (draft request 9e657ae3 from الحاج سيد's quote, [record](../demo-tenant/rtl-walkthrough-2026-10-18.md)). **Left:** savings baseline = last PO price (decided 2026-10-18, fix in progress); findings 37–38 for the guardrail scene | 1.3 |
| 1.3 | Fix whatever 1.2 finds (expect 2–4 fix cycles at the rate rounds have found Egypt-specific bugs) | Lane → Orch | ongoing — findings 1–21 fixed except 20 (partly: hosted on stub embedding); 6 fixed by #133 (invitation emails); 22 (no PO → purchase outcome path) and 23 (savings baseline) open; plus a security review (#137, #138, #142, #145 applied on hosted) and Codex post-merge follow-ups in progress | 1.2 |
| 1.4 | Switch the demo tenant to Arabic and walk the whole flow RTL; fix layout/translation gaps | Orch → Lane | walked 2026-10-18 ([record](../demo-tenant/rtl-walkthrough-2026-10-18.md)): layout mirrors correctly; findings 31–37 handed to a fix session; tenant default language still `en` (finding 37) | 1.2 |
| 1.5 | ✅ done — #103 merged + deployed (migrations applied). On-camera clean-up: Home page labels shipped modules "Upcoming (Chunk 4.x)" (finding 5); a saved RFQ draft cannot be sent from History (finding 8); drafts show a "Sent Date" and Save gives no confirmation (finding 9); duplicate "Kilogram" unit (finding 3); raw JSON pack in import preview (finding 4); wrong import counter (finding 13) | Lane | — | — |

Done in stage 1 so far: database pooler fix (#87), RFQ-reply supplier matching (#84), UTC date
shift (#88), supplier-ready Arabic RFQ email + i18n in the API image (#89), Arabic attachment names +
no silent email loss (#90), python-jose advisory allowlist (#86), DD/MM dates (#96), test role leak through the pooler (#97). All merged; app changes deployed 2026-10-15/17. CI speed-ups (#94/#95/#98) merged.

## Stage 2 — Demo data

| # | Item | Owner | Status | Depends on |
|---|---|---|---|---|
| 2.1 | Round 1 (dry goods: النور + الأمانة) — finish compare → approve → PO | Orch | ✅ PO-000001 (draft, EGP 56,425, النور) 2026-10-18; basket split run (job 2511bb47, EGP 55,975, saves 450) | 1.3 |
| 2.2 | Round 2 (vegetables: الحاج سيد) and round 3 (poultry/packaging: الفيروز, باك مصر), so the savings report has real history | Orch (+ User OK for each Gmail reply send) | ✅ 2026-10-18: three quotes authorized, 11 matches confirmed, requests approved on the phone, **PO-000002 / 000003 / 000004** (EGP 4,720 / 20,770 / 6,880) — [walkthrough](../demo-tenant/round-2-3/README.md); findings 24–29 | 1.2, 1.3 |
| 2.3 | Phone app as a web build at 390×844 against hosted, for the low-stock report and the approval; confirm it signs in to the demo tenant | Orch | ✅ for approvals: signs in to the demo tenant and approved four requests (62f27908, rounds 2–3) on 2026-10-18; the web build signs out on reload (finding 28). Low-stock report not yet tried | — |
| 2.4 | WhatsApp-photo quote for the recorded round (photo of a printed quote, forwarded by email) | Orch | ✅ 2026-10-18: phone-style photo of a stamped «الأمانة للتجارة» quote ([sources](../demo-tenant/round-4/quotes/)); read correctly on hosted (lines, EGP, total reconciled) | 1.1 |
| 2.5 | Recorded round dry run (Maadi low stock: oil, rice, onions → RFQ to 3 suppliers → quotes incl. «ج.م» and a photo → compare → guardrail → phone approval → PO → savings) | Orch | ✅ dry run complete 2026-10-19 ([record](../demo-tenant/round-4/README.md)): guardrail fired on the photo quote (EGP 25,600), approved on the phone, PO-000005 sent, savings 600 EGP vs last PO price; findings 39–43 | 1.x, 2.1–2.4 |

Accounts and setup already done: workspace «مطاعم سند» (EGP, Egypt VAT), owner `+pp-owner` and
buyer `+pp-buyer` accounts, 3 branches, 6 cost centres, 3 budgets, 5 suppliers with Gmail
plus-address send-as aliases, 30 products, inbound email address.

## Stage 3 — Video production

| # | Item | Owner | Status | Depends on |
|---|---|---|---|---|
| 3.1 | Opening shot: free kitchen/storeroom stock footage (Pexels/Pixabay) | Orch (User OK to download) | ✅ 2026-10-19: two Pexels clips downloaded with the owner's OK (16:9 kitchen, 9:16 chef at the grill), in `source/stock/` (not committed); sources in [README](README.md) | — |
| 3.2 | Motion-graphics boards: Arabic text cards, animated savings counter, «وصل إشعار للمدير» card, phone frame | Orch | ✅ boards built — logo canvas boards 14–17 (scene cards 7×3.2 s, savings counter with a `--target` variable, notification card, phone frame with the screen rect x741 y67 437×945); to render to MP4 once the recording exists | — |
| 3.3 | Record the screencast: web 1920×1080, phone 390×844, scene by scene per the storyboard | Orch | ✅ 2026-10-19: 9 clips recorded on hosted (web 1920×1080 in a clean kiosk window, phone 390×844); see [README](README.md#recording-and-edit-2026-10-19) | stages 1–2 |
| 3.4 | Edit on the music (Antalya Beaches) with the rendered outro at 2:50.25 → 3-minute cut | Orch | ✅ 2026-10-19: 3-minute Arabic cut rendered (music, cards, outro at 2:50.25); waiting for the owner’s review (3.7) | 3.1–3.3 |
| 3.5 | 60-second vertical cut (outro at 0:51.34) | Orch | ✅ 2026-10-19: 60-second 9:16 cut (track 2:00→, fast outro at 0:51.34, ends 0:59.85; phone scenes full height, web scenes cropped) | 3.4 |
| 3.6 | English versions (swap text cards; English outros already rendered) | Orch | ✅ 2026-10-19: English 3:00 and 60 s cuts: same footage, English cards (LTR) and the English outros | 3.4, 3.5 |
| 3.7 | User review of the recorded run, then of the cuts | User | ⏳ v2.1 comments (2026-10-20) applied in v2.2. Final review now waits for **3.8**: review v2.3 instead of picking between the v2.2 openings | 3.3, 3.6, 3.8 |
| 3.8 | **v2.3 brand editorial**: the v2.2 edit re-art-directed per [`motion-style.md`](motion-style.md): official Navy/Teal/Mist/Paper palette, Readex Pro, official logo SVGs, Converge bar/arrow transitions, navy duotone footage plates. Arabic + English, 16:9 + 9:16. Content, copy and timing unchanged | Orch | ⏳ Arabic 16:9 + 9:16 rendered 2026-10-22 ([`cuts/v2.3-brand/`](cuts/v2.3-brand/)); English (round-5 English-UI footage) after the owner approves the look | 3.6 |
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
| 2026-10-17 | 1.1 done (#96). Re-extraction exposed finding 15 (RTL tables merged into one line, one quote auto-accepted wrong) → 1.1b, #100 in progress. #97 merged. 1.5 started. External project drive had a transient I/O error overnight; recovered, no work lost. |
| 2026-10-17 (night) | #100 merged + deployed; both round-1 quotes correct on hosted (finding 15 closed). New blocker 1.1c (authorize dead end) with a fix session running. Boards 14–17 built (3.2). Mobile web build works at 390×844 (2.3). #97 merged. |
| 2026-10-17 (day) | #103 (polish) + #104 (authorize) merged + deployed, migrations applied. Round 1 live: quotes authorized, 10 matches confirmed, Smart Compare, request prepared/submitted/approved. New findings 17–20 (optimiser not deployed; pack-vs-base units — critical; request-flow gaps; match scores) with fix cards raised. PO not created. |
| 2026-10-18 | Round 1 reached PO-000001 on hosted (#108–#112 deployed). Walkthrough with screenshots added (#126). Label fixes #128 (migration applied to hosted) and quoted-price prefill #123 merged + deployed. Operator invite CLI #111 merged; invite email fix started. Codex asked to re-review 16 recent PRs whose later commits it had not reviewed. |
| 2026-10-18 (night) | Basket split on round 1 completed on hosted (الأمانة rice+sugar, النور the rest, 55,975 vs 56,425) but its result page returns 500 (finding 21, handed to the optimiser session). Savings ledger checked: findings 22–23 (manual entry per line; baseline = last quoted cost). PO labels verified fixed on hosted. |
| 2026-10-18 (night, later) | #131 merged + deployed: round-1 basket split result renders (EGP 55,975, saves 450). Docs re-review fixes merged (#129). Codex hit its usage limit; PRs reviewed by hand until it resets. |
| 2026-10-18 (day) | Rounds 2–3 done on hosted: three single-supplier RFQs, quotes by email with PDFs, 11 matches bulk-confirmed, requests approved on the phone (#146–#148 screens verified: names, packs, screen closes after a decision), PO-000002–000004 created. New findings 24–29; the budget one (approved spend not counted) has a fix task. |
| 2026-10-18 (afternoon) | Arabic RTL walkthrough (findings 31–37). Guardrail created in Arabic and fired on a real emailed quote: draft request 9e657ae3 (EGP 2,190) with no human prepare step. Savings baseline decided: last PO price (fix in progress). |
| 2026-10-18 (evening) | PRs #165/#168/#169/#170/#173/#176 merged; migrations 0011, 0012, 20261019000000, 20261019000001 applied to hosted. Round-4 dry run (2.4/2.5): RFQ sent from the app, three supplier replies from Gmail incl. a WhatsApp photo, guardrail fired on the photo quote and emailed the owner; request submitted. PO-000001–000004 marked sent so the last-PO-price baseline exists. Findings 39–43; #180 (RFQ email packs) and #181 (typed dates) merged. |
| 2026-10-19 | Round-4 dry run completed: phone approval, PO-000005 (EGP 25,600, الأمانة), outcome recorded from the PO, savings 600 EGP against the last PO price (rice +180, onions +100, oil +320). Stage 2 is ready for recording. |
| 2026-10-19 (evening) | Recording done on hosted (low-stock report, RFQ, WhatsApp-photo quote, guardrail draft 25,140 EGP, phone approval, PO-000006, savings 460; ledger 1,060 verified). 3-minute Arabic cut rendered and sent for review. Findings 44 (web signed out after ~8 h idle), 45 (no low-stock entry on phone home), 46 (raw «1.000000» quantity) raised as fix cards. |
| 2026-10-19 (night) | Comparison beat swapped to Smart Compare (recommended الأمانة, 12,880 vs 13,080 landed). 60-second vertical cut and both English cuts rendered; all four sent to the owner for review (3.7). Loudness −14.6 / −13.8 LUFS, peaks ≤ −2.2 dBFS. |
| 2026-10-19 (late) | Codex reviewed the plan; v2.0 (email masked, captions over footage, faster start) and v2.1 (phone low-stock re-recorded after #195, fuller vertical crops) built; all versions committed under `cuts/` with v1 rebuilt with the email masked at source (#194, #197–#199). |
| 2026-10-20 | Owner review of v2.1: English cuts showed the Arabic UI, the opening did not show the problem, loading shown too long, cropped click targets. v2.2 fixes those with two openings (animation / recorded clip) (#199); round 5 recorded with the English interface for English-UI cuts (#201, #202); Arabic editorial collage cuts from a cloud session reviewed, audio clipping fixed, merged (#200). Product fixes from round 5: findings 47–49 (#203, #206, #207). Next: owner picks the opening and gives the cuts a final look (3.7). |
| 2026-10-22 | Owner set a binding motion-graphics direction (editorial, brand-led, adaptive colour). Recorded in `motion-style.md` with a gap review: v2.2-editorial uses an invented palette and recolours the logo. Started 3.8 (v2.3 brand editorial); owner's final review moves to v2.3. |
| 2026-10-22 (later) | v2.3 brand editorial, Arabic 16:9 (1:59) and 9:16 (0:53) rendered: brand palette, navy duotone plates, Converge bar wipes, official logo SVGs. Waiting on owner review of the look before the English cut. |

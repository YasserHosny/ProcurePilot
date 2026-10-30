# Go-to-market — first customer

Everything for landing ProcurePilot's first pilot customer (Egypt, multi-branch F&B/retail).
Start with [`gtm-execution-plan.md`](gtm-execution-plan.md): current state, task list with
Jira keys, and the handoff log.

## In this folder

| File | What it is |
|---|---|
| [`first-customer-gtm-plan.md`](first-customer-gtm-plan.md) | The plan: ICP, fit and currency gaps (C1–C5, G1–G5), demo walkthrough, pilot prerequisites, sales-pipeline stages |
| [`gtm-execution-plan.md`](gtm-execution-plan.md) | Execution tracker and cold-start handoff for any model: Jira setup, tasks, dependencies, handoff log |
| [`one-pager/ProcurePilot-one-pager.pdf`](one-pager/ProcurePilot-one-pager.pdf) | Approved one-pager, 2 × A4 (Arabic, English) — PP-8 |
| [`demo-tenant/`](demo-tenant/) | Demo tenants (PP-5 / G-1): plan, restaurant dataset «مطاعم سند» on hosted, findings from building it live, lookups review |
| [`demo-tenant/round-1/`](demo-tenant/round-1/) | Round 1 walkthrough with live screenshots: RFQ → supplier quotes → compare → request → approval → PO-000001 on the demo tenant |
| [`demo-tenant/pps50-quote-expiry/`](demo-tenant/pps50-quote-expiry/) | PPS-50 hosted check with screenshots: the round-7 الأمانة photo quote, expiry confirmed as-is → Smart Compare shows «صالح حتى 2026/11/03» (EN + AR); UTC-timezone date-shift finding |
| [`demo-tenant/pps62-landing-gallery/`](demo-tenant/pps62-landing-gallery/) | PPS-62 landing gallery before/after: snap rail → guided steps, EN + AR, desktop and 375px |
| [`video/production-tracker.md`](video/production-tracker.md) | Demo video production tracker: what is left before recording (product flow, demo data, production), owners, status, user inputs |
| [`video/`](video/) | Demo video spec and decisions (PP-6): style, storyboard with music map, beat-locked logo sting, end card, audio sources and licences, beat data, render scripts |
| [`company-formation/us-company-fb-research.md`](company-formation/us-company-fb-research.md) | Research (Arabic): 13 posts + all comments from the Lean Startup Circle Egypt Facebook group on forming a US company from Egypt — per-post analysis, option comparison, consensus vs. disputed claims, providers |
| [`company-formation/recommendations.md`](company-formation/recommendations.md) | Conclusion & recommendations (Arabic): where to incorporate ProcurePilot now (Egyptian company, simplified tax regime) vs. later (Delaware C-Corp flip), questions for an Egyptian accountant, action plan, verified sources |
| [`company-formation/egypt-company-setup-guide.md`](company-formation/egypt-company-setup-guide.md) | Step-by-step guide (Arabic): one-person company at GAFI, Law 6/2025 simplified tax (verified rates + consulting exclusion), VAT, e-invoicing, banking, costs, checklist |
| [`company-formation/cost-comparison.md`](company-formation/cost-comparison.md) | 3-year cost comparison (Arabic): Egypt simplified vs. standard vs. adding US LLC / Delaware C-Corp / UAE free zone, at three revenue scenarios |
| [`company-formation/flip-readiness.md`](company-formation/flip-readiness.md) | Flip readiness (Arabic): what to set up now (IP assignment, assets, cap table) so a later Delaware/holding flip is cheap; Delaware facts verified; group experiences |
| [`competitor-profiles/`](competitor-profiles/) | Competitor quick-scan profiles (2026-10-28): Supy, Foodics, Suplyd, MarketMan, Apicbase + [`_summary.md`](competitor-profiles/_summary.md) landscape and positioning; raw scrapes under `raw/<slug>/<date>/` |
| [`battlecards/`](battlecards/) | Sales battlecards (2026-10-28, from the competitor profiles): Supy, Suplyd, Foodics; plus the status quo, WhatsApp + Excel (2026-10-30, PPS-114) — strengths, hypotheses to test, discovery questions, objections, when to walk away |
| [`outreach/cold-email-sequence.md`](outreach/cold-email-sequence.md) | Cold email sequence (AR + EN, 4 emails / 14 days) for pilot outreach where WhatsApp/intro can't reach; competitor variants, KSA adaptation, pre-send checklist — PPS-107 |
| [`outreach/discovery-demo-call-script.md`](outreach/discovery-demo-call-script.md) | Discovery call (20–30 min) + demo call (30 min) talk tracks, AR + EN: questions, three workflows tied to the buyer's pain, pilot offer, gaps to admit, after-call steps — PPS-114 |
| [`community/g7-community-plan.md`](community/g7-community-plan.md) | G-7 community plan: personal-network audit, Egyptian F&B and founder communities to join (to verify), give-first ideas, weekly cadence, intro → SP Lead — PPS-115 |
| [`research/`](research/) | Customer research kit: method (capture → synthesis after 5 calls, confidence levels) + call-notes template; filled notes stay local in `research/calls/` — PPS-116 |
| [`whatsapp-card/`](whatsapp-card/) | WhatsApp pilot-invite cards, 1080×1350, Arabic (`pilot-card-ar*`) and English (`pilot-card-en*`): brand-kit card, photo card (Higgsfield z_image background, text overlaid in HTML) and an 8 s push-in video of the photo card (ffmpeg; Higgsfield video needs a paid plan). Aligned with demo video v2.5 and end card v2 on 2026-10-29: restaurant purchasing, "2 weeks free, we set it up with you", founder + WhatsApp line, Iron Systems band. Source HTML, `caption-ar.txt`, `caption-en.txt` |
| [`gcc/`](gcc/) | GCC expansion, Saudi Arabia first (PPS-39): [`saudi-demo-plan.md`](gcc/saudi-demo-plan.md) — localization layers, product changes (#266), proposed Saudi demo workspace «مطاعم رواق», owner steps, order of work; [`script-saudi.md`](gcc/script-saudi.md) — Saudi demo video script (Gulf Arabic + English) on the revised v2.4 structure, approved 2026-10-25 |
| [`website/iron-sys-domain-setup.md`](website/iron-sys-domain-setup.md) | Company website domain (PP-19): `www.iron-sys.com` → bunny.net container `iron-systems-website` (GoDaddy CNAME + bunny SSL), bare domain 301-forwarded; steps to link another container to a subdomain |
| [`test-fixtures/egypt-quotes/`](test-fixtures/egypt-quotes/) | 5 synthetic Egyptian supplier quotes + `expected.json` for extraction testing (spec 022 US2, PP-3). Fictional suppliers, each marked TEST FIXTURE |

## Live documents (source of truth — edit there, not here)

| Document | Link | Jira |
|---|---|---|
| Pilot agreement (EN + AR, Annex A baseline) | <https://claude.ai/code/artifact/7f1d9481-a2a7-43a7-a0e4-b397c64e042b> | PP-10 |
| Outreach DM script (approved) | <https://claude.ai/code/artifact/30523eee-168f-4a1c-b7ac-dcb50cd9ded8> | PP-9 |
| One-pager design canvas | <https://claude.ai/artifact/6FPMTMHy37esXbEAZgQmmF> | PP-8 |
| Logo + video animation canvas (logo exploration, sting, end cards) | <https://claude.ai/artifact/CYVrF8484uFkpiJTqcGPdS> | PP-6 |
| Jira: ProcurePilot (non-code tasks) | <https://yasser-hosny.atlassian.net/jira/core/projects/PP/board> | — |
| Jira: Sales Pipeline | <https://yasser-hosny.atlassian.net/jira/core/projects/SP/board> | — |

When the one-pager canvas changes, re-export the PDF into `one-pager/`.

## Convention

New GTM / sales / pilot documents go in this folder. Product code specs stay in `specs/`.

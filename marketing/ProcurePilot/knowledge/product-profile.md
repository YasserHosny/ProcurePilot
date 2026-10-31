---
product_id: procurepilot
product_name: ProcurePilot
onboarding_status: positioning-approved
last_reviewed: 2026-10-28
reviewed_by: Claude (product-discovery session), pending owner review
sources_at: product repo f3ba1fe2 (2026-10-28, latest main; all branches merged) · website a1904c7 · live landing and privacy pages 2026-10-28
---

# ProcurePilot: product profile

Evidence labels: **V** verified (cite source) · **I** interpretation · **H** hypothesis · **?** unknown.
Only **V** items may be used in public copy, and only once the matching claim in `proof-points.md` is `approved`.

"V" in this file means one of two things, and the source column says which:
- **V-public**: a visitor can see it on the live landing page or the Iron Systems website.
- **V-docs**: documented as shipped in the product repo (roadmap release ledger, user documentation, code rules) and
  shown in the demo videos. Not checked by Claude inside the app (discovery never signs in).

Source ids are in `research/source-log.md`.

## 1. Overview

| Field | Value | Label | Source |
|---|---|---|---|
| One-line description (product's own) | "Every supplier price, traced to the quote it came from." It reads supplier quotations sent by email or upload, compares them pack for pack with delivery fees included, recommends an offer with its scoring shown; a person approves every purchase | V-public | SRC-016, SRC-017 |
| One-line description (Iron Systems website) | "Procurement intelligence for teams that buy from multiple suppliers." | V-public | SRC-004 |
| Category (the shelf buyers search) | Website says "Procurement intelligence". Buyers more likely search for quote comparison, purchasing or procurement software for restaurants | I (category term unvalidated) | SRC-004; no search data |
| Product type | Multi-tenant SaaS: web app (Angular) + mobile app (Flutter) + API, hosted on bunny.net | V-docs | SRC-011 |
| Availability / status | Live, invitation-only pilot. "Free for the agreed pilot period." Sign-up is invitation-gated; access is requested by email (hello@iron-sys.com) | V-public | SRC-017, SRC-004 |
| Environment caveat | The hosted app at procurepilot.iron-sys.com runs on the test/staging database. The product team's plan says it is fine for demos but **not** for real customer data; a separate production environment is planned (decision D-1, 2026-10-14) | V-docs | SRC-012, SRC-013 |
| Languages | English and Arabic throughout (every UI string in en + ar, RTL tested) | V-docs; V-public for the landing page | SRC-011, SRC-016 |
| Regions/currencies supported | Egypt (EGP, VAT 14%), Saudi Arabia (SAR, VAT 15%, #266), Ireland/eurozone (EUR, Irish VAT, #285). GBP/USD/AED exist in lists. KWD/BHD/OMR (3-decimal) not supported end to end | V-docs | SRC-012, SRC-014, SRC-013 |
| Target market on the landing page | "For restaurant groups and multi-branch buyers in Egypt" | V-public | SRC-017 |
| Product URL | https://procurepilot.iron-sys.com/ (`?lang=en` / `?lang=ar`) | V-public | SRC-017 |
| Provider named on the product | "ProcurePilot is a purchasing product built and run by Iron Systems" (privacy policy, live since 2026-10-26); footer "Built by Iron Systems", Privacy and Terms links, contact hello@iron-sys.com; mobile Help & about screen and email footers name Iron Systems | V-public, V-docs | SRC-032, SRC-033 |
| Demo workspaces (all fictional data) | Four hosted demo workspaces with real end-to-end runs: «مطاعم سند» (Egypt, EGP, Arabic and English UI), «مطاعم رواق» (Saudi Arabia, SAR, Arabic and English UI), Rawaq Restaurant Group (Saudi, all-English), Liffey Kitchen Group (Ireland, EUR, all-English). See section 11 | V-docs | SRC-030, SRC-031 |

## 2. Core features and capabilities (today)

Grouped by the buyer's workflow. Roadmap items are in section 8.

| Capability | What it does (plain words) | How we know | Label |
|---|---|---|---|
| Quotation capture | Supplier quotes arrive as PDFs, photos or spreadsheets, forwarded to a workspace email address or uploaded (including a phone photo) | Landing step 1; user docs §8, §28–30 | V-public, V-docs |
| Extraction with review | Every extracted line has a confidence score and a link to its page in the source document; low-confidence fields, unclear currency (`currency_unresolved`) and unverified totals go to a person for review before they are trusted | Landing step 1 and gallery 01; user docs §7, §9; CLAUDE.md recent changes (#96, #100, #104) | V-public, V-docs |
| Arabic quotes | Reads Arabic quotes, Arabic-Indic digits, Egyptian and Saudi currency markers (ج.م, جنيه, LE, ر.س, SAR), RTL tables row by row | SRC-011 (022, #100, #266) | V-docs. Accuracy **not measured** (no benchmark; release R1.2 "Unvalidated") |
| Product matching | Matches quoted lines to the catalogue; exact matches can be bulk-confirmed; fuzzy matches never auto-accept; a resolution queue for the rest | User docs §10; roadmap R1.3 "Partial" | V-docs. Precision gates not proven |
| Smart Compare (landed cost) | Offers ranked on total landed cost, pack for pack (25 kg sack vs 10 kg bag compared per kilo), delivery fee added, scoring shown, quote validity shown | Landing step 2, gallery 02; user docs §12 | V-public, V-docs |
| Basket split | Splits one order across suppliers when that lowers the total, counting each delivery fee | Landing gallery 03; user docs §13; optimiser deployed on hosted 2026-10-17 | V-public, V-docs |
| RFQ sending | A buyer builds an RFQ and sends it to several suppliers with one click (email, localised Arabic/English); sending is always a human action | GTM plan demo walkthrough; R4.3 shipped | V-docs |
| Guarded auto-preparation | With a guardrail switched on (off by default), the winning RFQ response is prepared as a **draft** purchase request; never purchased automatically | GTM plan; R4.3 release evidence; ADR-019 | V-docs |
| Purchase requests and approvals | Branch requests reach the approver with the remaining budget shown; nothing is ordered before approval | Landing step 3, gallery 04; user docs §18–20 | V-public, V-docs |
| Organisation model | Branches, cost centres, monthly budgets, roles and permissions, team invitations | User docs §21–22, §26; R2.0 | V-docs |
| Mobile app | Sign-in with biometric unlock, purchase requests, **request** approvals, low-stock reports, delivery confirmation, quality-issue photos | CLAUDE.md; mobile user docs | V-docs. Push notifications **never delivered** (no FCM/APNs; R2.2/R2.3 Partial). Purchase orders are web-only |
| Purchase orders and three-way match | Draft POs generated from an approved request (web), edit/cancel, order tracking, three-way match | User docs §11; R3.3 | V-docs |
| Savings ledger | Each saving calculated against the last PO or quoted price; counts as verified only after a person checks the evidence; pending and verified kept apart; export | Landing evidence band and gallery 05; user docs §16–17 | V-public, V-docs |
| Insight modules | Supplier scorecards / Supplier IQ, alerts and anomaly detection (v1), product price intelligence, reports centre, weekly digest, forecasting and reorder proposals, supplier risk and negotiation brief, grounded analyst (cited Q&A over the workspace's own data) | User docs §12–15, §23–25; roadmap R2.4–R4.2 | V-docs (shipped). On hosted, report schedules, digests, exports and offer refresh have **no background worker deployed** (roadmap risk 19, 2026-10-18) |
| Integrations | Accounting: QuickBooks Online, Xero. POS: Square. Read-only partner API + webhooks (beta) | Roadmap R3.1, R3.2, R3.4 | V-docs. The GTM plan says **do not pitch** these to the Egypt ICP (not used there); webhook worker not deployed |
| WhatsApp | No direct connection. WhatsApp quotes are saved as a file and uploaded, or forwarded by email | Landing FAQ; roadmap deferred list | V-public |

## 3. Technical and operational capabilities buyers ask about

| Topic | Fact | Label | Source |
|---|---|---|---|
| Deployment / hosting | bunny.net Magic Containers, Supabase Postgres 17 (managed), Docker/Nginx; a self-hosted option is a draft plan only | V-docs | SRC-011 |
| Integrations | See section 2. Odoo and local Egyptian accounting software are **not** integrated; CSV export covers hand-off | V-docs | SRC-012 |
| Tenant isolation | Enforced in the database: row-level security on every tenant table, tenancy from the verified sign-in token, cross-tenant reads return "not found"; a cross-tenant isolation test suite | V-docs | SRC-011 |
| Audit trail | `audit_event` is append-only (no update or delete for any role) | V-docs | SRC-011 |
| Security reviews | Internal security review of R3.2–R4.3 (2026-10-18), 7 Critical/High/Medium findings fixed; third-party pentest is scoped, not done | V-docs (internal only) | SRC-018 |
| Data handling, privacy, residency | Public privacy policy and terms (en + ar, 2026-10-26). Processors named: Supabase (database, sign-in, files) hosted on AWS in **Ireland**; bunny.net (hosting); AWS Bedrock (AI models, **United States**); Azure AI Document Intelligence; Mailgun; Sentry. "We do not sell your information and we do not use it for advertising." Pilot agreement drafts include Egypt PDPL (Law 151/2020), export and deletion on exit. Entity name, governing law, 90-day deletion and liability cap still to be confirmed by the owner (plan P-43) | V-public (policy text); legal details pending | SRC-032, SRC-033, SRC-012 |
| AI components and human review | Extraction (Azure Document Intelligence + AWS Bedrock/Claude per ADRs), matching, grounded analyst (Bedrock/Claude). Rule: "No autonomous purchasing. Automation prepares and routes; a human authorises." Privacy policy: results are shown for a person to check; customer data is **not used to train AI models** | V-docs, V-public | SRC-011, SRC-032 |
| Mobile / channels | Flutter app (see section 2). App-store availability **unknown** | V-docs; ? stores | SRC-011 |
| Arabic / RTL | Full Arabic UI with RTL, Arabic emails to suppliers, Arabic quote extraction | V-docs, V-public (landing) | SRC-011, SRC-016 |

## 4. Users and buyer roles

Detail in `target-audience.md`.

| Role | Uses it for | Label |
|---|---|---|
| Owner / GM (economic buyer) | Verified savings, spend control, approvals | H (PRD persona; no customer evidence) |
| Buyer / operations officer | Runs RFQs, reviews quotes, compares, drafts requests and POs | H |
| Branch / store manager | Purchase requests and low-stock reports from the phone, delivery confirmation | H |
| Approver | Approves requests within budget, on web or phone | H |
| Procurement analyst | Data quality, match resolution | H |

## 5. Customer problems and use cases

No customer interviews or pilot feedback exist in any source (pipeline in Jira SP not inspected). Problems below are
the product team's framing.

| Problem (product team's words) | Use case | Evidence | Label |
|---|---|---|---|
| Quotes collected manually over WhatsApp, phone and Excel, then compared by hand | Restaurant group buys the same staples from several suppliers each week | GTM plan ICP section; landing copy | H (no buyer quotes) |
| Quotes in different pack sizes and with delivery fees are hard to compare fairly | Compare a 25 kg sack with a 10 kg bag per kilo, fees included | Landing step 2 | I |
| Purchases made without checking the branch budget | Approver sees remaining budget before approving | Landing step 3 | I |
| Savings are claimed but never checked | Savings ledger separates calculated from verified | Landing evidence band | I |

## 6. Benefits supported by evidence

| Benefit | Which capability delivers it | Evidence | Label |
|---|---|---|---|
| Every price traceable to its source quote | Extraction keeps a link to the source page | Landing, gallery 01 | V-public (capability); benefit wording I |
| Fair comparison across pack sizes and delivery fees | Smart Compare landed cost | Landing, gallery 02 | V-public (capability) |
| A person stays in control of every purchase | Approvals; no autonomous purchasing rule | Landing FAQ, CLAUDE.md | V-public, V-docs |
| Savings you can audit | Savings ledger, verified vs calculated | Landing evidence band | V-public (capability). **No real savings figures exist**: all on-screen figures are demonstration data |
| Time saved, faster quote turnaround | — | None | ? unknown. No measurement; do not claim |

## 7. Pricing and commercial model

| Item | Value | Label | Source |
|---|---|---|---|
| Public pricing | None published. Landing: pilot is free for the agreed pilot period | V-public | SRC-017 |
| Internal post-pilot price (Egypt) | Decided internally 2026-10-14: EGP 1,500 per branch per month (minimum 2 branches), annual = 10 months, founding-customer 50% off for 12 months in exchange for case study + logo, savings guarantee (next month free if verified savings < 3× fee) | V-docs, **internal, not for marketing use** without owner approval | SRC-013 (D-2) |
| Pilot terms | Free 14-day pilot after onboarding and the first live RFQ; two check-ins; success metric against a week-0 baseline; data export and deletion on exit; EGP-quoting suppliers only, prices ex-VAT | V-docs (plan); the agreement itself lives in a claude.ai artifact not inspected | SRC-012 |
| Billing | Plans and limits enforced in the app; billing provider is a stub (no payment collection) | V-docs | SRC-018 |

## 8. Roadmap (not for public claims unless approved)

| Item | Status | Source |
|---|---|---|
| Production environment separate from staging (before any real customer data) | Decided, not built | SRC-012, SRC-013 (D-1, E-1) |
| Push notifications on mobile | Not delivered (stub) | SRC-018 |
| WhatsApp Business API ingestion | Deferred | SRC-018 |
| FX / cross-currency comparison, VAT-inclusive flag | Open (C4, C5) | SRC-012 |
| GCC beyond Saudi (QAR/KWD/BHD/OMR), ZATCA e-invoicing | Open (G1–G5) | SRC-012 |
| Policy engine, alert actions, anomaly v2, generic ERP connector | Deferred | SRC-018 |
| Background workers on hosted (schedules, digests, exports, webhooks, sync) | P-4, open | SRC-013, SRC-018 |
| App-store release of the mobile app | Unknown | — |

## 9. Assumptions and open questions

| # | Question / assumption | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q-01 | Which market leads marketing now: Egypt (landing, first-customer plan), Saudi Arabia (first GCC market, demo ready), or both? Ireland/eurozone demo exists too | Language, dialect, currency in creative, channels, SEO | Yasser | Open (D-07, D-11) |
| Q-02 | Are there any real pilot customers or active conversations? Can anything from them be used? | All proof today is demonstration data | Yasser | Open |
| Q-03 | Is the hosted app suitable to send prospects to while it runs on staging? | Marketing CTAs point at it | Yasser | Open |
| Q-04 | Is pricing ever to be public, and which (EGP per branch)? | Pricing page, FAQs | Yasser | Open |
| Q-05 | Category term: "procurement intelligence" (website) vs "purchasing for restaurant groups" (landing) | Positioning, SEO | Yasser | Open, see hypotheses |
| Q-06 | Mobile app: store availability, or web build only? | "On your phone" messaging | Product team | Open |
| Q-07 | Data residency and hosting region | Buyer and compliance questions in KSA/Egypt | Product team | **Answered 2026-10-28** by the public privacy policy: data on Supabase/AWS Ireland, AI on AWS Bedrock (US), no training on customer data (SRC-032) |
| Q-08 | Which demo video version is approved for public use | Video distribution | Yasser | **Answered:** v2.5 approved by Yasser 2026-10-27 for every version (12 cuts); Arabic cuts re-filmed 2026-10-28 with «ج.م» / «ر.س» money; end card v2 carries the Iron Systems band (iron-sys.com, hello@) (SRC-029, SRC-033) |
| Q-09 | Legal entity behind ProcurePilot | Footer, legal pages, "built by Iron Systems" | Yasser | Partly answered: the privacy policy and footer name Iron Systems as provider (SRC-032). Entity name, governing law and liability cap still open (plan P-43, G-10) |

## 10. Sources

See `research/source-log.md` SRC-004, SRC-007, SRC-008, SRC-011 to SRC-021, SRC-029 to SRC-033. Mirror of the product-repo documents:
`../` (refreshed by `npm run sources:sync`).

## 11. Demo workspaces and assets (latest, 2026-10-28)

Every demo is a real run through the hosted product with **fictional** restaurants, suppliers and prices. Records
and screens are in this repo; the files below are paths under `../docs/gtm/`.

| Workspace | Market | UI | Rounds (recorded) | Savings shown (demo data) | Screens | Video (v2.5, approved 2026-10-27) |
|---|---|---|---|---|---|---|
| «مطاعم سند» | Egypt, EGP | Arabic and English | Rounds 1–7 (Oct 16–24); round 6 Arabic and round 7 English on the Ledger design; Arabic re-shoot 2026-10-28 | Round 6 saving 300 ج.م; ledger 1,760 ج.م | Ledger-design stills: `docs/gtm/demo-tenant/round-6/screens-pps63/` (3: outcome form, ledger rows, verified ledger). Older stills in `docs/gtm/video/screens/` predate the Ledger design (2026-10-19): **don't use** | `v2.5/procurepilot-demo-ar-*.mp4` (Egyptian Arabic), `procurepilot-demo-en-*.mp4` |
| «مطاعم رواق» | Saudi Arabia, SAR, VAT 15% | Arabic (round A) and English (round E) | D dry, A, E (Oct 24–25); Arabic re-shoot 2026-10-28 | Round A 190 ر.س, round E SAR 120; ledger SAR 310 | 20 steps each: `docs/gtm/gcc/rounds/screens/ar/`, `docs/gtm/gcc/rounds/screens/en/` | `gcc-sa-v2/procurepilot-demo-sa-{ar,en}-*.mp4` |
| Rawaq Restaurant Group | Saudi Arabia, SAR, all-English | English | D dry, E (Oct 25) | SAR 310 | 20 steps: `docs/gtm/gcc/rounds/screens/sa-en/` | `gcc-sa-en-v2/` |
| Liffey Kitchen Group | Ireland, EUR, all-English | English | D dry, E (Oct 25) | €53.50; ledger €93.50 | 20 steps: `docs/gtm/gcc/rounds/screens/ie/` | `eu-en-v2/` (not in use: Ireland waits, MD-02) |

The 20 steps (same names in every screens folder): 01 phone home · 02 low-stock report · 03 report sent ·
04 RFQ lines in packs · 05 RFQ suppliers · 06 RFQ sent to 3 suppliers · 07 quotation inbox (2 PDFs + a WhatsApp
photo) · 08 photo quote read, VAT-inclusive total reconciled · 09 extracted lines beside the photo · 10 quote
authorised · 11 Smart Compare · 12 guardrail draft request within the limit · 13 phone approval detail · 14 phone
"Request approved" · 15 request approved and ordered · 16 PO from the request · 17 PO submitted · 18 record outcome
· 19 ledger, pending verification · 20 ledger verified.

File names: in the `ar/` and `en/` folders steps 05, 06 and 13 are saved as `5-…`, `6-…` and `3-…` (product repo naming).

Known display issues in demo material (don't screenshot them for marketing): a zero saving shows as red "-SAR 0.00";
euro amounts can drop a trailing zero (plan P-36). The RFQ flow was reworked on 2026-10-28 (RFQ Details page, line
order, product search; P-58), so RFQ screens older than that differ slightly from the live app.

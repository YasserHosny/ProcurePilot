---
product_id: procurepilot
report_status: ready-for-review   # draft | ready-for-review | reviewed
prepared_by: Claude (product-discovery session, Workflow A)
date: 2026-10-27
sources_at: product repo 74999690 (2026-10-26) · website a1904c7 · live landing page 2026-10-27
---

# Product Discovery Report: ProcurePilot

Evidence labels: **V** verified · **I** interpretation · **H** hypothesis · **?** unknown.
This report proposes; it does not finalise positioning. Decisions are listed in section 9.

## Update 2026-10-28: latest product data

Re-checked against the product repo at `f3ba1fe2` (latest `main`; every branch is merged) and the live site.

- **Demos:** four hosted demo workspaces with recorded rounds and screens: «مطاعم سند» (Egypt), «مطاعم رواق» (Saudi, Arabic and English UI), Rawaq Restaurant Group (Saudi, all-English), Liffey Kitchen Group (Ireland). 80 real screens (20 steps × 4) are now mirrored. Details: `product-profile.md` section 11.
- **Video:** v2.5 approved by Yasser on 2026-10-27 for all 12 cuts; Arabic cuts re-filmed on 2026-10-28 with «ج.م» / «ر.س»; end card v2 shows the Iron Systems band (Q-08 answered).
- **Legal and data:** public privacy policy and terms since 2026-10-26 name Iron Systems as provider; data on AWS Ireland, AI on AWS Bedrock (US), no training on customer data (Q-07 answered; new proposed claim C-17). Entity name and liability cap still open (Q-09).
- **Product changes since discovery:** one money format, Arabic «٣٠٠ ج.م»; RFQ flow reworked (RFQ Details page, line order, product search, P-58); sales enquiries go to hello@iron-sys.com.
- **Still open:** landing says Egypt with a SAR hero image (D-11, re-checked live); hosted runs on staging (D-12).

## 1. Summary

ProcurePilot is Iron Systems' purchasing product for businesses that buy the same goods from several suppliers. It
reads supplier quotations (PDF, photo, spreadsheet; by email or upload), keeps every extracted line linked to its
source page with a confidence score, compares offers pack for pack on landed cost, can split a basket across
suppliers, routes branch purchase requests to an approver with the remaining budget shown, and records savings that
count only once someone verifies them. It works in Arabic and English, on web and (for requests and approvals) mobile.
It is live at procurepilot.iron-sys.com as an **invitation-only pilot, free for the agreed pilot period** (V-public).

The product team has already chosen a target: **multi-branch restaurant groups in Egypt** first, with **Saudi
Arabia** as the first GCC market (V, documented choice). There is a detailed first-customer plan, a pilot design,
a one-pager, WhatsApp invite cards and a demo video now at **v2.5** for Egypt, Saudi Arabia and Ireland, all in the
product repo (`../docs/gtm/`).

The strongest verified capabilities are the ones on the live landing page: source-linked extraction, landed-cost
comparison, human approval within budget, and verified savings. The biggest unknowns are **all customer-side**: there
is no pilot customer, no buyer quote, no measured result and no competitor research in any source. Every figure
anywhere (landing, videos, screenshots) is demonstration data. Two operational facts constrain marketing: the hosted
app runs on the **staging database** (production is decided but not built), and several shipped modules lack
background workers or push notifications on hosted.

## 2. Method

| Item | Detail |
|---|---|
| Sources inspected | SRC-004, SRC-005, SRC-006, SRC-007, SRC-008 (workspace), SRC-011 to SRC-021 (product repo and live landing page). See `research/source-log.md` |
| Skills used and why | `product-discovery` (this workflow). `product-marketing` section list used as the completeness check (overview, audience, personas, pains, competition, differentiation, objections, switching, language, proof). `marketing-psychology` thinking for the switching forces and objections, with no persuasion tactics. **Not used:** `customer-research` (no customer material exists) and `competitor-profiling` (no competitor URLs given; left for Workflow B rather than guessed) |
| Not inspected and why | The signed-in app (discovery never signs in); Jira PPS/SP (sales pipeline and task state; outward system, not needed for facts); pilot agreement and DM script (claude.ai artifacts linked from the repo); the one-pager PDF contents (mirrored, not read in detail); `docs/gtm/company-formation/` (legal and tax research, not marketing); code beyond docs |
| Limitations | Features marked V-docs are documented as shipped and shown in demo videos but were not exercised by Claude. Product docs date from 2026-10-18 to 2026-10-26 and change daily; `npm run sources:sync` reports what has changed since this review |

## 3. Verified capabilities

Full table with sources: `product-profile.md` section 2. Summary:

| Capability | Evidence | Label |
|---|---|---|
| Reads supplier quotations sent by email or upload (PDF, photo, spreadsheet) | Landing hero and step 1; user docs §8, §28–30 | V-public |
| Each extracted line links to its source page, with a confidence score; unclear lines, currency and totals go to review | Landing gallery 01; repo fixes #96, #100, #104; spec 022 | V-public / V-docs. Accuracy unmeasured |
| Arabic quotes, Arabic-Indic digits, EGP and SAR markers | Spec 022, #266 | V-docs |
| Landed-cost comparison, pack for pack, delivery fees, scoring shown | Landing step 2, gallery 02 | V-public |
| Basket split across suppliers | Landing gallery 03; optimiser deployed 2026-10-17 | V-public |
| RFQ to several suppliers in one click (human sends); guardrail prepares a draft request (off by default) | GTM plan; R4.3 evidence | V-docs |
| Approval within the remaining branch budget; nothing ordered before approval | Landing step 3, gallery 04 | V-public |
| Mobile: requests, request approvals, low stock, delivery confirmation, quality photos | Mobile user docs | V-docs. No push notifications; POs on web only |
| Savings ledger: calculated vs verified; export | Landing evidence band, gallery 05 | V-public |
| Supplier IQ, alerts, price intelligence, reports, digest, forecasting, supplier risk, grounded analyst | User docs; roadmap R2.4–R4.2 | V-docs (several need workers not deployed on hosted) |
| QuickBooks, Xero, Square, partner API (beta) | Roadmap R3.1–R3.4 | V-docs; not relevant to the Egypt ICP |
| Workspace data isolation in the database; append-only audit log | Repo non-negotiables, isolation tests | V-docs (internal, no external audit) |
| Arabic and English UI throughout, RTL | i18n en + ar | V-docs, V-public |

## 4. Users, buyers and use cases

| Role / use case | Evidence | Label |
|---|---|---|
| Multi-branch restaurant groups (Egypt first) | Landing eyebrow; GTM plan wedge | V (team's choice), fit H |
| Saudi restaurant groups (first GCC market) | Saudi demo plan 2026-10-25 | V (team's choice) |
| Owner / GM as economic buyer; buyer, branch manager, approver, analyst as users | PRD personas | H |
| Weekly purchasing of staples from 5+ suppliers across 2+ branches | Pilot qualification criteria | V (criteria), fit H |
| Quotes arrive on WhatsApp, are saved and uploaded or forwarded | Landing FAQ | V-public |

## 5. Problems and alternatives

| Problem | Current alternative | Where the alternative falls short | Label | Source |
|---|---|---|---|---|
| Collecting and comparing supplier quotes by hand | WhatsApp, phone, Excel | Copying errors, no traceability, slow | H | SRC-012 |
| Pack sizes and delivery fees make unit prices misleading | Mental arithmetic, spreadsheets | Hard to compare fairly | I | SRC-017 |
| Branches buy without checking budget | Owner approval by phone or chat | No record, no budget view | H | SRC-012 |
| Savings are claimed but not checked | None | No evidence trail | I | SRC-017 |
| Software alternatives (ERP purchasing modules, restaurant procurement platforms) | Unknown | Unknown | ? | Not researched |

## 6. Positioning and messaging hypotheses

Detail in `product-positioning.md` and `messaging-matrix.md` (both `draft`).

- **A. Traceable prices for restaurant buyers.** Target: purchasing/operations managers of 2+ branch restaurant groups. Category: purchasing software for restaurant groups. Benefit: every supplier price traced to its quote, compared pack for pack with delivery fees. Proof: C-01–C-03, C-05, C-14. Risk: narrow; category term unproven. *Closest to the live landing page.*
- **B. Verified savings for owners.** Target: owner/GM. Category: spend control / procurement intelligence. Benefit: you see only savings someone has verified. Proof: C-05–C-07. Risk: invites "how much?", which nobody can answer with real data yet.
- **C. Arabic-first procurement for Egypt and the GCC.** Target: Arabic-speaking multi-branch businesses. Benefit: Arabic quotes and UI, local currencies and VAT. Proof: C-01, C-08. Risk: uniqueness unknown until competitors are researched.

Recommendation: **A leads, B is the proof story** once a pilot produces verified savings, C supports.

## 7. Proposed claims (for G-claims)

Full register: `proof-points.md` (C-01 to C-14, all `proposed`; most wording is already live on the landing page).

| id | Claim | Evidence | Recommended status |
|---|---|---|---|
| C-01 | Reads the quotations your suppliers send by email or upload | Landing, user docs | approve |
| C-02 | Every extracted line links to its source page, with a confidence score, and is reviewed before it is trusted | Landing, website | approve (no accuracy figure) |
| C-03 | Compares offers pack for pack, delivery fees included, scoring shown | Landing, website | approve |
| C-04 | Splits one order across suppliers when that lowers the total | Landing, website | approve |
| C-05 | A person approves every purchase; nothing is ordered before approval | Landing, repo rule 8 | approve |
| C-06 | Requests reach the approver with the remaining budget shown | Landing, website | approve |
| C-07 | A saving counts only once someone verifies its evidence | Landing, website | approve (never with a real-looking figure) |
| C-08 | Arabic and English, including Arabic supplier quotes | i18n, spec 022 | approve with caveat |
| C-09 | Approve purchase requests from your phone | Mobile docs, videos | approve after Q-06 (store availability) |
| C-10 | WhatsApp quotes: save and upload, or forward by email; no direct connection | Landing FAQ | approve |
| C-11 | Invitation-only pilot, free for the agreed pilot period | Landing, registry | approve |
| C-12 | Built by Iron Systems | Landing | approve after Q-09 |
| C-13 | Each workspace's data is kept separate, enforced in the database | Repo rules | owner to decide (internal evidence only) |
| C-14 | Real screens with synthetic data | Landing | approve (mandatory label) |

## 8. Discrepancies and open questions

| # | Question | Why it matters | Who can answer |
|---|---|---|---|
| D-05 | LinkedIn About says ProcurePilot "reads requests written in plain language"; no such feature. Revise it? | A live public claim that isn't supported | Yasser (approval for a live change) |
| D-06 | Arabic name: Latin "ProcurePilot" in Iron Systems materials, «بروكيور بايلوت» in product materials. Confirm the split | Consistency across channels | Yasser |
| D-07 / Q-01 | Lead market for marketing: Egypt, Saudi Arabia, both (and Ireland?) | Language, dialect, currency, channels, SEO | Yasser |
| D-11 | Landing says "Egypt" but its hero image shows SAR prices | Mixed signal on the main CTA page | Yasser / product team |
| D-12 / Q-03 | Can prospects be invited while the hosted app runs on staging? | Every CTA leads there | Yasser |
| Q-02 | Any real pilot customers or conversations? Anything usable with permission? | All proof is synthetic today | Yasser |
| Q-04 | Will pricing be public (internal Egypt price exists)? | FAQ, pricing content | Yasser |
| Q-05 | Category term | Positioning, SEO | Yasser, after keyword research |
| Q-06 | Mobile app in the stores, or web build only? | "On your phone" claims | Product team |
| Q-07 | Data hosting region / residency | Buyer trust questions, KSA | Product team |
| Q-08 | Which demo video version is approved for public use per market (v2.5?) | Video distribution | Yasser |
| Q-09 | Legal entity behind ProcurePilot; © line reads "ProcurePilot" | Footer, "built by" wording | Yasser |

## 9. Decisions needed from the owner

1. **Positioning (G-positioning):** choose hypothesis A, B or C (or a mix), or reject all. Recommendation: A, with B as the proof story later.
2. **Claims (G-claims):** approve, edit or reject C-01 to C-14 for reuse beyond the landing page.
3. **Lead market and language** for marketing (Egypt / Saudi / both; dialect per market).
4. **LinkedIn About text** (D-05): approve a revision to match the product (a live change).
5. **Prospect destination** (D-12): OK to drive organic traffic to the pilot request while hosted is staging, or wait for production.
6. **Public pricing:** keep "free during the pilot" only, or publish a price.
7. **Demo video for public channels:** which cut(s) per market.

## 10. Recommended next steps

1. Owner reviews this report and records the decisions above (positioning approval table in `product-positioning.md`; claim statuses in `proof-points.md`).
2. **Workflow B:** competitor and alternative research for restaurant procurement in Egypt and Saudi Arabia (named products, with URLs and dates), and keyword research for the category term.
3. Once positioning is approved: update `.agents/product-marketing.md` with verified, approved content; then **Workflow C** for a first organic campaign under `ProcurePilot/campaigns/`.
4. Keep current: run `npm run sources:sync` before any ProcurePilot work. It pulls the product repo, refreshes `../` and lists what changed since this review. After updating knowledge, run `npm run sources:sync -- --mark-reviewed`.

# ProcurePilot — Master Roadmap
## From Business Vision to Web + Mobile Implementation

---

### Document Control

| Field | Value |
|---|---|
| Document | ProcurePilot Master Roadmap |
| Version | 1.2 |
| Status | Active — delivery status maintained in the section "Delivery Status" below |
| Last updated | 2026-10-18 |
| Source of truth | `procurepilot_ai_context.md` (product context package) |
| Scope | Business vision, strategy, phased delivery, technical architecture, web and mobile implementation |
| Planning horizon | 24 months (M0 – M24) |
| Baseline start | M0 = Q3 2026 |
| Owner | Founder / Product Lead |

### How to Read This Document

- **Sections 1–4** define *why* the product exists and what success means.
- **Sections 5–9** define *what* gets built and *when*, phase by phase, with stage gates.
- **Sections 10–14** define *how* it gets built — architecture, web app, mobile app, AI.
- **Sections 15–20** define *execution reality* — team, cost, metrics, risk, critical path.
- **All numeric values are illustrative planning assumptions** unless explicitly marked as validated. This preserves the discipline set in the source context document.
- **Delivery Status** (next section) records what has actually shipped, what is partial, and what was deferred. Sections 1–22 are the original plan; where reality differs, the status section and the dated notes say so.

### Change Log

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-09-10 | Original plan |
| 1.1 | 2026-10-18 | Added Delivery Status (release ledger, gates, partial and deferred scope); first pilot market (Egypt); new risks 16–21 from the hosted demo build; walkthrough rule in the Definitions of Done; decision status in §20.2; current next actions in §21 |
| 1.2 | 2026-10-18 | Delivery Status: demo findings count, security review (R3.2–R4.3), background workers not deployed on hosted; §10.8 internal review row; risk 19 widened; §21.1 refreshed |

---

## Delivery Status (as of 2026-10-18)

### Release ledger

Every release R1.0–R4.3 has a Speckit spec under `specs/` and is merged to `main`. "Shipped" means the
release's spec was built and merged; it does not mean the phase's business gate was met (see Gates).

| Phase | Release | Spec | Status | Notes |
|---|---|---|---|---|
| 1 | R1.0 Foundation | `001-platform-foundation` | Shipped | |
| 1 | R1.1 Catalogue + Suppliers | `002-catalogue-suppliers` | Shipped | |
| 1 | R1.2 Ingestion + Extraction | `003-quotation-inbox-extraction` | Unvalidated | Built and merged; ≥90% extraction gate not measured (no held-out benchmark). Amended 2026-10-17 (FR-013A, a quotation can always be authorised) |
| 1 | R1.3 Matching + Normalisation | `004-matching-normalisation` | Partial | Built and merged; precision gates not proven (no held-out benchmark), T049 not exercisable. Fuzzy matches no longer auto-accept (PR #59); calibration waits for 500+ labelled decisions |
| 1 | R1.4 Compare + Intelligence | `005-smart-compare-intelligence` | Shipped | |
| 1 | R1.5 Value Proof + Launch | `006-value-proof-launch` | Partial | Plans and limits enforced; billing provider is a stub, no payment collection |
| 2 | R2.0 Organisation model | `007-organisation-model` | Shipped | |
| 2 | R2.1 Requests + Approvals | `008-requests-approvals` | Shipped | Policy engine deferred (see below) |
| 2 | R2.2 Mobile MVP | `009-mobile-app-mvp` | Partial | Push notifications are never delivered (no FCM/APNs provider) |
| 2 | R2.3 Mobile approvals + receipt | `010-mobile-approvals-receipt` | Partial | Approval and decision pushes never arrive (same stub) |
| 2 | R2.4 Optimisation + Supplier IQ | `011-optimisation-supplier-iq` | Shipped | Optimiser worker deployed on hosted 2026-10-17 (PR #108 + bunny.net container) |
| 2 | R2.5 Reporting + Hardening | `012-reporting-hardening` | Shipped | |
| 3 | R3.0 Email ingestion + catalogue refresh | `013-automated-ingestion` | Shipped | WhatsApp is manual capture only |
| 3 | R3.1 Accounting #1 | `014-accounting-integration` | Shipped | QuickBooks Online and Xero both supported. Connect is completed by the signed-in owner (#156); live mode needs a token encryption key (#160) |
| 3 | R3.2 POS / inventory | `015-pos-inventory-integration` | Shipped | Square, including stock on hand. Same connect and key hardening as R3.1 (#156, #160) |
| 3 | R3.3 Order tracking + three-way match | `016-order-tracking-three-way-match` | Shipped | Draft POs from approved requests (PR #61) |
| 3 | R3.4 Partner API + connectors | `017-partner-api-beta` | Partial | Read endpoints and webhook subscriptions; no partner credentials, generic connector framework or data-freshness engine. Outbound webhooks never delivered until #142 (2026-10-18), and the webhook worker is not deployed on hosted |
| 4 | R4.0 Forecasting + reorder | `018-forecasting-reorder` | Shipped | Some tests still unwritten (tasks T011, T016, T019, T020, T024) |
| 4 | R4.1 Supplier risk + negotiation | `019-supplier-risk-negotiation` | Shipped | Evidence: `docs/quality/r4.1-release-evidence.md` |
| 4 | R4.2 Grounded analyst | `020-grounded-procurement-analyst` | Shipped | Evidence: `docs/quality/r4.2-release-evidence.md` |
| 4 | R4.3 RFQ sourcing + guardrails | `021-rfq-sourcing-autonomy` | Shipped | Evidence: `docs/quality/r4.3-release-evidence.md` |
| Pilot | Home currency (Egypt) | `022-home-currency-readiness` | Merged, 3 tasks open | Real-quote extraction run, mobile screenshots, full test pass |

Since 2026-10-15 the hosted demo tenant build has produced 30 findings. As of 2026-10-18, 21 are fixed,
1 is partly fixed (20) and 8 are open (22, 23, 25–30); see `docs/gtm/demo-tenant/README.md`.

An internal security review of R3.2–R4.3 and the October fixes was completed on 2026-10-18
(`docs/quality/r3.2-r4.x-security-review-record.md`). Its 7 Critical, High and Medium findings are fixed
and merged (#137, #138, #142, #156, #160). #137 and #138 are deployed with their migrations applied to hosted;
#142, #156 and #160 need no migration, but the webhook-worker part of #142 is not active on hosted because
that worker is not deployed (see "Background workers on hosted" below). 8 Low and Info findings are tracked
there.

### Gates

| Gate | Recorded outcome |
|---|---|
| G1 → Phase 2 | Not passed; engineering proceeded by recorded exception (ADR-010) |
| G2 → Phase 3 | Software scope complete; business criteria (workflow origination, mobile adoption, retention) not measured — no pilot cohort (ADR-016, `docs/quality/g2-stage-gate-evaluation.md`) |
| G3 → Phase 4 | Unmet (`docs/quality/r3.4-release-evidence.md` … `r4.3-release-evidence.md`) |

No metric in §15.2 has been measured against real customer data yet. The first pilot (Egypt, see
§18) is what makes them measurable.

### Partial and deferred scope

| Item | Roadmap ref | State | Where recorded |
|---|---|---|---|
| Policy engine: blocked suppliers, spend limits beyond the budget check, exception justification | §7.1 | Not built; only preferred suppliers exist | Deferred in `specs/008-requests-approvals/spec.md` |
| Alerts inbox actions: assign, snooze, approve, purchase | §7.1 | Dismiss only; alert actions link to the relevant screen | — |
| Customer-configurable savings baseline | §6.4, risk 2 | Each saving stores its baseline policy; no workspace setting | — |
| Generic ERP connector framework | §8.1 | Accounting and POS each have their own connector interface | Deferred in `specs/013-automated-ingestion/spec.md` |
| Anomaly detection v2 (contract variance, false discounts) | §8.1 | Not built; v1 alerts exist | — |
| Data-freshness engine (source-quality scoring) | §8.1 | Partial: fresh/stale on offers, refresh schedules | — |
| Partner credentials (separate from user sign-in) | §8.1 | Partner endpoints use a user's sign-in token | `specs/017-partner-api-beta/spec.md` (later increments) |
| WhatsApp Business API | §8.1, decision 8 | Manual capture only | Deferred in `specs/013-automated-ingestion/spec.md` |
| Separate inventory-system connector | §8.1 | Stock on hand comes from the POS (Square) only | — |
| Payment collection for plans | §6.2 R1.5 | Stub billing provider | — |
| Exchange rates (pilot gap C4) | — | Cross-currency comparison refused by design | `docs/gtm/first-customer-gtm-plan.md` |
| VAT-inclusive prices (C5) and GCC items G1–G5 | — | Open | `docs/gtm/first-customer-gtm-plan.md` |
| Background workers on hosted | Risk 19 | Only the extraction, email-ingestion and optimiser workers are deployed. Report schedules, offer refresh, exports, digests, outbound webhooks and accounting/POS sync have no deploy workflow. Checked on hosted 2026-10-18: the only report schedule has been due since 2026-09-15 and never ran; 4 offer-refresh schedules are overdue; the only completed exports came from local E2E runs | `docker-compose.yml` lists them; `.github/workflows/deploy-*.yml` does not |

---

# PART I — BUSINESS VISION AND STRATEGY

---

## 1. Business Vision

### 1.1 Vision Statement

> **Every small business should buy as well as a large enterprise — with the same price visibility, supplier leverage, and decision evidence, without the same cost, staff, or complexity.**

Large organisations employ procurement teams, category managers, and source-to-pay suites. Small businesses buy the same categories of goods, repeatedly, with none of that infrastructure. They rely on habit, relationships, and memory. ProcurePilot's vision is to compress enterprise-grade purchasing intelligence into a tool a single owner or buyer can operate from a phone in five minutes a day.

### 1.2 Mission Statement

> **Turn fragmented supplier information into trusted, comparable, actionable purchasing decisions — and prove the money saved.**

Three verbs define the mission and the entire product:

1. **Normalise** — make offers genuinely comparable (identity, pack size, VAT, delivery, terms).
2. **Recommend** — convert comparison into a specific, evidence-backed action.
3. **Verify** — measure the realised financial outcome so value is provable, not claimed.

### 1.3 The Problem, Stated Commercially

Small businesses lose money on purchasing in ways they cannot see. The leakage is not one large error; it is dozens of small, invisible, repeated ones:

| Leakage cause | Illustrative share of leakage |
|---|---:|
| Poor comparison between offers | 27% |
| Emergency / rush buying | 22% |
| Wrong order quantities | 17% |
| Missed discounts and thresholds | 14% |
| Supplier concentration (no competitive tension) | 11% |
| Duplicate or unapproved spend | 9% |

The root cause is not laziness or lack of care. It is **structural incomparability**: a 6×5L quote from Supplier A, a 12×750ml quote from Supplier B via WhatsApp, and a marketplace listing with free delivery over a threshold cannot be compared by a human in the seconds available. So the business defaults to the familiar supplier.

### 1.4 The Product Thesis

ProcurePilot's entire value rests on one causal chain. Every feature must earn its place on this chain:

```
noisy supplier document
        ↓  (document intelligence)
extracted line items
        ↓  (product matching + entity resolution)
resolved product identity
        ↓  (unit + pack-size normalisation)
comparable unit basis
        ↓  (landed-cost engine)
true total cost of acquisition
        ↓  (recommendation scorer + basket optimiser)
specific recommended action
        ↓  (approval + order workflow)
executed purchase
        ↓  (outcome capture)
verified saving + model feedback
```

**Strategic consequence:** the normalisation and entity-resolution core *is* the product. Dashboards, alerts, and integrations are replaceable surface area. If the core is unreliable, no interface can rescue it — and a wrong match produces a *fabricated* saving, which is worse than no saving at all.

### 1.5 Why Now

| Enabler | Why it changes feasibility |
|---|---|
| **Vision-language models** | Quotation and invoice extraction from messy PDFs, photos, and scans is now accurate enough to be economically viable without bespoke per-supplier templates. |
| **Embedding-based entity resolution** | Matching noisy supplier descriptions to a catalogue no longer requires exhaustive rule engineering. |
| **Cheap vector + relational infrastructure** | A per-tenant purchasing graph with semantic search is affordable at SMB price points. |
| **Digital-first supplier behaviour** | Quotations already arrive as PDF, Excel, email, and WhatsApp files — machine-readable inputs exist without asking suppliers to change. |
| **SMB cost pressure** | Input-cost volatility has raised owner sensitivity to purchasing cost, shortening the sales conversation. |

### 1.6 Value Proposition by Persona

| Persona | Core job | What ProcurePilot delivers | Primary metric they feel |
|---|---|---|---|
| **Owner / GM** (economic buyer) | Protect margin, control spend | Verified savings, budget control, supplier-risk visibility, approval authority | £ saved per month |
| **Buyer / Operations Officer** (power user) | Get the right goods at the right price, fast | Quote ingestion, instant comparison, basket optimisation, one-click requests | Hours saved per buying cycle |
| **Branch / Store Manager** (demand owner) | Never run out, stay in budget | Simple mobile request, low-stock reporting, receipt confirmation | Stock-outs avoided |

### 1.7 Positioning Statement

> For **small businesses that buy recurring consumables**, ProcurePilot is an **AI purchasing co-pilot and lightweight procurement operating system** that **converts fragmented supplier offers into evidence-based purchasing decisions and verified savings** — unlike **spreadsheets, memory, and generic price-comparison sites**, which cannot normalise pack sizes, landed cost, or supplier performance.

### 1.8 Strategic Pillars

1. **Trustworthy data before clever AI.** Confidence scores, provenance, and human review are product features, not internal tooling.
2. **Every insight ends in an action.** No read-only dashboards. Each insight carries expected value, confidence, validity, and an executable next step.
3. **Verified value, not claimed value.** Savings must be auditable back to source documents.
4. **Depth in one wedge before breadth.** Recurring standardised consumables first.
5. **Data accretion as moat.** Optimise year 1 for volume and quality of structured purchase history.
6. **Phased complexity.** No enterprise source-to-pay features without validated demand.

### 1.9 Explicit Non-Goals

Carried forward from the product context and treated as binding for the roadmap horizon:

- Consumer shopping, coupon, or deals application
- Generic public price-comparison website
- Public supplier-review marketplace
- Marketplace seller repricing tool
- Full enterprise Source-to-Pay suite
- ERP replacement
- Autonomous purchasing without human approval
- Social features or public reviews

### 1.10 Business Objectives (3-Year, Illustrative)

| Horizon | Objective | Illustrative target |
|---|---|---|
| **Year 1** | Prove the value loop and reach product–market fit in one wedge | 40–60 paying businesses, £350+ verified monthly value per customer, ≥3.4× value-to-fee ratio |
| **Year 2** | Scale acquisition through partner channels, add workflow and integration depth | 250–400 paying businesses, net revenue retention >110%, 2–3 productised integrations |
| **Year 3** | Establish the purchasing graph as a defensible asset; expand categories and regions | 1,000+ businesses, predictive procurement live, benchmark data products |

### 1.11 Definition of Success at Each Level

- **Customer success:** the business can name the money ProcurePilot saved and would notice its absence within a week.
- **Product success:** ≥60% of active businesses act on ≥4 recommendations per month.
- **Business success:** CAC payback under 6 months with subscription gross margin above 75%.
- **Strategic success:** switching cost created by accumulated normalised history, not by contract lock-in.

---

## 2. Strategic Objectives and Phase OKRs

### 2.1 Phase Map

| Phase | Name | Window | Central question being answered |
|---|---|---|---|
| **Phase 0** | Concierge Validation | M0 – M3 | Is the problem real, and will businesses pay to solve it? |
| **Phase 1** | Procurement Intelligence MVP (Web) | M3 – M9 | Can software reliably produce the comparison and the saving? |
| **Phase 2** | Team Workflow + Mobile | M9 – M15 | Does it become the system of record for buying decisions? |
| **Phase 3** | Connected Operations | M15 – M20 | Can it plug into the customer's existing stack and stay current automatically? |
| **Phase 4** | Predictive Procurement | M20 – M24+ | Can it decide *when* and *how much* before the customer asks? |

### 2.2 Phase OKRs

**Phase 0 — Validation**

| Objective | Key results |
|---|---|
| Validate problem severity | 15+ structured customer interviews; leakage quantified in ≥8 businesses |
| Prove savings exist | Identify ≥5% addressable saving on reviewed spend in ≥70% of reviews |
| Test willingness to pay | ≥3 signed paid pilots or letters of intent |
| Build the ground-truth asset | 300+ labelled quotation line items; 500+ labelled product-match pairs |

**Phase 1 — Intelligence MVP**

| Objective | Key results |
|---|---|
| Reliable extraction | ≥90% field-level accuracy on priority fields, measured on held-out set |
| Reliable matching | ≥92% precision at the auto-accept confidence threshold; ≤8% routed to human review |
| Comparison customers trust | ≥80% of comparisons accepted without manual correction |
| Provable value | Savings ledger live; ≥10 businesses with a verified saving recorded |

**Phase 2 — Team Workflow + Mobile**

| Objective | Key results |
|---|---|
| Become the workflow | ≥70% of a customer's tracked purchases originate inside ProcurePilot |
| Mobile adoption | ≥50% of branch requests submitted from mobile |
| Multi-user depth | Average ≥2.5 active users per paying account |
| Retention | ≥90% logo retention over the phase |

**Phase 3 — Connected Operations**

| Objective | Key results |
|---|---|
| Reduce manual entry | ≥60% of stock and spend data arriving via integration or email ingestion |
| Integration coverage | 2 accounting + 1 POS integration in production |
| Data freshness | ≥85% of active offers under 14 days old |

**Phase 4 — Predictive Procurement**

| Objective | Key results |
|---|---|
| Forecast usefulness | Reorder-date recommendations accepted ≥60% of the time |
| Emergency reduction | Emergency-order rate down ≥40% versus customer baseline |
| Negotiation value | Negotiation briefs used in ≥30% of supplier reviews |

### 2.3 Stage Gates (Go / No-Go)

Each phase ends in a gate. **Failing a gate means iterating inside the phase, not proceeding.**

| Gate | Exit criteria | If not met |
|---|---|---|
| **G0 → Phase 1** | ≥3 paid pilots; documented savings in ≥5 businesses; labelled dataset built | Re-select wedge vertical or reframe offer; do not build software |
| **G1 → Phase 2** | Matching precision and extraction accuracy targets met; ≥10 verified savings; ≥8 paying customers on self-serve product | Invest further in data quality and review UX before adding workflow |
| **G2 → Phase 3** | Workflow-origination ≥70%; mobile adoption target met; retention ≥90% | Deepen workflow before spending on integrations |
| **G3 → Phase 4** | Integration-sourced data ≥60%; ≥6 months of purchase history for ≥30 accounts | Continue data accumulation; forecasting without history will fail |

---

## 3. Product Scope by Phase

### 3.1 Capability Matrix

Legend: **●** in scope · **◐** partial / basic · **○** out of scope

| Capability | P0 | P1 | P2 | P3 | P4 |
|---|:--:|:--:|:--:|:--:|:--:|
| Business catalogue (normalised product master) | ◐ | ● | ● | ● | ● |
| Supplier hub | ◐ | ◐ | ● | ● | ● |
| Quotation inbox (upload PDF / image / Excel) | ○ | ● | ● | ● | ● |
| Document extraction (AI) | ○ | ● | ● | ● | ● |
| Product matching (AI) | ◐ | ● | ● | ● | ● |
| Unit + pack-size normalisation | ◐ | ● | ● | ● | ● |
| Landed-cost engine | ◐ | ● | ● | ● | ● |
| Smart Compare | ○ | ● | ● | ● | ● |
| Human review / exception queue | ● | ● | ● | ● | ● |
| Price history + product intelligence | ○ | ● | ● | ● | ● |
| Savings ledger + verification | ◐ | ● | ● | ● | ● |
| Alerts inbox (actionable) | ○ | ◐ | ● | ● | ● |
| Basket optimiser | ○ | ◐ | ● | ● | ● |
| Purchase requests | ○ | ◐ | ● | ● | ● |
| Approvals, budgets, branches | ○ | ○ | ● | ● | ● |
| Mobile application | ○ | ○ | ● | ● | ● |
| Supplier performance intelligence | ○ | ○ | ● | ● | ● |
| Email ingestion (forwarding address) | ○ | ○ | ◐ | ● | ● |
| Accounting / POS / inventory integrations | ○ | ○ | ○ | ● | ● |
| Order tracking + reconciliation | ○ | ○ | ◐ | ● | ● |
| Demand forecasting + reorder points | ○ | ○ | ○ | ◐ | ● |
| Anomaly detection | ○ | ○ | ◐ | ● | ● |
| Negotiation assistant | ○ | ○ | ○ | ○ | ● |
| Natural-language procurement analyst | ○ | ○ | ○ | ○ | ● |
| Partner / public API | ○ | ○ | ○ | ◐ | ● |

### 3.2 Deliberate Deferrals and Rationale

| Deferred item | Deferred to | Rationale |
|---|---|---|
| Demand forecasting | Phase 4 | Requires ≥6 months of usage history; premature forecasts destroy trust |
| Basket optimisation (full) | Phase 2 | Needs multiple concurrent normalised offers per SKU — data that does not exist in month 1 |
| Executive dashboard (rich) | Phase 2 | Nothing meaningful to display until history accumulates |
| Integrations | Phase 3 | CSV, upload, and email cover 80% of need at 10% of cost |
| Mobile app | Phase 2 | Branch requests and approvals are the mobile-native jobs; both are Phase 2 features |
| In-platform ordering / payments | Post-Phase 3, subject to validation | Large architectural fork; keep ordering external until demand is proven |

---

## 4. Cross-Cutting Workstreams

These run continuously across all phases rather than belonging to one.

| Workstream | Purpose | Continuous deliverables |
|---|---|---|
| **Data quality** | Protect the trust foundation | Confidence calibration, review-queue throughput, correction feedback loop, accuracy dashboards |
| **AI evaluation** | Prevent silent regression | Versioned benchmark sets, per-release eval runs, prompt/model changelog, accuracy gates in CI |
| **Architecture** | Keep the core replayable and auditable | Rule versioning, bitemporal price data, event log for outcomes |
| **Security & compliance** | Customer financial data is sensitive | Tenant isolation, encryption at rest and in transit, audit logging, GDPR/data-residency posture, DPA templates |
| **Design system** | One visual language across web and mobile | Shared tokens, component library, accessibility baseline (WCAG 2.1 AA) |
| **Localisation** | Bilingual readiness from the schema up | English + Arabic content, RTL layout support, multi-currency, configurable tax models |
| **QA & release** | Ship weekly without fear | Test pyramid, staging environment, seeded demo tenant, feature flags |
| **Customer feedback** | Keep the wedge honest | Weekly pilot calls in P0–P1, in-product feedback capture, monthly insight review |

---

# PART II — PHASED DELIVERY PLAN

---

## 5. Phase 0 — Concierge Validation (M0 – M3)

**Objective:** prove the problem, the saving, and the willingness to pay — **with almost no software**.

### 5.1 Why Concierge First

Building the matching and extraction engine before knowing the real shape of customer documents is the most expensive mistake available. Phase 0 buys three assets: **evidence**, **labelled training data**, and **paying pilot customers who become design partners**.

### 5.2 Workstreams

**A. Customer discovery**
- Recruit 5–10 businesses in the wedge (cleaning/hygiene, office supplies, café packaging).
- Run a structured interview guide: current process, suppliers, documents, pain, workarounds, willingness to pay.
- Capture spend profile: monthly purchasing value, SKU count, supplier count, order frequency.

**B. Manual spend review (the acquisition offer)**
- Collect 3 months of invoices, sample quotations, product list, supplier list.
- Manually normalise products and pack sizes in a spreadsheet.
- Manually compute landed cost and identify alternatives.
- Deliver a **Spend Review Report**: leakage found, pack-size issues, emergency-buying pattern, supplier alternatives, quantified savings opportunity, pilot proposal.

**C. Weekly concierge recommendations**
- For pilot businesses, deliver a weekly recommendation set by email or WhatsApp.
- Record which recommendations were actioned and what was actually paid.
- This is the first version of the savings ledger — maintained by hand.

**D. Ground-truth dataset construction**
- Label 300+ quotation line items with correct field values (supplier, product, SKU, qty, unit, unit price, VAT, delivery, discount, terms, currency, expiry).
- Label 500+ product-match pairs, including hard negatives (same brand different pack, same pack different variant, compatible substitute).
- This dataset becomes the **acceptance test** for Phase 1 AI. Without it, Phase 1 has no definition of done.

**E. Foundational decisions to close**
Phase 0 must resolve the schema-determining open questions before any code is written:
1. **Savings baseline policy** — last paid price, rolling average, best-available-at-decision-time, or contract price. Must be explicit, documented, and defensible to an auditing customer.
2. **Launch region, currency, and tax model.**
3. **Whether ordering happens inside the platform** or remains external.
4. **Whether stock is owned by ProcurePilot or read-only from the customer's systems.**
5. **Acceptable product-matching accuracy for launch**, and the confidence threshold for auto-accept.

### 5.3 Phase 0 Deliverables

| Deliverable | Format |
|---|---|
| Customer interview guide + 15 completed interviews | Document + notes repository |
| 5–10 Spend Review Reports | PDF per customer |
| Weekly recommendation log with actioned/not-actioned outcomes | Spreadsheet |
| Product-matching benchmark dataset (v1) | Labelled dataset |
| Quotation extraction test dataset (v1) | Labelled dataset |
| Savings baseline policy | Signed-off decision document |
| Pricing validation summary | Document |
| Phase 1 PRD + domain model | Document |

### 5.4 Phase 0 Tooling (deliberately minimal)

Spreadsheets, a shared drive, a document-labelling sheet, and off-the-shelf LLM tooling used manually. **No product engineering.** The only acceptable engineering spend is a lightweight internal script to speed up manual extraction.

---

## 6. Phase 1 — Procurement Intelligence MVP, Web (M3 – M9)

**Objective:** software reliably reproduces the concierge output — trusted extraction, matching, normalisation, comparison, and a verified savings ledger.

**Platform decision:** **web first, desktop-optimised.** The Phase 1 jobs (uploading documents, resolving matches, comparing offers) are dense, keyboard-and-screen tasks. Mobile arrives in Phase 2 when the mobile-native jobs (requesting and approving) exist.

### 6.1 Minimum Coherent Slice

The narrowest scope that proves the thesis end to end:

1. Tenant, users, and authentication
2. Business catalogue with normalised units and pack sizes
3. Supplier records (basic)
4. Quotation ingestion — PDF, image, Excel, CSV upload
5. AI extraction → **human review and correction queue**
6. AI product matching with confidence, correction, and audit
7. Landed-cost normalisation engine (versioned, replayable)
8. Smart Compare with last-paid and average-paid context
9. Recorded decision + purchase outcome capture
10. Savings ledger with auditable trail to source documents

Everything else in Phase 1 is optional polish.

### 6.2 Release Breakdown

| Release | Window | Theme | Scope |
|---|---|---|---|
| **R1.0** | M3 – M4 | Foundation | Monorepo, CI/CD, environments, auth, multi-tenancy, RBAC skeleton, design system v1, app shell |
| **R1.1** | M4 – M5 | Catalogue + Suppliers | Product master, families, variants, brands, units, pack sizes, normalised quantity, substitute rules, supplier profiles, CSV import with validation |
| **R1.2** | M5 – M6 | Ingestion + Extraction | Upload pipeline, storage, document extraction service (Bedrock/Azure DI), extraction confidence, **review queue UI**, field-level correction, versioned quotations |
| **R1.3** | M6 – M7 | Matching + Normalisation | Entity-resolution service, candidate generation, confidence scoring, auto-accept threshold, human match resolution UI, unit normaliser, landed-cost engine v1 |
| **R1.4** | M7 – M8 | Compare + Intelligence | Smart Compare view, product intelligence page, price history, last/average paid, basic actionable alerts, basic two-supplier basket split |
| **R1.5** | M8 – M9 | Value Proof + Launch Readiness | Savings ledger, outcome capture, savings dashboard, exports (Excel/PDF), onboarding flow, billing and plans, Arabic/RTL readiness, pilot-to-paid migration |

### 6.3 Phase 1 Definition of Done

- Extraction and matching meet the accuracy targets **measured against the Phase 0 benchmark datasets**, not against internal impressions.
- Every recommendation displays source data, calculation, confidence, risk, and validity period.
- Every saving in the ledger is traceable to the source quotation and purchase record.
- A new customer can self-onboard, upload a real quotation, and see a trusted comparison without founder intervention.
- Review-queue throughput allows one operator to clear a typical customer's weekly documents in under 30 minutes.
- *(Added v1.1)* Each user-facing release is walked through end to end on the hosted environment, in both English and Arabic, before it is called done. The 2026-10 demo-tenant build found 20 defects that unit, integration and E2E suites had passed (`docs/gtm/demo-tenant/README.md`).

### 6.4 Explicit Phase 1 Risks

| Risk | Control |
|---|---|
| Matching accuracy plateaus below threshold | Barcode/GTIN support, richer candidate features, human review as permanent safety net, per-tenant learned aliases |
| Customers do not upload documents | Email forwarding fallback, concierge-assisted onboarding, WhatsApp file export instructions |
| Savings figures disputed | Explicit baseline policy, full audit trail, conservative default baseline, customer-configurable baseline |
| Scope creep into dashboards | Gate every feature against the causal chain in §1.4 |

---

## 7. Phase 2 — Team Workflow and Mobile (M9 – M15)

**Objective:** move from *intelligence tool* to *system of record for purchasing decisions*. This is where retention is created, because workflow dependency and team adoption are what make removal painful.

### 7.1 Scope

**Workflow**
- Purchase requests with branch and cost-centre assignment
- Approval routing with threshold rules and delegation
- Budget definition and budget checks at request time
- Policy engine: preferred suppliers, blocked suppliers, spend limits, exception justification
- Full audit log on every request, approval, and override
- Advanced basket optimiser: minimum order values, free-delivery thresholds, quantity tiers, urgency constraints, supplier-preference weighting, risk tolerance
- Supplier performance intelligence: lead-time actuals, fulfilment rate, quality incidents, risk score
- Actionable alerts inbox with assign / snooze / dismiss / approve / purchase
- Scheduled reports and email digests
- Basic anomaly detection (price spike, duplicate invoice, decimal error, delivery-cost anomaly)

**Mobile application** — see §12 for full implementation detail. Phase 2 mobile scope is deliberately narrow and job-focused:
- Branch request submission (including photo of shelf/label)
- Low-stock reporting
- Approval decisions with full context
- Delivery receipt confirmation and quality issue reporting
- Push notifications for approvals and urgent alerts

### 7.2 Release Breakdown

| Release | Window | Theme | Scope |
|---|---|---|---|
| **R2.0** | M9 – M10 | Organisation model | Branches, cost centres, roles and permissions, budgets, org settings |
| **R2.1** | M10 – M11 | Requests + Approvals (web) | Request creation, approval routing, threshold rules, budget check, audit log, approval queue |
| **R2.2** | M11 – M12 | Mobile MVP | Mobile shell, auth, request submission, low-stock report, push notifications, offline-tolerant drafts |
| **R2.3** | M12 – M13 | Mobile approvals + receipt | Approval flow on mobile, delivery confirmation, quality issue reporting, camera capture pipeline |
| **R2.4** | M13 – M14 | Optimisation + Supplier IQ | Advanced basket optimiser, supplier scorecards, risk scoring, anomaly detection v1 |
| **R2.5** | M14 – M15 | Reporting + Hardening | Scheduled reports, digests, exports, performance tuning, accessibility pass, security review |

### 7.3 Phase 2 Definition of Done

- A purchase can be requested, approved, ordered, received, and measured entirely inside ProcurePilot.
- Branch managers use mobile without training beyond a one-screen guide.
- Approval cycle time is measurably shorter than the customer's documented baseline.
- Supplier scorecards are populated from actual recorded outcomes, not manual entry.
- *(Added v1.1)* Same hosted walkthrough rule as §6.3, including the mobile app.

---

## 8. Phase 3 — Connected Operations (M15 – M20)

**Objective:** remove manual data entry as the ceiling on value. Data must arrive continuously without the customer working for it.

### 8.1 Scope

- **Email ingestion**: dedicated per-tenant forwarding address; automatic supplier identification; attachment extraction; thread-to-quotation linking
- **Accounting integrations**: two providers, prioritised by pilot demand (invoice and supplier sync, spend reconciliation)
- **POS integration**: one provider — sales velocity feeding usage signals
- **Inventory integration**: stock-on-hand sync where a system exists
- **ERP connector framework**: generic pattern rather than bespoke builds
- **Order tracking and reconciliation**: PO → confirmation → delivery note → invoice three-way match
- **Supplier catalogue import**: scheduled refresh of full supplier price files
- **Data freshness engine**: source-quality scoring, staleness flags, refresh scheduling
- **Partner API (beta)**: read endpoints plus webhooks
- **Anomaly detection v2**: contract variance, supplier price drift, false discounts

### 8.2 Release Breakdown

| Release | Window | Theme |
|---|---|---|
| **R3.0** | M15 – M16 | Email ingestion + supplier catalogue refresh |
| **R3.1** | M16 – M17 | Accounting integration #1 + reconciliation foundation |
| **R3.2** | M17 – M18 | POS / inventory integration + usage signals |
| **R3.3** | M18 – M19 | Order tracking, three-way match, accounting integration #2 |
| **R3.4** | M19 – M20 | Partner API beta, webhooks, connector framework, data-freshness engine |

### 8.3 Integration Principles

1. **CSV and email before APIs.** Never build an integration a spreadsheet can satisfy for the first ten customers.
2. **One connector framework, many providers.** Normalise at the boundary; never let a provider's schema leak into the domain.
3. **Integrations must be revocable.** Failure of an integration must degrade gracefully to manual input, never block purchasing.
4. **Prioritise by pilot demand, not by market size.** Build the integration three paying customers are asking for.

---

## 9. Phase 4 — Predictive Procurement (M20 – M24+)

**Objective:** shift from reactive comparison to proactive, anticipatory purchasing. Only viable once ≥6 months of history exists for a meaningful cohort.

### 9.1 Scope

- **Demand forecasting**: expected usage, seasonality, safety stock, reorder point, suggested order date and quantity, stock-out and overstock risk — each with explicit uncertainty ranges
- **Predictive reorder proposals**: pre-built baskets awaiting approval
- **Negotiation assistant**: evidence-based briefs using historical price, volume, alternatives, service performance, payment behaviour, purchase frequency
- **Supplier risk model**: concentration risk, price-drift trajectory, reliability decay, single-source exposure
- **Automated sourcing**: structured RFQ dispatch to suppliers and automated response ingestion
- **Natural-language procurement analyst**: grounded question answering over the tenant's own data, with linked source records, shown calculations, and stated confidence — never ungrounded generation
- **Autonomous recommendation workflows**: rules-based auto-approval within tight, customer-defined guardrails; **purchasing remains human-authorised**

### 9.2 Release Breakdown

| Release | Window | Theme |
|---|---|---|
| **R4.0** | M20 – M21 | Forecasting engine + reorder recommendations with uncertainty |
| **R4.1** | M21 – M22 | Supplier risk model + negotiation briefs |
| **R4.2** | M22 – M23 | Grounded procurement analyst (retrieval over tenant data) |
| **R4.3** | M23 – M24 | Automated RFQ sourcing + guarded autonomous workflows |

### 9.3 Guardrails for Phase 4

- **No forecast without uncertainty.** Point predictions without ranges will be treated as promises.
- **No analyst answer without a citation** to a source record and a visible calculation.
- **No autonomous purchase.** Automation may prepare and route; a human authorises.
- **Cold-start honesty.** Where history is insufficient, the product must say so rather than produce a low-confidence number silently.

---

# PART III — TECHNICAL IMPLEMENTATION

---

## 10. System Architecture

### 10.1 Architectural Principles

1. **Modular monolith first, extract services later.** One deployable backend with strict internal module boundaries. Extract only the AI/extraction worker and the optimiser when scale demands it. A distributed system at Phase 1 is self-inflicted cost.
2. **Normalisation is a pure, versioned, replayable function.** Store raw inputs plus the rule-set version; derive landed cost deterministically. Historical recommendations must be reproducible for savings audits when rules change.
3. **Confidence and provenance are first-class columns**, not metadata blobs. Every extracted or inferred value carries source, method, model version, confidence, and reviewer.
4. **Bitemporal price data.** Offers and prices need both valid-time (when the price applied) and record-time (when we learned it). Defensible savings claims require answering "what did we know, and when?"
5. **Outcomes are event-sourced.** Recommendation → action → purchase → delivery → quality → saving is an append-only event stream. Mutable rows destroy the audit trail the north-star metric depends on.
6. **Shared canonical spine with per-tenant overlay.** A global canonical product layer enables future cross-tenant benchmarking; tenant-specific aliases and preferences layer on top without leaking data between tenants.
7. **Human-in-the-loop is architectural.** The review queue is a core domain concept with its own state machine, SLAs, and metrics.
8. **Multi-currency, multi-tax, bilingual from the schema up.** Retrofitting these is disproportionately expensive.

### 10.2 Layered Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  EXPERIENCE LAYER                                                │
│  Web console (Angular)  ·  Mobile app (Flutter)                 │
│  Email digests  ·  Scheduled reports  ·  Partner API             │
└───────────────────────────┬──────────────────────────────────────┘
                            │  REST/JSON + OpenAPI · JWT · tenant scope
┌───────────────────────────▼──────────────────────────────────────┐
│  API GATEWAY / BFF (Nginx reverse proxy)                           │
│  Auth · rate limiting · tenant resolution · request validation   │
└───────────────────────────┬──────────────────────────────────────┘
┌───────────────────────────▼──────────────────────────────────────┐
│  BUSINESS SERVICES (modular monolith)                            │
│  Catalogue · Supplier · Quotation · Offer · Request · Approval    │
│  Order · Savings Ledger · Alert · Report · Subscription · Tenant │
└──────┬──────────────────────────────────┬────────────────────────┘
       │                                  │
┌──────▼───────────────────┐   ┌───────────▼──────────────────────┐
│  DECISION ENGINE         │   │  AI / DATA LAYER                 │
│  Landed-cost engine      │   │  Bedrock/Azure document AI       │
│  Basket optimiser        │   │  Entity resolution / matching    │
│  Policy engine           │   │  Unit normaliser                 │
│  Recommendation scorer   │   │  Embedding + vector search       │
│  Supplier-risk scorer    │   │  Confidence calibration          │
│  Forecast service (P4)   │   │  Anomaly detection               │
└──────┬───────────────────┘   └───────────┬──────────────────────┘
       │                                   │
┌──────▼───────────────────────────────────▼──────────────────────┐
│  INGESTION LAYER                                                │
│  File upload · Email forwarding · API connectors · Schedulers    │
│  Validation queue · Human review queue                          │
└──────┬──────────────────────────────────────────────────────────┘
┌──────▼──────────────────────────────────────────────────────────┐
│  DATA LAYER                                                     │
│  PostgreSQL (relational + pgvector) · Object storage (documents) │
│  Redis (cache + queue) · Event log · Audit log · Analytics store │
└─────────────────────────────────────────────────────────────────┘
```

### 10.3 Recommended Technology Stack

| Layer | Recommendation | Rationale |
|---|---|---|
| **Web frontend** | Angular 19 (latest stable) + TypeScript | SPA framework; aligns with blueprint; mature enterprise ecosystem; one language across stack |
| **Styling / UI** | Angular Material + Angular CDK + SCSS | Fast, accessible, consistent; low custom-CSS burden |
| **Icons** | Material Icons | Consistent with Angular Material |
| **Data fetching** | Angular HttpClient + RxJS | Cache, retry, optimistic updates for review queues |
| **Charts** | ng2-charts / Chart.js | Price history, spend, savings trends |
| **Tables** | Angular Material Table | Comparison grids and review queues need virtualisation and column control |
| **Forms** | Angular Reactive Forms + Zod | Shared validation schema with backend contract |
| **Mobile** | Flutter (Dart, iOS + Android) | Single codebase, native UI performance, store distribution from one team |
| **Backend** | Python 3.12 + FastAPI 0.115.6 + Uvicorn 0.34.0 | AI/data-heavy core; explicit versions from blueprint |
| **Data validation** | Pydantic v2 + pydantic-settings + Zod | Shared schemas across Python backend and Angular frontend |
| **Auth / HTTP** | python-jose 3.3.0 + httpx 0.28.1 + SlowAPI 0.1.9 | JWT verification, async HTTP client, rate limiting |
| **Database client** | supabase-py 2.11.0 | Official Python SDK for Postgres/Auth/Storage |
| **Migrations** | Versioned SQL files + Supabase CLI | Application-managed schema evolution; local dev with Supabase CLI |
| **Database** | Supabase Postgres 17 + `pgvector` + `pg_trgm` | Managed Postgres 17 with Auth, Storage and Realtime; relational integrity, semantic search and fuzzy matching in one engine |
| **Object storage** | Supabase Storage (S3-compatible) | Source documents retained for audit; MIME/size filters |
| **Cache / queue** | Redis | Sessions, rate limits, lightweight job queue |
| **Background jobs** | RQ (Redis Queue) | Extraction, matching, refresh, digests |
| **Workflow orchestration** | Temporal (Phase 3+, if needed) | Long-running integration and reconciliation flows |
| **Document AI** | AWS Bedrock (Claude 3 Haiku) primary + Azure Document Intelligence fallback | Template-free extraction; fallback for cost and resilience |
| **Optimisation** | OR-Tools (CP-SAT / MIP) | Basket allocation with thresholds, MOVs, and discount tiers is a constrained optimisation problem, not a heuristic |
| **Auth** | Supabase Auth | Do not hand-roll authentication; same identity layer as the database |
| **Payments** | Stripe | Subscriptions, plan gating, dunning |
| **Reverse proxy** | Nginx | SPA fallback, `/api/` proxy to backend, security headers |
| **Analytics / product telemetry** | PostHog | Self-hostable, funnel and feature analysis |
| **Error tracking** | Sentry | Web, mobile, backend |
| **Monorepo** | Turborepo + pnpm (JS) · uv (Python) | Shared types, one CI pipeline |
| **CI/CD** | GitHub Actions · Docker Buildx · GHCR · BunnyWay/container-update-image | Path-filtered backend/frontend/mobile workflows; secrets `BUNNY_API_KEY`, `BUNNY_*_APP_ID` |
| **Hosting** | bunny.net Magic Containers — **Production app:** Web FE (port 80) + Backend (port 8000), shared network namespace with `BACKEND_HOST=localhost`. **Workers app:** Extraction worker + Redis (port 6379), shared namespace; cross-app communication via Anycast IP | Two-app topology isolates background AI inference from HTTP serving; independent scaling and deployment |
| **IaC** | Terraform | Reproducible environments |

**Platform note:** Supabase (Postgres + Auth + Storage + Realtime) is the Phase 1 platform, materially reducing initial infrastructure work. A future path to self-managed Postgres + custom Auth/Storage remains available if residency, scale, or pricing require it.

### 10.4 Repository Structure

```
procurepilot/
├── apps/
│   ├── web/                  # Angular SPA
│   ├── mobile/               # Flutter app (iOS + Android)
│   └── api/                  # FastAPI backend (modular monolith)
├── services/
│   ├── extraction-worker/    # document extraction (Bedrock/Azure DI)
│   ├── matching-worker/      # entity resolution + embeddings
│   └── optimiser/            # OR-Tools basket allocation
├── packages/
│   ├── domain-types/         # shared TS types generated from OpenAPI
│   ├── ui/                   # shared design tokens + primitives
│   ├── validation/           # shared Zod schemas
│   └── i18n/                 # en + ar message catalogues
├── ml/
│   ├── benchmarks/           # matching + extraction eval datasets
│   ├── evals/                # eval harness and reports
│   └── notebooks/            # exploration
├── docker-compose.yml        # Local multi-service orchestration
├── .github/workflows/          # CI/CD pipelines
├── infra/                    # Terraform, Docker, CI config
└── docs/                     # Documentation index and subfolders
    ├── product/              # PRD, user stories, AI context
    ├── architecture/         # ADRs, engineering spec, API spec, data dictionary, tech-stack blueprint
    ├── quality/              # Test strategy
    ├── operations/           # Deployment plan, runbook
    ├── user/                 # User documentation
    ├── roadmap/              # Master roadmap and visual
    └── README.md             # Documentation index
```

### 10.5 Core Domain Model (Implementation View)

Extends the conceptual model in the context document with the entities implementation requires.

| Entity | Purpose | Implementation notes |
|---|---|---|
| `Tenant` | Customer account | Root of all isolation; every table carries `tenant_id` |
| `User`, `Role`, `Membership` | Access control | RBAC: owner, buyer, branch manager, approver, viewer |
| `Branch`, `CostCentre` | Organisational demand units | Budgets attach here |
| `CanonicalProduct` | Shared product spine | Global, brand + variant + GTIN normalised |
| `TenantProduct` | Per-tenant catalogue entry | Links to canonical; holds tenant naming, preferences, substitutes |
| `Unit`, `PackDefinition` | Pack-size normalisation | `pack_count × unit_size → normalised_quantity` in a base unit |
| `ProductAlias` | Learned supplier description → product | Per-tenant learning surface; primary matching accelerator |
| `Supplier` | Supplier master | Terms, MOV, delivery fee, lead time, reliability, risk, status |
| `Document` | Ingested artefact | Immutable; stores hash, source channel, storage URI, MIME type |
| `Quotation` | Structured document interpretation | Versioned; links to `Document`; carries extraction confidence and review status |
| `QuotationLine` | Raw extracted line | Retains original text alongside resolved values |
| `SupplierOffer` | Normalised, comparable offer | Bitemporal: `valid_from`, `valid_to`, `recorded_at`; links to source line |
| `PriceObservation` | Immutable price fact | Append-only; feeds history, drift, and anomaly detection |
| `LandedCostComputation` | Derived cost with rule version | Stores inputs + `ruleset_version` for replay |
| `MatchDecision` | Match audit record | Candidate set, scores, method, model version, threshold, human reviewer |
| `ReviewTask` | Human-in-the-loop unit of work | State machine: open → in review → resolved → rejected; SLA tracked |
| `PurchaseRequest`, `RequestLine` | Demand record | Branch, cost centre, required-by date, budget reference |
| `ApprovalStep` | Routing instance | Threshold rule applied, approver, status, comments, exception reason |
| `PurchaseOrder` | Issued order | Optional in Phase 1–2; first-class if in-platform ordering is validated |
| `Receipt`, `QualityEvent` | Fulfilment outcome | Feeds supplier reliability and quality scores |
| `Recommendation` | Emitted advice | Evidence refs, calculation, confidence, risk, validity window |
| `RecommendationOutcome` | What actually happened | Actioned / ignored / modified; the model feedback signal |
| `SavingRecord` | **Verified savings ledger** | Baseline policy, baseline value, actual value, delta, verification status, evidence refs — **immutable once verified** |
| `StockSignal` | Stock and usage state | Source-tagged: manual, CSV, POS, inventory, ERP |
| `Budget`, `BudgetPeriod` | Spend control | Checked at request time |
| `Policy`, `PolicyRule` | Guardrails | Preferred/blocked suppliers, limits, required approvals |
| `Alert` | Actionable signal | Reason, impact, action, validity, confidence, risk, assignment state |
| `AuditEvent` | Append-only audit log | Actor, action, entity, before/after, timestamp, IP |
| `Subscription`, `PlanEntitlement` | Commercial state | Feature and quota gating |

**Note on the savings ledger:** the source context document treats verified savings as the north-star metric but does not model it as an entity. `SavingRecord` closes that gap and is treated here as a **Phase 1 requirement**, not a reporting afterthought.

### 10.6 API Design Standards

- **REST + JSON**, resource-oriented, OpenAPI 3.1 as the contract; TypeScript types generated from it for web and mobile.
- **Tenant scoping enforced server-side** from the token — never from a client-supplied parameter.
- **Cursor pagination** on all collections; `limit` capped.
- **Idempotency keys** on all mutating endpoints (critical for mobile retries on poor connectivity).
- **Standard error envelope**: `code`, `message`, `details`, `trace_id`.
- **Async operations return a job resource** with polling and webhook completion (extraction, optimisation, bulk import).
- **Versioned under `/v1`**; additive changes only within a version.
- **Every response carrying a derived value includes** `confidence`, `computed_at`, and `ruleset_version`.

### 10.7 Key API Surface (Phase 1)

| Domain | Representative endpoints |
|---|---|
| Auth / tenant | `POST /v1/auth/login`, `GET /v1/me`, `GET /v1/tenant` |
| Catalogue | `GET/POST /v1/products`, `POST /v1/products/import`, `GET /v1/products/{id}/price-history` |
| Suppliers | `GET/POST /v1/suppliers`, `GET /v1/suppliers/{id}/performance` |
| Documents | `POST /v1/documents` (presigned upload), `GET /v1/documents/{id}` |
| Extraction | `POST /v1/quotations/{id}/extract` → job, `GET /v1/jobs/{id}` |
| Review | `GET /v1/review-tasks`, `POST /v1/review-tasks/{id}/resolve` |
| Matching | `GET /v1/match-candidates?line_id=`, `POST /v1/match-decisions` |
| Offers | `GET /v1/offers?product_id=`, `GET /v1/offers/compare?product_id=&qty=` |
| Optimisation | `POST /v1/baskets/optimise` → job |
| Recommendations | `GET /v1/recommendations`, `POST /v1/recommendations/{id}/action` |
| Savings | `GET /v1/savings`, `GET /v1/savings/{id}/evidence` |
| Reports | `POST /v1/reports/export` |

### 10.8 Security and Compliance Plan

| Area | Control | Phase |
|---|---|---|
| **Authentication** | Supabase Auth, MFA available, session revocation | P1 |
| **Tenant isolation** | `tenant_id` on every row + row-level security policies; enforced in a single query layer | P1 |
| **Authorisation** | RBAC with explicit permission checks per endpoint; deny by default | P1 |
| **Rate limiting** | SlowAPI per-endpoint limits; configurable via env | P1 |
| **CORS** | Configurable origin allowlist via env var | P1 |
| **Encryption** | TLS 1.3 in transit; AES-256 at rest for database and object storage | P1 |
| **Nginx hardening** | CSP, HSTS, X-Frame-Options, X-Content-Type-Options | P1 |
| **Secrets** | Managed secret store; no secrets in code or environment files in the repository | P1 |
| **Audit logging** | Append-only `AuditEvent` on every mutation; exportable per tenant | P1 |
| **Document retention** | Source documents retained for the audit window; configurable deletion | P1 |
| **AI data handling** | No customer data used for third-party model training; zero-retention endpoints where available; documented sub-processor list | P1 |
| **PII minimisation** | Supplier contacts are the only significant PII; no consumer data | P1 |
| **GDPR posture** | DPA template, data-processing register, subject-access and deletion workflows, documented residency | P1–P2 |
| **Backups** | Daily automated backups, tested restore, documented RPO/RTO | P1 |
| **Penetration test** | Third-party test before general availability | End P2 |
| **SOC 2 readiness** | Policy set and evidence collection begun when enterprise-adjacent demand appears | P3 |
| **Internal security review** | Manual review per release group before the pen test. R3.2–R4.3 done 2026-10-18 (`docs/quality/r3.2-r4.x-security-review-record.md`) | Each phase |

---

## 11. Web Application Implementation

### 11.1 Design Principles

1. **Action-first layout.** Every screen answers "what should I do next?" before "what happened?"
2. **Evidence always one click away.** Any number can be expanded to its calculation and source document.
3. **Confidence made visible, never hidden.** Low-confidence values are visually distinct and correctable inline.
4. **Density where experts work.** Comparison grids and review queues are dense and keyboard-navigable; dashboards are calm.
5. **Bilingual and RTL from the first component.** Direction-aware layout primitives, no hard-coded left/right spacing. CSS logical properties (`margin-inline-start`, `padding-block-end`) are mandatory.
6. **Responsive across mobile, tablet, and desktop.** Shared SCSS breakpoints (mobile ≤ 599px, tablet 600–959px, desktop ≥ 960px); layouts collapse gracefully with no horizontal overflow. Procurement users access the system from phones and tablets on the shop floor.
7. **Accessibility baseline WCAG 2.1 AA.** Contrast, focus order, keyboard operability, screen-reader labels.

### 11.2 Information Architecture

```
/                         Dashboard (savings + actions)
/inbox                    Action / alerts inbox
/quotations               Quotation inbox (list)
/quotations/[id]          Quotation detail + extraction review
/review                   Review queue (extraction + matching tasks)
/products                 Business catalogue
/products/[id]            Product intelligence (price history, best cost, reorder)
/compare                  Smart Compare workspace
/baskets/[id]             Basket optimiser result
/suppliers                Supplier hub
/suppliers/[id]           Supplier profile + performance
/requests                 Purchase requests            (P2)
/requests/[id]            Request detail + approval trail (P2)
/approvals                Approval queue                (P2)
/savings                  Savings ledger + verification
/reports                  Reports and exports
/settings/organisation    Branches, cost centres, budgets (P2)
/settings/policies        Policy rules                    (P2)
/settings/team            Users and roles
/settings/integrations    Connectors                      (P3)
/settings/billing         Plan and subscription
```

### 11.3 Screen Specifications — Phase 1 Priority Order

**1. Quotation Inbox + Extraction Review** *(highest engineering value in Phase 1)*
- Drag-and-drop upload for PDF, image, Excel, CSV; multi-file; progress states.
- Side-by-side layout: rendered document on the left, extracted fields on the right.
- Field-level confidence badges; click a field to highlight its source region in the document.
- Inline correction with keyboard flow (Tab through low-confidence fields only).
- Header fields: supplier, currency, dates, VAT treatment, delivery terms, payment terms, expiry.
- Line table: original description retained beside resolved product, quantity, unit, pack, unit price.
- Bulk actions: accept all high-confidence, escalate, reject document.
- Version comparison when a supplier re-quotes.

**2. Match Resolution**
- Candidate list with score, and the *reason* for the score (brand match, size match, GTIN match, alias hit).
- Explicit outcome vocabulary: same product · different pack size · different variant · compatible alternative · no match.
- "Create new product" path when nothing fits.
- One decision creates a reusable `ProductAlias`, so the same supplier text never needs review twice.
- Keyboard-first: number keys select candidates, Enter confirms.

**3. Smart Compare**
- Row per supplier offer; columns: displayed price, normalised unit price, VAT, delivery, discounts, **total landed cost**, lead time, payment terms, reliability, match confidence, stock.
- Quantity input recalculates thresholds, tiers, and MOVs live.
- Context columns: last paid price, 6-month average, best historical.
- AI recommendation banner with the calculation shown, confidence, risk, and validity period.
- Actions: create request, add to basket, record purchase, export.

**4. Product Intelligence**
- Best current landed cost, last paid, average paid, 30-day change.
- Price-history chart with supplier series and annotated purchase events.
- Preferred supplier, approved alternatives, substitute rules.
- Reorder date and recommended quantity (placeholder until Phase 4, clearly labelled).

**5. Savings Ledger**
- Row per saving: date, product, supplier chosen, baseline policy used, baseline value, actual value, delta, verification status.
- Evidence drawer: source quotation, competing offers considered, purchase record, calculation.
- Filters by period, branch, category, supplier.
- Export to Excel and PDF for the customer's own reporting.

**6. Dashboard**
- Top band: actions required (highest information priority), then savings opportunities, then realised savings.
- Secondary: price increases detected, quotations expiring, products above target cost, supplier concentration, budget status.
- Every tile links to a filtered actionable list — no dead-end metrics.

**7. Catalogue and Supplier Hub**
- CSV import with a validation and mapping step; error report before commit.
- Catalogue table with pack normalisation shown explicitly (`6 × 5L = 30L`).
- Supplier profile: terms, MOV, delivery fee, lead time, reliability, quality incidents, status.

### 11.4 Web Delivery Sequence (Sprint-Level, Phase 1)

| Sprint | Weeks | Deliverable |
|---|---|---|
| W1 | M3 | Repo, CI, environments, design tokens, app shell, auth screens |
| W2 | M3–M4 | Tenant onboarding, team/roles settings, navigation, empty states |
| W3 | M4 | Catalogue list, product create/edit, unit and pack model UI |
| W4 | M4–M5 | CSV import with validation and mapping; supplier list and profile |
| W5 | M5 | Upload pipeline UI, document viewer, job/progress states |
| W6 | M5–M6 | Extraction review screen (fields, confidence, source highlighting) |
| W7 | M6 | Review queue, bulk actions, quotation versioning |
| W8 | M6–M7 | Match resolution screen, alias creation, new-product path |
| W9 | M7 | Smart Compare grid, quantity recalculation, landed-cost breakdown |
| W10 | M7 | Product intelligence page, price-history chart |
| W11 | M8 | Basic basket split view, actionable alerts inbox |
| W12 | M8 | Savings ledger, evidence drawer, outcome capture |
| W13 | M8–M9 | Dashboard, exports, scheduled email summary |
| W14 | M9 | Billing and plan gating, Arabic/RTL pass, onboarding polish |
| W15 | M9 | Performance, accessibility, bug burn-down, launch readiness |

### 11.5 Web Non-Functional Targets

| Attribute | Target |
|---|---|
| First contentful paint (dashboard) | < 1.5 s on broadband |
| Comparison grid interaction latency | < 150 ms for recalculation |
| Extraction turnaround (per document, user-visible) | < 45 s p95 |
| Table virtualisation threshold | Smooth at 5,000 rows |
| Browser support | Latest 2 versions of Chrome, Edge, Safari, Firefox |
| Uptime target | 99.5% (Phase 1) → 99.9% (Phase 3) |

---

## 12. Mobile Application Implementation

### 12.1 Strategic Role of Mobile

Mobile is **not** a shrunken web console. It exists to serve three jobs that happen away from a desk:

1. **Request** — a branch manager standing in front of an empty shelf.
2. **Approve** — an owner deciding in under 30 seconds, with enough evidence to be confident.
3. **Confirm** — receipt, shortage, or quality problem at the point of delivery.

Everything else stays on web. Resisting feature parity is the main design discipline for mobile.

### 12.2 Platform Decision

**Flutter**, single codebase for iOS and Android.

| Reason | Detail |
|---|---|
| Shared types and validation | OpenAPI-generated Dart types and shared domain contracts; backend Zod/Pydantic remains source of truth |
| One team | No separate native hiring for Phase 2 |
| Store distribution | App Store / Play Store releases enforce quality and rollback discipline |
| Native capability coverage | Camera, push, biometrics, file system all well supported |
| Escape hatch | Native modules or custom platform channels available if a specific need emerges |

### 12.3 Mobile Screen Set (Phase 2)

| Screen | Purpose | Key behaviour |
|---|---|---|
| **Login / biometric unlock** | Access | Biometric re-entry after first login; long-lived refresh token |
| **Home** | Role-aware landing | Branch manager sees "Request items"; approver sees pending approvals count |
| **Quick request** | Primary branch job | Search catalogue, recent items shortcut, quantity stepper, required-by date, note, photo attach |
| **Scan / photo capture** | Reduce typing | Barcode scan to identify product; photo of shelf or label as request evidence |
| **Low-stock report** | Demand signal | One-tap "running low" per product with optional count |
| **My requests** | Status tracking | Draft, submitted, approved, ordered, delivered states with timeline |
| **Approval queue** | Primary owner job | Card per request: amount, branch, budget impact, recommended supplier, expected saving, policy exceptions |
| **Approval detail** | Decision evidence | Landed-cost comparison summary, confidence, alternatives, one-tap approve / reject / request change with comment |
| **Delivery confirmation** | Outcome capture | Confirm quantities received, flag shortage, photo of damage, quality rating |
| **Alerts** | Urgent signals | Price spike, expiring quotation, stock risk — each with an action |
| **Settings** | Basics | Language (en/ar with RTL), notifications, branch context, sign out |

### 12.4 Mobile Technical Requirements

| Requirement | Approach |
|---|---|
| **Offline tolerance** | Local draft persistence (MMKV/SQLite); queue mutations and replay with idempotency keys when connectivity returns |
| **Poor-network resilience** | Aggressive request timeouts, retry with backoff, optimistic UI with clear pending state |
| **Image handling** | Client-side compression before upload; presigned direct-to-storage upload; background upload task |
| **Push notifications** | Expo Notifications; categories for approvals, urgent alerts, delivery due; deep links into the target screen |
| **Deep linking** | Universal links from email digests to the exact request or alert |
| **Authentication** | Short-lived access token + refresh; biometric gate; remote session revocation |
| **Localisation** | Shared `i18n` catalogue with web; full RTL layout support tested on both platforms |
| **Accessibility** | Minimum 44 pt touch targets, dynamic type support, screen-reader labels |
| **App size** | Target under 30 MB download |
| **Cold start** | Under 2.5 s on a mid-range Android device |
| **Distribution** | TestFlight and Google Play internal testing during pilot; staged public release |
| **Crash / telemetry** | Sentry + PostHog with the same event taxonomy as web |

### 12.5 Mobile Delivery Sequence

| Sprint | Window | Deliverable |
|---|---|---|
| M1 | M11 | Flutter project, navigation, theming from shared tokens, auth + biometric, role-aware home |
| M2 | M11–M12 | Catalogue search, quick request flow, quantity and date inputs, draft persistence |
| M3 | M12 | Camera + barcode scan, image compression and upload, low-stock report |
| M4 | M12–M13 | Push notification infrastructure, deep links, my-requests timeline |
| M5 | M13 | Approval queue and approval detail with evidence summary |
| M6 | M13–M14 | Delivery confirmation, shortage and quality reporting |
| M7 | M14 | Offline queue hardening, RTL/Arabic pass, accessibility pass |
| M8 | M14–M15 | Store submission, staged rollout, pilot feedback iteration |

### 12.6 Mobile Out of Scope (Deliberate)

Quotation extraction review, match resolution, catalogue administration, basket optimisation configuration, reporting builders, integration setup, and billing. These are desk tasks; putting them on mobile would degrade both platforms.

---

## 13. AI Implementation Roadmap

### 13.1 Build Order and Rationale

| Order | Capability | Phase | Why here |
|---|---|---|---|
| 1 | **Product matching** | P1 | Nothing downstream is trustworthy without resolved identity |
| 2 | **Document extraction** | P1 | Primary data intake; removes the manual-entry ceiling |
| 3 | **Landed-cost normalisation** | P1 | Deterministic engine, not a model — but the source of the core insight |
| 4 | **Supplier recommendation** | P1–P2 | Rules and weighted scoring first; learned ranking later |
| 5 | **Anomaly detection** | P2–P3 | Needs a price-history baseline to define "abnormal" |
| 6 | **Forecasting** | P4 | Needs ≥6 months of usage history |
| 7 | **Negotiation assistant** | P4 | Needs supplier performance and volume history |
| 8 | **Procurement analyst (NL)** | P4 | Needs a complete, trustworthy data layer to ground answers |

### 13.2 Matching Approach (Phase 1)

A layered pipeline, cheapest and most certain signals first:

1. **Deterministic keys** — GTIN/EAN/UPC, supplier SKU, prior confirmed alias. High precision, resolves the majority of repeat lines.
2. **Lexical candidate generation** — `pg_trgm` similarity on normalised description text.
3. **Semantic candidate generation** — embedding similarity via `pgvector`.
4. **Feature scoring** — brand agreement, variant agreement, pack count, unit size, unit-of-measure compatibility, price plausibility versus history.
5. **Calibrated confidence** — score mapped to a calibrated probability; two thresholds: auto-accept and auto-reject, with the band between routed to human review.
6. **Feedback loop** — every human decision writes a `ProductAlias` and a labelled training example.

**Current MVP note:** until a labelled benchmark and calibration model are in place, the live
matching score is presented as a heuristic ranking/routing score, not a calibrated probability.

**Non-negotiable:** human review is a permanent component, not a temporary crutch. Target is to *shrink* the review band over time, never to remove the safety net.

### 13.3 Extraction Approach (Phase 1)

- **Primary:** AWS Bedrock (Claude 3 Haiku) with a strict JSON schema, field-level confidence, and page/region references for source highlighting.
- **Structured inputs:** Excel and CSV bypass the LLM and use a mapping-assisted parser.
- **Fallback:** Azure Document Intelligence for cost control, layout heuristics, and high-volume, low-variance documents.
- **Validation layer:** arithmetic checks (line total = qty × unit price; document total = sum of lines + VAT + delivery − discounts). Any failed check forces review regardless of model confidence.
- **Currency, decimal, and locale handling** validated explicitly — decimal-separator errors are a known leakage source.

### 13.4 Evaluation Harness (Built in Phase 0, Enforced from Phase 1)

| Element | Requirement |
|---|---|
| **Benchmark datasets** | Versioned; extraction set and matching set; grown continuously from review-queue corrections |
| **Metrics — extraction** | Field-level accuracy, document-level exact match, arithmetic-validation pass rate |
| **Metrics — matching** | Precision at auto-accept threshold, recall, review-band size, alias hit rate over time |
| **Metrics — calibration** | Expected calibration error; confidence must mean what it claims |
| **CI gate** | Any model, prompt, or threshold change runs the eval suite; a precision regression blocks merge |
| **Change log** | Every model version, prompt version, and threshold change recorded with its eval result |
| **Cost tracking** | Cost per document and cost per matched line tracked per release; unit economics depend on it |

### 13.5 AI Product Requirements (Apply to Every Capability)

Every AI-generated output surfaced to a user must carry:

- **Source data** — linked records, not prose references
- **Calculation** — visible and reproducible
- **Confidence** — calibrated, not decorative
- **Risk** — what could make this wrong
- **Validity period** — when this stops being true
- **Correction mechanism** — the user can override, and the override is learned from

---

# PART IV — EXECUTION

---

## 14. Team and Resourcing Plan

### 14.1 Role Ramp by Phase

| Role | P0 | P1 | P2 | P3 | P4 |
|---|:--:|:--:|:--:|:--:|:--:|
| Founder / Product | 1 | 1 | 1 | 1 | 1 |
| Full-stack engineer | — | 2 | 3 | 3 | 3 |
| AI / data engineer | 0.5 | 1 | 1 | 2 | 2 |
| Mobile engineer | — | — | 1 | 1 | 1 |
| Product designer | 0.5 | 1 | 1 | 1 | 1 |
| Procurement analyst / data operations | 1 | 1 | 1.5 | 2 | 2 |
| Customer success | — | 0.5 | 1 | 2 | 2 |
| Sales / partnerships | — | 0.5 | 1 | 2 | 2 |
| **Total FTE (approx.)** | **3** | **7** | **10.5** | **14** | **14** |

**Note on the analyst role:** a procurement/data operations person is required from Phase 0 and never removed. They run the review queue, own data quality, and are the reason customers trust the output. Treating this as a cost to eliminate would be a strategic error in the first two years.

### 14.2 Illustrative Cost Envelope

| Category | P0 (3 mo) | P1 (6 mo) | P2 (6 mo) | P3 (5 mo) |
|---|---:|---:|---:|---:|
| People | Low | Primary cost driver | Primary cost driver | Primary cost driver |
| AI inference | Minimal (manual tooling) | Moderate — scales with documents | Moderate | Moderate, optimised |
| Infrastructure | Negligible | Low | Low–moderate | Moderate |
| Third-party services (Stripe, Sentry, PostHog, email) | Negligible | Low | Low | Low |
| Security testing | — | — | One-off penetration test | Ongoing |

**Cost control levers:** structured-input fast paths that bypass Bedrock calls, aggressive caching of extraction results by document hash, tiered model selection (cheap model first, escalate on low confidence), and alias hits that avoid matching inference entirely.

---

## 15. Metrics Framework

### 15.1 KPI Tree

```
NORTH STAR
Verified savings + cost avoidance per active business per month
│
├── Value created
│   ├── Savings opportunities identified (£)
│   ├── Recommendations actioned (count, %)
│   ├── Realised saving per actioned recommendation (£)
│   └── Cost avoidance (price increases avoided, emergency orders prevented)
│
├── Decision quality  (enables value)
│   ├── Match precision at auto-accept threshold
│   ├── Extraction field accuracy
│   ├── Offer data completeness
│   ├── Offer freshness (% under 14 days)
│   └── Recommendation acceptance rate
│
├── Engagement  (enables decisions)
│   ├── Weekly active business rate
│   ├── Documents processed per business per week
│   ├── Products tracked per business
│   ├── Active users per account
│   └── % of purchases originating in-platform
│
├── Operational efficiency
│   ├── Review-queue items per 100 lines
│   ├── Review resolution time
│   ├── Procurement cycle time
│   └── Approval cycle time
│
└── Commercial
    ├── Value-to-fee ratio
    ├── Logo and net revenue retention
    ├── CAC payback period
    └── Expansion revenue
```

### 15.2 Metric Targets by Phase

| Metric | P1 exit | P2 exit | P3 exit | P4 exit |
|---|---:|---:|---:|---:|
| Match precision (auto-accept) | 92% | 94% | 96% | 97% |
| Extraction field accuracy | 90% | 93% | 95% | 96% |
| Review band (% lines to human) | ≤8% | ≤6% | ≤4% | ≤3% |
| Weekly active business rate | 45% | 60% | 65% | 70% |
| Actioned recommendations / business / month | 2 | 4 | 5 | 6 |
| Verified monthly value per customer | £180 | £350 | £500 | £700 |
| Value-to-fee ratio | 3.0× | 3.4× | 4.0× | 4.5× |
| Purchases originating in-platform | — | 70% | 80% | 85% |
| Emergency-order rate vs. baseline | — | −15% | −25% | −40% |
| Logo retention (annualised) | — | 90% | 92% | 93% |

### 15.3 Instrumentation Requirements

- Event taxonomy defined **before** Phase 1 build, shared across web, mobile, and backend.
- Every recommendation emits view, action, and outcome events — this is the model feedback loop, not just analytics.
- Review-queue throughput and resolution time instrumented from R1.2 onward.
- A per-tenant "value report" query must be runnable on demand for any customer conversation.

---

## 16. Risk Register

Severity and likelihood are illustrative planning assessments (1–5 scale).

| # | Risk | Sev | Lik | Mitigation | Owner | Phase |
|---:|---|:--:|:--:|---|---|---|
| 1 | **Incorrect product matching** contaminates savings and destroys trust | 5 | 4 | Confidence thresholds, permanent human review, GTIN support, alias learning, match audit trail, CI eval gate | AI lead | P1+ |
| 2 | **Savings baseline disputed** by customer | 5 | 3 | Baseline policy decided and documented in P0; conservative default; full evidence trail; customer-configurable | Product | P0 |
| 3 | **Price data stale or unavailable** | 4 | 4 | Multiple source channels, freshness scoring, explicit timestamps, quotation-first strategy | Data ops | P1+ |
| 4 | **Customers will not upload documents** | 5 | 3 | Email forwarding, concierge onboarding, WhatsApp export guidance, do-it-for-them first month | Customer success | P0–P1 |
| 5 | **Over-broad market scope** dilutes product | 4 | 3 | Single wedge discipline; feature requests outside the wedge logged, not built | Founder | All |
| 6 | **Insufficient history** makes forecasting weak | 3 | 4 | Forecasting deferred to P4; rules-based interim; uncertainty always shown | AI lead | P4 |
| 7 | **Low actionability** — interesting but not payable | 4 | 3 | Every insight attached to an executable action with expected value; measure action rate | Product | All |
| 8 | **Integration burden** slows delivery | 3 | 3 | CSV/email first; connector framework; build only on 3+ customer demand | Engineering lead | P3 |
| 9 | **AI inference cost** erodes gross margin | 3 | 3 | Tiered models, hash caching, structured-input fast paths, per-document cost tracking | Engineering lead | P1+ |
| 10 | **Review-queue operations do not scale** | 4 | 3 | Alias learning to shrink the band; throughput metrics; queue prioritised by financial impact | Data ops | P1+ |
| 11 | **Pricing misaligned with value** (count-based tiers vs. spend-driven value) | 3 | 4 | Revisit plan gating after 10 paying customers; consider tracked-spend dimension | Founder | P1–P2 |
| 12 | **Mobile scope creep** toward web parity | 3 | 3 | Written mobile scope charter; three-jobs rule enforced in review | Product | P2 |
| 13 | **Data security incident** | 5 | 2 | Tenant isolation with RLS, encryption, least privilege, audit logs, penetration test, incident runbook | Engineering lead | P1+ |
| 14 | **Key-person dependency** on founder for domain knowledge | 3 | 4 | Document decisions as ADRs; train analyst; record customer-review methodology | Founder | All |
| 15 | **Supplier resistance** to being compared | 2 | 3 | Position as buyer-side tool; no public price publication; no supplier shaming | Founder | P2+ |
| 16 | **Silent data loss in ingestion** — a document fails and leaves no trace (seen: Arabic attachment names lost emails, PR #90) | 5 | 3 | Every failure leaves a visible log or review item; alert on repeated job failures | Engineering lead | All |
| 17 | **Locale drift** — dates, digits, number formats and RTL tables from Arabic-language suppliers misread (seen: DD/MM dates refused whole quotes, #96; RTL tables merged lines, #100; UTC date shift, #88) | 5 | 4 | Fixtures from real regional documents; unreadable values go to review, never guessed | Engineering lead | All |
| 18 | **Unit-of-measure errors** — pack vs base unit mixed in estimates (seen: request estimate ~9× too low, #110) | 5 | 3 | One rule: quantities and prices per pack (ADR-020); tests on pack sizes > 1 | Engineering lead | All |
| 19 | **Service built but not deployed** (seen: optimiser worker had no deploy, #108; on 2026-10-18 the report-schedule, offer-refresh, export, digest, webhook and sync workers still had none, see Delivery Status) | 4 | 3 | Every service has a deploy workflow and a liveness check; hosted walkthrough per release | Engineering lead | All |
| 20 | **Hosted AI configuration differs from tests** (seen: stub embedding on hosted, exact names scored 55%) | 4 | 3 | Record provider settings per environment; decide the hosted embedding provider | AI lead | P1+ |
| 21 | **Database pooler incompatibility** (seen: prepared statements failed through Supabase's transaction pooler, #87) | 4 | 3 | All connections through `db.connect` with prepared statements off; integration tests against the pooler | Engineering lead | All |

---

## 17. Dependencies and Critical Path

### 17.1 Critical Path

```
Savings baseline policy decided (P0)
        ↓
Labelled benchmark datasets (P0)
        ↓
Domain model + unit/pack normalisation schema (R1.0–R1.1)
        ↓
Extraction pipeline + review queue (R1.2)
        ↓
Matching engine meeting precision gate (R1.3)
        ↓
Landed-cost engine + Smart Compare (R1.4)
        ↓
Savings ledger with verified records (R1.5)   ← GATE G1
        ↓
Organisation model: branches, budgets, roles (R2.0)
        ↓
Requests + approvals (R2.1)
        ↓
Mobile app (R2.2–R2.3)                        ← GATE G2
        ↓
Email ingestion + integrations (P3)           ← GATE G3
        ↓
Forecasting + predictive procurement (P4)
```

### 17.2 Hard Dependencies

| Dependent item | Requires | Consequence if violated |
|---|---|---|
| Any AI accuracy claim | Benchmark datasets from P0 | No definition of done; accuracy becomes opinion |
| Smart Compare | Unit/pack normalisation + landed-cost engine | Comparisons are wrong but look right |
| Savings ledger | Baseline policy + outcome capture | Savings unverifiable; north star unmeasurable |
| Basket optimiser | Multiple concurrent normalised offers per SKU | Optimiser has nothing to optimise |
| Approvals | Branches, cost centres, budgets, roles | Approval rules have no subject |
| Mobile approvals | Web approval engine complete | Duplicate divergent logic |
| Forecasting | ≥6 months usage history per tenant | Forecasts are noise; trust damaged |
| Anomaly detection | Price-history baseline | False positives train users to ignore alerts |
| Procurement analyst | Complete, trusted data layer | Ungrounded answers; credibility loss |

### 17.3 External Dependencies

- AWS Bedrock and Azure Document Intelligence availability, pricing, and data-retention terms
- Accounting and POS partner API access and approval processes
- App Store and Google Play review timelines (build 2–3 weeks buffer into P2 release)
- Payment provider onboarding in the launch region
- Legal review of supplier-data usage and web-sourced pricing in the launch jurisdiction

---

## 18. Go-to-Market Alignment

| Phase | GTM motion | Primary asset | Channel focus |
|---|---|---|---|
| **P0** | Founder-led, concierge spend review | Spend Review Report | Direct outreach, personal network, SME communities |
| **P1** | Design-partner conversion, self-serve pilot | Live product + verified savings evidence | Accountants (highest-attractiveness channel), SME communities |
| **P2** | Repeatable sales with proof cases | Case studies with verified £ saved | Accountants, POS partners, wholesalers |
| **P3** | Partner-led and integration-marketplace driven | Integration listings, partner API | Accounting and POS marketplaces, referral programme |
| **P4** | Expansion and category widening | Benchmark insights, predictive value | Partner channel + targeted outbound |

**Funnel model (illustrative, per 100 leads):** 100 leads → 40 spend reviews → 20 pilots → 11 paid → 5 expanded accounts.

**Channel attractiveness (illustrative):** accountants 91 · POS partners 88 · wholesalers 82 · SME communities 76 · targeted outbound 69 · paid digital 48.

**Pricing at launch (illustrative, to be validated in P0):**

| Plan | Fee | Quotas | Headline capability |
|---|---:|---|---|
| **Free** | £0 | 1 user · 20 products · 2 suppliers | Manual uploads, monthly report |
| **Starter** | £39/mo | 100 products · 5 suppliers | Alerts, basic extraction, savings dashboard |
| **Team** | £99/mo | 500 products · 10 users | Approvals, branches, basket optimisation |
| **Growth** | £249/mo | 2,000 products | Integrations, advanced AI, API, custom policies |

Plans are gated on **product, supplier, and user counts** while value is driven by **tracked spend and decision volume** — the tension recorded as risk 11. Revisit gating after 10 paying customers and consider tracked spend as the primary dimension.

**Illustrative unit economics per plan:**

| Plan | MRR | Serving cost | Gross margin | Indicative customer value / mo |
|---|---:|---:|---:|---:|
| Starter | £39 | £9 | 76% | £180 |
| Team | £99 | £18 | 81% | £520 |
| Growth | £249 | £42 | 84% | £1,450 |

These margins are the basis of the >75% subscription gross-margin objective in section 1.11.

**Illustrative revenue mix at maturity:** subscriptions 72% · API and integrations 13% · partner revenue 9% · premium services 6%.

**First pilot market (added v1.1, 2026-10):** the first pilot is a multi-branch food-service or retail
business in **Egypt**, quoting and budgeting in **EGP**, with Arabic-first users and suppliers. The
GBP figures in this section and in §15.2 are the original illustrative baseline and have not been
re-priced for Egypt; pilot terms and pricing are in `docs/gtm/first-customer-gtm-plan.md` and
`docs/gtm/gtm-execution-plan.md`. Requirements this market added to the product: a home currency per
workspace (spec 022), no guessed currency on extraction, DD/MM dates, Arabic-Indic digits, Arabic
right-to-left quote tables, Arabic file names, and Arabic supplier emails.

**Other revenue opportunities (post-P2):** API fees, integration fees, partner revenue, premium services, white-label licensing, supplier analytics, referral commission. Sponsored placement is permissible only if clearly labelled and never allowed to influence ranking — otherwise it contradicts the buyer-side positioning and the non-goals in section 1.9.

---

## 19. Consolidated Timeline

| Month | Business track | Product / engineering track | Milestone |
|---|---|---|---|
| M0–M1 | Recruit 5–10 wedge businesses; interviews | — | Wedge validated |
| M1–M2 | Manual spend reviews; weekly recommendations | Benchmark dataset labelling | Savings evidence collected |
| M2–M3 | Paid pilot agreements; pricing tests | PRD, domain model, ADRs, baseline policy | **G0 gate** |
| M3–M4 | Design-partner cadence established | R1.0 foundation, R1.1 catalogue + suppliers | Platform skeleton live |
| M5–M6 | Continue concierge in parallel | R1.2 ingestion + extraction + review | First automated extraction |
| M6–M7 | Pilot customers on product | R1.3 matching + landed cost | Precision gate met |
| M7–M8 | Convert pilots to paid | R1.4 compare + intelligence | First in-product decision |
| M8–M9 | Case-study capture | R1.5 savings ledger, billing, launch prep | **G1 gate — MVP live** |
| M9–M11 | Accountant channel pilots | R2.0 org model, R2.1 requests + approvals | Workflow live on web |
| M11–M13 | Multi-branch customer acquisition | R2.2–R2.3 mobile MVP + approvals | Mobile in stores |
| M13–M15 | Repeatable sales motion | R2.4 optimiser + supplier IQ, R2.5 hardening | **G2 gate** |
| M15–M18 | Partner integrations marketing | R3.0–R3.2 email ingestion, accounting, POS | Automated data inflow |
| M18–M20 | Referral and marketplace listings | R3.3–R3.4 reconciliation, API beta | **G3 gate** |
| M20–M24 | Expansion revenue focus | R4.0–R4.3 forecasting, risk, analyst, RFQ | Predictive procurement live |

---

## 20. Assumptions and Open Decisions

### 20.1 Assumptions Underpinning This Roadmap

1. Recurring standardised consumables is the correct first wedge.
2. Small businesses will share invoices and quotations once trust is established.
3. Document extraction accuracy of ≥90% on priority fields is achievable with Bedrock/Azure Document Intelligence.
4. A human review layer is commercially sustainable at the stated price points.
5. Accountants are a viable and willing distribution channel.
6. Ordering can remain external through Phase 2 without blocking value.
7. All quantitative targets in this document are planning assumptions pending validation.

### 20.2 Decisions Required Before Phase 1 Engineering Begins

| # | Decision | Blocks | Target |
|---:|---|---|---|
| 1 | **Savings baseline policy** — which baseline, and is it customer-configurable? | Savings ledger schema, entire value narrative | End M2 |
| 2 | **Launch region, currency set, tax model** | Landed-cost engine, all monetary fields | End M2 |
| 3 | **Does ordering happen in-platform?** | Whether `PurchaseOrder` is transactional with supplier-side state | End M2 |
| 4 | **Is stock owned or mirrored?** | Stock-signal model; risk of drifting into inventory management | End M2 |
| 5 | **Auto-accept confidence threshold** and acceptable launch precision | Matching pipeline, review-queue sizing, ops headcount | End M3 |
| 6 | **Bilingual scope at launch** — English only, or English + Arabic day one? | Design system, content pipeline, QA effort | End M2 |
| 7 | **Build platform** — Supabase for Phase 1 (decided) | Infrastructure work in R1.0 | End M2 |
| 8 | **WhatsApp ingestion** — direct integration or file-based export? | Ingestion layer scope | End M4 |

**Status of these decisions (2026-10-18):** (2) first region Egypt, currency EGP as the workspace home
currency (spec 022); (5) fuzzy matches do not auto-accept until scores are calibrated (PR #59);
(6) English and Arabic, both shipped with RTL; (7) Supabase, in use; (8) manual capture now, direct
WhatsApp integration deferred (spec 013). (1) A baseline policy is stored on each saving, but it is not
customer-configurable. Decisions 3 and 4 have not been revisited in this document.

### 20.3 Deliberately Unresolved (Revisit at Gates)

- Whether pricing should shift from count-based to spend-based tiers (**revisit at G1**)
- Whether cross-tenant benchmarking becomes a product (**revisit at G3**; requires explicit customer consent design)
- Whether in-platform payment facilitation is pursued (**revisit at G3**)
- Which second vertical to expand into (**revisit at G2**)

---

## 21. Immediate Next Actions

### 21.1 Current next actions (2026-10-18)

| # | Action | Where tracked |
|---:|---|---|
| 1 | Finish the hosted demo tenant and record the demo video | `docs/gtm/video/production-tracker.md` (PP-5, PP-6) |
| 2 | After the demo video is recorded (its flow needs none of them), deploy the background workers hosted lacks (report schedules, offer refresh, exports, digests, webhooks, sync) as **one** combined jobs container — one image/entrypoint serving all these low-volume queues, one deploy workflow modelled on #108, its env documented in `docs/operations/runbook.md` — then fix the open demo findings (22, 23, 25–30; 23 needs the owner's savings-baseline decision). The basket-split read (finding 21) was fixed in #131 | Delivery Status; `docs/gtm/demo-tenant/README.md` |
| 3 | Run real Egyptian supplier quotes through extraction | `specs/022-home-currency-readiness/tasks.md` T015 (Jira PP-3) |
| 4 | Reach 20 prospect conversations and sign the first pilot | `docs/gtm/gtm-execution-plan.md` (PP-11, PP-13, PP-10) |
| 5 | Choose what to build from the partial and deferred scope above, driven by the pilot | This document, Delivery Status |

### 21.2 Original Phase 0 actions (2026-09-10, kept for history)

| # | Action | Output | Owner |
|---:|---|---|---|
| 1 | Recruit the first 5 wedge businesses | Signed discovery participation | Founder |
| 2 | Write and run the customer interview guide | 15 completed interviews | Founder |
| 3 | Deliver 3 manual spend reviews | 3 Spend Review Reports with quantified savings | Founder + analyst |
| 4 | Decide and document the savings baseline policy | Signed decision record | Founder |
| 5 | Build the product-matching benchmark dataset | 500+ labelled pairs | Analyst |
| 6 | Build the quotation extraction test dataset | 300+ labelled line items | Analyst |
| 7 | Write the Phase 1 PRD and domain model | PRD + ERD + ADR set | Founder + engineering lead |
| 8 | Close the eight pre-engineering decisions in §20.2 | Decision log | Founder |

**Do not begin Phase 1 engineering until items 4, 5, 6, and 8 are complete.** Building the matching and extraction core without a benchmark and a baseline policy means building without a definition of correct.

---

## 22. One-Paragraph Roadmap Summary

ProcurePilot begins with three months of concierge validation that proves savings by hand, produces the labelled datasets that define AI correctness, and closes the schema-determining decisions — above all the savings baseline policy. Phase 1 then builds a web-first intelligence MVP whose only job is to reproduce that concierge output reliably: document ingestion, AI extraction with human review, product matching with calibrated confidence, a versioned landed-cost engine, Smart Compare, and an auditable savings ledger. Phase 2 converts the tool into the customer's purchasing system of record by adding branches, budgets, requests, approvals, supplier performance, full basket optimisation, and a deliberately narrow mobile app serving three jobs — request, approve, confirm. Phase 3 removes manual data entry through email ingestion, accounting and POS integrations, order reconciliation, and a partner API. Phase 4 turns history into foresight with forecasting, supplier risk, negotiation briefs, automated sourcing, and a grounded procurement analyst. Each phase ends in a hard gate, every recommendation carries evidence, confidence, risk, and validity, and no phase proceeds on optimism instead of measured accuracy and verified customer value.

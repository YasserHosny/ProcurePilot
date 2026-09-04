# ProcurePilot — Product Requirements Document (PRD)

> Source of truth for product functionality from Phase 1 through Phase 2.  
> Companion to the [Master Roadmap](../roadmap/procurepilot_roadmap.md).

---

## 1. Goals

1. Replace manual quotation comparison with AI-assisted, evidence-backed purchasing decisions.
2. Make every saving auditable back to the source quotation and purchase record.
3. Become the system of record for purchasing decisions by Phase 2 (requests, approvals, outcomes).
4. Keep a human reviewer in the loop for every high-stakes AI inference.

## 2. Target Personas

- **Owner / GM** — economic buyer; cares about verified savings and spend control.
- **Buyer / Operations Officer** — power user; runs the procurement process.
- **Branch / Store Manager** — creates purchase requests away from a desk.
- **Approver** — owner or delegated manager; approves requests under 30 seconds.
- **Procurement Analyst** — reviews data quality and feeds the review queue.

## 3. Functional Requirements

### 3.1 Auth, Tenant & Organisation

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F1 | Multi-tenant accounts | Every row carries `tenant_id`; RLS enforced; one signup creates a tenant | P1 |
| F2 | Role-based access | Owner, buyer, branch manager, approver, viewer roles with explicit permissions | P1 |
| F3 | User invitation | Owner invites users and assigns roles; invite link enforces role on first login | P1 |
| F4 | Organisation model | Branches, cost centres, budgets, and approval thresholds configurable by owner | P2 |

### 3.2 Catalogue & Suppliers

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F5 | Product master | Create, edit, archive products; define base unit, pack size, GTIN, substitutes | P1 |
| F6 | Supplier profiles | Name, terms, lead time, MOV, delivery fee, reliability score, status | P1 |
| F7 | CSV import | Upload catalogue/supplier CSV; validate before commit; error report with row numbers | P1 |
| F8 | Product aliases | System learns supplier description → canonical product per tenant | P1 |

### 3.3 Document Ingestion & Extraction

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F9 | Multi-format upload | Accept PDF, image, Excel, CSV; presigned direct-to-storage upload | P1 |
| F10 | AI extraction | Extract header and line fields with field-level confidence and source region | P1 |
| F11 | Validation layer | Arithmetic checks force review if line totals or document totals do not reconcile | P1 |
| F12 | Review queue | Side-by-side document and fields; inline correction; keyboard navigation | P1 |
| F13 | Versioned quotations | Re-quoted documents linked; prior versions visible | P1 |

### 3.4 Matching & Normalisation

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F14 | Product matching | Propose candidate products with calibrated confidence and reason codes | P1 |
| F15 | Human resolution | Reviewer picks match, marks different pack/variant, or creates new product | P1 |
| F16 | Unit normalisation | Compare offers on a common base unit and landed cost | P1 |
| F17 | Auto-accept threshold | Precision at auto-accept ≥ 92% on held-out benchmark | P1 |

### 3.5 Smart Compare & Recommendations

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F18 | Landed-cost comparison | Show total landed cost, unit price, VAT, delivery, discounts, lead time | P1 |
| F19 | Historical context | Display last paid, average paid, best historical price per product | P1 |
| F20 | Recommendations | Surface recommended action with evidence, confidence, risk, validity window | P1 |
| F21 | Basket optimisation | Allocate quantities across suppliers respecting MOV, tiers, urgency, preference | P2 |

### 3.6 Savings Ledger

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F22 | Outcome capture | Record what was actually ordered, delivered, and paid | P1 |
| F23 | Verified savings | Ledger row shows baseline policy, baseline value, actual value, delta, evidence refs; immutable once verified | P1 |
| F24 | Export | Export ledger to Excel and PDF with evidence summary | P1 |

### 3.7 Workflow (Phase 2)

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F25 | Purchase requests | Branch manager creates request with product, qty, required-by date, branch, cost centre | P2 |
| F26 | Approval routing | Request routes by threshold, branch, and delegation rules; audit log per step | P2 |
| F27 | Budget checks | Block or warn if request exceeds branch/cost-centre budget | P2 |
| F28 | Policy engine | Preferred/blocked suppliers, spend limits, exception justification | P2 |

### 3.8 Mobile (Phase 2)

| ID | Requirement | Acceptance Criteria | Phase |
|---|---|---|---|
| F29 | Quick request | Search catalogue, scan barcode, attach photo, choose quantity, submit | P2 |
| F30 | Approval decision | Card shows amount, branch, budget impact, recommended supplier, expected saving; one-tap approve/reject/comment | P2 |
| F31 | Delivery confirmation | Confirm quantity received, flag shortage/quality issue, attach photo | P2 |
| F32 | Offline tolerance | Drafts persist locally and sync when connectivity returns; idempotency prevents duplicates | P2 |

## 4. Non-Functional Requirements

- **Performance** — dashboard FCP < 1.5 s; comparison grid recalculation < 150 ms; extraction p95 < 45 s.
- **Accessibility** — WCAG 2.1 AA across web and mobile.
- **Responsive design** — the web SPA must be usable on mobile (< 600px), tablet (600–959px), and desktop (≥ 960px) viewports. Layouts collapse gracefully with no horizontal overflow. CSS logical properties are mandatory for RTL support.
- **Security** — TLS 1.3 in transit, AES-256 at rest, tenant isolation via RLS, no customer data used for model training.
- **Reliability** — 99.5% uptime in Phase 1; 99.9% by Phase 3.
- **Localisation** — English + Arabic RTL from day one; multi-currency and configurable tax models.
- **Database** — hosted Supabase exclusively; no local database build. Migrations are forward-only SQL files; RLS enforced on all tenant-scoped tables.

## 5. Constraints

- Ordering remains external through Phase 2 unless validated otherwise.
- Mobile deliberately avoids parity with the web console.
- Human review is a permanent safety net, not a temporary crutch.

## 6. Open Questions

1. Should savings baseline be customer-configurable or a single conservative default?
2. Does WhatsApp ingestion require a direct integration or manual file export?
3. Which accounting/POS providers are pilot priorities for Phase 3?

# ProcurePilot — Speckit Orchestration Plan

> Step-by-step entry point for using Speckit across all phases.  
> The [Master Roadmap](roadmap/procurepilot_roadmap.md) is the constitution/plan source; this file translates it into Speckit-sized specification chunks.

---

## 1. How to Use This Plan

1. Feed the relevant section below to Speckit's `/constitution`, `/plan`, or `/specify` command as instructed.
2. Each **Speckit chunk** contains:
   - **Goal** — what must be true after the chunk.
   - **Inputs** — source files to read first.
   - **Specification** — what to specify/implement.
   - **Acceptance** — how to verify the output.
3. Do **not** run Phase 2+ chunks until the preceding **stage gate** is passed.

---

## 2. `/constitution` — Why We Are Building This

Use the following as the `/constitution` input.

> **Vision:** Every small business should buy as well as a large enterprise — with the same price visibility, supplier leverage, and decision evidence, without the same cost, staff, or complexity.
> **Mission:** Turn fragmented supplier information into trusted, comparable, actionable purchasing decisions — and prove the money saved.
> **Thesis:** Noisy supplier document → AI extraction → product matching → unit/pack normalisation → landed-cost engine → recommendation → approval/order → outcome capture → verified saving + model feedback.
> **Strategic pillars:** trustworthy data before clever AI; every insight ends in an action; verified value not claimed value; depth in one wedge before breadth.
> **Target users:** small-business owners, buyers, branch managers, approvers.
> **Non-goals:** consumer deals site, public supplier marketplace, ERP replacement, autonomous purchasing.
> **North-star metric:** verified savings + cost avoidance per active business per month.

**Inputs:** `docs/roadmap/procurepilot_roadmap.md` §1-2.

---

## 3. `/plan` — Phased Delivery

Use the following as the `/plan` input.

### Phase 0 — Concierge Validation (M0–M3)
- Goal: prove the problem, the saving, and willingness to pay with almost no software.
- Output: 15 interviews, 5–10 Spend Review Reports, labelled datasets, baseline policy.
- Gate G0: ≥3 paid pilots, documented savings in ≥5 businesses, labelled dataset built.
- Speckit scope: **none** — no code generation in Phase 0.

### Phase 1 — Procurement Intelligence MVP, Web (M3–M9)
- Goal: software reproduces concierge output — trusted extraction, matching, normalisation, comparison, savings ledger.
- Releases: R1.0 foundation → R1.1 catalogue+suppliers → R1.2 ingestion+extraction → R1.3 matching+normalisation → R1.4 compare+intelligence → R1.5 value proof+launch readiness.
- Gate G1: extraction/matching targets met, ≥10 verified savings, ≥8 paying customers on self-serve.
- Speckit scope: **full coding plan** (chunks 4.1–4.6 below).

### Phase 2 — Team Workflow + Mobile (M9–M15)
- Goal: become the system of record for purchasing decisions.
- Releases: R2.0 org model → R2.1 requests+approvals → R2.2–R2.3 mobile MVP+approvals → R2.4 optimisation+supplier IQ → R2.5 reporting+hardening.
- Gate G2: workflow-origination ≥70%, mobile adoption target met, retention ≥90%.
- Speckit scope: **plan only until G1 is passed**; code chunks may be sketched but not executed.

### Phase 3 — Connected Operations (M15–M20)
- Goal: remove manual data entry via email ingestion, accounting/POS integrations, partner API.
- Gate G3: integration-sourced data ≥60%, ≥6 months history for ≥30 accounts.
- Speckit scope: **plan only until G2 is passed**.

### Phase 4 — Predictive Procurement (M20–M24+)
- Goal: proactive recommendations, forecasting, negotiation assistant, grounded analyst.
- Gate G3 passed required.
- Speckit scope: **plan only until G3 is passed**.

---

## 4. `/specify` — Phase 1 Coding Chunks

Run these chunks sequentially. Each chunk should produce code, tests, and docs that pass its acceptance criteria before the next chunk starts.

### Chunk 4.1 — Foundation (R1.0)
**Goal:** Working monorepo, CI/CD, environments, auth, multi-tenancy, RBAC skeleton, design system v1, app shell.

**Inputs:**
- `docs/architecture/tech-stack-blueprint.md`
- `docs/architecture/adrs.md`
- `docs/architecture/engineering-spec.md` §1-2, §7
- `docs/operations/deployment-plan.md`

**Specify / implement:**
1. Repo layout: `apps/web`, `apps/mobile`, `apps/api`, `packages/*`, `services/*`, `ml/*`, `infra/`, `.github/workflows/`, `docker-compose.yml`.
2. FastAPI monolith skeleton with health endpoint.
3. Angular app shell with routing, i18n stubs, and Supabase Auth integration.
4. CI/CD workflows for backend/frontend and Bunny Magic Container deploy stubs.
5. Terraform/Bunny infrastructure skeleton.

**Acceptance:**
- `docker compose up --build` starts backend + frontend + Supabase locally.
- `/api/health` returns `{"status":"ok"}`.
- GitHub Actions build passes.
- A test user can sign up and the JWT carries `tenant_id`.

---

### Chunk 4.2 — Catalogue + Suppliers (R1.1)
**Goal:** Tenant can manage products, suppliers, units/packs, and import catalogue via CSV.

**Inputs:**
- `docs/product/prd.md` §3.1-3.2
- `docs/architecture/data-dictionary.md` (Tenant, User, CanonicalProduct, TenantProduct, Unit, PackDefinition, Supplier)
- `docs/architecture/api-specification.md` §Catalogue

**Specify / implement:**
1. DB migrations for tenant, user, canonical/tenant products, units/packs, suppliers.
2. RLS policies enforcing `tenant_id`.
3. CRUD endpoints for products and suppliers.
4. CSV import endpoint with validation and error report.
5. Angular screens: Catalogue list, Product create/edit, Supplier list/profile, CSV import wizard.

**Acceptance:**
- Unit tests for CSV validation cover happy path and malformed rows.
- Integration tests verify tenant isolation (user A cannot read user B's products).
- Web UI supports creating a product with pack normalisation displayed.

---

### Chunk 4.3 — Ingestion + Extraction (R1.2)
**Goal:** Users can upload documents; AI extracts fields with confidence; review queue supports correction.

**Inputs:**
- `docs/product/prd.md` §3.3
- `docs/product/user-stories.md` US-001 to US-004
- `docs/architecture/engineering-spec.md` §2.2
- `docs/architecture/api-specification.md` §Documents, §Quotations, §Review Queue
- `docs/quality/test-strategy.md` §4 AI Evaluation

**Specify / implement:**
1. Supabase Storage presigned upload flow.
2. `services/extraction-worker` with Bedrock primary + Azure DI fallback.
3. Document metadata, quotation header, and line storage.
4. Validation layer (arithmetic checks, locale handling).
5. Review queue API and UI (side-by-side document + fields, inline correction, keyboard flow).

**Acceptance:**
- Extraction field accuracy ≥90% on held-out benchmark.
- Arithmetic mismatches always force review.
- Review UI allows correcting fields and re-running extraction.

---

### Chunk 4.4 — Matching + Normalisation (R1.3)
**Goal:** Lines are matched to products with calibrated confidence; landed cost is computed deterministically.

**Inputs:**
- `docs/product/prd.md` §3.4
- `docs/product/user-stories.md` US-005 to US-008
- `docs/architecture/engineering-spec.md` §2.3, §5.1
- `docs/architecture/api-specification.md` §Review Queue, §Offers & Compare

**Specify / implement:**
1. Matching pipeline: deterministic keys → `pg_trgm` → `pgvector` → feature scoring → calibrated confidence.
2. `ProductAlias` learning from human decisions.
3. Unit/pack normalisation engine.
4. Landed-cost engine with rule versioning.
5. Match resolution UI with candidate list, reasons, and keyboard shortcuts.

**Acceptance:**
- Precision at auto-accept threshold ≥92% on benchmark.
- Review band ≤8%.
- Landed-cost computation is deterministic and replayable.

---

### Chunk 4.5 — Smart Compare + Intelligence (R1.4)
**Goal:** Users see comparable offers, historical context, and AI recommendations.

**Inputs:**
- `docs/product/prd.md` §3.5
- `docs/product/user-stories.md` US-009 to US-011
- `docs/architecture/engineering-spec.md` §5.2
- `docs/architecture/api-specification.md` §Offers & Compare, §Baskets
- `docs/product/ui-mockup-prompts.md` §W6 Smart Compare

**Specify / implement:**
1. `GET /offers/compare` endpoint with recommendation scorer.
2. Price-history chart and product intelligence page.
3. Smart Compare grid with live quantity recalculation.
4. Basic basket split view (two suppliers) using OR-Tools.
5. Actionable alerts inbox v1.

**Acceptance:**
- Compare grid recalculation < 150 ms.
- Recommendation shows evidence, confidence, risk, validity period.
- 80% of comparisons accepted without manual correction.

---

### Chunk 4.6 — Value Proof + Launch Readiness (R1.5)
**Goal:** Savings ledger, outcome capture, exports, onboarding, billing, Arabic/RTL.

**Inputs:**
- `docs/product/prd.md` §3.6
- `docs/architecture/api-specification.md` §Savings, §Reports
- `docs/operations/runbook.md` §Deployment Day Checklist
- `docs/quality/test-strategy.md` §5 E2E, §7 Accessibility

**Specify / implement:**
1. Savings ledger entity and API; outcome capture flows.
2. Excel/PDF export service.
3. Onboarding flow and plan gating with Stripe.
4. Arabic/RTL pass and accessibility audit.
5. Performance optimisation and security review.

**Acceptance:**
- E2E test: self-onboard → upload → extract → compare → record purchase → verify saving.
- Savings ledger is immutable once verified.
- WCAG 2.1 AA pass with automated axe-core scan.
- G1 gate criteria met.

---

## 5. Future Phase Sketches (Do Not Code Yet)

### Phase 2 chunks
- 5.1 Organisation model (branches, cost centres, budgets, roles).
- 5.2 Requests + approvals web.
- 5.3 Flutter app shell + auth + home.
- 5.4 Mobile quick request + scan + low-stock report.
- 5.5 Mobile approvals + delivery confirmation.
- 5.6 Advanced basket optimiser + supplier scorecards.

### Phase 3 chunks
- 6.1 Email ingestion.
- 6.2 Accounting integration #1.
- 6.3 POS/inventory integration.
- 6.4 Order tracking + three-way match.
- 6.5 Partner API beta + webhooks.

### Phase 4 chunks
- 7.1 Demand forecasting + reorder recommendations.
- 7.2 Supplier risk model + negotiation briefs.
- 7.3 Grounded procurement analyst.
- 7.4 Automated RFQ sourcing.

---

## 6. Cross-Cutting Inputs for Every Chunk

- `docs/product/prd.md` — functional requirements and constraints.
- `docs/product/user-stories.md` — persona-driven acceptance scenarios.
- `docs/architecture/api-specification.md` — endpoint contract.
- `docs/architecture/data-dictionary.md` — entities and fields.
- `docs/product/ui-mockup-prompts.md` — screen prompts for mockup generation.
- `docs/quality/test-strategy.md` — testing expectations.
- `docs/operations/deployment-plan.md` — CI/CD and environment expectations.
- `docs/operations/runbook.md` — operational expectations.

---

## 7. Gate Conditions Before Phase 2

Do not run Speckit `/specify` for Phase 2 until:
- Matching precision ≥92% and extraction accuracy ≥90% on held-out sets.
- ≥10 verified savings recorded in the ledger.
- ≥8 paying customers on self-serve product.
- Savings baseline policy is documented and signed off.

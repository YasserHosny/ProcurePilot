# R4.2 Grounded Procurement Analyst Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tenant-scoped, evidence-backed natural-language question-answering surface over
existing ProcurePilot data, with every numeric answer citing a source record and showing its
calculation, while keeping G3 explicitly unmet.

**Architecture:** A new `analyst` module in `apps/api` with three layers: (1) a pure, deterministic
retrieval-and-calculation service per supported question category (spend/savings, supplier
risk, orders/quotations, reorder forecasts) that queries existing tenant tables directly — no new
source of truth is created; (2) a thin question-understanding step that calls the existing Bedrock/
Claude provider (already used for document extraction, per ADR-004/ADR-014) purely to classify a
free-text question into a supported category plus structured entities (supplier, product, date
range) — it never generates the answer's facts or numbers; (3) conversation/turn persistence that
stores the question, resolved category+entities, the deterministic answer, its citations, and an
optional deep link to an existing actionable surface (FR-003A — this is how R4.2 satisfies
Constitution Principle IV's "every insight carries an executable next step" without creating any
new action capability) as immutable rows. A focused Angular chat-style feature presents the
conversation with inline citations, calculations, and next-step links, without any path to
autonomous purchasing.

**Tenant-scoping note (FR-007):** the retrieval layer's own queries (Task 2) must scope every
lookup by the resolved category's entities *and* the caller's tenant — RLS on
`analyst_conversation`/`analyst_turn` protects the conversation rows themselves, but does not by
itself guarantee that a question referencing another tenant's supplier/product name resolves to
"no data" rather than leaking a match. Existing tenant-scoped tables already carry their own RLS,
so this should be inherited, not bespoke — Task 2 must include a test proving it.

**Tech Stack:** Python 3.12, FastAPI, psycopg, Supabase Postgres RLS, Pydantic v2, the existing
Bedrock/Claude client already wired into `services/extraction-worker` (reused, not reintroduced),
Angular 19, RxJS, ngx-translate.

**Decision — reuse the existing LLM provider, don't add a new one:** ADR-004 and ADR-014 already
establish AWS Bedrock (Claude 3 Haiku) as the extraction-worker's primary LLM provider with an
Azure fallback chain. R4.2's question-understanding step is a new *use* of that same provider
(intent + entity classification, not document extraction), not a new provider decision. Task 3
records this as an ADR-017 addendum rather than re-litigating the provider choice.

---

### Task 1: Add R4.2 schema, RLS, and specification traceability

**Files:**
- Create: `supabase/migrations/20260924000001_analyst_conversations.sql`
- Create: `docs/quality/r4.2-release-evidence.md` — its own file, matching the one-doc-per-release
  convention already used for R3.4 and R4.1; record the same G3-unmet exception pattern
- Test: `apps/api/tests/integration/test_analyst_isolation.py`

- [ ] **Step 1: Write the failing isolation fixtures** for two tenants, one conversation, one
  turn, and one citation each.
- [ ] **Step 2: Run the focused integration test** and verify the tables are absent or the test
  fails at setup.
- [ ] **Step 3: Add the migration** for `analyst_conversation`, `analyst_turn`, and
  `analyst_turn_citation` — composite tenant foreign keys, append-only turns (no `UPDATE`, per
  FR-010), forced RLS, `USING`/`WITH CHECK` policies scoped to the creating member plus
  owner/buyer read-all per FR-009, and authenticated/service-role grants matching the
  `negotiation_brief`/`negotiation_brief_item` precedent from `019-supplier-risk-negotiation`.
  `analyst_turn_citation` MUST use the same typed-reference-per-row pattern as
  `supplier_scorecard_evidence` (exactly one of purchase order, quotation line, landed cost,
  saving record, supplier scorecard/risk snapshot, delivery receipt, or reorder proposal per row).
- [ ] **Step 4: Run the isolation test** and verify cross-tenant list and direct reads return no
  rows, and that a non-owner member cannot list another member's conversations.
- [ ] **Step 5: Record the controlled R4 exception** in the release evidence doc without changing
  the G3 measurements, mirroring the existing "R4.0 exception posture" section.

### Task 2: Implement the deterministic retrieval-and-calculation service

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/analyst/__init__.py`
- Create: `apps/api/src/procurepilot_api/modules/analyst/retrieval.py`
- Create: `apps/api/src/procurepilot_api/modules/analyst/schemas.py`
- Test: `apps/api/tests/unit/test_analyst_retrieval.py`

- [ ] **Step 1: Write failing tests** for each FR-002 category (spend/savings, supplier
  performance/risk, orders/quotations, reorder forecasts), covering: a normal answer with
  citations, a category question with zero grounding data (must say so, not guess), a
  conflicting-records case (must surface both, not pick one), explicit currency handling
  (no cross-currency aggregation, matching R4.0/R4.1's `Decimal` convention), and a question
  referencing a supplier/product ID that belongs to a *different* tenant (FR-007 — must resolve
  to "no grounding data," not a leak or a distinguishable error).
- [ ] **Step 2: Run the unit tests** and verify they fail because the retrieval functions don't
  exist.
- [ ] **Step 3: Implement one pure function per category**, each taking a resolved category +
  entities + tenant scope and returning a typed answer (value, calculation inputs, formula,
  citations) or an explicit "no grounding data" result — never an approximate one. Pin a
  `analyst-retrieval-v1` calculation version on every answer, matching R4.0/R4.1's versioning
  convention.
- [ ] **Step 4: Run the focused unit tests** and verify all pass, including a replay-determinism
  assertion (Constitution Principle II) — the same inputs at the same calculation version produce
  a bit-identical result on a second call.

### Task 3: Add question understanding, conversation persistence, and the API

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/analyst/intent.py`
- Create: `apps/api/src/procurepilot_api/modules/analyst/service.py`
- Create: `apps/api/src/procurepilot_api/modules/analyst/router.py`
- Modify: `apps/api/src/procurepilot_api/main.py`
- Modify: `apps/api/src/procurepilot_api/config.py`
- Modify: `docs/architecture/adrs.md` (ADR-017: question-understanding reuses the ADR-004/ADR-014
  Bedrock/Claude provider, does not add a new one)
- Test: `apps/api/tests/contract/test_analyst_contract.py`
- Test: `apps/api/tests/integration/test_analyst_api.py`
- Test: `apps/api/tests/unit/test_analyst_intent.py`

- [ ] **Step 1: Write failing contract tests** for the conversation/turn response envelopes, role
  checks (FR-009), rate-limit headers (FR-015), and the unsupported-category response shape
  (FR-002).
- [ ] **Step 2: Implement question understanding** — a thin call to the existing Bedrock/Claude
  client that classifies free text into a supported category (or "unsupported") plus entities
  (supplier, product, date range), with a strict output schema and no free-text passthrough into
  the answer. Resolve a follow-up turn's omitted entities from the immediately preceding turn only
  (FR-008), never the full conversation. Write a failing adversarial unit test first (FR-005): a
  classification with no matching retrieval result must still produce an explicit refusal — the
  turn service must reject any answer content that didn't come from Task 2's retrieval return
  value, never let the model's own wording leak into the stored answer.
- [ ] **Step 3: Implement the turn service** — classify, retrieve (Task 2), persist the immutable
  turn + citations atomically, append an audit event (FR-012 — assert the row exists in the
  integration test, not just that the call was made), and expose `release_posture = g3_unmet` on
  every response.
- [ ] **Step 4: Implement conversation list/detail endpoints** with cursor pagination and the
  creator-scoped-plus-owner/buyer-oversight read rule from FR-009.
- [ ] **Step 5: Add per-member rate limiting** on the ask-question endpoint (FR-015) and register
  the router. Run focused API tests.

### Task 4: Add the analyst conversation UI

**Files:**
- Create: `apps/web/src/app/features/analyst/conversation/conversation.component.ts`
- Create: `apps/web/src/app/features/analyst/conversation/conversation.component.html`
- Create: `apps/web/src/app/features/analyst/conversation/conversation.component.scss`
- Create: `apps/web/src/app/features/analyst/conversation/conversation.component.spec.ts`
- Modify: `apps/web/src/app/app.routes.ts`
- Modify: `packages/i18n/en.json`
- Modify: `packages/i18n/ar.json`

- [ ] **Step 1: Write failing component tests** for asking a question, an answer with inline
  citations and a visible calculation, an answer with a next-step deep link (FR-003A), the
  "can't answer that yet" state (FR-002), the "no grounding data" state (FR-006), and a follow-up
  turn.
- [ ] **Step 2: Implement the API client and standalone component** — a chat-style thread with
  translated strings, logical CSS, and accessible controls; citations link out to the same
  underlying record screens used elsewhere in the product (FR-003), not a summary or copy; a
  next-step link, when present, routes to the existing actionable surface it names (FR-003A).
- [ ] **Step 3: Add the route and navigation entry** only where the existing shell pattern
  requires it.
- [ ] **Step 4: Run focused Angular tests and production build.**

### Task 5: Verify and document the exception boundary

**Files:**
- Modify: `docs/architecture/api-specification.md`
- Modify: `docs/architecture/data-dictionary.md`
- Test: `apps/api/tests/integration/test_tenant_isolation.py`

- [ ] **Step 1: Add API and data-dictionary contracts** for the conversation, turn, and citation
  entities.
- [ ] **Step 2: Run API unit, integration, contract, web unit, `pnpm test:a11y`
  (axe-core/WCAG 2.1 AA — a separate gate from web unit tests, per FR-014 and the constitution's
  Quality Gates table), and production build gates.**
- [ ] **Step 3: Run the G3 evidence command** and confirm its output remains unmet.
- [ ] **Step 4: Run a live hosted walkthrough** (ask a question in each supported category, in
  English and Arabic) mirroring the R4.0/R4.1 verification pattern, and record it in the release
  evidence doc.

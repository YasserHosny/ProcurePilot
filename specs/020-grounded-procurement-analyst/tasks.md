# Tasks: R4.2 Grounded Procurement Analyst

**Input**: Design documents from `/specs/020-grounded-procurement-analyst/`
**Prerequisites**: plan.md, spec.md

**Tests**: Included — this project's established convention (constitution's Development Workflow,
`docs/quality/test-strategy.md`) is test-first for every chunk; follow the same pattern used in
`018-forecasting-reorder`/`019-supplier-risk-negotiation`.

**Organization**: Tasks are grouped by user story (US1-US4 from spec.md) to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US4)

---

## Phase 1: Setup

**Purpose**: Project skeleton, no behavior yet.

- [x] T001 Create the `analyst` module skeleton: `apps/api/src/procurepilot_api/modules/analyst/__init__.py`
- [x] T002 [P] Create the Angular analyst feature directory skeleton at `apps/web/src/app/features/analyst/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, isolation, and the pure retrieval layer every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Write failing isolation fixtures for two tenants, one conversation, one turn, one
      citation each in `apps/api/tests/integration/test_analyst_isolation.py`
- [x] T004 Add migration `supabase/migrations/20260924000001_analyst_conversations.sql`:
      `analyst_conversation`, `analyst_turn` (append-only — no `UPDATE` grant), and
      `analyst_turn_citation` (exactly one typed tenant-pinned source reference per row,
      mirroring `supplier_scorecard_evidence`), each with composite tenant foreign keys, forced
      RLS, and `USING`/`WITH CHECK` policies scoped to the creating member plus owner/buyer
      read-all (FR-009)
- [x] T005 Run the isolation test (T003) against the new migration and verify cross-tenant reads
      and a non-owner member's attempt to list another member's conversations both return no rows
- [x] T006 [P] Define `AnalystConversation`/`AnalystTurn`/`AnalystCitation` Pydantic schemas in
      `apps/api/src/procurepilot_api/modules/analyst/schemas.py`, including the
      `release_posture = g3_unmet` field on every turn response
- [x] T007 [P] Write failing unit tests for each FR-002 retrieval category (spend/savings,
      supplier performance/risk, orders/quotations, reorder forecasts) in
      `apps/api/tests/unit/test_analyst_retrieval.py` — cover a normal cited answer, zero
      grounding data (must say so explicitly), conflicting records (must surface both),
      explicit-currency handling (no cross-currency aggregation), a question referencing a
      supplier/product ID that belongs to a *different* tenant (FR-007 — must resolve to "no
      grounding data," never a leak), and a replay-determinism case (Constitution Principle
      II — identical inputs at the same calculation version produce a bit-identical result)
- [x] T008 Implement one pure retrieval-and-calculation function per category in
      `apps/api/src/procurepilot_api/modules/analyst/retrieval.py`, pinning
      `calculation_version = "analyst-retrieval-v1"` on every answer, and scoping every internal
      lookup by both the resolved entities *and* the caller's tenant so a cross-tenant reference
      cannot resolve to a match (FR-007) (depends on T006, T007)

**Checkpoint**: Foundation ready — schema isolated and proven, retrieval layer answers every
supported category from real tenant data with citations, before any API or UI exists.

---

## Phase 3: User Story 1 - Ask a grounded question about tenant data (Priority: P1) 🎯 MVP

**Goal**: A member types a free-text question and gets back an answer with citations and a visible
calculation, or an explicit refusal — never a guess.

**Independent Test**: Sign in, ask one question per supported category plus one unsupported
question, and confirm each response matches FR-002/FR-003/FR-004/FR-006 without touching any other
user story.

### Tests for User Story 1

- [x] T009 [P] [US1] Contract test for `POST /api/v1/analyst/conversations` (create + first turn)
      in `apps/api/tests/contract/test_analyst_contract.py` — response envelope, role checks,
      `Idempotency-Key`, rate-limit headers
- [x] T010 [P] [US1] Integration test: ask one question per FR-002 category and one unsupported
      question, in `apps/api/tests/integration/test_analyst_api.py`
- [x] T011 [P] [US1] Adversarial unit test (FR-005) in `apps/api/tests/unit/test_analyst_intent.py`:
      a classification with no matching retrieval result must still produce an explicit refusal —
      the turn service must reject any answer content that didn't come from Task 2's retrieval
      return value, never let the model's own wording leak into the stored answer

### Implementation for User Story 1

- [x] T012 [US1] Implement question understanding in
      `apps/api/src/procurepilot_api/modules/analyst/intent.py` — reuses the existing Bedrock/
      Claude client (ADR-004/ADR-014) to classify free text into a supported category or
      "unsupported" plus entities (supplier, product, date range), with a strict output schema;
      it must never pass free text through into the answer itself (depends on T011)
- [x] T013 [US1] Implement the turn service in
      `apps/api/src/procurepilot_api/modules/analyst/service.py`: classify (T012) → retrieve
      (T008) → persist the immutable turn + citations atomically → append an audit event and
      assert the row exists in the integration test, not just that the call was made (FR-012) →
      expose `release_posture = g3_unmet` on every response (depends on T008, T012)
- [x] T014 [US1] Implement the ask-question endpoint in
      `apps/api/src/procurepilot_api/modules/analyst/router.py` and register it in
      `apps/api/src/procurepilot_api/main.py` / `apps/api/src/procurepilot_api/config.py`
      (depends on T013)
- [x] T015 [US1] Add per-member rate limiting on the ask-question endpoint (FR-015)
- [x] T016 [P] [US1] Write a failing component test for asking a question and seeing a cited,
      calculated answer (and the unsupported-category state) in
      `apps/web/src/app/features/analyst/conversation/conversation.component.spec.ts`
- [x] T017 [US1] Implement the API client and standalone conversation component in
      `apps/web/src/app/features/analyst/conversation/conversation.component.ts`/`.html`/`.scss`
- [x] T018 [US1] Add the route to `apps/web/src/app/app.routes.ts`, the nav entry, and i18n keys
      in `packages/i18n/en.json` / `packages/i18n/ar.json`

**Checkpoint**: User Story 1 is fully functional and testable independently — ask a question,
get a grounded answer or an honest refusal.

---

## Phase 4: User Story 2 - Inspect the evidence behind an answer (Priority: P1)

**Goal**: Every citation resolves to the real underlying record, every calculation's inputs and
formula are visible (not summarized), and — where one exists — the answer links to the existing
actionable surface for that entity (FR-003A).

**Independent Test**: From an answer produced in US1, open a citation and confirm it links to the
same record screen used elsewhere in the product; expand the calculation and confirm it matches
the retrieval function's actual inputs; for a risky-supplier or low-stock answer, confirm the
next-step link routes to the existing negotiation-brief or reorder-queue screen.

### Tests for User Story 2

- [x] T019 [P] [US2] Integration test: each citation kind (purchase order, quotation line, landed
      cost, saving record, scorecard/risk snapshot, delivery receipt, reorder proposal) resolves
      to a real, existing tenant record, in `apps/api/tests/integration/test_analyst_api.py`
- [x] T020 [P] [US2] Component test: calculation detail expands and citation links navigate to the
      correct existing screens, in `conversation.component.spec.ts`
- [x] T021 [P] [US2] Integration test (FR-003A / SC-007): an answer about a risky supplier, a
      low-stock forecast, and a spend/savings question each include the correct deep link to
      their existing actionable surface; a question with no such surface includes none

### Implementation for User Story 2

- [x] T022 [US2] Ensure the citation payload from `retrieval.py`/`service.py` carries stable IDs/
      links to the exact underlying record for each source kind (extends T008/T013)
- [x] T023 [US2] Implement the next-step deep-link field per category in
      `retrieval.py`/`service.py` (FR-003A) — links to existing negotiation-brief, reorder-queue,
      or report screens only, never a new action capability
- [x] T024 [US2] Implement the citation and "show calculation" UI in
      `conversation.component.html`/`.ts` — inline expansion, links out to existing record screens
- [x] T025 [US2] Implement the next-step link in the UI, rendered only when the answer includes one

**Checkpoint**: US1 + US2 together deliver the full "ask and verify" MVP, including the
Constitution Principle IV next-step requirement.

---

## Phase 5: User Story 3 - Ask a follow-up question in context (Priority: P2)

**Goal**: A short follow-up resolves using the immediately preceding turn's grounded entities,
without the member repeating themselves.

**Independent Test**: Ask a question, then a follow-up that omits the subject ("and last
quarter?"), and confirm it resolves against the prior turn; then ask an unrelated follow-up and
confirm it's treated as a fresh question.

### Tests for User Story 3

- [x] T026 [P] [US3] Unit test: a follow-up resolves omitted entities from the immediately
      preceding turn only, not the full conversation, in `apps/api/tests/unit/test_analyst_intent.py`
- [x] T027 [P] [US3] Integration test: a two-turn conversation where turn 2 depends on turn 1, and
      a second case where turn 2 changes subject entirely, in `test_analyst_api.py`

### Implementation for User Story 3

- [x] T028 [US3] Extend `intent.py`/`service.py` to pass the preceding turn's resolved category
      and entities into classification for a follow-up (FR-008)
- [x] T029 [US3] Update the conversation UI to keep the thread visible and send the prior turn's
      context alongside a follow-up submission

**Checkpoint**: Multi-turn conversations work without repeating the full question each time.

---

## Phase 6: User Story 4 - Review my own question history (Priority: P3)

**Goal**: A member can list and reopen their own past conversations; owners/buyers can see all
conversations in the tenant for oversight.

**Independent Test**: Ask questions across two conversations as one member, confirm both list and
both replay their original stored answers unchanged; confirm a second member sees only their own
conversations, and an owner sees both.

### Tests for User Story 4

- [x] T030 [P] [US4] Contract test for `GET /api/v1/analyst/conversations` and
      `GET /api/v1/analyst/conversations/{id}` in `test_analyst_contract.py`
- [x] T031 [P] [US4] Integration test: a member lists only their own conversations; an owner/buyer
      lists all; a reopened conversation replays its original stored answers rather than
      recomputing them (FR-010), in `test_analyst_api.py`

### Implementation for User Story 4

- [x] T032 [US4] Implement conversation list/detail endpoints in `router.py`/`service.py` with
      cursor pagination and the creator-scoped-plus-owner/buyer-oversight read rule (FR-009)
- [x] T033 [US4] Implement the history UI: list past conversations, reopen one, and render its
      stored turns exactly as originally given

**Checkpoint**: All four user stories are independently functional.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [x] T034 [P] Add API and data-dictionary contracts for the conversation, turn, and citation
      entities in `docs/architecture/api-specification.md` and `docs/architecture/data-dictionary.md`
- [x] T035 [P] Record ADR-017 in `docs/architecture/adrs.md`: question understanding reuses the
      existing Bedrock/Claude provider (ADR-004/ADR-014), no new LLM provider is introduced
- [ ] T036 Run API unit, integration, contract, web unit, `pnpm test:a11y` (axe-core/WCAG 2.1 AA —
      a separate gate from web unit tests, per FR-014 and the constitution's Quality Gates table),
      and production build gates
- [ ] T037 Run the G3 evidence command, confirm output remains unmet, and record the R4.2
      exception posture in a new `docs/quality/r4.2-release-evidence.md` (its own file, matching
      the one-doc-per-release convention already used for R3.4/R4.1 — not appended to R4.1's file)
- [ ] T038 Run a live hosted walkthrough — one question per supported category, in English and
      Arabic, including at least one answer with a next-step link (FR-003A) — mirroring the
      R4.0/R4.1 verification pattern, and record it in the release evidence doc

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phase 3-6)**: All depend on Foundational completion.
  - US1 and US2 are both P1 and tightly coupled (an answer without visible citations isn't
    grounded, and without a next-step link where one applies, it doesn't satisfy Constitution
    Principle IV); implement them back-to-back as the MVP slice.
  - US3 and US4 can proceed in either order once US1/US2 exist.
- **Polish (Final Phase)**: Depends on all four user stories being complete.

### User Story Dependencies

- **US1 (P1)**: No dependency on other stories.
- **US2 (P1)**: Extends US1's answer payload with citation/calculation/next-step detail; not
  independently meaningful without US1, but its own tasks touch different files and can be built
  as soon as US1's retrieval/service layer (T008/T013) exists.
- **US3 (P2)**: Extends US1's intent/service layer with prior-turn context; depends on US1 existing.
- **US4 (P3)**: Extends US1's persistence with list/detail reads; depends on US1's schema (T004,
  T006) but not on US2/US3.

### Parallel Opportunities

- T001/T002 (Setup) in parallel.
- T006/T007 (Foundational) in parallel once T004 lands.
- Once Foundational (Phase 2) completes, US1 and US4 can be staffed in parallel (US4 only needs
  the schema, not US1's UI); US2 and US3 each need US1's service layer first.
- Within each story, all `[P]`-marked test tasks run in parallel before implementation begins.

---

## Implementation Strategy

### MVP First (User Story 1 + 2)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (schema, isolation, retrieval layer) — CRITICAL, blocks
   everything else.
3. Complete Phase 3: US1 (ask a question, get a grounded answer).
4. Complete Phase 4: US2 (inspect the evidence, and the Principle IV next-step link) — without
   this, US1's answers aren't actually verifiable or actionable, so treat US1+US2 together as the
   real MVP, not US1 alone.
5. **STOP and VALIDATE**: live hosted walkthrough of the MVP slice before adding US3/US4.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 + US2 → MVP: ask and verify a grounded, actionable answer.
3. US3 → conversational follow-ups.
4. US4 → question history and oversight.
5. Polish → docs, ADR-017, full gates (including `test:a11y`), G3 evidence, live walkthrough.

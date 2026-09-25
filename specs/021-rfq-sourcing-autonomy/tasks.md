# Tasks: R4.3 Automated RFQ Sourcing and Guarded Autonomous Workflows

**Input**: Design documents from `/specs/021-rfq-sourcing-autonomy/`
**Prerequisites**: plan.md, spec.md

**Tests**: Included — this project's established convention (constitution's Development Workflow,
`docs/quality/test-strategy.md`) is test-first for every chunk; follow the same pattern used in
`018-forecasting-reorder`/`020-grounded-procurement-analyst`.

**Organization**: Tasks are grouped by user story (US1-US5 from spec.md) to enable independent
implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)

---

## Phase 1: Setup

**Purpose**: Project skeleton and the new outbound-email configuration surface, no behavior yet.

- [x] T001 Create the `rfq` module skeleton: `apps/api/src/procurepilot_api/modules/rfq/__init__.py`
- [x] T002 [P] Create the Angular RFQ feature directory skeleton at `apps/web/src/app/features/rfq/`
- [x] T003 [P] Add `MAILGUN_API_KEY`/`MAILGUN_SENDING_DOMAIN`/`RFQ_MAILER_MODE` to
      `apps/api/src/procurepilot_api/config.py` and document them in `.env.example`
      (`MAILGUN_SIGNING_KEY` already exists for inbound verification — these are new, outbound-only)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, isolation, and the outbound mailer every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T004 Write failing isolation fixtures for two tenants — one RFQ with a recipient, a response,
      a guardrail, and an auto-preparation event each — in
      `apps/api/tests/integration/test_rfq_isolation.py`
- [x] T005 Add migration `supabase/migrations/<ts>_rfq_sourcing.sql`: `rfq`, `rfq_recipient`,
      `rfq_response`, `auto_preparation_guardrail`, `auto_preparation_event` (append-only — no
      `UPDATE`/`DELETE` grant, same discipline as `audit_event`), each with composite tenant
      foreign keys, forced RLS, and `USING`/`WITH CHECK` policies scoped to the creating member
      plus owner/buyer read-all (FR-016) — mirror `analyst_conversation`'s policy shape exactly
- [x] T006 Add migration `supabase/migrations/<ts>_supplier_contact_email.sql`: nullable
      `supplier.contact_email` — confirmed against the live schema that no outbound contact
      address exists today (`email_domains` is an inbound-matching heuristic only)
- [x] T007 Run the isolation test (T004) against the new migrations and verify cross-tenant reads
      of every new table return no rows
- [x] T008 [P] Write failing unit tests for the mailer interface in
      `apps/api/tests/unit/test_rfq_mailer.py`: `FakeMailer` is deterministic and network-free;
      `SendResult` always carries a `Message-ID`
- [x] T009 Implement `apps/api/src/procurepilot_api/shared/mailer.py`: a pure `send(to, subject,
      body, headers) -> SendResult` interface, a real `MailgunMailer` (Messages API), and a
      `FakeMailer` stub, selected by `RFQ_MAILER_MODE=stub|mailgun` (stub is the test/CI default,
      matching the `FakeIntentProvider`/`FakeExtractionProvider` convention)
- [x] T010 [P] Define `Rfq`/`RfqRecipient`/`RfqResponse`/`AutoPreparationGuardrail` Pydantic
      schemas in `apps/api/src/procurepilot_api/modules/rfq/schemas.py`
- [x] T011 Record ADR-018 (reuse Mailgun for outbound, don't add a second vendor) in
      `docs/architecture/adrs.md`

**Checkpoint**: Foundation ready — schema exists, isolation is proven, the mailer works against a
stub. User story work can now proceed.

---

## Phase 3: User Story 1 - Send a structured RFQ to chosen suppliers (Priority: P1)

**Goal**: A buyer can create an RFQ for a product/quantity/needed-by date, pick suppliers with an
on-file contact email, review it, and send it — nothing is dispatched until they explicitly do.

**Independent Test**: Create an RFQ for a known product and two suppliers with contact emails,
send it, and confirm both recipients show `sent` status with a real outbound `Message-ID`
recorded; confirm a third supplier with no contact email is rejected as a recipient specifically,
without blocking the other two.

### Tests for User Story 1

- [x] T012 [P] [US1] Unit test for `build_rfq_message()` in
      `apps/api/tests/unit/test_rfq_dispatch.py`: real content only (product identity, quantity,
      needed-by date, tenant terms), and a stable `Message-ID` derived from
      `(tenant_id, rfq_id, recipient_id)` so a resend under the same idempotency key doesn't
      fork the thread
- [x] T013 [P] [US1] Integration test in `apps/api/tests/integration/test_rfq_api.py`: creating an
      RFQ with a recipient lacking `contact_email` rejects that recipient specifically (FR-002);
      an RFQ is never dispatched on create, only on an explicit send call (FR-003); a Mailgun send
      failure leaves the recipient `draft`, never `sent`

### Implementation for User Story 1

- [x] T014 [US1] Implement `build_rfq_message()` in
      `apps/api/src/procurepilot_api/modules/rfq/service.py`
- [x] T015 [US1] Implement `RfqService.create()` — draft-only, per-recipient `contact_email`
      validation (FR-001, FR-002), and records an "RFQ created" audit event (FR-015)
- [x] T016 [US1] Implement `RfqService.send()` — calls `mailer.send()` per recipient, persists the
      outbound `Message-ID` on `rfq_recipient`, records an audit event (FR-015), and leaves a
      recipient `draft` on send failure rather than marking it `sent`
- [x] T017 [US1] Add router endpoints `POST /rfq` and `POST /rfq/{id}/send` in
      `apps/api/src/procurepilot_api/modules/rfq/router.py`, with `Idempotency-Key` on both
      mutations matching this codebase's convention
- [x] T018 [P] [US1] Write a failing component test for RFQ creation and send in
      `apps/web/src/app/features/rfq/create/create.component.spec.ts`
- [x] T019 [US1] Implement the RFQ creation + send UI in
      `apps/web/src/app/features/rfq/create/`, using `apps/web/src/app/features/rfq/rfq-api.ts`

**Checkpoint**: A buyer can send a real RFQ end to end. Nothing to compare or capture yet — that's
US2/US3.

---

## Phase 4: User Story 2 - Automatically capture supplier responses (Priority: P1)

**Goal**: A supplier's reply to a sent RFQ becomes a structured, comparable quotation
automatically, using the existing extraction and review pipeline unchanged.

**Independent Test**: Send an RFQ, reply as the supplier with a priced quotation, and confirm the
reply is captured as a structured `rfq_response` linked to that RFQ; confirm a reply matching no
open RFQ falls through to the ordinary quotation-ingestion path unchanged.

### Tests for User Story 2

- [x] T020 [P] [US2] Integration tests in
      `apps/api/tests/integration/test_rfq_response_capture.py`: a reply matching an open RFQ's
      `Message-ID` captures a linked `rfq_response`; a reply matching no open RFQ falls through to
      the existing general quotation path unchanged (FR-006); a reply matching an *expired* RFQ is
      still captured but the RFQ's status stays `expired`, not `responded`; an arithmetic-mismatch
      response still hits the existing mandatory review task with no RFQ-specific exemption
      (FR-005)
- [x] T021 [US2] Write the failing cross-tenant matching-isolation test — will complete T004's
      isolation proof once T022/T023 land: tenant B's inbound webhook must not be able to match a
      reply against tenant A's outbound `Message-ID`

### Implementation for User Story 2

- [x] T022 [US2] Implement `apps/api/src/procurepilot_api/modules/rfq/response_matching.py`: a
      pure function, `ingestion_email_log` row (already carries `in_reply_to`/`references_list`)
      plus a tenant's open RFQ recipients → matched `rfq_recipient_id` or `None`
- [x] T023 [US2] Wire `response_matching.py` into
      `apps/api/src/procurepilot_api/modules/ingestion/orchestrator.py`'s `process_inbound_email()`
      (corrected from `ingestion/router.py`, which only verifies and enqueues — matching actually
      happens in the orchestrator, called async from `workers/email_ingestion_worker.py`) as an
      additive step after existing quotation/supplier matching completes; query/insert against
      `rfq`/`rfq_recipient`/`rfq_response` under `set local role service_role` with an explicit
      tenant_id filter, since those tables' RLS policies require a real membership/owner-buyer
      claim that the orchestrator's tenant-only session does not carry (`ingestion_email_log`'s
      simpler tenant-only policy is why the existing code works without this); record a "response
      received" audit event on a match (FR-015)
- [x] T024 [US2] Run the full existing ingestion suite
      (`test_email_ingestion_worker.py`, `test_capture_service.py`, the quotation-matching
      suites) to confirm the additive matching step regresses nothing already shipping

**Checkpoint**: US1 + US2 together mean a buyer sends an RFQ and gets back real, structured
responses with zero manual re-entry — the core sourcing loop works, even before comparison exists.

---

## Phase 5: User Story 3 - Compare responses and prepare a request by hand (Priority: P1)

**Goal**: A buyer compares every structured response to one RFQ side by side and turns their
chosen winner into a draft purchase request that enters the existing, unmodified approval queue.

**Independent Test**: With two structured responses to one RFQ, open the comparison view, select
one, and confirm a draft purchase request is created citing that response and appears in the
approval queue exactly like any other purchase request.

### Tests for User Story 3

- [x] T025 [P] [US3] Real-Postgres integration tests in
      `apps/api/tests/integration/test_rfq_service_e2e.py` (mirror
      `test_analyst_service_e2e.py`'s pattern — mocked tests miss real schema/RLS bugs, proven
      repeatedly this program): both responses to one RFQ appear in `list_responses()`; preparing
      from a response creates a real `purchase_request`/`purchase_request_line` citing the source
      `rfq_response_id`, using `RequestsService.create_request()`; a second prepare call under the
      same idempotency key returns the identical request, never a duplicate (FR-008); an RFQ with
      zero responses by its needed-by date cannot have a request prepared from it

### Implementation for User Story 3

- [x] T026 [US3] Implement `RfqService.list_responses()` in
      `apps/api/src/procurepilot_api/modules/rfq/service.py`
- [x] T027 [US3] Implement `RfqService.prepare_request()` — calls
      `RequestsService.create_request()` exactly as `forecasting/service.py`'s
      `prepare_request()` already does for reorder proposals (read that function first); the new
      `purchase_request_line`'s `estimated_unit_price_amount/currency` comes from the winning
      response's quoted price, not landed cost — do not silently fall back
- [x] T028 [US3] Add router endpoints `GET /rfq/{id}/responses` and
      `POST /rfq/{id}/prepare-request`
- [x] T029 [P] [US3] Write a failing component test for the comparison view in
      `apps/web/src/app/features/rfq/compare/compare.component.spec.ts` — reuses the existing
      offer-comparison component/pattern scoped to one RFQ's responses, not a new comparison
      implementation
- [x] T030 [US3] Implement the comparison + manual "prepare request" UI in
      `apps/web/src/app/features/rfq/compare/`

**Checkpoint**: US1 + US2 + US3 together are the full manual MVP — send, capture, compare,
prepare — with every draft still requiring the existing human approval step. US4 is an optional
acceleration on top of this, not a dependency for it.

---

## Phase 6: User Story 4 - Configure guardrails for automatic preparation (Priority: P2)

**Goal**: An owner can define tight, explicit conditions under which a qualifying RFQ response is
auto-prepared into a draft purchase request without a human reviewing responses first — off by
default, and never bypassing the existing approval step.

**Independent Test**: Configure a guardrail (max order value, one pre-approved supplier, minimum
one response), send a qualifying RFQ, receive a response that satisfies every condition, and
confirm a draft purchase request is auto-prepared with the triggering rule recorded; confirm a
response failing even one condition falls back to requiring the manual US3 action.

### Tests for User Story 4

- [x] T031 [P] [US4] Unit tests for `guardrails.py` in
      `apps/api/tests/unit/test_rfq_guardrails.py` covering every FR-010–FR-014 condition as its
      own case: no guardrail configured → never fires (default-off); every condition met → fires
      with the triggering rule identified; wrong supplier, over value, under minimum response
      count, price variance exceeded, tied responses, partial-line response, expired RFQ, and
      mismatched currency (FR-018) each individually prevent firing — never silently approximated
- [x] T032 [P] [US4] Test for rejected guardrail configuration (FR-013): a zero, negative, or
      degenerate max-value guardrail is refused at creation, never silently accepted
- [x] T033 [US4] Real-Postgres end-to-end test in
      `apps/api/tests/integration/test_rfq_guardrails_e2e.py`: configure a guardrail, capture a
      qualifying response through the *full* ingestion path (not a direct service call — prove
      the whole chain), assert a real `purchase_request` appears in the approval queue with the
      auto-preparation note visible, and that disabling the guardrail afterward does not
      retroactively touch an already-fired event (FR-014)

### Implementation for User Story 4

- [x] T034 [US4] Implement `apps/api/src/procurepilot_api/modules/rfq/guardrails.py`: a pure
      function, `AutoPreparationGuardrail` + `RfqResponse` typed inputs → fire/no-fire + reason,
      no database access, calculation-version-pinned the same way `retrieval.py`'s
      `CALCULATION_VERSION` is (R4.2 precedent) — a guardrail firing is exactly the kind of
      consequential, replayable decision Constitution Principle II governs
- [x] T035 [US4] Wire guardrail evaluation into the response-capture path (T023) and call
      `RequestsService.create_request()` on a fire, recording an append-only
      `auto_preparation_event` row with the triggering rule (FR-011)
- [x] T036 [US4] Add guardrail management endpoints `POST`/`GET`/`PATCH /rfq/guardrails`,
      owner-only per FR-010, with the FR-013 rejection wired into create/update, and a
      "guardrail changed" audit event recorded on every create/update (FR-015)
- [ ] T037 [P] [US4] Write failing component tests: guardrail settings in
      `apps/web/src/app/features/rfq/guardrails/guardrails.component.spec.ts` (owner-only route
      guard, matching the existing `*appRole="'owner'"` convention), and — extending US3's compare
      view spec (`apps/web/src/app/features/rfq/compare/compare.component.spec.ts`) — a response
      that failed to auto-fire an active guardrail shows the reason it didn't (FR-012)
- [ ] T038 [US4] Implement the guardrail settings UI in
      `apps/web/src/app/features/rfq/guardrails/`; extend `RfqService.list_responses()` (T026) to
      compute each response's guardrail-evaluation outcome on demand by calling `guardrails.py`
      read-only against the tenant's active guardrails (no new persistence — a non-fire is never
      stored, only a fire is, per FR-011/T035) and include the reason in the response payload;
      extend T030's compare view (`apps/web/src/app/features/rfq/compare/`) to render it when one
      applies (FR-012) — this is the correct phase to add it, not US3 (T029/T030), since
      guardrails don't exist until this phase

**Checkpoint**: All P1/P2 stories done — the full guarded-autonomy loop the roadmap names for
R4.3 works end to end, and every auto-prepared draft is indistinguishable in the approval queue
from a manually-prepared one except for its visible triggering-rule note.

---

## Phase 7: User Story 5 - Track RFQ status and history (Priority: P3)

**Goal**: A member can see every RFQ sent from their tenant, its recipients, response status, and
what it became — sent, responded, expired, or converted into a request.

**Independent Test**: Send RFQs to three suppliers across two requests, let one expire with no
response, and confirm the history view shows all three with distinct, accurate statuses.

### Tests for User Story 5

- [x] T039 [P] [US5] Write a failing component test for RFQ history in
      `apps/web/src/app/features/rfq/history/history.component.spec.ts`: status, recipients,
      response counts, and — where applicable — the converted purchase-request link

### Implementation for User Story 5

- [x] T040 [US5] Add `GET /rfq` (list, cursor-paginated, scoped per FR-016 — creator plus
      owner/buyer oversight, mirroring `analyst_conversation`'s RLS-enforced pattern) to
      `apps/api/src/procurepilot_api/modules/rfq/router.py`/`service.py`
- [x] T041 [US5] Implement the RFQ history UI in `apps/web/src/app/features/rfq/history/`
- [x] T042 [US5] Add the route (`apps/web/src/app/app.routes.ts`), shell nav entry (mirror the
      existing nav-item structure exactly, no tooltip —
      `apps/web/src/app/layout/shell/shell.component.html`), and i18n keys in both
      `packages/i18n/en.json` and `packages/i18n/ar.json` under a new `rfq` namespace, with
      verified exact key parity between the two files (a repeated real bug in every prior R4.x UI
      phase — check it explicitly, don't assume it)

**Checkpoint**: All five user stories are independently functional.

---

## Final Phase: Polish & Cross-Cutting Concerns

- [x] T043 [P] Write the Principle-III boundary proof: an integration test that attempts, and
      fails, to find any code path from an `auto_preparation_event` firing to a transmitted
      purchase order or a bypassed approval step — this is the one test in this release that
      exists purely to make the constitution's NON-NEGOTIABLE guarantee executable, not just
      asserted in the plan's prose
- [x] T044 [P] Add R4.3 sections to `docs/architecture/api-specification.md` and
      `docs/architecture/data-dictionary.md`, mirroring the R4.0–R4.2 entries already there
- [ ] T045 Run API unit, integration, contract, web unit, `pnpm test:a11y` (axe-core/WCAG 2.1 AA,
      English + Arabic), and production build gates
- [ ] T046 Run the G3 evidence command, confirm output remains unmet, and record the R4.3
      exception posture in a new `docs/quality/r4.3-release-evidence.md` (its own file, matching
      the one-doc-per-release convention)
- [ ] T047 Run a live walkthrough: send a real RFQ, reply from a real test-supplier mailbox
      through the actual Mailgun round trip (not the stub), confirm capture, compare, manual
      prepare, and — separately — a guardrail-triggered auto-prepare; English and Arabic; record
      it in the release evidence doc, mirroring the R4.0–R4.2 walkthrough pattern

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories. Schema, isolation, and
  the mailer are load-bearing for every story that follows.
- **User Stories (Phase 3-7)**: All depend on Foundational completion.
  - US1, US2, and US3 are all P1 and form a single sequential chain — send (US1) produces nothing
    to capture without US2, and US2's captured responses have nothing to act on without US3.
    Implement them in order as the MVP slice; do not parallelize their core service logic even
    though they touch different files, because US2's response-matching logic is meaningless
    without US1's dispatched `Message-ID`s to match against.
  - US4 extends US3's `prepare_request()` with an automatic trigger; depends on US1-US3 existing.
  - US5 only needs US1's schema (T005) for read access; can be built any time after Foundational,
    in parallel with US2-US4's service-layer work.
- **Polish (Final Phase)**: Depends on all five user stories being complete.

### Parallel Opportunities

- T002/T003 (Setup) in parallel.
- T008/T010 (Foundational) in parallel once T005/T006 land.
- Once Foundational (Phase 2) completes, US5's read-only history work (T039-T042) can be staffed
  in parallel with US2/US3/US4's service-layer work, since it only needs the schema, not the
  dispatch/matching/preparation logic itself.
- Within each story, all `[P]`-marked test tasks run in parallel before implementation begins.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 + 3)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (schema, isolation, the mailer) — CRITICAL, blocks everything
   else.
3. Complete Phase 3: US1 (send a structured RFQ).
4. Complete Phase 4: US2 (capture supplier responses automatically).
5. Complete Phase 5: US3 (compare and manually prepare a request) — without this, US1+US2 produce
   structured data a buyer still has to act on by hand outside the product; treat US1+US2+US3
   together as the real MVP, not US1 alone.
6. **STOP and VALIDATE**: live walkthrough of the manual MVP slice — a real RFQ, a real reply
   through Mailgun, a real comparison, a real prepared draft in the approval queue — before adding
   the guarded-autonomy layer (US4).

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 + US2 + US3 → MVP: send, capture, compare, and manually prepare a request, with the
   existing human approval step completely untouched.
3. US4 → the guarded autonomous workflow the roadmap names for this release: the same prepare
   action, automatically, inside tight tenant-configured limits.
4. US5 → status and history visibility.
5. Polish → docs, ADR-018 already recorded in Foundational, full gates (including `test:a11y`),
   the Principle-III boundary proof, G3 evidence, live walkthrough.

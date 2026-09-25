# R4.3 Automated RFQ Sourcing and Guarded Autonomous Workflows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a buyer send a structured RFQ to chosen suppliers, capture and structure their
replies automatically, compare responses, and prepare a draft purchase request from the winner —
manually always, and automatically when a tenant has explicitly configured tight guardrails for
it — without ever creating a path to an autonomous purchase.

**Architecture:** A new `rfq` module in `apps/api`, deliberately thin, that composes four
already-existing systems rather than re-implementing any of them:

1. **Outbound dispatch** — the one genuinely new capability. The inbound side of email ingestion
   (`003-quotation-inbox-extraction`) already runs on Mailgun (`verify_mailgun_signature` in
   `ingestion/webhook_security.py`; `MAILGUN_SIGNING_KEY` is already configured). Mailgun's
   Messages API also sends outbound mail from the same domain already verified for inbound —
   this plan adds outbound sending as a new *use* of the existing vendor relationship, not a new
   vendor. See the Decision note below; this is recorded as ADR-018.
2. **Response capture** reuses the existing inbound pipeline unchanged (`email_parser.py`,
   the extraction worker, the quotation/matching pipeline) — an RFQ response is an ordinary
   quotation with one addition: matching it back to the RFQ it answers. `ingestion_email_log`
   already carries `in_reply_to` and `references_list` (RFC 2822 threading headers) precisely
   because Mailgun's inbound routing preserves them; dispatching each RFQ with a generated
   `Message-ID` and matching a reply's `in_reply_to` against it is additive, not new
   infrastructure.
3. **Comparison** reuses the existing offer-comparison capability (`offers/` module) scoped to
   one RFQ's responses — no new comparison UI or algorithm.
4. **Preparation** (manual and guarded-automatic) reuses `RequestsService.create_request()`
   exactly as `forecasting/service.py`'s `prepare_request()` already does for reorder proposals —
   same deterministic idempotency-key pattern (`uuid5` over tenant+source+target), same
   `purchase_request`/`purchase_request_line` shape, same downstream human-approval workflow,
   completely untouched. Guardrail evaluation is a pure, deterministic function (no LLM, no
   judgment call) over a response's price, supplier, category, and count against a tenant's own
   configured `AutoPreparationGuardrail` rows — architecturally the same "typed input in, typed
   decision out, no side effects" shape as `retrieval.py` in R4.2, for the same reason: a decision
   this consequential must be replayable and testable without a live database.

**Constitution Principle III note (binding on every task below):** "prepare" here means exactly
what it means in `018-forecasting-reorder` today — creating a `draft` `purchase_request` that
enters the existing, unmodified approval queue. No task in this plan may add a path from an RFQ
response to a transmitted purchase order, a submitted request, or any other state that bypasses
human approval. Guardrail evaluation only ever decides *whether to call `create_request()`*, never
whether to approve, submit, or send anything downstream of it.

**New external dependency (requires an ADR — Constitution Principle VI):** outbound email sending
via Mailgun's Messages API. This is the single most consequential new technical dependency in
this release; Task 1 records it as ADR-018, reusing the existing vendor rather than introducing a
second one, and explicitly notes the failure mode (Mailgun send failure must leave the RFQ in
`draft`, never silently mark it `sent`).

**Tenant-scoping note (mirrors R4.2's FR-007 discipline):** every new table is tenant-scoped with
forced RLS from its first migration — this is Non-negotiable #1/Principle V, not new practice.
The one genuinely new isolation risk is outbound dispatch itself: the Mailgun send must be
constructed so that a tenant can never be tricked into dispatching to, or the webhook into
matching a reply against, another tenant's RFQ — Task 2's isolation tests must prove this
explicitly, not just table-level RLS.

**Tech Stack:** Python 3.12, FastAPI, psycopg, Supabase Postgres RLS, Pydantic v2, Mailgun
(inbound — existing; outbound — new, this release), Angular 19, RxJS, ngx-translate. No new LLM
usage — RFQ response extraction reuses the existing Bedrock/Claude extraction pipeline exactly as
every other quotation source already does.

**Decision — reuse Mailgun for outbound, don't add a new email vendor:** the inbound ingestion
pipeline already authenticates Mailgun webhooks and the tenant's inbound domain is already
verified with Mailgun. Introducing a second transactional-email vendor for outbound would mean
two DNS/domain-verification relationships, two credential sets, and two failure-mode runbooks for
one conceptual capability (sending and receiving mail on the tenant's behalf). Mailgun's Messages
API sends from the same verified domain and its inbound webhook already threads replies via
`In-Reply-To`/`References`, which this release depends on directly. Recorded as ADR-018.

---

### Task 1: Add outbound email sending (ADR-018) and R4.3 schema/RLS

**Files:**
- Create: `apps/api/src/procurepilot_api/shared/mailer.py` — thin Mailgun Messages API client
  (send only; the existing `webhook_security.py` remains the inbound-verification half)
- Update: `apps/api/src/procurepilot_api/config.py` — `MAILGUN_API_KEY`, `MAILGUN_SENDING_DOMAIN`
  settings (new; `MAILGUN_SIGNING_KEY` already exists for inbound)
- Update: `.env.example` — document the two new variables
- Update: `docs/architecture/adrs.md` — ADR-018 (reuse Mailgun for outbound, see Decision above)
- Create: `supabase/migrations/<ts>_rfq_sourcing.sql` — `rfq`, `rfq_recipient`, `rfq_response`,
  `auto_preparation_guardrail`, `auto_preparation_event`; forced RLS on all five; append-only
  `auto_preparation_event` (no update/delete grant, same discipline as `audit_event` and R4.2's
  `analyst_turn`)
- Update: `supabase/migrations/<ts>_supplier_contact_email.sql` — **`supplier` today has no
  outbound contact address at all** (`email_domains text[]` is an inbound-matching heuristic,
  not a send-to address — confirmed against the live schema, do not assume otherwise). Add a
  nullable `contact_email` column; FR-002 depends on this being present and explicit.
- Test: `apps/api/tests/integration/test_rfq_isolation.py`

- [ ] **Step 1: Write the failing isolation fixtures** for two tenants, one RFQ each with a
  recipient, a response, a guardrail, and an auto-preparation event — assert tenant A cannot
  read, and cannot cause a reply to be matched against, tenant B's RFQ.
- [ ] **Step 2: Add the migration** for the five new tables plus `supplier.contact_email`,
  composite tenant FKs throughout, forced RLS with `USING`/`WITH CHECK` scoped per FR-016 (creator
  plus owner/buyer oversight, the same pattern as `analyst_conversation`'s policy).
- [ ] **Step 3: Add `mailer.py`** — a pure `send(to, subject, body, headers) -> SendResult`
  interface with a real `MailgunMailer` and a `FakeMailer` (matching this codebase's established
  `FakeIntentProvider`/`FakeExtractionProvider` stub convention) selected by
  `RFQ_MAILER_MODE=stub|mailgun`, stub as the test/CI default. `SendResult` MUST carry the
  outbound `Message-ID` — Task 3 depends on it for reply matching.
- [ ] **Step 4: Run the isolation suite** against real Postgres; all green.
- [ ] **Step 5: Record ADR-018** and update `.env.example`.

---

### Task 2: Implement RFQ creation, dispatch, and the outbound-isolation proof

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/rfq/schemas.py`, `service.py`, `router.py`
- Test: `apps/api/tests/unit/test_rfq_dispatch.py`, `apps/api/tests/integration/test_rfq_api.py`

- [ ] **Step 1: Write failing unit tests** for `build_rfq_message()` — a pure function, real
  content only (no fabricated supplier-facing prose): product identity, quantity, needed-by date,
  tenant terms, and a stable outbound `Message-ID` derived from `(tenant_id, rfq_id,
  recipient_id)` so a resend under the same idempotency key produces the same `Message-ID` rather
  than a duplicate thread.
- [ ] **Step 2: Implement `RfqService.create()`** (FR-001) — draft only, no dispatch; rejects a
  recipient with no `contact_email` (FR-002) per-recipient, without blocking the rest of the RFQ.
- [ ] **Step 3: Implement `RfqService.send()`** (FR-003) — human-triggered only in this task
  (US1's baseline path); calls `mailer.send()` per recipient, persists each outbound `Message-ID`
  on its `rfq_recipient` row, and — critically — leaves a recipient `draft` rather than marking it
  `sent` if the Mailgun call itself fails, per the ADR-018 failure-mode note. Records an audit
  event per FR-015.
- [ ] **Step 4: Write the cross-tenant dispatch-isolation test** — tenant A cannot send to, or
  reference, tenant B's supplier as an RFQ recipient, and tenant B's inbound webhook cannot match
  a reply against tenant A's outbound `Message-ID` (Task 3 will add the matching logic this test
  depends on; write the test now, implement against it in Task 3).
- [ ] **Step 5: Add the router** — `POST /rfq`, `POST /rfq/{id}/send`, matching this codebase's
  Idempotency-Key-on-mutation convention throughout.

---

### Task 3: Match inbound replies to RFQs and capture responses (FR-005, FR-006)

**Files:**
- Update: `apps/api/src/procurepilot_api/modules/ingestion/orchestrator.py`'s
  `process_inbound_email()` — corrected during Phase 4 research: the inbound webhook handler in
  `ingestion/router.py` only verifies/enqueues (`job_type='email_ingest'`); all supplier/quotation
  matching actually happens inside `process_inbound_email()`, called from
  `workers/email_ingestion_worker.py`'s `_process_job()`. RFQ-reply matching goes there, as an
  additional, non-exclusive classification alongside the existing `match_supplier()` call (an
  inbound email can be an ordinary quotation AND happen to match an open RFQ's `Message-ID` in
  `in_reply_to`/`references_list`)
- Create: `apps/api/src/procurepilot_api/modules/rfq/response_matching.py` — pure function,
  `ingestion_email_log` row (already carries `in_reply_to`/`references_list`) + open RFQ
  recipients for the tenant → matched `rfq_recipient_id` or `None`
- Test: `apps/api/tests/integration/test_rfq_response_capture.py`

**RLS note (found during Phase 4 research):** `process_inbound_email()` runs under
`_act_as_tenant()`, which sets only the `tenant_id`/`role` JWT claims — no `sub` (user id) or
`member_role`. `rfq`/`rfq_recipient`/`rfq_response` RLS policies require either
`created_by_membership_id = current_membership_id()` (a live lookup keyed off `sub`, which is
unset here) or `current_member_role() in ('owner', 'buyer')` (also unset here) — so a plain
tenant-scoped query against these tables from inside the orchestrator returns zero rows, silently,
never an error. `quotation`/`ingestion_email_log`, by contrast, use plain
`tenant_id = current_tenant_id()` policies, which is why the existing orchestrator code works
unmodified. The RFQ-matching/response-insert step must use `set local role service_role` (the
same pattern already used by `workers/accounting_sync_worker.py`, `workers/pos_sync_worker.py`,
etc. for system-initiated writes) with an explicit manual `tenant_id = %s` filter on every query,
since RLS is bypassed under `service_role`.

- [ ] **Step 1: Write failing tests** for: a reply matching an open RFQ's `Message-ID` captures a
  linked `rfq_response`; a reply that matches no open RFQ falls through to the existing general
  quotation path unchanged (FR-006); a reply matching an RFQ that has since expired is still
  captured as a response but the RFQ's own status stays `expired` (per the spec's edge case,
  not `responded`); an arithmetic-mismatch response still hits the existing mandatory review task
  with no RFQ-specific exemption (FR-005).
- [ ] **Step 2: Implement `response_matching.py`** and wire it into `orchestrator.py`'s
  `process_inbound_email()` as an additive step after the existing quotation/supplier matching
  completes, using a `service_role` connection with an explicit tenant_id filter (see the RLS
  note above).
- [ ] **Step 3: Complete Task 2 Step 4's** cross-tenant matching-isolation test now that matching
  exists; all green.
- [ ] **Step 4: Run the full existing ingestion test suite** (`test_email_ingestion_worker.py`,
  `test_capture_service.py`, the quotation-matching suites) to confirm the additive matching step
  regresses nothing already shipping.

---

### Task 4: Comparison and manual preparation (US3)

**Files:**
- Update: `apps/api/src/procurepilot_api/modules/rfq/service.py` — `list_responses()`,
  `prepare_request()`
- Test: `apps/api/tests/integration/test_rfq_service_e2e.py`

- [ ] **Step 1: Write failing real-Postgres tests** (matching R4.2's established
  `test_analyst_service_e2e.py` pattern — this codebase's own dispatch history this cycle showed
  mocked-only tests miss real schema/RLS bugs; do not repeat that here) for: two responses to one
  RFQ both appear in `list_responses()`; preparing from a response creates a real
  `purchase_request`/`purchase_request_line` citing the source `rfq_response_id`, using
  `RequestsService.create_request()` exactly as `forecasting/service.py`'s `prepare_request()`
  does (same file, read it before writing this one); a second prepare call under the same
  idempotency key returns the same request, never a duplicate (FR-008); an RFQ with zero
  responses by its needed-by date cannot have a request prepared from it (spec's US3 scenario 3).
- [ ] **Step 2: Implement against the tests.** `estimated_unit_price_amount/currency` on the new
  `purchase_request_line` comes from the winning response's quoted price, not from landed cost —
  this is a real, deliberate difference from the reorder-proposal path; do not silently fall back
  to a landed-cost estimate when a real quoted price exists.
- [ ] **Step 3: Wire the router** — `GET /rfq/{id}/responses`, `POST /rfq/{id}/prepare-request`.

---

### Task 5: Guardrails and guarded auto-preparation (US4)

**Files:**
- Create: `apps/api/src/procurepilot_api/modules/rfq/guardrails.py` — pure function,
  `AutoPreparationGuardrail` + `RfqResponse` (typed inputs) → fire/no-fire + reason, no database
  access, mirroring `retrieval.py`'s architecture
- Update: `apps/api/src/procurepilot_api/modules/rfq/service.py` — evaluate guardrails at response
  capture time (Task 3's capture path), call the same `prepare_request()` from Task 4 on a fire
- Test: `apps/api/tests/unit/test_rfq_guardrails.py`,
  `apps/api/tests/integration/test_rfq_guardrails_e2e.py`

- [ ] **Step 1: Write failing unit tests for `guardrails.py`** covering every FR-010–FR-014
  condition as its own case: no guardrail configured → never fires (FR-010 default-off); every
  condition met → fires with the triggering rule identified (FR-011); wrong supplier, over value,
  under minimum response count, price variance exceeded, tied responses, partial-line response,
  expired RFQ, mismatched currency (FR-018) → each individually prevents firing, never silently
  approximated.
- [ ] **Step 2: Write the rejected-guardrail-configuration test** (FR-013) — a zero, negative, or
  degenerate max-value guardrail is refused at creation, not silently accepted and never fired.
- [ ] **Step 3: Implement `guardrails.py`** against the unit tests — pure, no side effects,
  calculation-version-pinned the same way `retrieval.py`'s `CALCULATION_VERSION` is, since a
  guardrail firing is exactly the kind of consequential, replayable decision Principle II governs.
- [ ] **Step 4: Wire evaluation into response capture** (Task 3) and call
  `RequestsService.create_request()` on a fire, recording an `auto_preparation_event` row with
  the triggering rule (FR-011) — append-only, never editable after the fact.
- [ ] **Step 5: Real-Postgres end-to-end test**: configure a guardrail, capture a qualifying
  response via the full ingestion path (not a direct service call — prove the whole chain), assert
  a real `purchase_request` appears in the approval queue with the auto-preparation note visible,
  and that disabling the guardrail afterward does not retroactively touch it (FR-014).
- [ ] **Step 6: Guardrail management endpoints** — `POST/GET/PATCH /rfq/guardrails`, owner-only
  per FR-010, with the FR-013 rejection wired into the create/update path.

---

### Task 6: RFQ UI — create, send, compare, prepare, history, and guardrail settings

**Files:**
- Create: `apps/web/src/app/features/rfq/` — `rfq-api.ts`, `create/`, `compare/`,
  `history/`, `guardrails/` (settings, owner-only per FR-010)
- Update: `apps/web/src/app/app.routes.ts`, `apps/web/src/app/layout/shell/shell.component.html`
- Update: `packages/i18n/en.json`, `packages/i18n/ar.json` — new `rfq` namespace; verify exact
  key parity between the two files explicitly (this has been a repeated real bug in every prior
  R4.x UI phase — check it, don't assume it)
- Test: component specs per view, matching the R4.2 UI phases' coverage depth

- [ ] **Step 1: Failing component test for RFQ creation** — product/quantity/needed-by/recipient
  selection, blocking a recipient with no `contact_email` with a clear reason (FR-002), send only
  on explicit confirmation (FR-003).
- [ ] **Step 2: Implement creation + send UI.**
- [ ] **Step 3: Failing component test for the comparison view** — reuses the existing offer-
  comparison component/pattern scoped to one RFQ, not a new comparison implementation.
- [ ] **Step 4: Implement comparison + manual "prepare request" action.**
- [ ] **Step 5: Failing component test for guardrail settings** (owner-only route guard, matching
  the existing `*appRole="'owner'"` convention already used elsewhere in the shell) and for RFQ
  history (status, recipients, response counts, converted-request link where applicable).
- [ ] **Step 6: Implement guardrail settings + history UI**, route, nav entry (no tooltip, mirror
  the existing nav-item structure exactly), and i18n.

---

### Task 7: Verify and document the exception boundary

**Files:**
- Create: `docs/quality/r4.3-release-evidence.md` — its own file, matching the one-doc-per-release
  convention
- Update: `docs/architecture/api-specification.md`, `docs/architecture/data-dictionary.md` — R4.3
  sections, mirroring the R4.0–R4.2 entries already there

- [ ] **Step 1: Run full API + web gates** (unit, integration, contract, `pnpm test:a11y`,
  production build) — matching R4.2's T036 exactly.
- [ ] **Step 2: Write and run the Principle-III boundary proof explicitly** — an integration test
  that attempts, and fails, to find any code path from an `auto_preparation_event` firing to a
  transmitted purchase order or a bypassed approval step. This is the one test in this release
  that exists purely to make the constitution's NON-NEGOTIABLE guarantee executable, not just
  asserted in the plan's prose.
- [ ] **Step 3: G3 evidence command + release-evidence doc**, matching R4.0–R4.2's format exactly.
- [ ] **Step 4: Live walkthrough** — send a real RFQ, reply from a real test-supplier mailbox
  through the actual Mailgun round trip (not a stub), confirm capture, compare, manual prepare,
  and — separately — a guardrail-triggered auto-prepare, English and Arabic, mirroring R4.0–R4.2's
  walkthrough pattern.

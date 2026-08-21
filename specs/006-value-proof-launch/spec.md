# Feature Specification: Value Proof + Launch Readiness

**Feature Branch**: `006-value-proof-launch`
**Created**: 2026-08-21
**Status**: Draft
**Input**: User description: "Chunk 4.6 Value Proof and Launch Readiness: savings ledger with outcome capture, Excel/PDF export service, onboarding flow with Stripe-gated plans (stub billing provider for now), Arabic/RTL pass and accessibility audit, performance and security review"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A buyer records what actually happened and sees a verified saving (Priority: P1)

After choosing a supplier on the compare screen, a buyer records what was actually ordered,
delivered, and paid. The system compares that actual outcome against a documented baseline (the
product's last-paid price, or its rolling-average price) and produces a savings-ledger row showing
the baseline, the actual value, and the verified delta — with a link back to the exact quotation,
competing offers, and match evidence behind the number, so the buyer can defend the figure to
anyone who asks.

**Why this priority**: This is the entire product thesis made real — "prove the money saved." Every
prior chunk built toward this moment; without it, Smart Compare is just a nicer way to look at
prices, never a case for value delivered.

**Independent Test**: Can be fully tested by recording a purchase outcome against a product with an
existing compare recommendation and confirming a savings-ledger row appears with baseline value,
actual value, verified delta, and a working link to its evidence.

**Acceptance Scenarios**:

1. **Given** a buyer has compared offers for a product and chosen one, **When** they record the
   actual order (quantity, supplier, price paid, delivery outcome), **Then** a savings-ledger row is
   created showing baseline value, actual value, and delta, each as an explicit amount and
   currency.
2. **Given** a savings-ledger row has been created, **When** the buyer opens its evidence view,
   **Then** they see the originating quotation, the competing offers it was compared against, and
   the purchase record — enough to defend the number to a supplier or an accountant.
3. **Given** a savings-ledger row has been verified, **When** anyone (including the buyer who
   created it) attempts to edit or delete it, **Then** the system refuses — a verified row is
   immutable, the same append-only discipline already applied to this project's audit trail.
4. **Given** the actual price paid is higher than the baseline, **When** the outcome is recorded,
   **Then** the ledger still records a truthful (negative or zero) delta rather than hiding or
   refusing to show an unfavourable outcome.

---

### User Story 2 - A buyer exports the savings ledger for their accountant (Priority: P1)

A buyer needing to report on procurement performance exports the savings ledger — filtered to a
period, branch, or supplier — as an Excel file or a PDF, each carrying enough evidence detail to
stand on its own outside the product.

**Why this priority**: A verified saving that can't leave the product to reach an accountant or a
supplier negotiation is only half the value proposition; export is the second half of "prove it,"
right after "compute it," and is explicitly called out in the roadmap's launch-readiness scope.

**Independent Test**: Can be fully tested by requesting an export of a period containing at least
one verified saving and confirming the resulting file contains that row's baseline, actual, delta,
and evidence reference.

**Acceptance Scenarios**:

1. **Given** at least one verified saving exists in the requested period, **When** a buyer requests
   an Excel export, **Then** they receive a file listing every matching row with baseline, actual,
   delta, currency, and a reference back to its evidence.
2. **Given** the same request, **When** a buyer requests a PDF export instead, **Then** they receive
   a human-readable summary document suitable for sharing outside the product.
3. **Given** an export is requested for a period with zero verified savings, **When** the export
   completes, **Then** the buyer receives a clearly empty (not broken or silently missing) result.

---

### User Story 3 - A prospective buyer self-onboards onto a gated plan (Priority: P1)

Someone evaluating ProcurePilot signs up, creates their workspace, and is shown the plan they are
on, with account behaviour (which features are available) gated by that plan — without needing
someone else to provision the account for them.

**Why this priority**: Launch readiness requires the product to acquire a paying customer without a
manual sales/ops step in the way; this is the last piece of scaffolding standing between the
platform-foundation signup flow (chunk 4.1) and repeatable, self-serve customer acquisition.

**Independent Test**: Can be fully tested by signing up as a new user, completing workspace setup,
and confirming the workspace shows an active plan that gates at least one plan-dependent behaviour.

**Acceptance Scenarios**:

1. **Given** a new user completes signup and workspace creation (chunk 4.1's existing flow),
   **When** they reach the end of onboarding, **Then** they are shown their current plan and what it
   includes.
2. **Given** a workspace is on a plan with a defined limit (for example, a maximum number of
   catalogue products or seats), **When** that limit is reached, **Then** the product clearly
   communicates the limit rather than silently failing or silently allowing unlimited use.
3. **Given** no real payment provider credentials exist yet (see Assumptions), **When** a workspace
   is created, **Then** it is assigned a default plan through a stand-in billing provider, in a way
   that can later be swapped for a real Stripe integration without changing the plan-gating logic
   itself.

---

### User Story 4 - Every screen works correctly in Arabic and passes an accessibility audit (Priority: P2)

A buyer using the product in Arabic, or using assistive technology, gets a fully mirrored,
correctly laid-out, fully operable experience across every screen this project has shipped so far
— not just the newest ones.

**Why this priority**: Every prior chunk already tested its own new screens in both languages with
zero axe-core violations as it shipped; this story is the whole-product audit that catches drift
and regressions across the accumulated surface area before calling Phase 1 launch-ready, so it is
sequenced after the P1 value-proof stories rather than ahead of them.

**Independent Test**: Can be fully tested by running an automated accessibility scan across every
shipped screen in both languages and confirming zero violations, and by visually confirming RTL
mirroring on a sample of screens spanning every prior chunk.

**Acceptance Scenarios**:

1. **Given** the full set of screens shipped across chunks 4.1–4.6, **When** an automated
   accessibility scan runs against each in both languages, **Then** zero WCAG 2.1 AA violations are
   reported.
2. **Given** any screen is viewed in Arabic, **When** its layout is inspected, **Then** it mirrors
   correctly using logical CSS properties, not a hardcoded left/right assumption that only happens
   to look right in English.

---

### Edge Cases

- What happens when a buyer records an outcome for a product that was never compared (no
  recommendation exists)? The system must still accept the outcome but cannot compute a
  recommendation-based baseline — it falls back to the product's historical baseline (last paid or
  rolling average) from chunk 4.5's price history, and says so explicitly in the evidence.
- What happens when a purchase outcome is recorded but never verified? It must not appear in the
  ledger as a verified saving, and must not be exportable as one — an unverified outcome is visible
  as pending, not silently promoted.
- What happens when an export is requested for a very large period? It must behave as a tracked,
  asynchronous job (consistent with this project's existing job pattern), not a request that blocks
  the caller indefinitely.
- What happens when a workspace somehow has no plan assigned (a data gap, not a normal state)? The
  system must treat this as a configuration error to be surfaced, not silently grant or deny every
  feature.
- What happens when an accessibility violation is found on an existing (not new) screen during the
  audit? It must be fixed as part of this chunk's scope, not merely logged for a future chunk —
  launch readiness cannot ship with known violations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST let a buyer record a purchase outcome (quantity, supplier, price paid,
  currency, delivery result) against a specific product and, where one exists, the compare
  recommendation or offer it followed.
- **FR-002**: System MUST compute a savings-ledger row from a recorded outcome: a baseline value
  (from the product's chunk 4.5 price history — last paid or rolling average, whichever the
  workspace's baseline policy specifies), the actual value paid, and the delta between them, each
  as an explicit amount-and-currency pair.
- **FR-003**: System MUST require an explicit verification step before a savings-ledger row counts
  as verified; an unverified outcome capture MUST be visibly distinct (e.g. "pending") and MUST NOT
  be included in exports or verified-savings totals.
- **FR-004**: System MUST make a verified savings-ledger row immutable — no update or delete, for
  any role — matching this project's existing append-only discipline for its audit trail.
- **FR-005**: System MUST provide an evidence view for any savings-ledger row linking back to its
  originating quotation, the competing offers it was compared against, and the purchase record,
  sufficient to defend the figure outside the product.
- **FR-006**: System MUST record a truthful delta even when the actual price paid is worse than the
  baseline — never suppress, hide, or refuse to show an unfavourable outcome.
- **FR-007**: System MUST let a buyer export the savings ledger, filtered by period and optionally
  by branch or supplier, as an Excel (.xlsx) file.
- **FR-008**: System MUST let a buyer export the same filtered savings ledger as a PDF summary
  document.
- **FR-009**: System MUST treat an export request as a tracked, asynchronous job with an observable
  status, consistent with this project's existing job pattern (chunk 4.3's extraction jobs, chunk
  4.5's basket-split jobs) — not a request that blocks the caller.
- **FR-010**: System MUST let a new user complete signup and workspace creation (reusing chunk
  4.1's existing flow) and see their assigned plan and its limits at the end of onboarding.
- **FR-011**: System MUST gate at least one concrete, testable behaviour (for example, a maximum
  catalogue size or seat count) by the workspace's assigned plan, and communicate clearly when a
  plan limit is reached rather than failing silently or allowing unlimited use.
- **FR-012**: System MUST assign every new workspace a plan through a billing-provider abstraction
  that can be backed by a stand-in (stub) provider today and a real Stripe integration later without
  changing the plan-gating logic that reads from it.
- **FR-013**: System MUST NOT execute, simulate, or claim to execute any real financial transaction
  in this chunk — plan assignment and gating are functional today using a stub provider; real
  payment collection is out of scope until real provider credentials exist (see Assumptions).
- **FR-014**: System MUST pass an automated accessibility scan with zero WCAG 2.1 AA violations
  across every screen shipped in chunks 4.1 through 4.6, in both English and Arabic.
- **FR-015**: System MUST correctly mirror every screen's layout in Arabic using CSS logical
  properties, verified across a representative sample spanning every prior chunk, not only the
  screens this chunk adds.
- **FR-016**: System MUST express every monetary value introduced by this chunk (outcome capture,
  savings-ledger rows, export content) as an explicit amount-and-currency pair, matching the
  convention already established in chunks 4.2–4.5.
- **FR-017**: System MUST NOT expose data from another tenant's workspace through any endpoint or
  screen introduced by this chunk; a cross-tenant reference MUST behave as not found, never as
  forbidden, matching this project's existing tenant-isolation convention.
- **FR-018**: System MUST restrict outcome-capture and export actions to roles already permitted to
  act on purchasing decisions (owner, buyer); other roles may view the savings ledger and its
  evidence but not record outcomes or trigger exports.

### Key Entities

- **PurchaseRecord**: What was actually ordered, from which supplier, at what price, and its
  delivery outcome — the factual record an outcome capture creates. References the quotation line
  and/or compare recommendation it followed, when one exists.
- **SavingRecord**: The computed, eventually-verified comparison between a `PurchaseRecord`'s actual
  value and a documented baseline value — baseline policy, baseline value, actual value, delta,
  verification state, and a link to its evidence. Immutable once verified; this project's second
  append-only entity alongside `audit_event`.
- **Plan**: A named tier a workspace is assigned to, defining which behaviours or limits apply.
  Assigned via a billing-provider abstraction, not hardcoded per workspace.
- **BillingAccount**: A workspace's record of its assigned plan and its billing-provider reference
  (a stub identifier today; a real Stripe customer/subscription reference once real credentials
  exist) — the seam between plan-gating logic and whichever concrete provider backs it.
- **ExportJob**: A tracked, asynchronous request to render the savings ledger (filtered) as an
  Excel or PDF file, with an observable status and, once complete, a downloadable result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A buyer can go from "chose a supplier on the compare screen" to "see a verified saving
  in the ledger with working evidence links" without leaving the product or involving anyone else.
- **SC-002**: Every verified savings-ledger row remains byte-for-byte unchanged after creation — no
  code path, including an administrative one, can alter or remove it once verified.
- **SC-003**: An export of any period completes (or reports empty) without requiring the requester
  to manually poll more than the existing job-status pattern already requires elsewhere in the
  product.
- **SC-004**: A new user can reach a usable, plan-aware workspace through self-service signup alone,
  with zero manual account provisioning steps.
- **SC-005**: Zero WCAG 2.1 AA violations are reported by an automated scan across every shipped
  screen, in both languages, at the close of this chunk.
- **SC-006**: The full self-onboard → upload → extract → compare → record purchase → verify saving
  path (this project's canonical smoke test, named in both `docs/quality/test-strategy.md` and
  `docs/operations/runbook.md`) passes end-to-end.

## Assumptions

- **No real Stripe (or any other real payment provider) credentials exist yet.** Per an explicit,
  user-approved decision for this chunk (the same situation chunk 4.3 faced with no real
  Bedrock/Azure Document Intelligence credentials), plan assignment and gating are built against a
  stub/fake billing provider behind a real abstraction boundary, so the real integration is a later
  swap-in, not a rebuild. No real financial transaction of any kind is executed by this chunk.
- **The G1 business gate itself (≥10 verified savings, ≥8 paying customers on self-serve) is a
  post-launch, real-world usage milestone, not something this chunk's code can pass as an acceptance
  test.** This chunk builds and verifies the mechanisms G1 depends on (a working savings ledger, a
  working self-serve onboarding path); whether real customers actually reach those numbers is
  outside any specification's ability to verify and is not claimed here.
- **A savings-ledger row's baseline is drawn from chunk 4.5's existing price-history computation**
  (last paid or rolling average) rather than a new baseline computation — this chunk introduces no
  second source of historical-price truth, the same discipline chunk 4.5 already applied to its own
  reads of chunk 4.4's data.
- **"Verification" of a savings-ledger row is a deliberate, explicit human action** (matching
  Constitution Principle III, human authority over automation) — not automatic the moment an
  outcome is recorded. Who exactly may verify (the recording buyer themselves, or a second role) is
  an implementation-level RBAC decision resolved in planning, not a product ambiguity requiring
  user clarification here, since either choice is a reasonable, easily-adjusted default.
- **The accessibility/RTL audit (User Story 4) covers every screen already shipped in chunks
  4.1–4.5 plus everything this chunk adds** — it does not extend to Phase 2 sketches, which are
  explicitly unbuilt.
- **Performance and security review** (named in the roadmap's chunk 4.6 scope) is treated as a
  cross-cutting verification pass over the whole product at this stage-gate boundary, not a new
  user-facing feature — its acceptance criteria are folded into this chunk's technical tasks rather
  than given a separate user story, since there is no distinct user journey to test independently.

## Out of Scope

- Purchase requests, approval routing, branches, cost centres, and the policy engine (Phase 2,
  F25–F28) — this project's CLAUDE.md explicitly defers all Phase 2 features. `branch_id` appears
  in the pre-existing sketch-only `SavingRecord`/API docs as a future filter; this chunk does not
  build branches themselves, only accepts an optional filter that is a no-op until they exist.
  Reworded/removed from those sketch sections if left stale, since Phase 1 has no `Branch` entity.
- A real Stripe (or other) payment integration — deferred until real provider credentials exist, per
  Assumptions. This chunk builds the plan-gating abstraction and a stub provider behind it.
- Mobile onboarding and offline drafts (Phase 2, F29–F32).
- Any change to chunk 4.1–4.5's own core domain logic (auth, catalogue, extraction, matching,
  landed cost, compare/recommendation) beyond what outcome capture needs to read from them.

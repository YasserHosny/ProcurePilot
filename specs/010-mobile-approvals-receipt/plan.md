# Implementation Plan: Mobile Approvals and Delivery Receipt

**Branch**: `010-mobile-approvals-receipt` | **Date**: 2026-09-13 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-mobile-approvals-receipt/spec.md`

## Summary

R2.3 (roadmap §7.2/§12). Closes the two mobile jobs R2.2 deliberately deferred: an approver can
now decide (approve/reject with comment) on a pending request from their phone with full context,
using 008-requests-approvals' existing decision endpoints unchanged; and a branch member can
confirm delivery of an approved request (quantities received, shortage flagging) and, separately,
report a delivery quality issue with photo evidence. Delivery confirmation and quality-issue
reporting are new capabilities — `purchase_request`'s lifecycle currently ends at
`approved`/`rejected`/`withdrawn`, with nothing recording what happened to an order afterward. This
plan extends that lifecycle rather than introducing a second, disconnected record (spec.md
Assumptions), and gives photo evidence its own Storage bucket mirroring the existing
quotation-document isolation pattern exactly.

## Technical Context

**Language/Version**: Unchanged — `apps/api`: Python 3.12; `apps/mobile`: Dart/Flutter (stable
channel, established in 009-mobile-app-mvp). No new language or runtime.

**Primary Dependencies**: `apps/api` gains no new dependency — the new endpoints are ordinary
FastAPI/Pydantic/supabase-py CRUD, identical shape to every existing module in `requests/`.
`apps/mobile` needs one genuinely new capability this codebase doesn't have yet: camera access and
local image handling for quality-issue photos. Use whatever camera/image-picker package is already
the Flutter ecosystem's standard choice at implementation time (research.md R2) — this plan does
not pin a specific package version, matching how 009's own plan left library selection to
implementation for anything not already a project convention. The existing offline-queue primitive
(`apps/mobile/lib/core/offline_queue/`) is reused unchanged for queuing delivery/quality
submissions; no new sync mechanism.

**Storage**: Supabase Postgres 17 (unchanged). New columns on `purchase_request` for the delivery
half of its lifecycle (research.md R1), a new `delivery_quality_issue` table (tenant-scoped, FK to
`purchase_request`), and a new `quality-issue-photos` Storage bucket with the same
tenant-isolation-on-object-path pattern `quotation-documents` already established (research.md R3).
No changes to `approval_step`'s schema — the decision itself is fully reused (research.md R2 covers
only how the *client* reaches it, not a data model change).

**Testing**: Same disposable-Postgres integration recipe used throughout 008/009 for the new
backend endpoints (contract + integration, mirroring `apps/api/tests/{contract,integration}/`
exactly); Flutter widget/integration tests for the new screens, following 009's own test pyramid
(no new framework).

**Target Platform**: iOS and Android via the existing `apps/mobile` Flutter codebase. No new
backend deployable.

**Performance Goals**: Same budgets as 009 (cold start <2.5s, app size <30MB) — this feature adds
screens and a camera dependency to the same app, so its own build-size/cold-start check
(009's T046, already landed) must be re-run once this feature is built, not assumed to still pass.
Roadmap §12.1's own target for the "Approve" job — a decision in under 30 seconds — is this
feature's headline UX budget (spec.md SC-001).

**Constraints**: FR-009's no-autonomous-purchasing rule is unchanged and, if anything, more load-
bearing here than in 009 — this is the first mobile release that can actually cause a request to
become `approved`, so the Constitution Check below scrutinizes this specifically. A decision
requires live connectivity (spec.md FR-003) — the one deliberate asymmetry with 009's offline-queue
precedent, and worth re-stating here so implementation does not "fix" it into symmetry with
delivery/quality submissions, which DO queue offline (spec.md FR-009).

**Scale/Scope**: Same pilot scale as every prior chunk. No new backend deployable, no new mobile
project — additive screens and endpoints inside `apps/mobile` and `apps/api`'s existing `requests`
module.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | **Yes** | A delivery-quality-issue photo is exactly the kind of evidence this principle asks for — a claim ("this arrived damaged") backed by something verifiable, not an unsupported assertion. Delivery confirmation's shortage figures are raw counts a person entered, not a derived/inferred value. | ✅ PASS — nothing here is a derived claim requiring provenance beyond its own actor/timestamp/photo |
| **II. Deterministic, Replayable Normalisation** | No | This feature touches no pricing, matching, or landed-cost computation. | N/A |
| **III. Human Authority Over Automation** | **Yes** | This is the first mobile release where a decision endpoint becomes reachable from the client at all — the highest-scrutiny principle for this plan. Mobile MUST reuse 008-requests-approvals' `approve_request`/`reject_request` service methods and their existing authorization/audit behavior completely unchanged; it MUST NOT add a mobile-specific decision path, an auto-approve shortcut, or any way to reach "approved" without the same human-authorization check the web endpoint already enforces. | ⏳ Design must show the mobile client calls the exact same `/requests/{id}/approve`\|`/reject` endpoints with no new server-side branch for "mobile-originated" decisions |
| **IV. Every Insight Ends in an Action** | **Yes** | A quality-issue report exists to prompt exactly one action (a follow-up with the supplier); it is not a passive log nobody reads. | ✅ PASS |
| **V. Tenant Isolation by Construction** | **Yes** | The new `delivery_quality_issue` table and the delivery-lifecycle columns on `purchase_request` need only `purchase_request`'s own existing tenant/branch-scoped RLS mechanism — no new isolation axis. The new Storage bucket needs the same tenant-scoped object-path policy `quotation-documents` already established. | ⏳ Design must confirm both reuse the existing mechanism verbatim, per research.md R1/R3 |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes** | New endpoints stay inside `apps/api`'s existing `requests` module (delivery/quality are request-adjacent facts, not a new domain) — no new backend service, no new module unless research.md R1 finds a specific reason to split one out. | ⏳ Design must confirm no new module is needed |
| **VII. Money, Tax, and Language Correct from the Schema Up** | **Yes** | Neither new table stores money. Every new mobile string comes from `packages/i18n`, full RTL — same requirement as every prior release. | ⏳ Design must confirm no feature-specific hardcoded copy |

**Workflow gates**: specification precedes code ✅ (spec approved, checklist passes, zero
clarification markers — one open architectural question resolved via a stated Assumption instead,
flagged explicitly for this plan's own research.md to confirm); stage gates — same recorded
exception already in effect for every Phase 2 chunk (ADR-010); this plan itself is the gate this
chunk needs to clear before implementation — **no code may be written against it until `tasks.md`
(Phase 2) is written**, per the constitution's `specify → clarify → plan → tasks → analyze →
implement` chain.

## Constitution Check — re-evaluated post-design (Phase 0/1 complete)

| Principle | Pre-design | Post-design |
|---|---|---|
| **III. Human Authority Over Automation** | ⏳ Must show no mobile-specific decision path | ✅ PASS — data-model.md introduces no new decision table or state-transition path; `contracts/`'s decision endpoints ARE 008-requests-approvals' existing `POST /requests/{id}/approve`\|`/reject`, called with no new parameter distinguishing a mobile caller from a web one. research.md R2 confirms the mobile client is a new *caller* of an unchanged endpoint, not a new code path. |
| **V. Tenant Isolation by Construction** | ⏳ Must confirm no new isolation axis | ✅ PASS — data-model.md's RLS Summary shows the new `purchase_request` delivery columns riding that table's own existing branch-scoped RESTRICTIVE policy verbatim (no new policy needed — they are columns on an already-governed row, per research.md R1), `delivery_quality_issue` using the identical policy shape via an `EXISTS` join to its parent request (mirroring how `purchase_request_line` already derives its own visibility from its parent, per 008's data-dictionary entry), and the new Storage bucket using `quotation-documents`' exact tenant-isolation-by-object-path pattern (research.md R3). |
| **VI. Modular Monolith Until Scale Demands Otherwise** | ⏳ Must confirm no new module needed | ✅ PASS — Project Structure below keeps every new backend surface inside the existing `requests` module; no new module was needed. |
| **VII. Money, Tax, and Language Correct from the Schema Up** | ⏳ Must confirm no hardcoded copy | ✅ PASS — quickstart.md and data-model.md introduce no money field and no new string outside the plan to add real `packages/i18n` keys (mirroring 009's own precedent of checking for existing keys before adding new ones). |

No principle regressed. The one genuinely new category of decision this plan makes that 008/009
didn't have to — write access to a decision endpoint from a second client, and a first-ever photo
upload pipeline in this codebase — is specified in research.md R2 (reuse, don't fork, the decision
endpoints) and R3 (photo storage mirrors the one existing precedent for tenant-isolated files
exactly, rather than inventing a second pattern).

## Project Structure

### Documentation (this feature)

```text
specs/010-mobile-approvals-receipt/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/           # Phase 1 output — mobile-approvals-receipt.openapi.yaml
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks) — NOT created by /speckit.plan
```

### Source Code (repository root)

```text
apps/mobile/
  lib/
    features/
      approvals/                    # NEW — mobile approval queue + decision detail screen, calls
                                      #   the EXISTING /approvals/pending and /requests/{id}/
                                      #   approve|reject endpoints (008-requests-approvals)
      delivery/                     # NEW — delivery confirmation screen (quantity received per
                                      #   line, shortage flagging) and quality-issue report screen
                                      #   (description + camera capture), calling the NEW endpoints
                                      #   below
      home/                         # EXTENDED, not replaced — the existing read-only pending-
                                      #   approvals count (009) becomes a link into features/
                                      #   approvals/
    core/
      camera/                       # NEW — a thin camera-capture wrapper, mirroring the existing
                                      #   core/auth/biometric_gate.dart abstraction-plus-fake
                                      #   pattern so screens don't depend on a concrete plugin
                                      #   directly
  test/                             # Flutter widget + integration tests for the above

apps/api/
  src/procurepilot_api/modules/
    requests/                       # EXTENDED, not replaced — delivery confirmation and quality-
                                      #   issue endpoints added here (request-adjacent facts, same
                                      #   reasoning 009 used to place low_stock_report here); the
                                      #   decision endpoints themselves are UNCHANGED
  tests/{unit,integration,contract}/ # new test files for the additions above

supabase/migrations/                 # NEW — purchase_request delivery-lifecycle columns,
                                      #   delivery_quality_issue table (RLS ENABLE+FORCE, deriving
                                      #   visibility from its parent request), and the
                                      #   quality-issue-photos Storage bucket + policy
```

**Structure Decision**: Delivery/quality endpoints live inside the existing `requests` module,
mirroring 009's own reasoning for `low_stock_report` — these are request-adjacent facts, not a new
domain, and a fourth backend module for two small endpoint groups would be premature (Principle
VI). The approval-decision endpoints themselves need no backend change at all — this plan is purely
additive on the mobile client side for that half of the feature. Mobile gets two new feature
directories (`approvals/`, `delivery/`) rather than folding into `requests/`, since on the mobile
side (unlike the backend) `features/requests/` already means "submit and track my own requests" —
deciding on someone else's request and confirming delivery are different enough user jobs to
warrant their own screens, matching how 009 already separated `features/requests/` from
`features/low_stock/` for the same reason.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No unjustified violations. Camera/image-picker access is a new capability for this codebase, which
would normally warrant scrutiny under Principle VI — but it is not a violation: the roadmap
pre-authorized camera capability as part of Phase 2's mobile scope (§12.2's "native capability
coverage" table explicitly lists camera as already-evaluated-and-available), and 009's own spec
explicitly deferred it to this exact release rather than rejecting it. This plan implements a
already-scoped capability, it does not introduce a fresh architectural decision that needs
justifying here.

# Implementation Plan: Mobile MVP

**Branch**: `009-mobile-app-mvp` | **Date**: 2026-09-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/009-mobile-app-mvp/spec.md`

## Summary

The first mobile app release (R2.2, roadmap §7.2/§12). A branch manager can sign in with
biometric re-entry, submit a purchase request and report low stock from their phone, and get
notified when a request they submitted is decided — all built on R2.1's existing request/approval
data model and endpoints, unchanged. Two small new backend surfaces support it: device push-token
registration and a lightweight low-stock report, neither of which touches `purchase_request`. The
app itself is a new Flutter project (`apps/mobile/`), the platform choice the roadmap already
ratified (§12.2) — this plan implements that decision, it does not re-open it. Approving from
mobile, delivery confirmation, and camera/barcode capture are explicitly out of scope (R2.3).

## Technical Context

**Language/Version**: Dart / Flutter (stable channel) — new to this codebase; every other
`Language/Version` entry below is unchanged. `apps/api`: Python 3.12, unchanged. Two new
endpoints in the existing `requests` module (or a new, small sibling module — see Project
Structure) need no new backend language/framework.

**Primary Dependencies**: Flutter, plus `flutter_secure_storage` or platform keychain access for
the refresh token, `local_auth` (or equivalent) for biometric unlock, MMKV or SQLite for local
draft/queue persistence (roadmap §12.4), Expo Notifications or an equivalent FCM/APNs push client
(same). `apps/api` gains no new dependency — the two new endpoints are ordinary FastAPI/Pydantic/
supabase-py CRUD, identical shape to every existing module.

**Storage**: Supabase Postgres 17 (unchanged). New tables: `device_registration`,
`low_stock_report` — both tenant-scoped, both requiring RLS `ENABLE`+`FORCE`. Neither touches
`purchase_request`, `purchase_request_line`, or `approval_step`; R2.1's schema is reused exactly
as it stands. On-device: MMKV/SQLite for offline drafts and a submission queue keyed by
`Idempotency-Key` (research.md R4 — reuses the existing header, not a new sync protocol).

**Testing**: Flutter widget tests for the new screens; an integration/golden-test pass against a
running `apps/api` (the same disposable-Postgres recipe already proven this session) for the two
new endpoints (contract + integration, mirroring `apps/api/tests/{contract,integration}/`
exactly); no new E2E framework — mobile does not get Playwright, it gets its own widget/
integration test pyramid per `flutter test`.

**Target Platform**: iOS and Android via one Flutter codebase (roadmap §12.2). No new backend
deployable — the two new endpoints live in the existing `apps/api` container.

**Performance Goals**: cold start under 2.5s on a mid-range Android device, app size under 30MB
download (roadmap §12.4) — both are mobile-specific budgets with no equivalent in any prior
chunk's Technical Context; a Wave 2 task must include a build-size and cold-start check before
store submission, not just functional testing.

**Constraints**: no request may reach "approved" without a recorded human decision — unchanged,
mobile does not touch that state machine at all (FR-009, this spec); every user-facing string
from `packages/i18n`, full RTL in Arabic, extended to a second runtime (Flutter) for the first
time — the string catalogue itself does not change, but this is the first client that has to
consume it outside Angular's `@ngx-translate` pipeline, so Wave 2 needs a decision on how a
Flutter client reads the same JSON files (see research.md R6); a submission made offline must
never be lost or double-submitted (FR-011, this spec) — solved by reusing the existing
Idempotency-Key mechanism, not inventing a new one (research.md R4).

**Scale/Scope**: same pilot scale as every prior chunk. One new `apps/mobile` Flutter project
(new — everything else in this plan is additive to `apps/api`, nothing removed or restructured).
Two new, small backend endpoints. No changes to any existing endpoint's request/response shape.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design |
|---|---|---|---|
| **I. Evidence Over Assertion** | Partially | A low-stock report is a raw signal, not a derived/inferred value — it carries no confidence score because it asserts nothing beyond "a person tapped this," which is itself the evidence (who, when, which product/branch). No new inferred metric is introduced this release. | ✅ PASS — nothing here is a derived claim requiring provenance beyond its own actor/timestamp |
| **II. Deterministic, Replayable Normalisation** | No | This release touches no pricing, matching, or landed-cost computation. | N/A |
| **III. Human Authority Over Automation** | **Yes** | Mobile MUST NOT add a second way for a request to become approved — FR-009 (this spec) explicitly forbids any approve/reject surface on mobile this release; the approver's home card is read-only. | ⏳ Design must show the mobile client has no code path that can call `POST /requests/{id}/approve`\|`/reject` at all this release, not merely a hidden UI for it |
| **IV. Every Insight Ends in an Action** | **Yes** | A low-stock report and a push notification both exist to prompt a specific next action (restock awareness; check a decided request) — neither is a passive read-only surface with no purpose. | ✅ PASS |
| **V. Tenant Isolation by Construction** | **Yes** | `device_registration` and `low_stock_report` are both tenant-scoped, RLS `ENABLE`+`FORCE`, same `current_membership_id()`/branch-scoped mechanism R2.0 built and R2.1 reused verbatim. | ⏳ Design must confirm both new tables need only the existing mechanism, no new isolation axis |
| **VI. Modular Monolith Until Scale Demands Otherwise** | **Yes** | The two new endpoints stay inside `apps/api`'s existing modular-monolith shape — no new backend service. `apps/mobile` is a new **client**, not a new backend service, and was pre-authorized by the roadmap (§12.2) before this plan, not a fresh architectural decision this plan is making unilaterally. | ✅ PASS |
| **VII. Money, Tax, Language from the Schema Up** | **Yes** | Neither new table stores money. Every mobile string comes from `packages/i18n`, full RTL — same requirement as every other client, now extended to a second consumer of that catalogue. | ⏳ Design must specify how a Flutter client consumes the existing JSON i18n files (research.md R6) |

**Workflow gates**: specification precedes code ✅ (spec approved, checklist passes, zero
clarification markers); stage gates — same recorded exception already in effect for every Phase 2
chunk (ADR-010, the project-owner override of the G1 → Phase 2 gate); this plan itself is the
gate this specific chunk needs to clear before implementation — **no code may be written against
it until `tasks.md` (Phase 2 of this plan) is written and reviewed**, per the constitution's
`specify → clarify → plan → tasks → analyze → implement` chain; delegated work reviewed ✅
(planned — every delegated diff reviewed against this plan and the constitution, same discipline
as every prior chunk).

## Constitution Check — re-evaluated post-design (Phase 0/1 complete)

| Principle | Pre-design | Post-design |
|---|---|---|
| **III. Human Authority Over Automation** | ⏳ Must show no approve/reject code path on mobile | ✅ PASS — data-model.md introduces no new state-transition table; the mobile client's only writes are `device_registration` (upsert), `low_stock_report` (insert), and the *unchanged* `/requests` create/submit/withdraw endpoints. Nothing in this plan's contract touches `/requests/{id}/approve`\|`/reject`. |
| **V. Tenant Isolation by Construction** | ⏳ Must confirm no new isolation axis | ✅ PASS — data-model.md's RLS Summary shows both new tables using `tenant_id = current_tenant_id()` plus a straightforward "own row only" restriction (a member manages their own device registrations and sees their own low-stock reports; an owner sees all) — no branch-scoped RESTRICTIVE layer needed, since neither table is something one branch's staff would need to see another branch's rows for. |
| **VII. Money, Tax, Language from the Schema Up** | ⏳ Must specify how Flutter consumes `packages/i18n` | ✅ PASS — research.md R6: the Flutter app bundles the same `packages/i18n/en.json`/`ar.json` files at build time (via a small generation step turning the flat JSON into Dart constants, or reading the JSON as an asset at runtime) rather than forking a parallel Flutter-only string catalogue that could drift from web's. |

No principle regressed. The one genuinely new *category* of decision this plan makes that R2.1
didn't have to — offline-tolerant, locally-queued mutations — is fully specified in research.md R4
as a reuse of the existing Idempotency-Key mechanism, not a new protocol.

## Project Structure

### Documentation (this feature)

```text
specs/009-mobile-app-mvp/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── contracts/           # Phase 1 output — mobile.openapi.yaml (device registration, low-stock report)
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks) — NOT created by /speckit.plan
```

### Source Code (repository root)

```text
apps/mobile/                       # NEW — Flutter project (currently a placeholder per CLAUDE.md)
  lib/
    core/                          # auth (reuses the existing Supabase JWT/refresh flow),
                                    #   biometric gate, api client, offline queue + idempotency-key
                                    #   generation, i18n loader (research.md R6)
    features/
      auth/                        # login, biometric enable/unlock
      home/                        # role-aware home (branch manager / approver read-only stat)
      requests/                    # new request form, my-requests list + detail — calls the
                                    #   EXISTING /requests and /approvals/pending endpoints
      low_stock/                   # low-stock report screen — calls the NEW /low-stock-reports
                                    #   endpoint
      settings/                    # notifications toggle, language, sign out
  test/                            # Flutter widget + integration tests

apps/api/
  src/procurepilot_api/modules/
    requests/                      # EXTENDED, not replaced — low-stock report endpoints added
                                    #   here (it is a requests-adjacent concept, not a new domain);
                                    #   /requests and /approvals/* endpoints themselves UNCHANGED
    devices/                       # NEW, small — device push-token registration only; kept
                                    #   separate from requests/ because it has nothing to do with
                                    #   purchase requests and may be reused by future push-worthy
                                    #   features (alerts, etc.) without requests/ owning them
  tests/{unit,integration,contract}/  # new test files for the two additions above

supabase/migrations/                # NEW — device_registration, low_stock_report, both RLS
                                     #   ENABLE+FORCE, per the Constitution Check above
```

**Structure Decision**: Flutter for `apps/mobile/` implements the roadmap's already-ratified
platform decision (§12.2) — this plan does not re-litigate Flutter vs. React Native vs. native.
Backend-side, the low-stock report lives inside the existing `requests` module (it is
conceptually a request-adjacent signal, and keeping it there avoids a fourth backend module for
one small endpoint pair); device registration gets its own small `devices` module because it is
genuinely a different concern (push delivery infrastructure) that has no reason to depend on or
be depended on by `requests` — a future feature needing push (e.g. a low-stock alert to an owner)
should not have to import through `requests/` to reach it.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No unjustified violations. Flutter is a new toolchain for this codebase, which would normally
warrant a Complexity Tracking entry under Principle VI — but it is not a violation, because the
roadmap (§12.2) already made and justified this exact decision (shared types via OpenAPI-generated
Dart, one team, store-distribution quality gates, native capability coverage, an escape hatch to
platform channels if needed) before this plan existed; this plan implements a ratified decision,
it does not introduce a fresh one that needs justifying here. The two new backend endpoints add no
new pattern beyond what every prior chunk's module already establishes.

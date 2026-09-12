# ProcurePilot — Wave 3 Execution Plan (Codex / OpenCode)

**Written**: 2026-09-12, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave2.md` ("Wave 2"). That document's §4 promised this one
once Phase 2's Checkpoint was independently confirmed — it now is (PRs #15, #16, #17, all merged
to `main` as of commit `bd4873f`; 791 backend tests, 1 skipped, 0 failed; Flutter 25/25 tests,
`analyze` clean, `build web` succeeds).

**Audience**: shared verbatim with both agents. Read the whole thing, then act only on your own
section. If you are Codex or OpenCode reading this cold: everything you need is below.

---

## 0. Repo state right now

- `main` @ `bd4873f`. `apps/mobile/` is a real Flutter project (not a placeholder) with a working
  `core/` — auth (sign-in/refresh/biometric gate/sign-out), i18n loader, offline queue, and a
  typed API client for `/devices` and `/low-stock-reports`. The `devices` backend module
  (register/delete, push-send job, retry sweep) is live. None of this has any screen UI yet —
  Wave 2 was core/plumbing only, per its own scope boundary.
- **This wave covers only Phase 3 of `specs/009-mobile-app-mvp/tasks.md`: User Story 1 (T018-T022)
  — sign in, biometric re-entry, sign-out, and the role-aware home screen.** Nothing from Phase 4
  onward (submitting a request, low-stock, push, offline) starts here — Phase 4 needs US1's
  sign-in flow to reach any screen at all.
- **One addition this wave needs that isn't yet in `apps/mobile/lib/core/api/`**: T022's home
  screen calls the *existing, unchanged* `GET /approvals/pending` (from 008's own contract,
  `specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml`) for an approver's
  pending-decision count. The current Dart `MobileApiClient` only covers the R2.2-specific
  contract (`devices`, `low-stock-reports`) — it has no method for this R2.1 endpoint yet. Adding
  one is in scope for T022 (see Track: OpenCode below); it is not a new backend surface, just a
  new caller of an existing one.
- **Known, deliberately out-of-scope-here defects** (do not go looking for these; flag if you
  happen to hit them, don't fix them as part of this wave): the pre-existing WCAG 2.1 AA
  color-contrast violations in `apps/web/tests/e2e/requests-a11y.spec.ts`'s approval-queue screen
  (found during Wave 1 review).

---

## 1. Non-negotiables (unchanged from Wave 1/2)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied (`tasks.md` reviewed and merged).
2. **Tenant isolation is enforced in the database**, not app code. Nothing in this wave adds a new
   table or RLS policy — if either implementer finds themselves needing one, **stop and hand it to
   Claude**, per this project's standing rule that tenancy/migration work is not delegated by
   default.
3. **No autonomous purchasing.** This is this wave's single most load-bearing rule: **FR-009
   requires the mobile app to have NO approve/reject code path anywhere, not merely no visible
   button.** T019 exists specifically to prove this at two levels (widget tree AND the generated
   API client / route table) because a widget-only proof was already flagged on Wave 2's review as
   too weak. Do not treat T019(b) as optional or as "the same thing as T019(a) restated."
4. **Every user-facing string comes from `packages/i18n`** — every string in the auth/home screens
   built this wave, no exceptions, via the existing `I18nLoader` (`apps/mobile/lib/core/i18n/`).
5. **Every monetary value carries an explicit currency.** Not directly relevant to this wave's
   screens (no money is displayed on the sign-in or home screen), but if `GET /approvals/pending`'s
   embedded request data is rendered anywhere on the home screen (it should not be — the home
   screen shows only a *count*, per T022's own text), any amount shown must carry its currency.
6. **Secrets never enter the repo.**
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report** —
   restated because Wave 2 found real, meaningful issues this way in both tracks (a missing
   functional-test gap in Codex's devices module; a wrong-base-URL bug in OpenCode's API client)
   that a self-report alone would have missed.

---

## 2. Wave 3 scope — Phase 3 (User Story 1), T018-T022

### Track: Codex

**File scope**: `apps/api/tests/integration/test_session_revocation.py` (new file only).

**Task**: T020 — prove a revoked refresh token fails to refresh regardless of a valid biometric
match having occurred client-side (FR-014), i.e. the server-side half of research.md R3's
guarantee. This is **a proof of already-existing behaviour**, not a new feature: research.md R3
states plainly that session revocation already works today because R1's refresh-token
invalidation is server-side, and biometric unlock is purely a client-side gate in front of using
an already-valid stored token — it has no way to bypass a server-side revocation. Your job is to
write the integration test that actually demonstrates this against a real Postgres/auth flow, the
same way every other integration test in `apps/api/tests/integration/` proves a real behaviour
against a real database rather than a mock.

**If the test reveals this DOESN'T actually hold** (a genuine gap, not a test-authoring mistake):
stop and report it precisely (repro, expected vs actual) rather than trying to fix the underlying
auth/session code yourself — that would be new scope well outside a single test file, and outside
this track's file scope entirely.

**Land as**: one branch, e.g. `backend/009-session-revocation-proof`.

---

### Track: OpenCode

**File scope**: `apps/mobile/lib/features/auth/**` (new), `apps/mobile/lib/features/home/**`
(new), `apps/mobile/test/features/auth/**` (new), `apps/mobile/test/features/home/**` (new),
`apps/mobile/test/core/no_approval_surface_test.dart` (new), plus ONE additive method group in the
existing `apps/mobile/lib/core/api/` (see the `GET /approvals/pending` note below — add it as a
clearly separate method/class from the R2.2-specific `MobileApiClient`, since it belongs to a
different contract; your call whether that's a new small class or an additive method on the
existing one, just don't blur the two contracts' identities together).

**Tasks**: T018, T019, T021, T022 — full task text is in `specs/009-mobile-app-mvp/tasks.md`
Phase 3; summarized precisely here, but that file is the source of truth if anything conflicts:

1. **(T021) Sign-in, biometric-enable, and sign-out screens** in `apps/mobile/lib/features/auth/`,
   built on the EXISTING `core/auth/` (`AuthService`, `BiometricGate`) and `core/i18n/`
   (`I18nLoader`) from Wave 2 — do not reimplement or duplicate what's already in `core/`, these
   screens are thin UI wrapping already-tested logic. Sign-out must actually invoke the existing
   `AuthService.signOut()` (which already calls `DELETE /devices/{id}` internally, per Wave 2) —
   wire the screen's sign-out action to that, don't reimplement the device-deletion call in the
   screen layer.

2. **(T022) Role-aware home screen** in `apps/mobile/lib/features/home/`:
   - A branch-scoped member sees a primary "Request items" action (no request-submission screen
     exists yet — Phase 4's job — so this can be a placeholder navigation target/button that does
     nothing yet, or a clearly-marked "coming soon" state; don't build a fake request flow to make
     the button do something).
   - A member holding an approver role additionally sees a **count** of requests pending their
     decision, fetched from the existing `GET /approvals/pending` (008's contract). Add the
     minimal client method needed for this (see the file-scope note above) — the endpoint returns
     a cursor-paginated list with full embedded request context per item (requester, branch,
     lines, budget status, etc.); you only need `items.length` for the count. A known, acceptable
     simplification for this release: counting only the first page (`limit` capped at 100) rather
     than exhaustively paginating for an exact total beyond that — a pilot-scale tenant is not
     expected to have more than 100 requests pending one approver at once; note this simplification
     in a code comment so it's not mistaken for an oversight later.
   - **Nothing** in the response's per-item data (assigned approver, decision fields, etc.) may be
     rendered as an actionable control — count only.

3. **(T018) Widget tests** for the sign-in/biometric-enable/sign-out flow — first sign-in,
   biometric-enable prompt, next-launch biometric unlock reaching the home screen without
   credential re-entry, and sign-out actually invoking device deletion before clearing the local
   session (assert against a fake/mock `AuthService`/`DeviceRegistrar`, matching how Wave 2's own
   `auth_service_test.dart` already fakes its dependencies — don't hit a real network).

4. **(T019) FR-009 proof, two ways** — this is the wave's single most important test, read it
   twice:
   - **(a)** A widget test on the home screen asserting NO widget tree anywhere on it contains an
     approve/reject control or a route to one — for both a branch-manager view and an approver
     view (the approver view is the one that actually has something to decide on, so it's the
     meaningful case to check; the branch-manager view trivially has nothing to check but include
     it anyway for completeness).
   - **(b)** A SEPARATE, static test (`test/core/no_approval_surface_test.dart`) that does NOT
     render any widget — instead it inspects the generated Dart API client(s) (both
     `MobileApiClient` and whatever you add for `GET /approvals/pending`) and the app's route
     table (`MaterialApp.routes`/`onGenerateRoute`, or whatever routing mechanism `T021`/`T022`'s
     screens register) and asserts that **no method name and no route name anywhere in the mobile
     app matches or calls `approve` or `reject`** in a `/requests/{id}/approve`\|`/reject` sense.
     A reasonable implementation: reflect over (or just directly reference and enumerate) the
     client class(es)' public method names and the route table's registered names/paths, and
     assert neither collection contains anything matching that pattern. This test's whole point is
     that it would catch someone adding an approve/reject call in Phase 4+ even if they never wire
     it to a visible button — don't write a test that only re-proves (a) in different words.

**Land as**: one branch, e.g. `mobile/009-auth-home-screens`.

---

## 3. Review protocol (unchanged pattern from Wave 1/2)

| Implementer | Reviewer |
|---|---|
| **Codex** (T020) | **Claude** |
| **OpenCode** (T018, T019, T021, T022) | **Claude** |

No Track A (Claude-implemented) work this wave — Phase 3 has no schema/RLS/tenancy-shaped task,
so Claude's role this wave is entirely review, matching the same "re-run the gates yourself, read
the diff against the brief, check against §1" discipline as every prior wave. Both of Wave 2's
findings (a missing-test gap, and a wrong-base-URL bug) were caught by literally running the code
and reading it line by line, not by trusting a green self-report — do the same here, especially
for T019(b), since it is the one new kind of test this project hasn't written before.

---

## 4. Wave 4 — blocked until Phase 3's Checkpoint is reviewed

Per `tasks.md`'s own Phase 3 Checkpoint: *"US1 is independently testable — sign-in, biometric
re-entry, sign-out's immediate device de-registration, and the correct role-aware home screen
(with FR-009 proven at both the widget and code-path level) all work with no request-submission or
push code required to observe the behaviour."* Once that's independently confirmed, Claude issues
a Wave 4 plan for Phase 4 — User Story 2, submitting a purchase request from mobile (T023-T027).
Phase 4 is pure mobile UI (the backend endpoints it calls are already complete, from 008) — expect
a single-track OpenCode wave with Claude reviewing, similar in shape to this one but without a
Codex track at all, unless Phase 4's own review surfaces something that needs one.

---

## 5. Cautions

- **T019(b) is new territory** — this project has never written a "prove a capability doesn't
  exist anywhere in the codebase" test before (every prior isolation/security proof tests that a
  restriction correctly *blocks* an attempted action; this one proves the action was never wired
  up to attempt in the first place). Read the delivered test carefully rather than pattern-matching
  it against familiar test shapes.
- **Don't let OpenCode re-derive Wave 2's `core/` work.** The sign-in/sign-out screens are thin UI
  over already-tested `AuthService`/`BiometricGate`/`I18nLoader` — if the diff touches
  `apps/mobile/lib/core/**` at all, that's scope creep into someone else's already-landed,
  already-reviewed work; flag it rather than accepting it.
- **Resource pressure**: per Wave 1/2's own finding, stagger Codex and OpenCode dispatches rather
  than firing both at once — Flutter's toolchain plus a disposable Postgres for Codex's test can
  both be memory-heavy on this machine.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

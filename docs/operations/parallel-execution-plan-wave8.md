# ProcurePilot — Wave 8 Execution Plan (dynamic pool)

**Written**: 2026-09-13, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave7.md` ("Wave 7"). That document's §4 promised this one
once Phase 7's Checkpoint was reviewed — it now is (T039/T041-T043 merged to `main` at `fb10b04`,
alongside T040; mobile suite 73 passed/0 failed/1 skipped, backend suite 814 passed beyond the 6
known pre-existing failures).

**Orchestration model** (unchanged from Waves 6-7, user-directed): neither the orchestrator role nor
an implementer assignment is fixed to one model. Pool: **Claude (in-house), Codex, Agy** — OpenCode
rejoins 2026-09-14. If a dispatched model hits a limit or fails mid-task, re-dispatch immediately to
another pool member; do not schedule a wait for a specific reset time.

---

## 0. Repo state right now

- `main` @ `fb10b04`. Phases 1-7 of `specs/009-mobile-app-mvp/tasks.md` are complete — all five user
  stories (sign-in, request submission, low-stock reporting, push notifications, offline queue) are
  built and independently tested.
- **This wave covers Phase 8: Polish and Cross-Cutting (T044-T049)** — tasks.md's own dependency
  note says this phase "depends on all five user stories being implemented," which is now true.
- **Every task in this phase is genuinely `[P]`** (tasks.md's own parallel marker) — none depend on
  each other, and (unlike every prior wave) **none require a new production-code write path with an
  atomicity or correctness property to get right**. T044/T045 test already-implemented behavior;
  T048/T049 correct already-stale docs; T046/T047 add tooling/tests around already-shipped screens.
  **No task in this wave is being kept in-house by default** — a departure from Waves 5-7's own
  precedent (T031/T037/T042 were kept in-house for exactly the correctness-critical-write-path
  reason that doesn't apply to anything here). If an implementer's own investigation surfaces a real
  gap that DOES turn into new production logic (e.g., T044 finding the branch-scoped-visibility
  policy doesn't actually work for `low_stock_report`), stop and hand it to the orchestrator rather
  than quietly expanding scope.
- **Confirmed already implemented, not needing new production code** (verified by reading the
  current migrations/service code before writing this plan, so implementers don't have to
  rediscover it):
  - `low_stock_report`'s branch-scoped-visibility RLS policy already exists
    (`supabase/migrations/20260912000002_low_stock_report.sql`'s `low_stock_report_scoped_visibility`
    policy) — same shape as `purchase_request`'s own scoped-visibility policy (owner sees everything,
    a member always sees their own report regardless of branch scope, an unassigned member sees
    everything, a branch-scoped member sees only their own branch). **T044 is a pure test-writing
    task against an already-correct policy** — if the tests reveal it does NOT actually behave this
    way, that is a real, reportable finding, not an assumption to code around.
  - The three audit actions T045 needs already fire on every call: `create_request()` records
    `"requests.purchase_request_created"`, `submit_request()` records
    `"requests.purchase_request_submitted"`, `create_low_stock_report()` records
    `"requests.low_stock_report_created"` (all in `apps/api/src/procurepilot_api/modules/requests/
    service.py`, each via the existing `self._record(...)` helper). **T045 is also a pure
    test-writing task** — proving the existing `test_requests_audit.py` pattern (live HTTP
    round-trip, not a mock) holds for these three specific actions, not adding new recording calls.
  - Neither `docs/architecture/data-dictionary.md` nor `docs/architecture/api-specification.md`
    mentions `DeviceRegistration`, `LowStockReport`, `PushNotification`, `/devices`, or
    `/low-stock-reports` at all yet (confirmed by grep) — T048/T049 are genuinely new doc sections,
    not corrections to something already-wrong.
- **T046 needs a scope decision the implementer should not have to guess at** (see its own section
  below) — this repo has **no existing CI workflow that touches `apps/mobile/` or Flutter at all**
  (confirmed: no `.github/workflows/*.yml` references `flutter` or `mobile`). Building a full CI job
  from nothing is a bigger lift than the other five tasks in this phase, and cold-start timing
  specifically cannot be measured in a headless CI runner without an emulator — see below for the
  recommended split.
- **Known, deliberately out-of-scope-here items** (do not go looking for these; flag if you happen
  to hit them, don't fix them as part of this wave): the pre-existing WCAG 2.1 AA color-contrast
  violation in `apps/web/tests/e2e/requests-a11y.spec.ts` (web, not mobile — unrelated to T047);
  T020's documented FR-014 (session-revocation) test-coverage gap; the no-periodic-scheduler gap for
  push-retry-sweep (Wave 6 §0); the `submit_request` Idempotency-Key enforcement gap (Wave 7 §0,
  resolved client-side for the offline-replay case only, not fixed server-wide).

---

## 1. Non-negotiables (unchanged from Wave 1-7)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied.
2. **Tenant isolation is enforced in the database.** T044 is proving an *existing* RLS policy's
   behavior, not writing a new one. If a task in this phase finds itself needing a new policy or
   migration, **stop and hand it to the orchestrator.**
3. **No autonomous purchasing (FR-009).** Not directly relevant to this phase's polish/docs/test
   work, but any accessibility fix to a screen must not add a decision-making control that doesn't
   already exist.
4. **Every user-facing string comes from `packages/i18n`.** If T047's accessibility pass adds any
   new semantic label text, it must be a real i18n key in both `en.json`/`ar.json`, not a hardcoded
   string — check first whether relevant labels already exist (Material widgets often already
   surface the existing visible label as their default semantic label with no extra code needed).
5. **Every monetary value carries an explicit currency** — not relevant to this phase.
6. **Secrets never enter the repo.**
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Same discipline as every prior wave — Wave 7's own review caught two off-by-one test-assertion
   bugs and a genuine app gap this way, in tasks that looked simple going in.

---

## 2. Wave 8 scope — Phase 8 (Polish and Cross-Cutting), T044-T049

### Track: backend tests (Codex) — T044, T045

**File scope**: `apps/api/tests/integration/test_branch_scoped_visibility.py` (extend — new test
functions only, do not restructure the existing `ScopedWorkspace` fixture or existing test
functions), `apps/api/tests/integration/test_mobile_audit.py` (new). No production code changes
expected — see §0.

**T044**: Add cases to `test_branch_scoped_visibility.py` for `low_stock_report`, mirroring the
existing `purchase_request` cases in that same file (`test_a_scoped_manager_sees_a_request_in_
their_own_branch`, `test_a_scoped_manager_does_not_see_another_branchs_request`,
`test_a_direct_fetch_of_another_branchs_request_resolves_not_found_not_forbidden`,
`test_the_requester_sees_their_own_request_even_outside_their_branch_scope` — reuse the same
`ScopedWorkspace` fixture and helper functions already in the file, don't reinvent them). Cover
exactly tasks.md's three cases:
1. A branch-scoped member sees only low-stock reports for their own branch.
2. A member always sees a report they personally raised, regardless of their own branch scoping
   (mirrors `purchase_request`'s requester-always-sees-their-own-request rule).
3. A direct reference (`GET` or equivalent fetch) to another branch's report resolves not-found,
   never forbidden (Principle III).

**T045** (new file `test_mobile_audit.py`): Follow `test_requests_audit.py`'s existing pattern
exactly (a live HTTP round-trip through the real app, not a mock of the audit writer — see that
file's own `test_audit_event_accepts_and_stores_every_requests_action` for the shape). Prove:
1. A `POST /requests` call produces a `"requests.purchase_request_created"` row in `audit_event`.
2. A `POST /requests/{id}/submit` call produces a `"requests.purchase_request_submitted"` row.
3. A `POST /low-stock-reports` call produces a `"requests.low_stock_report_created"` row.
4. (Mirroring `test_requests_audit.py`'s own existing checks) each row is immutable — no UPDATE/
   DELETE possible for any role, matching `audit_event`'s append-only constitution requirement.

**Land as**: one branch, e.g. `backend/009-cross-cutting-tests`.

---

### Track: mobile build-size / cold-start gate (dynamic — Agy, Codex as fallback) — T046

**Recommended split** (see §0 for why): this repo has no Flutter CI at all today, and cold-start
timing genuinely cannot be measured without a running emulator/device, which a headless GitHub
Actions Ubuntu runner does not provide by default.

1. **Build-size check — automate this for real**, since it doesn't need an emulator: a new
   `.github/workflows/mobile-build-size.yml` (or extend an existing workflow if one already runs
   `flutter` commands — re-check, since this changes fast) that runs `flutter build apk --release`
   (GitHub's `ubuntu-latest` runners ship the Android SDK) and asserts the resulting APK is under
   30MB (plan.md's own budget), failing the job otherwise. Keep it a single, focused job — don't
   wire up iOS/IPA size in the same pass unless a macOS runner is already budgeted for something
   else in this repo (check `.github/workflows/*.yml` first).
2. **Cold-start — write a documented manual gate**, not a fake automated one: a short, concrete
   checklist in `apps/mobile/docs/` (or `docs/operations/` if that fits this repo's existing doc
   layout better — check first) describing exactly how to measure cold start on a real or emulated
   mid-range Android device (e.g., `adb shell am start -W <package>/<activity>` gives a direct
   `TotalTime` figure) and the <2.5s budget it must meet, to be run once before any store submission
   is attempted. Do not simulate this in CI with a fake number — an unmeasured "check" that always
   passes is worse than an honest manual gate.
3. If the implementer has a good reason to believe cold-start CAN be reliably automated in this
   repo's actual CI environment (e.g., a macOS runner with an iOS simulator, or an Android emulator
   action already proven fast/stable enough not to flake), that's a reasonable alternative — but
   it's a scope decision, not the default; flag it to the orchestrator rather than silently building
   a flaky emulator-based CI job that becomes its own maintenance burden.

**Land as**: one branch, e.g. `infra/009-mobile-build-budget`.

---

### Track: mobile accessibility tests (dynamic — Agy, OpenCode once available, or Codex as fallback) — T047

**File scope**: `apps/mobile/test/a11y/**` (new directory). No production code changes are expected
by default — see the note below on when a real fix is warranted.

**Use Flutter's own built-in accessibility-guideline testing API** — this is the actual Flutter
equivalent of axe-core, not something to build from scratch: `package:flutter_test`'s
`WidgetTester.meetsGuideline()` matcher plus its four built-in guideline objects
(`androidTapTargetGuideline`, `iOSTapTargetGuideline`, `textContrastGuideline`,
`labeledTapTargetGuideline`), used together with a `SemanticsHandle` (`tester.ensureSemantics()`) so
the semantics tree is actually populated during the test. This checks real, structural properties
(minimum tap-target size, text/background contrast ratio, every tappable control having a semantic
label) against the actual rendered widget tree — not a hand-rolled heuristic.

Cover, for each of the sign-in, home, request form, and low-stock screens (already built, Wave 3/4/5):
1. `await expectLater(tester, meetsGuideline(androidTapTargetGuideline));` and the iOS equivalent —
   every interactive control meets the minimum tap-target size.
2. `await expectLater(tester, meetsGuideline(textContrastGuideline));` — text meets WCAG-equivalent
   contrast, mirroring the rigor (not the tooling) of the web app's axe-core coverage.
3. `await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));` — every tappable control
   has a semantic label a screen reader can announce.
4. A basic screen-reader-navigation smoke check using `SemanticsTester`/`find.bySemanticsLabel` to
   confirm key controls (sign-in button, submit button, etc.) are actually reachable in the
   semantics tree, not just visually present.

**If any of these genuinely fail** (a real gap, not a test-authoring mistake): that is real,
reportable production work — a missing `Semantics(label: ...)` wrapper on an icon-only button, or a
tap target sized below the guideline. Fixing a *found* gap is in scope for this task (it is
specifically what T047 exists to catch); inventing new a11y features nobody asked for is not. Any
new label text must be a real i18n key (§1.4).

**Land as**: one branch, e.g. `mobile/009-a11y-tests`.

---

### Track: architecture docs (Codex) — T048, T049

**File scope**: `docs/architecture/data-dictionary.md`, `docs/architecture/api-specification.md`.
No code changes.

**T048**: Add `## DeviceRegistration`, `## LowStockReport`, `## PushNotification` entity sections to
`data-dictionary.md`, following the exact heading/field-table convention already used for the
adjacent `## PurchaseRequest`/`## ApprovalStep`/etc. sections under "Implemented requests and
approvals entities (chunk R2.1, `008-requests-approvals`)" — add a new `## Implemented mobile MVP
entities (chunk R2.2, `009-mobile-app-mvp`)` heading above them, mirroring that pattern. Pull field
names/types/constraints directly from the actual migrations
(`supabase/migrations/20260912000001_device_registration.sql`,
`20260912000002_low_stock_report.sql`, `20260912000003_push_notification.sql`, plus
`20260912000004_low_stock_report_review_fixes.sql` and `20260912000005_purchase_request_idempotency_
key.sql` for the fields those later migrations added/changed) — don't guess field shapes from
memory, read the actual current schema.

**T049**: Add `### POST /devices`, `### DELETE /devices/{id}` (or whatever the actual verb/path is —
read `apps/api/src/procurepilot_api/modules/devices/router.py` for the real signatures, don't
assume), and `### POST /low-stock-reports` · `### GET /low-stock-reports` sections to
`api-specification.md`, under a new `## Delivered Mobile MVP API (chunk R2.2, `009-mobile-app-mvp`)`
heading, following the exact convention of the adjacent `### POST /requests` / `### GET /requests`
sections. Include the `Idempotency-Key` header behavior for both POST endpoints (real enforcement
for `/requests` and `/low-stock-reports`, per Wave 7 §0 — don't describe it as enforced everywhere
if it isn't).

**Land as**: one branch, e.g. `docs/009-architecture-updates`.

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T044, T045 | Codex (or another pool member if Codex is unavailable) | orchestrator |
| T046 | dynamic (Agy, Codex as fallback) | orchestrator |
| T047 | dynamic mobile-lane pick | orchestrator |
| T048, T049 | Codex (or another pool member if Codex is unavailable) | orchestrator |

No track in this wave needs a second implementer's independent review pass before landing (unlike
T031/T037/T042 in prior waves) — none of them touch a new correctness-critical write path. The
orchestrator's own re-run of gates remains mandatory for all four tracks regardless.

Sequencing: all four tracks are logically independent of each other and may be dispatched in any
order. Per every prior wave's own resource-contention finding, **do not run two implementer
dispatches at once on this machine** — sequence them even though tasks.md marks all of T044-T049
`[P]`.

---

## 4. Phase 8 Checkpoint, and what comes after

Per tasks.md's own Phase 8 Checkpoint: *"branch-scoped visibility and full audit coverage are proven
for both client-facing new tables, performance budgets are checked before any store submission, and
docs reflect the real delivered API/data model."* Once T044-T049 land and this is independently
confirmed, **all 49 tasks of `specs/009-mobile-app-mvp/tasks.md` are complete** — R2.2 Mobile MVP is
done. There is no Wave 9 plan implied by this spec; the next work item is whatever the product
roadmap names next (check `docs/roadmap/procurepilot_roadmap.md` §7 for the next release in
sequence) — do not assume what it is without checking, the same discipline used for every prior
"what's next" decision this session.

---

## 5. Cautions

- **Don't let T044/T045 quietly turn into "fix the policy/audit call I found broken."** Both are
  believed-correct already (§0) — if a test proves otherwise, that is exactly the kind of finding
  this phase exists to catch, but fixing it is a scope decision for the orchestrator, not something
  to silently absorb into a "test-writing" branch.
- **Don't fake the cold-start check.** A CI job that always reports "pass" without ever measuring
  anything real is worse than an honestly-manual gate — this repeats a lesson this project has
  already learned the hard way with `_send_to_device`'s old "always sent" stub (Wave 5/6).
- **T047 may not find anything to fix** — Flutter's Material widgets already provide reasonable
  accessibility defaults for a lot of standard controls. A clean pass on all four guideline checks
  is a legitimate, complete outcome; don't invent tap-target or contrast problems to "fix" something.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

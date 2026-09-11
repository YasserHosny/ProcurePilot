# ProcurePilot — Wave 2 Execution Plan (Claude / Codex / OpenCode)

**Written**: 2026-09-12, by Claude (orchestrator), continuing the 3-agent run from
`docs/operations/parallel-execution-plan.md` ("Wave 1"). That document's §4 promised this one once
Track A's `specs/009-mobile-app-mvp/tasks.md` was written and reviewed — it now is (PR #12,
merged to `main` as of commit `844fa91`).

**Audience**: shared verbatim with all three agents, same as Wave 1. Read the whole thing, then
act only on your own section. If you are Codex or OpenCode reading this cold: everything you need
is below — you do not need the orchestrating conversation's context.

---

## 0. Repo state right now (read this before doing anything)

- `main` @ `d1767af`. All four Wave 1 PRs are merged: the Web-unit-tests regression fix, the R2.2
  plan (`specs/009-mobile-app-mvp/{plan,research,data-model,contracts,tasks,quickstart}.md`), the
  two closed E2E gaps from 008 (T033/T041), and the Backend tests CI fix (dependency + audit-client
  stub + a real arithmetic-validation bug fix). CI is green: 776 backend tests, web unit tests, and
  the closed E2E gaps all pass.
- **One pre-existing, unrelated defect surfaced during Wave 1 review, still unfixed**: two WCAG
  2.1 AA color-contrast violations in `apps/web/tests/e2e/requests-a11y.spec.ts` (the approval
  queue's muted-text and reject-button colors) — found while verifying PR #13's E2E job, not
  caused by anything in Wave 1, and not assigned to anyone yet. **Not in scope for this wave.**
  Flag if you happen to touch `approval-queue.component.scss` for any reason, but do not go looking
  for it.
- `apps/mobile/` is **still exactly a placeholder README** — nothing in Wave 1 touched it. Every
  Flutter file in this wave is a genuinely new file, not an edit.
- `specs/009-mobile-app-mvp/tasks.md` (T001-T049, 8 phases) is the authoritative task list. This
  wave covers **only Phase 1 (Setup, T001-T007) and Phase 2 (Foundational, T008-T017)** — nothing
  from Phase 3 onward (User Stories 1-5) starts here. Foundational blocks every user story per
  `tasks.md`'s own Dependencies section, so there is nothing conflict-free to hand out past T017
  until this wave's Checkpoint (§4 below) is met and reviewed.
- A resource note from Wave 1, worth carrying forward: this machine hit repeated out-of-memory
  kills when two delegate CLI dispatches (Codex + OpenCode) ran in parallel, especially once a
  local Supabase stack or a Flutter toolchain was also resident. Stagger Track B and Track C's
  heavier steps rather than firing both simultaneously — see §5.

---

## 1. Non-negotiables (unchanged from Wave 1)

Same seven, from `.specify/memory/constitution.md` and `CLAUDE.md` — restated because this wave's
audience includes agents reading cold:

1. **Specification precedes code** — already satisfied for this wave (`tasks.md` reviewed and
   merged); no one re-litigates the plan while implementing it.
2. **Tenant isolation is enforced in the database**, not app code — `ENABLE`+`FORCE` RLS, both
   `USING`/`WITH CHECK`, JWT-claim tenancy only, cross-tenant reads return not-found never
   forbidden. **Every migration and RLS policy in this wave (T001-T003) is Claude's, not
   delegated** — restated explicitly in §2 below, not a general reminder this time.
3. **No autonomous purchasing.** Nothing in this wave touches `/requests/{id}/approve`\|`/reject`
   at all — Foundational doesn't reach User Story 1's FR-009 proof yet, but no task here should add
   a code path toward one either.
4. **Every user-facing string comes from `packages/i18n`** (en + ar) — applies to T005 directly,
   and to any UI copy any Flutter screen work in this wave might touch (there shouldn't be much;
   Phase 2 is mostly core/plumbing, not screens).
5. **Every monetary value carries an explicit currency.** Nothing in Phase 1-2 handles money
   directly (the three new tables carry no amount columns), but flag it if that changes.
6. **Secrets never enter the repo.** Same disposable-Postgres discipline as Wave 1 for anything
   DB-backed — Track B has a working recipe (Wave 1's own verification steps, reusable verbatim).
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report** —
   same as Wave 1's §3, restated below.

---

## 2. Wave 2 scope — Phase 1 (Setup) + Phase 2 (Foundational), T001-T017

Each track's file scope is an allowlist. If a task needs a file outside your scope, stop and say
so rather than expanding scope on your own judgment — same rule as Wave 1.

### Track A — Claude (in-house; not delegated, per Non-negotiable 2)

**File scope**: `supabase/migrations/20260911000049_device_registration.sql`,
`supabase/migrations/20260911000050_low_stock_report.sql`,
`supabase/migrations/20260911000051_push_notification.sql`,
`apps/api/tests/integration/test_tenant_isolation.py`.

**Tasks**: T001, T002, T003, T007 (`tasks.md`'s own text for each — reproduced there, not
re-derived here to avoid drift between the two documents).

**Sequencing note**: these four are genuinely independent of Track B and Track C — no other track
needs the migrations applied to do its own Phase 1-2 work (Track B's T008-T009 build the Python
module skeleton and schemas without touching the live table; Track C's Flutter/i18n work doesn't
touch the database at all). Track B's T010 is the one task in this wave that needs T001 actually
merged and migrated before it can be verified for real — call this out when Track B starts (§5).

**Land as**: one branch, e.g. `schema/009-mobile-tables`. Self-reviewed and landed the same way
Wave 1's Track A work was (Codex review, per §3), since this is schema/RLS work that stays
in-house regardless of review pairing.

---

### Track B — Codex

**File scope**: `apps/api/src/procurepilot_api/modules/devices/**` (new — `__init__.py`,
`schemas.py`, `service.py`, `router.py`, `push_job.py`), one additive line in
`apps/api/src/procurepilot_api/main.py` (router registration), an additive
`LowStockReport`/`LowStockReportCreate` block in the **existing**
`apps/api/src/procurepilot_api/modules/requests/schemas.py` (do not touch anything else in that
file), `apps/api/tests/contract/test_mobile_openapi_drift.py`.

**Tasks**: T008, T009, T011, T012, T014 — plus T010, **gated on Track A's T001 migration actually
being merged and applied** (T010's `POST /devices` upsert and `DELETE /devices/{id}` need the real
`device_registration` table to write against; T008/T009's schema/skeleton work does not).

**Do not touch**: `.github/workflows/ci.yml` or `services/extraction-worker/**` — Wave 1's Track B
work there is done and merged; nothing in this wave reopens it.

**Land as**: one branch, e.g. `backend/009-devices-module`. Push when ready; do not merge yourself
— per §3, Claude reviews.

---

### Track C — OpenCode (+ Agy for the one web-side file named below)

**File scope**: `apps/mobile/**` (the entire new Flutter project — `pubspec.yaml`, `lib/main.dart`,
platform folders, `lib/core/auth/`, `lib/core/i18n/`, `lib/core/offline_queue/`, `lib/core/api/`),
`packages/i18n/en.json` and `packages/i18n/ar.json` (additive `devices.*`/`lowStock.*` keys only —
do not touch existing keys).

**Tasks**: T004, T005, T006, T015, T016, T017, plus the **Dart-client half only** of T013 (the
Flutter API client generated from `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml` into
`apps/mobile/lib/core/api/`) — the OpenAPI contract is already merged, so this can start
immediately, independent of Track B's backend work actually running.

**Same-file caution**: T004 and T006 both edit `apps/mobile/pubspec.yaml` (T004 declares
`flutter_secure_storage`/`local_auth`/an MMKV-or-SQLite package; T006 declares the bundled i18n
JSON as Flutter assets). **Do these sequentially in one session, not as two parallel dispatches** —
a genuine two-writer conflict on the same file otherwise.

**Land as**: one branch, e.g. `mobile/009-flutter-scaffold`.

---

### T013's other half — the web client addition, via Agy

`tasks.md`'s T013 also calls for a typed frontend client addition on the **web** side
(`apps/web/src/app/features/requests/requests-api.ts`, low-stock report methods for any future web
admin visibility). Per the standing cross-cutting rule (Wave 1 §5, still in force): any
`apps/web/src/**` touch goes through Agy, not a direct edit by any track. Claude dispatches this
piece separately from Track C's Dart-client work — they're the same numbered task in `tasks.md`
but two different ecosystems with two different routing rules, already split this way in
`tasks.md`'s own Delegation lanes table.

**If Agy fails again** (Wave 1 saw three failed headless-mode dispatch attempts before this
capability was worked around): stop and report it, the same as Wave 1's own instruction — don't
silently self-implement without saying so first.

---

## 3. Review protocol (unchanged from Wave 1)

| Implementer | Reviewer |
|---|---|
| **Claude** (Track A: T001-T003, T007) | **Codex** |
| **Codex** (Track B: T008-T012, T014) | **Claude** |
| **OpenCode** (Track C: T004-T006, T013's Dart half, T015-T017) | **Claude** |

Each review: re-run the gates for that track's files (never accept a self-reported "passed" —
Wave 1 caught real gaps this way twice, once in a delegate's own sandbox limits and once in a
diagnosis that turned out incomplete), read the diff against this plan's brief for that track and
flag both scope creep and scope shortfall, check against §1's non-negotiables, then either approve
and land (push the feature branch, `git merge --no-ff` into `main`, push `main`) or send back
itemized feedback and re-review.

---

## 4. Wave 3 — blocked until Phase 2's Checkpoint is reviewed

Per `tasks.md`'s own Phase 2 Checkpoint: *"FastAPI imports the new `devices` module (register +
sign-out removal) and the extended `requests` schemas, the push-send/retry-sweep job pair exists as
an independently-invokable unit, and the Flutter app has a working auth/i18n/offline-queue core
every feature screen can build on."* Once Track A/B/C's Wave 2 work lands and that Checkpoint is
independently confirmed (not just claimed), Claude issues a Wave 3 plan dividing Phase 3 — User
Story 1, sign-in and the role-aware home screen (T018-T022) — the same conflict-free way. Phase 3
is the first phase with a hard UI dependency on Foundational actually working end-to-end (a
Flutter screen calling a real, running `/devices` endpoint), so Wave 3 cannot start from a partial
or unreviewed Wave 2.

---

## 5. Cautions

- **Migration-then-module ordering**: Track B's T010 is blocked on Track A's T001 landing on
  `main` and being migrated in whatever environment T010 is verified against. Don't let Track B
  start T010 against an un-migrated schema and call it done from a mock.
- **T013's split**: the Dart client (Track C) and the web client (Agy) are the same `tasks.md`
  task number but different files, different ecosystems, and different routing rules — don't let
  either track assume the other's half is theirs to also do.
- **T004/T006 same-file sequencing** (Track C, restated from §2): both touch
  `apps/mobile/pubspec.yaml`. One session, in order, not two parallel dispatches.
- **Resource pressure**: this machine repeatedly hit OOM kills in Wave 1 when two delegate
  dispatches (a Docker/Postgres-heavy one and a plain one) ran at the same time. Track B's
  verification (a disposable Postgres) and Track C's (a Flutter toolchain — likely its own
  resource footprint, untested yet in this repo) are both heavier than a plain read/lint dispatch.
  Stagger them; don't fire both the moment this plan is read.
- **Agy's headless-mode limitation** (Wave 1 finding, unresolved as a capability — only worked
  around once by Claude self-implementing and flagging it): if the web half of T013 hits the same
  wall, stop and report rather than repeating the workaround silently.
- **The pre-existing a11y contrast bug** (§0): not this wave's job. If Wave 3 or a later wave
  wants to pick it up, it needs its own explicit assignment, not an incidental fix bundled into
  unrelated work.
- **Constitution non-negotiables** (§1): unchanged from Wave 1, still apply to every task, however
  small.

# ProcurePilot — Wave 7 Execution Plan (dynamic pool)

**Written**: 2026-09-12, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave6.md` ("Wave 6"). That document's §4 promised this one
once Phase 6's Checkpoint was confirmed — it now is (T033-T038 merged to `main` at `1010c7e`:
backend push-notification outbox/enqueue atomically wired to a decision, mobile-side permission
abstraction + device registration + deep-link routing, 812 backend tests / 64 mobile tests passing
beyond known pre-existing gaps).

**Status of this document: written, not dispatched.** Per explicit instruction, this plan is a
write-only deliverable this round — no track below has been assigned to a live session, no worktree
has been created for it, and nothing should be dispatched from it until the user says to proceed.

**Orchestration model** (unchanged from Wave 6, user-directed): neither the orchestrator role nor
an implementer assignment is fixed to one model. The pool for this wave is **Claude (in-house),
Codex, Agy** — OpenCode rejoins the pool 2026-09-14 (still paused as of this writing, 2026-09-12).
A task below is labeled with the *best-fit* implementer for its shape, not an exclusive assignment.
If a dispatched model hits a limit or fails mid-task (including local resource exhaustion — see
Wave 6's Agy memory-pressure incident), re-dispatch the same brief to another pool member
immediately; do not schedule a wait for a specific reset time.

**Audience**: shared verbatim with whichever implementer picks up each track, once dispatch begins.

---

## 0. Repo state right now

- `main` @ `1010c7e`. Phase 6 (durable push notifications) is complete.
- **This wave covers Phase 7 of `specs/009-mobile-app-mvp/tasks.md`: User Story 5 (T039-T043) —
  keep working with a weak or no connection (FR-011, FR-012).**
- **The offline-queue primitive (T017) already exists and is already tested** —
  `apps/mobile/lib/core/offline_queue/offline_queue_service.dart` (`OfflineQueueService`:
  `createDraft`/`enqueue`/`pending`/`markConfirmed`/`markFailed`, JSON-serialized into a Hive box
  keyed by idempotency key) and `offline_queue_replay.dart` (`OfflineQueueReplay`: listens to
  `connectivity_plus`, replays every `pending` item on reconnect, dispatches by `item.endpoint`).
  `apps/mobile/test/core/offline_queue/offline_queue_service_test.dart` already covers the service
  half (5 tests: idempotency-key stamped at creation not send time, draft→queued promotion,
  `pending` excludes confirmed, retry keeps the same key, `markConfirmed` removal). **There is no
  test file for `OfflineQueueReplay` at all** — the actual replay/fan-out/send-outcome logic is
  currently untested. `hive`, `hive_flutter`, and `connectivity_plus` are already pubspec
  dependencies; this wave adds no new package.
- **`OfflineQueueReplay._send()` already special-cases `low-stock-reports` (calls
  `MobileApiClient.createLowStockReport(..., idempotencyKey: item.idempotencyKey)`) but its
  `requests` branch is a deliberate placeholder**: `throw UnimplementedError('Request queue replay
  not yet wired')`. That line is the literal, precise scope of T042's request-side half.
- **Server-side idempotent-replay coverage is asymmetric between the two mutation types this phase
  must handle — read this bullet before writing or assigning T040/T042, it is the single highest-risk
  point in this wave:**
  - `POST /low-stock-reports` (`create_low_stock_report`) is a single call, and is **fully
    idempotent-replay-safe today**: `low_stock_report` carries a real `idempotency_key` column with
    a partial unique index (`(tenant_id, idempotency_key) where idempotency_key is not null`,
    landed Wave 5 per research.md R4), and the service does an `insert ... on conflict do nothing
    returning *` with a fallback read on a zero-row insert. A replayed low-stock submission is a
    clean, already-solved problem.
  - `POST /requests` (`create_request`) **also now has real idempotency-key enforcement** — a
    parallel `idempotency_key` column + unique index landed on `purchase_request` as part of Wave
    5's PR-review remediation pass (`20260912000005_purchase_request_idempotency_key.sql`), and
    `create_request()` returns `tuple[PurchaseRequest, bool]` exactly like the low-stock path. This
    part of the flow is also already replay-safe. (`research.md`'s own R4 text, written earlier,
    says this endpoint's enforcement gap was "out of scope for this chunk" — that line is now
    **stale**; the remediation pass closed it after R4 was written. Don't let a fresh reader be
    misled by research.md's original wording without checking the current migration/service code,
    which this plan just did.)
  - **But submitting a request is a *second*, separate call — `POST /requests/{id}/submit`
    (`submit_request`) — and that endpoint's `Idempotency-Key` header is still accepted and
    ignored** (`router.py`'s `submit_request` captures it into an unused, underscore-prefixed
    `_idempotency_key` parameter; `service.py`'s `submit_request()` takes no idempotency key at
    all). Confirmed still true on `main` at time of writing. Retrying a submit that already
    succeeded does not duplicate anything (the service raises `ConflictError({"reason":
    "not_draft"})` because the status guard is `status == 'draft'`), but it also does **not**
    return the original success the way `create_request`/`create_low_stock_report` do — a naive
    replay that treats any non-2xx as "still queued, retry later" will loop forever on an already-
    submitted request.
  - **This asymmetry is exactly why T042's two mutation types are not symmetric work**, even though
    tasks.md describes them side by side. Low-stock is "swap the direct API call for the queue,
    done." Requests are not — see §2's Track: in-house for why and the recommended resolution.

- **Known, deliberately out-of-scope-here items** (do not go looking for these; flag if you happen
  to hit them, don't fix them as part of this wave): the periodic push-retry-sweep scheduler gap
  (Wave 6 §0); the pre-existing WCAG 2.1 AA color-contrast violations in `requests-a11y.spec.ts`;
  T020's documented FR-014 test-coverage gap; the raw branch/product UUID display issues on web;
  fixing `submit_request`'s idempotency-key gap as a general, codebase-wide fix (only its
  *offline-replay* consequence, scoped narrowly to what T042 needs, is this wave's job — see below).

---

## 1. Non-negotiables (unchanged from Wave 1-6)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied (spec.md/research.md/tasks.md for
   009-mobile-app-mvp already cover this phase).
2. **Tenant isolation is enforced in the database.** No new table this phase; if any task here
   finds itself needing a schema change beyond what §2 already specifies, **stop and hand it to the
   orchestrator** rather than improvising a migration.
3. **No autonomous purchasing (FR-009).** This phase is purely retry/resilience plumbing around
   submissions a human already composed and chose to send — nothing here should add a way to
   approve, reject, or auto-adjust a request or report.
4. **Every user-facing string comes from `packages/i18n`.** The three-state indicator (T043) needs
   real `offlineQueue.*`-or-similar i18n keys in both `en.json`/`ar.json` — check first whether
   anything already exists (e.g. `requests.createSuccess`/`requests.submitSuccess`, already used by
   the online path) before adding new ones, and keep en/ar in exact key parity.
5. **Every monetary value carries an explicit currency** — not directly relevant; no new money
   display in this phase.
6. **Secrets never enter the repo.**
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Every wave this session found something real this way — most recently Wave 6's T033-T035 review
   (two environment stand-in gaps) and its mobile-track review (a test-assertion bug in Codex's own
   new test, caught only by actually running it). Same discipline here — this phase's whole point is
   correctness under retry/partial-failure, exactly the kind of thing a plausible-looking diff can
   get subtly wrong without ever failing to compile.

---

## 2. Wave 7 scope — Phase 7 (User Story 5), T039-T043

### Track: in-house (T042, and the request-replay design it requires)

**Why in-house**: per this project's standing carve-out for correctness-critical outbox/retry logic
(the same reasoning that kept T002/T012/T017/T031/T037 in-house in earlier waves) — already flagged
as a likely in-house candidate in Wave 6's own §4. Confirmed correct by this plan's investigation:
the request-submission half of T042 is not a mechanical "call the queue instead of the API client"
swap, it requires a real design decision about a two-step, partially-idempotent server flow.

**Scope**: `apps/mobile/lib/core/offline_queue/offline_queue_replay.dart` (implement the `requests`
branch, currently `throw UnimplementedError`), `apps/mobile/lib/features/requests/
request_form_screen.dart` (route through the queue when offline), `apps/mobile/lib/features/
low_stock/low_stock_report_screen.dart` (route through the queue when offline — the simple half),
and wiring `OfflineQueueReplay.start()` somewhere at app lifecycle (`main.dart`, mirroring how T038
just added the notification-tap listener there — additive only).

**The low-stock half** (do this part first — it's a template for the request half's shape, and has
no open design question): on submit, check connectivity (`connectivity_plus`, already a dependency);
if offline, call `OfflineQueueService.createAndEnqueue(endpoint: 'low-stock-reports', payload: {...})`
instead of `MobileApiClient.createLowStockReport()` directly, and show the "queued" state (T043) in
place of the normal success snackbar. `OfflineQueueReplay._send()`'s existing `low-stock-reports`
case already knows how to replay this — no replay-side change needed here.

**The request half — read §0's asymmetry note above before starting**:

The form's current online flow is genuinely two sequential calls, not one:
`_saveDraft()` → `POST /requests` (creates a `draft`-status row, needs network to obtain the
server-assigned id) → `_submit()` → `POST /requests/{id}/submit` (needs that id, gated in the UI on
`_savedRequest != null`). If the device is offline from the moment the form opens, `_savedRequest`
can never be set today, so `_submit()` is currently unreachable offline — this phase must restructure
that gate, not just redirect one API call.

**Recommended design** (not mandatory if the implementer finds a better one, but any alternative
must be justified against the same constraints): model one offline "submit a request" user action as
a **single queue item** whose payload is the full `PurchaseRequestCreate` body (branch, cost centre,
required-by date, lines) plus its own stamped idempotency key — the same shape `low-stock-reports`
already uses, so `OfflineQueueService` needs no new fields. On replay, `OfflineQueueReplay`'s
`requests` case does, in order:

1. `POST /requests` with the queue item's idempotency key. Safe to call even on a second replay
   attempt after a partial prior failure — the server-side unique index means this always returns
   the *original* created row, never a duplicate (§0).
2. `POST /requests/{that id}/submit`. If this succeeds, mark the queue item `confirmed`.
3. If step 2 returns `409` with `{"reason": "not_draft"}` — the request's own current idempotency
   gap, per §0 — **re-fetch the request** (`GET /requests/{id}`, already exists) and check its
   status: `submitted` (or anything past submitted, e.g. an already-decided status) means a prior
   replay attempt's submit call actually landed and the client just didn't see the response — treat
   this as success and mark `confirmed`. Any other status on a `not_draft` conflict (e.g.
   `withdrawn`) is a genuine failure state, not a replay artifact — mark `failed`, do not silently
   swallow it.
4. Any other error on either call → `markFailed`, same as the existing low-stock path.

This keeps the fix entirely client-side and inside this wave's actual file scope (no backend change
needed, since step 1 is already enforced and step 3's re-fetch-and-check is a client-side read of
data that already exists) — consistent with research.md R4's own established precedent of not
retrofitting a systemic gap wholesale, only closing the one path this wave's own correctness
actually depends on. **If whoever implements this disagrees with keeping it client-side** (e.g.
because they'd rather give `submit_request` real idempotency-key enforcement, mirroring
`create_request`/`create_low_stock_report`, so a future caller doesn't inherit the same trap) —
that is a reasonable position and a small, well-precedented migration+service change, but it is a
scope decision, not a default: flag it to the orchestrator rather than silently expanding file scope
into a new migration.

**Land as**: its own commit(s) directly on `main` — reviewed independently (see §3) before the
mobile test tracks depend on it, same precedent as T037/Wave 6.

---

### Track: backend (Codex) — T040

**File scope**: `apps/api/tests/integration/test_idempotent_replay.py` (new). No production code
changes expected — per §0, both mutation types this test covers (`POST /requests`, `POST
/low-stock-reports`) already have real server-side enforcement landed from earlier waves.

1. A `POST /requests` call, then a second `POST /requests` with the **same** `Idempotency-Key`
   header and the same body (simulating a client retry after a dropped response) returns the
   **original** request (same `id`, `201` the first time / `200` the second — `router.py` already
   sets this via `response.status_code = status.HTTP_200_OK` when `created` is `False`) and creates
   **no second row** in `purchase_request` for that tenant.
2. Same shape for `POST /low-stock-reports` via T031's `on conflict` handling.
3. **Do not test `POST /requests/{id}/submit`'s replay behavior here** — per §0, that endpoint does
   not yet have real enforcement; testing it now would either need to assert the current
   not-idempotent behavior (a strange thing for a test named `test_idempotent_replay.py` to assert)
   or assume the in-house track's client-side fix, which lives in Flutter, not here. If the in-house
   track ends up adding real server-side enforcement to `submit_request` instead (see the escape
   hatch above), the orchestrator will fold a third case into this file at that point — don't
   anticipate it speculatively.
4. Use this codebase's standard real-Postgres integration pattern (`make_workspace()`, the fixture
   conventions already used throughout `apps/api/tests/integration/`).

**Land as**: one branch, e.g. `backend/009-idempotent-replay-tests`.

---

### Track: mobile (dynamic — Agy, OpenCode once available, or Codex as fallback) — T039, T041, T043

**Sequencing within this track**: T039 has no dependency on the in-house track and can start
immediately. **T041 needs the in-house track's T042 landed first** (it drives the actual offline→
online round trip through the real wiring, the same way Wave 6's T035 needed T037 landed before it
could be written meaningfully) — do not dispatch T041 before T042 is on `main`. T043 (the indicator
widget) can be built alongside T039 and wired in by T042 once both exist; sequence so it lands no
later than T042 needs it.

**T039 — `apps/mobile/test/core/offline_queue_test.dart`** (tasks.md's stated path; check whether
the existing `apps/mobile/test/core/offline_queue/offline_queue_service_test.dart` should instead be
extended, since it already covers most of `OfflineQueueService` — don't duplicate those 5 existing
tests). **The real gap to close: `OfflineQueueReplay` has no test file at all.** Cover:
- `processQueue()` sends every `pending` item and calls `markConfirmed` on success.
- A send failure for one item calls `markFailed` (and increments `retries`) without stopping the
  loop from processing the rest of the queue — mirror the existing `sweep_stale_push_notifications`
  unit-test pattern from Wave 6 (`test_push_sweep.py`'s "one failure doesn't stop the rest") since
  it's the same shape of loop-with-partial-failure logic, already proven useful in this codebase.
- `_onChanged` only triggers `processQueue()` on a result other than `ConnectivityResult.none` (i.e.
  going offline does not spuriously trigger a send attempt).
- The queue never reports "confirmed" without the fake API client actually having been called and
  returned success (FR-012 — no optimistic marking).

**T040**: see the backend track above.

**T041 — `apps/mobile/test/integration/offline_submission_test.dart`** (new): simulate no
connectivity (fake `Connectivity`/`ConnectivityResult.none`, matching how `auth_flow_test.dart` or
similar already fake platform channels in this suite), build and submit a request AND a low-stock
report, confirm each shows queued (not failed, not silently "done" — use T043's status widget's own
keys/labels to assert this, not a guess at what text might appear), then simulate connectivity
restored and confirm each completes exactly once with the confirmed state showing (SC-005, SC-006).
Reuse `test_helpers.dart`'s existing fake API clients — extend, don't reinvent (the same review
finding from Wave 4/6 that keeps recurring).

**T043 — `apps/mobile/lib/core/offline_queue/status_widgets.dart`** (new): a small set of widgets
(or one widget parameterized by `QueueItemStatus`) rendering the three honest states — local draft /
queued / confirmed — consumed by both `request_form_screen.dart` and `low_stock_report_screen.dart`
so neither screen invents its own success-state logic (FR-012, tasks.md's own wording). Check
`packages/i18n` for existing strings close to this shape before adding new keys; keep en/ar parity.

**File scope discipline** (carried over verbatim from every prior mobile track's review): do not
touch `apps/mobile/lib/features/auth/**` or `apps/mobile/lib/features/notifications/**`, and nothing
resembling an approve/reject/decision surface anywhere.

**Land as**: one branch, e.g. `mobile/009-offline-queue-tests` (T039/T041/T043 together, since
they're one implementer's track) — separate from the in-house track's T042 commit(s).

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T042 (+ request-replay design) | in-house (whichever model is orchestrating) | another pool member, independent read-only pass — same precedent as Wave 5's T031 and Wave 6's T037 |
| T040 | Codex (or another pool member if Codex is unavailable) | orchestrator |
| T039, T041, T043 | dynamic mobile-lane pick | orchestrator |

Sequencing: T039/T040 have no dependency on T042 and may be dispatched immediately once this plan
is approved to proceed. T042 should land before T041 is dispatched (T041 needs real wiring to drive
end-to-end). Per every prior wave's own resource-contention finding, **do not run two implementer
dispatches at once on this machine** — sequence them even when there is no logical dependency,
and prefer Codex over Agy for anything dispatched while system memory is under visible pressure
(Wave 6's Agy dispatch died twice to local memory exhaustion, unrelated to permissions).

Given this phase's core risk is a subtle, easy-to-miss server/client asymmetry (§0) rather than an
obviously wrong design (Wave 6's T037 problem) or a missing dependency (Wave 6's T038 problem), the
independent reviewer of T042 should specifically re-verify the request-replay behavior against a
real disposable Postgres with a real "submit already happened, retry the submit call anyway"
scenario — not just read the code and agree it looks reasonable.

---

## 4. Wave 8 — blocked until Phase 7's Checkpoint is reviewed

Per `tasks.md`'s own Phase 7 Checkpoint: *"US1-US4 already work correctly on a normal connection;
this phase only adds resilience for a degraded one, now proven for both of FR-011's mutation
types."* Once confirmed, the next plan covers Phase 8 — Polish and Cross-Cutting, which per
tasks.md's own dependency note depends on all five user stories being implemented (i.e., it cannot
start before this wave lands). No task-by-task breakdown for Phase 8 is attempted here; write that
plan once Phase 7 is actually done, the same discipline used for every wave so far.

---

## 5. Cautions

- **§0's create/submit asymmetry is this wave's single highest-risk point** — a request-side replay
  implementation that doesn't handle the `submit_request` "already succeeded but the header is
  ignored" case will either loop forever retrying a submit that already landed, or (worse, if
  someone "fixes" it by treating any error as success) silently swallow a real failure. Whoever
  reviews T042 should specifically force this exact scenario, not just the happy path.
- **`research.md`'s R4 section contains one now-stale sentence** (that `/requests`' idempotency gap
  was out of scope for the mobile-MVP chunk) — it was true when written and became false after
  Wave 5's PR-review remediation pass closed part of that gap. Don't propagate the stale claim
  forward into new documentation without checking current code first, the same mistake research.md
  itself flags having made once already (its own "Correction to the original version of this
  decision" language).
- **Don't duplicate existing test coverage.** `offline_queue_service_test.dart` already covers
  `OfflineQueueService` well; T039's real job is `OfflineQueueReplay`, which has zero coverage today.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

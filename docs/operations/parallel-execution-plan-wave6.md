# ProcurePilot — Wave 6 Execution Plan (Codex / dynamic mobile lane)

**Written**: 2026-09-12, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave5.md` ("Wave 5"). That document's §4 promised this
one once Phase 5's Checkpoint was independently confirmed — it now is (all of T028-T032 merged to
`main`, 799 backend tests passing beyond the 6 pre-existing unrelated failures, 61 mobile tests
passing). Wave 5 also included a separate, user-requested remediation pass fixing 9 confirmed
findings from automated GitHub PR review across earlier waves (`54fd802`, `bae71f9`) — unrelated
to Phase 6 itself but landed on `main` before this plan was written, so §0 reflects that state.

**Orchestration model for this wave (new, user-directed)**: neither the orchestrator role nor an
implementer assignment is fixed to one model.
- **Orchestrator**: whichever session is acting as orchestrator initiates dispatch; if it hits a
  usage limit, any other available model picks up the orchestrator role from this same plan doc
  and the current git state — there is no single "only Claude can run this" assumption.
- **Implementer dispatch is dynamic**: the pool for this wave is **Claude (in-house), Codex, Agy**
  — OpenCode rejoins the pool on 2026-09-14 (weekly-limit pause, see the standing memory on this).
  A task below is labeled with the *best-fit* implementer for its shape, not an exclusive
  assignment. If a dispatched model hits a limit or otherwise fails mid-task, re-dispatch the same
  brief to another pool member immediately — do not schedule a wait for a specific reset time.
- Per this wave's own Codex-reviews-Claude precedent from Wave 5, **T037 (in-house) gets an
  independent review pass from another pool member before landing**, same as before.

**Audience**: shared verbatim with whichever implementer picks up each track.

---

## 0. Repo state right now

- `main` @ `bae71f9`. Phase 5 (low-stock reporting) is complete. The Wave 5 remediation pass also
  changed two files this wave's own tasks touch:
  - `apps/api/src/procurepilot_api/modules/devices/push_job.py`: `_send_to_device` is now
    **honest** — with no real FCM/APNs provider configured (none exist anywhere in this codebase),
    it returns `False` rather than faking success, so `process_push_notification` correctly lands
    a real registration in `failed` rather than a lying `sent`. **This wave's T037 does not change
    that behavior** — it only adds the *write-and-enqueue* half (a decision creates the row and
    schedules the job); whether that job's own send later succeeds or honestly fails is unrelated
    to whether T037 wired it correctly.
  - `sweep_stale_push_notifications()` (T012, already built) is still not invoked by anything
    periodic — `python -m procurepilot_api.modules.devices.push_job` runs one pass on demand, but
    no scheduler exists in this codebase yet (confirmed: no APScheduler, no rq-scheduler, no cron
    container). **This remains an open operational gap, not something this wave resolves** — T037
    only needs the job *enqueued immediately* on a decision, which already works via the existing
    RQ queue; the periodic *retry* path for a job that never got enqueued in the first place is the
    unresolved piece, unaffected by this wave.
- **This wave covers Phase 6 of `specs/009-mobile-app-mvp/tasks.md`: User Story 4 (T033-T038) —
  durable push notifications on decision.**
- **The one piece of this phase that is NOT obvious from tasks.md and must not be gotten wrong**:
  `push_notification`'s own migration (`supabase/migrations/20260912000003_push_notification.sql`)
  grants `select, insert, update, delete` to `service_role` **only** — `authenticated` has **no
  grant at all** on this table (deliberate: "no client-facing read policy this release"). This
  means **T037's insert into `push_notification` cannot go through the decider's own
  `authenticated_client(bearer_token)`** (the pattern every other write in `requests/service.py`
  uses) — it will fail with a permission error. It must go through a **service-role client**,
  exactly the pattern `catalogue/service.py`'s `_service_role_client()` already establishes
  (`create_client(settings.supabase_url, settings.supabase_service_role_key.get_secret_value())`).
  Get this wrong and every decision on a submitted request starts failing outright, not just
  silently skipping the notification.
- **Known, deliberately out-of-scope-here items** (do not go looking for these; flag if you happen
  to hit them, don't fix them as part of this wave): the periodic-scheduler gap noted above; the
  pre-existing WCAG 2.1 AA color-contrast violations in `requests-a11y.spec.ts`; T020's documented
  FR-014 test-coverage gap; the raw branch/product UUID display issues on web.

---

## 1. Non-negotiables (unchanged from Wave 1-5)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied.
2. **Tenant isolation is enforced in the database.** `push_notification`'s RLS
   (`ENABLE`+`FORCE`, tenant-isolation policy) is already live — T037 must not touch it, only
   write through the service-role client per §0. If any task here finds itself needing a new
   table, column, or RLS policy, **stop and hand it to the orchestrator.**
3. **No autonomous purchasing (FR-009).** This phase is purely notification plumbing — informing a
   requester their own request was decided. It must not add any new way to approve/reject from
   mobile. If `apps/mobile/lib/features/notifications/` ends up referencing anything that looks
   like a decision action, that's a scope violation — flag it.
4. **Every user-facing string comes from `packages/i18n`.** Push notification title/body content
   (T038's deep-link screen, any permission-request copy) needs real `notifications.*`-style i18n
   keys in both `en.json`/`ar.json` — check first whether anything already exists from earlier
   scaffolding before adding new ones.
5. **Every monetary value carries an explicit currency** — not directly relevant; no money is
   shown in a push notification or its deep-linked screen beyond what the existing request detail
   screen (T027, already correct) already renders.
6. **Secrets never enter the repo.** No real FCM/APNs credentials exist and none should be
   fabricated or hardcoded as part of this wave — the send path stays the honest stub from §0.
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Every wave this session found something real this way — most recently Wave 5's T031 review
   (a missing branch-authorization check and a numeric/string decode bug, both found by an
   independent Codex pass over Claude's own "verified" work) and the PR-review remediation pass
   (9 confirmed, previously-unactioned findings from automated review). Same discipline here.

---

## 2. Wave 6 scope — Phase 6 (User Story 4), T033-T038

### Track: in-house (T037)

**Why in-house**: per this project's standing carve-out for correctness-critical outbox/write
logic (the same reasoning that kept T002/T012/T017/T031/T042 in-house in earlier waves).

**Revised after Codex's debate pass on this plan (2026-09-12) — the original design below was
wrong and would not have shipped a real atomicity guarantee.** The original text proposed
inserting `push_notification` via a *second, separate* service-role client call after
`_decide_request()`'s existing writes — that is not "the same transaction as the decision"
tasks.md's own T037 wording requires (research.md R1), it is a third independent HTTP write on top
of two that the method's own existing comment already admits aren't atomic with each other. Codex
caught this; it is the single most important thing this plan needed to get right.

**The existing pre-write checks are unchanged**: `_fetch_request()`, the `status != 'submitted'`
conflict check, `_fetch_step()`, the `status != 'pending'` conflict check, and
`_require_assigned_approver_or_owner(step_row, member)` all stay exactly as they are today, via
the existing `authenticated_client()` reads, run *before* opening the new transaction below. Only
the three *writes* that currently happen as separate PostgREST calls move into one atomic block —
this is deliberately narrow in scope, not a rewrite of the method's authorization logic.

**Corrected implementation**: `_decide_request()`'s three writes — the `purchase_request` status
update, the `approval_step` decision update, and the `push_notification` insert — move to a
**single raw `psycopg` transaction**, mirroring the exact pattern `devices/service.py`'s
`_authenticated_db()` already establishes in this codebase (a deliberate, isolated exception to
this file's otherwise-uniform PostgREST/`authenticated_client` style, and worth a code comment
explaining why, so it doesn't read as an oversight later):

1. Open one `psycopg.connect(...)` block (`dict_row` factory, matching `devices/service.py`'s
   convention so the resulting rows are drop-in compatible with this file's existing
   `_purchase_request_with_budget_status()`/`_one_row_or_conflict()`-style helpers).
2. `set local role authenticated` + `set_config('request.jwt.claims', ...)` with the deciding
   member's claims (same shape `_authenticated_db()` builds) — this is what makes the next two
   writes respect RLS exactly as they do today (the assigned-approver-or-owner check, the
   `status = 'submitted'`/`status = 'pending'` guards).
3. `UPDATE purchase_request ... WHERE id = %s AND status = 'submitted' RETURNING *` — same guard
   as today's existing code.
4. `UPDATE approval_step ... WHERE id = %s AND status = 'pending' RETURNING *` — same guard as
   today.
5. `set local role service_role` — switches privilege **within the same open transaction** (no new
   connection) for the one write that needs it, since `push_notification` grants nothing to
   `authenticated` at all (§0).
6. `INSERT INTO push_notification (tenant_id, purchase_request_id, member_id) VALUES (...)
   RETURNING id` — `member_id` is the REQUESTER (`requested_by_membership_id` from step 3's row),
   not the decider.
7. Exit the `with` block with no exception → psycopg commits all three writes atomically. Any
   exception anywhere in steps 3-6 → the whole block rolls back — the decision itself never
   partially applies, and a `push_notification` insert failure now cleanly fails the *entire*
   decision rather than leaving an ambiguous half-applied state (this resolves Codex's second
   finding: the ambiguity existed only because the design was non-atomic in the first place).
8. **Only after that transaction has committed successfully**, enqueue T011's existing job for the
   new row (via a public wrapper around `push_job.py`'s currently-private `_enqueue_push_job` —
   expose it properly rather than reaching into another module's private function, per this
   project's own module-boundary convention). The enqueue call is necessarily outside the DB
   transaction (Redis isn't Postgres) — if it fails, log it and do not raise: the row is already
   durably `queued` in the database at that point, so nothing about the decision itself is lost.
   **Correction to the original wording**: do not call this "recoverable by the periodic sweep" —
   per §0, no scheduler exists yet, so a lost enqueue currently has **no automatic recovery path**,
   only a durable row an operator could requeue manually. State that plainly rather than implying
   an automatic safety net that doesn't exist.
9. Line/budget-status assembly for the method's *response* (unchanged) still goes through the
   existing `authenticated_client()`-based read helpers *after* the transaction commits — only the
   three writes move to raw psycopg; the existing read/response-assembly path is untouched, to keep
   this change as surgical as possible.

**Land as**: its own commit directly on `main` — reviewed independently (see §3) before Codex's
T035 depends on it. Given the scope grew from a simple insert to a transaction rewrite of
`_decide_request()`'s write path, the reviewer should re-verify the RLS-guard behavior (a
non-owner, non-assigned-approver member attempting a decision) still refuses exactly as it does
today, not just that the happy path now writes three rows atomically.

---

### Track: Codex (backend) — T033, T034, T035

**File scope**: `apps/api/tests/unit/test_push_job.py` (new),
`apps/api/tests/unit/test_push_sweep.py` (new),
`apps/api/tests/integration/test_decision_push_trigger.py` (new). No production code changes.

1. **(T033) Unit test for the push-send job's fan-out** in `test_push_job.py`: sends to every
   current `device_registration` for the notification's member; no send attempted when the member
   has zero registrations (FR-008 — already covered at the integration level in
   `test_devices.py::test_push_job_marks_sent_even_with_zero_device_registrations`, but T033 wants
   this at the **unit** level, mocking `_send_to_device` directly rather than hitting a real
   Postgres); the job marks the row `sent`/`failed` correctly (note: with no real provider
   configured, per §0, a real registration currently always yields `failed` — write this test
   against that actual current behavior, not the pre-remediation "always sent" behavior); the job
   never raises in a way that could propagate to its caller. This has zero UI dependency and zero
   dependency on T037 — can start immediately, does not need to wait for the in-house track.
2. **(T034) Unit test for the retry-sweep task** in `test_push_sweep.py`: a row stuck `queued`/
   `failed` past `RETRY_SWEEP_AGE` is re-enqueued; a `sent` row is left alone; a row that has
   exhausted `MAX_PUSH_ATTEMPTS` stops being re-swept. Also has zero dependency on T037 — can start
   immediately.
3. **(T035) Integration test** in `test_decision_push_trigger.py`, using this codebase's standard
   `make_workspace()`/`act_as()`/shared-`conn`-fixture pattern: an approve/reject decision writes
   **exactly one** `push_notification` row (`queued`) in the same request, with the correct
   `purchase_request_id` and `member_id` (the requester, not the decider — get this backwards and
   the requester never finds out their own request was decided), and that the row survives (is
   still queryable) even when the job-enqueue call itself is simulated as failing. **This test
   needs T037 already landed** — do not start it until the in-house track's commit is on `main`.

**If T037 (already landed by the time you read this, or landed partway through your dispatch) has
a real bug**: report it precisely rather than patching `service.py`/`push_job.py` yourself — same
rule as every prior wave's in-house-track carve-out.

**Land as**: one branch, e.g. `backend/009-push-notification-tests`.

---

### Track: mobile (dynamic — Agy, OpenCode once available, or Codex as fallback) — T036, T038

**Revised after Codex's debate pass — two real gaps in the original scope below:**
- `apps/mobile/pubspec.yaml` has **no push-notification plugin at all** (no `firebase_messaging`,
  no APNs package) — the original wording ("request OS permission," "the platform's push token")
  silently assumed a real native SDK integration that doesn't exist and is out of scope to add
  this wave (the backend side of this feature is *also* a deliberate stub with no real FCM/APNs
  credentials, per §0 — building a real client-side SDK integration against a backend that cannot
  really deliver anything yet would be asymmetric and largely unverifiable work). **This wave
  builds an injectable permission/token abstraction with a fake implementation, mirroring
  `BiometricAuth`'s existing abstract-class-plus-fake pattern in this exact codebase** —
  real plugin wiring is future work once Phase 6's backend side has a real provider.
- The original file scope forbade touching `main.dart`, `features/home/`, and `features/auth/`
  entirely — but permission-prompting and notification-tap routing both need a real integration
  point somewhere in the app's existing navigation/lifecycle, which those "forbidden" files own.
  The scope below now explicitly names the allowed touch points instead of a blanket ban.

**File scope**: `apps/mobile/lib/features/notifications/**` (new — the permission abstraction,
its fake implementation, and the deep-link handler), `apps/mobile/test/features/notifications/
push_notification_test.dart` (new). **Explicitly allowed, narrowly**: `apps/mobile/lib/main.dart`
(registering the notification-tap listener and wiring the permission-request call into app
startup — additive only, mirroring how `ServiceProvider`/`appRoutes` are already wired there) and
`apps/mobile/test/test_helpers.dart` (extending the shared fakes). **Still forbidden**: anything
in `apps/mobile/lib/features/requests/**`, `apps/mobile/lib/features/home/**`, or
`apps/mobile/lib/features/auth/**` beyond that one `main.dart` wiring point — and, as always,
nothing resembling an approve/reject surface anywhere. No changes expected in
`apps/mobile/lib/core/api/**` beyond what's needed to call `POST /devices` on permission grant —
that endpoint and its Dart method (`MobileApiClient.registerDevice(platform:, pushToken:, ...)`)
already exist from Wave 2; if you find yourself adding a new client method for this, check
`mobile_api_client.dart` again first.

1. **(T038) Notification-permission abstraction, registration, and deep-link routing**:
   - Define an abstract `NotificationPermission` (or similar) interface — mirroring
     `BiometricAuth`'s shape in `apps/mobile/lib/core/auth/biometric_gate.dart` — with a real
     platform-agnostic implementation that, for now, always resolves "granted" and returns a
     locally-generated placeholder token (e.g. a UUID, same discipline as the offline queue's own
     idempotency-key generation) rather than a real FCM/APNs token — clearly commented as a stand-
     in for the real plugin integration Phase 6's backend doesn't yet support anyway.
   - On grant (real or stand-in), call `MobileApiClient.registerDevice()` with that token (T015's
     existing device-registration flow, already built — reuse it, don't reimplement).
   - On decline, the app must remain fully functional and a decided request must still be visible
     on the requester's next app open via the existing request list/detail screens (T027) —
     permission is a notification-delivery convenience, never a gate on using the app (FR-008,
     mirroring the already-proven backend principle that zero device registrations is not an
     error).
   - Deep-link routing: a tapped notification carries only `purchase_request_id` (T037's write has
     no other payload) — the handler fetches the request via `RequestsApiClient.getRequest()`
     before navigating to `RequestDetailScreen` (already built in Wave 4, and already has an
     ID-based-argument code path per its own existing handling of a bare id — reuse that, don't
     add a second navigation shape to the same screen).
2. **(T036) Widget/integration tests** in `push_notification_test.dart`: permission granted (via
   the fake implementation) → registration call fires with the generated token; permission
   declined → app remains fully functional (no crash, no gate) and a previously-decided request is
   still visible on next open via the existing list screen; tapping a (simulated) notification
   payload fetches the request and opens directly to its detail view. Fake
   `MobileApiClient`/`RequestsApiClient` the same way `test_helpers.dart` already fakes them
   elsewhere — extend the shared fakes, don't write new divergent ones (a Wave 4 review finding
   already caught this pattern once).

**Scope discipline** (carried over verbatim from every prior mobile track's review): stay inside
the file scope above. Do not touch `apps/mobile/lib/features/requests/**`,
`apps/mobile/lib/features/home/**`, `apps/mobile/lib/features/auth/**`, or anything under
`apps/mobile/lib/core/**` beyond calling already-existing methods. If your tool reformats a file it
merely opens to read, revert it before finishing or flag it plainly in your report.

**Land as**: one branch, e.g. `mobile/009-push-notifications`.

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T037 | in-house (whichever model is orchestrating) | another pool member, independent read-only pass — same precedent as Wave 5's T031 |
| T033-T035 | Codex (or another pool member if Codex is unavailable) | orchestrator |
| T036, T038 | dynamic mobile-lane pick | orchestrator |

Sequencing: T037 lands first (T035 needs it live; T036/T038 do not strictly need it, since they
exercise the client side of an already-existing, unchanged `/devices` registration flow and a
simulated notification payload, but land it first anyway to keep the wave's own dependency graph
simple). T033/T034 have no dependency on T037 and may be dispatched immediately, even before T037
lands, if the orchestrator wants to parallelize — but per every prior wave's own resource-
contention finding, **do not run two implementer dispatches at once on this machine**; sequence
them even when there's no logical dependency.

---

## 4. Wave 7 — blocked until Phase 6's Checkpoint is reviewed

Per `tasks.md`'s own Phase 6 Checkpoint: *"a decided request reliably produces exactly one
durable, recoverable push record, and the app degrades correctly with permission declined, on top
of US1/US2's working sign-in-and-submit loop."* Once confirmed, the next plan covers Phase 7 —
User Story 5, the offline queue (T039-T043), wrapping the already-built request form (US2) and
low-stock screen (US3) with the offline-queue primitive that already exists
(`apps/mobile/lib/core/offline_queue/`). T042 (wiring) is another in-house-carve-out candidate by
the same reasoning as T037.

---

## 5. Cautions

- **The service-role-client detail in §0/§2 is this wave's single highest-risk point** — a wrong
  client on that insert doesn't just skip a notification, it can make the entire approve/reject
  endpoint start returning errors on every submitted-request decision. Whoever reviews T037 should
  specifically re-verify this against a real (or realistically mocked) permissions boundary, not
  just read the code and assume it's right.
- **Don't treat "sent" as the expected outcome of any new test in this wave.** Per §0, a real
  device registration with no provider configured now honestly lands in `failed` — a test written
  against the pre-remediation "always sent" assumption will be wrong, not just outdated.
- **No periodic scheduler exists for the retry sweep** — do not assume T037's enqueue is a
  complete recovery story; a lost enqueue still has no automatic retry path in this codebase yet.
  That gap is unchanged by this wave and remains open.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

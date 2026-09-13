# ProcurePilot — Wave 10 Execution Plan (dynamic pool)

**Written**: 2026-09-13, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave9.md` ("Wave 9"). That document's §4 named this wave
next once T001-T008 landed and were independently reviewed — both are now true (`main` @
`ad19409`, Codex's read-only review found no findings).

**Orchestration model** (unchanged from Waves 6-9): neither the orchestrator role nor an
implementer assignment is fixed to one model. Pool: **Claude (in-house), Codex, Agy** — OpenCode
rejoined the pool 2026-09-14 per the standing memory, one day before this wave's date; treat it as
available unless a dispatch proves otherwise. If a dispatched model hits a limit or fails
mid-task, re-dispatch immediately to another pool member; do not schedule a wait for a specific
reset time.

---

## 0. Repo state right now

- `main` @ `ad19409`. `specs/010-mobile-approvals-receipt/tasks.md`'s Phase 1 (Setup) and Phase 2
  (Foundational) are complete: `purchase_request_status` has `ordered`/`delivered`, an approval
  automatically lands a request on `ordered`, `delivery_quality_issue`/`_photo` exist, and the
  mobile side has the new model fields plus a `CameraCapture` abstraction.
- **This wave covers tasks.md's Phase 3 (User Story 1, T009-T016)** — deciding on a pending
  request from mobile. Per tasks.md's own Dependencies section, this phase needs only Phase 2
  (already done) — it is pure mobile-client work against 008-requests-approvals' existing,
  unchanged decision endpoints (research.md R2). **No backend change is expected in this wave.**
- **Unlike Wave 9, this wave is a genuine delegation candidate**, not an in-house track — it
  touches no schema, no RLS policy, and no correctness-critical write path; it is UI plus two new
  thin client methods calling an already-proven endpoint. Dispatch to Codex (or Agy as fallback,
  with the standing `--dangerously-skip-permissions` approval) rather than keeping it in-house.
- **Two concrete groundwork findings from this plan's own investigation, so the implementer
  doesn't have to rediscover them**:
  1. `RequestsApiClient` (not `ApprovalsApiClient`) is where `submitRequest`/`withdrawRequest`
     already live — T012's new `approveRequest`/`rejectRequest` methods should go there too, for
     consistency, even though tasks.md left the exact class an open question. `ApprovalsApiClient`
     stays read-focused (`listPendingApprovals`).
  2. **Nearly all the i18n copy T016 needs already exists**, from the web approval queue's own
     `approvals.*` keys in `packages/i18n/en.json`/`ar.json`: `approvals.title`,
     `approvals.actions.approve`\|`reject`, `approvals.decisionDialog.*` (approve/reject title,
     comment label/placeholder, confirm/cancel), `approvals.approveSuccess`\|`rejectSuccess`,
     `approvals.genericError`, `approvals.empty`, and the `approvals.columns.*`/budget labels
     already used to render exactly the fields this feature's decision screen needs (lines,
     estimated total, budget status, requester). **The one genuinely missing key** is a specific
     message for spec.md's Acceptance Scenario 4 (a request already decided by someone else) —
     the web app has no equivalent key today (it appears to just show `genericError` for this
     case), so add `approvals.alreadyDecided` as the one new key, in both `en.json`/`ar.json`.
     T016 should be "reuse existing keys, add exactly one new one," not a fresh key set.

---

## 1. Non-negotiables (unchanged from Wave 1-9)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied.
2. **Tenant isolation is enforced in the database.** Not directly exercised by this wave (no new
   table, no new endpoint) — this wave calls existing, already-isolated endpoints.
3. **No autonomous purchasing.** The single most important gate for this wave, mirroring Wave 9's
   own T006 caution but on the client side this time: the mobile client MUST call the exact same
   `POST /requests/{id}/approve`\|`/reject` endpoints 008 already built, with no new parameter, no
   client-side shortcut, and no way to reach a decided state without the member actually tapping
   approve/reject with the real endpoint round-trip completing.
4. **No secrets in the repo.**
5. **Every user-facing string comes from `packages/i18n`.** Per §0's finding, this wave should add
   exactly one new key (`approvals.alreadyDecided`) — reuse everything else. Do not add a
   parallel, mobile-only copy of text that already exists for web.
6. **Every monetary value carries an explicit currency.** Not touched — the estimated
   total/budget status this wave displays are already-`Money`-typed fields from the existing
   `PurchaseRequest` model.
7. **`audit_event` is append-only.** Not touched — this wave calls the existing decision
   endpoints, whose audit recording is already correct and unchanged (Wave 9 verified this).
8. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Same discipline as every prior wave.

---

## 2. Wave 10 scope — tasks.md Phase 3 (User Story 1), T009-T016

### Track: mobile (Codex, or Agy as fallback) — T009-T016

**File scope**: `apps/mobile/lib/core/api/approvals_api_client.dart`,
`apps/mobile/lib/core/api/requests_api_client.dart` (new methods only, per §0's finding #1),
`apps/mobile/lib/features/approvals/**` (new directory), `apps/mobile/lib/features/home/
home_screen.dart` (the one existing-file edit, additive — turning the read-only count into a
link), `apps/mobile/test/features/approvals/**` (new), `packages/i18n/en.json`/`ar.json` (one new
key per §0). No backend file should need to change for this wave — if the implementer finds
themselves needing to touch `apps/api/`, stop and flag it to the orchestrator rather than
expanding scope, since research.md R2 specifically designed this feature to need none.

1. **(T011)** Replace `PendingApprovalsList`'s deliberately-untyped `Map<String, dynamic>` items
   (added in 009-mobile-app-mvp specifically so approve/reject-relevant fields could not be
   rendered — read that class's own doc comment in `approvals_api_client.dart` first) with proper
   `PurchaseRequest` objects, now that this release authorizes mobile to act on them.
2. **(T012)** Add `approveRequest(requestId, {comment})` and `rejectRequest(requestId, {comment})`
   to `RequestsApiClient` (§0 finding #1 — not `ApprovalsApiClient`), calling the existing
   `POST /requests/{id}/approve`\|`/reject` endpoints with no new parameters.
3. **(T013)** Build the approval queue screen (`features/approvals/approval_queue_screen.dart`)
   listing pending requests via T011's now-typed `listPendingApprovals()`. Reuse
   `approvals.title`/`approvals.empty` i18n keys.
4. **(T014)** Build the decision detail screen (`features/approvals/approval_decision_screen.dart`)
   — lines, estimated total, budget status, requester. Reuse `RequestDetailScreen`'s existing
   rendering pieces for these (it already renders exactly this shape for a requester's own view —
   do not duplicate that layout logic in a second widget tree). Add a comment field and
   approve/reject buttons using `approvals.decisionDialog.*`/`approvals.actions.*` keys. On a
   `409` response with `details.reason == "no_pending_approval"`, show the new
   `approvals.alreadyDecided` message (spec.md Acceptance Scenario 4) rather than
   `approvals.genericError`.
5. **(T015)** Turn the existing read-only pending-approvals count on `home_screen.dart` (built in
   009) into a tappable link into T013's queue, for a member holding approval authority only —
   additive change to an existing file, do not restructure the screen otherwise.
6. **(T016)** Add exactly one new i18n key, `approvals.alreadyDecided`, to both `en.json`/`ar.json`
   in parity. Do not add any other new key without first confirming (per §0) that an existing one
   doesn't already cover it.
7. **(T009-T010)** Widget tests for both new screens, per tasks.md's own descriptions — reuse
   `test_helpers.dart`'s existing fake API clients, extend them if a new fake method is needed
   (e.g. `FakeRequestsApiClient` gaining `approveRequest`/`rejectRequest` call-tracking), don't
   build a second, divergent fake.

**Land as**: one branch, e.g. `mobile/010-decide-from-mobile`.

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T009-T016 | Codex (or Agy as fallback) | orchestrator |

No independent second-implementer review is needed for this track (unlike Wave 9's T006) — it
touches no correctness-critical write path or RLS policy, only client-side UI calling an
already-proven, already-audited endpoint pair. The orchestrator's own gate re-run (flutter
analyze, the full mobile suite, and a manual read of the diff against research.md R2's "no new
decision path" constraint) remains mandatory regardless.

---

## 4. What comes after

Once T009-T016 land, tasks.md's own Dependencies section leaves Phase 4 (US2, confirm delivery,
T017-T023) and Phase 5 (US3, quality issue + photo, T024-T032) both still unblocked by Phase 2
alone — neither needs US1 to be done first (an `ordered` request can come from a decision made on
web just as validly as one made from this wave's new mobile screen). Wave 11 should cover
Phase 4 next, per tasks.md's own priority ordering (P1 before P2), followed by Wave 12 (Phase 5)
and Wave 13 (Phase 6, Cross-cutting) — the same one-phase-per-wave pattern used throughout this
feature's predecessor, 009-mobile-app-mvp.

---

## 5. Cautions

- **Don't let T014's conflict handling become a silent swallow.** Acceptance Scenario 4 requires
  the member to be told plainly, not left wondering why nothing happened.
- **Don't duplicate i18n copy that already exists.** Check `packages/i18n/en.json`'s `approvals.*`
  block before adding anything — per §0, almost everything this wave needs is already there.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

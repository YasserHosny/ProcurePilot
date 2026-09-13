# ProcurePilot — Wave 13 Execution Plan (dynamic pool)

**Written**: 2026-09-13, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave12.md` ("Wave 12"), now fully landed (`main` @
`5077cbb`): all three user stories (T009-T032) are independently functional and integrated.

**Orchestration model**: this wave is the closing, cross-cutting phase for
`010-mobile-approvals-receipt` — mirroring `009-mobile-app-mvp`'s own Phase 8 exactly, which the
orchestrator completed **entirely in-house** after a delegate hit a usage limit. This wave's five
tasks (T033-T037) are small, mechanical extensions of already-established patterns in existing
files (no new architecture, no new schema, no new screen) — the same profile as that prior
in-house closeout. **Doing this wave in-house rather than dispatching it** is the orchestrator's
call for this specific wave, not a change to the pool's standing dynamic-dispatch policy: Codex
and Agy remain the default for genuinely new implementation work in later waves/features.

---

## 0. Repo state right now

- `main` @ `5077cbb`. All of `specs/010-mobile-approvals-receipt/tasks.md`'s Phases 1-5 are
  complete and landed. This wave covers **Phase 6 (Cross-Cutting, T033-T037)** — the final phase
  for this feature.
- **No new schema, no new endpoint, no new screen.** Every task extends an existing file with more
  cases/content, following that file's own already-established convention exactly (per tasks.md's
  own description: "mirroring 009-mobile-app-mvp's own Phase 8 exactly").

### Groundwork findings from this plan's own investigation

1. **T033's exact fixture shape is already fully determined by the existing file.**
   `apps/api/tests/integration/test_branch_scoped_visibility.py`'s `ScopedWorkspace` fixture
   already has `request_a` (branch A, requested by the unscoped manager), `request_b` (branch B,
   requested by the SCOPED manager), and `request_c` (branch B, requested by the owner) — the
   exact three shapes needed to prove "own branch," "requester regardless of branch," and
   "another branch resolves not-found." `delivery_quality_issue`'s own RLS
   (`delivery_quality_issue_scoped_visibility`, migration `20260913000003`) derives visibility via
   an `EXISTS` join to the **parent `purchase_request`'s own requester/branch** — not from the
   issue's own `reported_by_membership_id` — so the three new quality-issue rows should attach one
   each to `request_a`/`request_b`/`request_c` (reusing them, not inventing new parent requests),
   and `issue_b`'s "always sees an issue they personally reported" case is naturally satisfied by
   `request_b` already being requested by the scoped manager — the fixture doesn't need to
   entangle "who filed the issue" with "who requested the parent," since the RLS itself doesn't.
2. **T034's three new tests reuse `test_mobile_audit.py`'s existing `_client_for()` fixture
   unchanged.** That fixture builds a real `TestClient(app)` against a `RequestsService.__new__`
   instance with only `_estimate_products`/`_insert_lines`/`_budget_status_for` stubbed (needed
   for `create_request` alone) — `approve_request`/`confirm_delivery`/`create_quality_issue` are
   all real, unstubbed methods on that same instance, so the existing fixture already supports all
   three new flows with no changes to the fixture itself. Since `make_workspace`'s own workspace is
   the **owner**, every one of `_authorize_delivery_confirmation`'s/`_require_assigned_approver_or_
   owner`'s own owner-bypass branches applies — no extra branch-assignment plumbing is needed to
   drive create → submit → approve → confirm-delivery → quality-issue as one caller.
3. **T035's four new screens all need `cameraCapture`/`offlineQueueService` threaded through
   `pumpWithServices`** (both already exist as optional parameters there, added across Waves
   11-12) — nothing new to wire, just supply `FakeCameraCapture`/omit the queue where a screen
   doesn't need it, matching how the existing four a11y cases already pick only the fakes their
   own screen needs.
4. **T037's existing `approve`/`reject` section text is now stale** — it still says the decision
   "moves the request to `approved` / `rejected`," which was true before Wave 9's `010` work but
   is no longer accurate (an approval now lands directly on `ordered`, per
   `specs/010-mobile-approvals-receipt/research.md` R1/R2 and `service.py`'s `_decide_and_notify`).
   Fixing this one stale sentence is in scope for T037 even though it's not one of the three new
   endpoints listed in the task text — the task's own purpose ("docs reflect the real delivered
   API/data model") is not met while this sentence stays wrong.

---

## 1. Non-negotiables (unchanged from Wave 1-12)

Every non-negotiable from Waves 1-12 still applies; this wave is pure test/doc extension, so the
ones most directly exercised are:
1. **Tenant isolation / branch-scoped visibility** — T033 IS the proof for the newest tables.
2. **`audit_event` is append-only** — T034 proves the mobile-facing HTTP path actually reaches it,
   not just the service's own source code.
3. **Every user-facing string comes from `packages/i18n`** — not newly exercised (no new copy),
   but T035's accessibility check (`labeledTapTargetGuideline`) indirectly re-confirms every
   interactive control on the four new screens has a real semantic label, which only exists
   because those screens already pull every label from i18n.
4. **Gate commands are re-run by the reviewer, not trusted from a self-report** — since this wave
   is in-house, "the reviewer" is the same person doing the work; the discipline that matters here
   is running the REAL gates (disposable Postgres, `flutter analyze`/`test`) before calling
   anything done, not skipping straight to "it should work."

---

## 2. Wave 13 scope (all in-house)

1. **(T033)** Extend `apps/api/tests/integration/test_branch_scoped_visibility.py`: add
   `issue_a`/`issue_b`/`issue_c` fields to `ScopedWorkspace`, a `_issue(request_id, reporter)`
   helper inserting into `delivery_quality_issue`, and three new test functions mirroring the
   existing `low_stock_report` section's exact three-case shape (own branch, own report
   regardless of branch, another branch resolves not-found) — but keyed to the parent
   request per finding #1, not to the issue's own reporter directly.
2. **(T034)** Extend `apps/api/tests/integration/test_mobile_audit.py` with three new tests, each
   building create→submit→(the relevant further steps) via real HTTP calls against the existing
   `_client_for()` fixture, asserting the exact `audit_event` row: `requests.approval_step_approved`
   (via `POST /requests/{id}/approve`), `requests.delivery_confirmed` (via
   `POST /requests/{id}/confirm-delivery`, after approving), `requests.quality_issue_reported` (via
   `POST /requests/{id}/quality-issues`, after also confirming delivery).
3. **(T035)** Extend `apps/mobile/test/a11y/screens_a11y_test.dart` with four new `group`s —
   Approval queue, Decision detail, Delivery confirmation, Quality-issue report — each pumping the
   real screen with the minimum fakes it needs (per finding #3) and running the same
   `_checkGuidelines()` helper already defined in this file.
4. **(T036)** Update `docs/architecture/data-dictionary.md`: extend `PurchaseRequest`'s existing
   table (new `ordered`/`delivered` status values, `delivered_at`,
   `delivery_confirmed_by_membership_id`, `has_delivery_discrepancy` columns) and
   `PurchaseRequestLine`'s existing table (`quantity_received`), then add two new entity sections
   — `DeliveryQualityIssue` and `DeliveryQualityIssuePhoto` — under a new
   "Implemented mobile approvals and receipt entities (chunk R2.3, `010-mobile-approvals-receipt`)"
   heading, matching the file's own established section style exactly.
5. **(T037)** Update `docs/architecture/api-specification.md`: fix the stale `approve`/`reject`
   sentence per finding #4, then add a new
   "## Delivered Mobile Approvals and Delivery Receipt API (chunk R2.3, `010-mobile-approvals-receipt`)"
   section (before `## Health`, after the R2.2 mobile section) documenting
   `POST /requests/{id}/confirm-delivery`, `POST`/`GET /requests/{id}/quality-issues`, and
   `POST /quality-issues/{id}/photos`, matching the existing R2.2 section's exact style (a short
   intro paragraph, one `###` per endpoint, request/response notes, a sample request body where
   the endpoint takes one).

**Land as**: one branch, `docs-tests/010-cross-cutting` (a single combined branch, since every
task here is small and none conflict on files with each other or with anything else in flight).

---

## 3. Review protocol

Since this wave is in-house, "review" means the same real-verification discipline applied to every
delegated wave, not skipped because there's no separate implementer:
- T033/T034: run against real disposable Postgres (the established stand-in-SQL + migrations
  recipe), confirm the new tests pass AND the full backend suite still shows exactly the 6 known
  pre-existing failures, nothing more.
- T035: `flutter analyze` (zero issues) and the full mobile suite, confirming the new a11y cases
  pass AND nothing else regresses. If any of the four screens fails a guideline (mirroring Wave
  8's own real `isDense: true` tap-target finding), fix the screen, not the test.
- T036/T037: no gate command exists for prose docs — the check is a careful proofread against the
  actual current schema/contract (re-read the migrations and `schemas.py`/`router.py` while
  writing, don't write from memory of what they "should" say).

---

## 4. What comes after

Once T033-T037 land, `010-mobile-approvals-receipt` is complete — every phase, every user story,
cross-cutting concerns closed out, mirroring `009-mobile-app-mvp`'s own finished state. The next
piece of work is whatever the roadmap names next after R2.3 (check
`docs/roadmap/procurepilot_roadmap.md` §7.2), not a further wave of this feature.

---

## 5. Cautions

- **Don't invent a new fixture shape for T033** when the existing `request_a`/`b`/`c` triple
  already covers exactly the three cases needed (finding #1) — reusing them keeps this test file
  internally consistent with its own established pattern.
- **Don't skip fixing the stale approve/reject sentence in T037** just because it wasn't one of
  the three endpoints named in the task text — leaving it wrong defeats the task's own purpose.
- **Don't trust a docs update without re-reading the actual current source** — this is exactly the
  kind of task where writing from memory (rather than the real migration/schema file) quietly
  reintroduces the same staleness this wave exists to fix.

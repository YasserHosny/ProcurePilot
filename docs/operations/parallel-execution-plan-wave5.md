# ProcurePilot — Wave 5 Execution Plan (Codex / Agy)

**Written**: 2026-09-12, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave4.md` ("Wave 4"). That document's §4 promised this one
once Phase 4's Checkpoint was independently confirmed — it now is (PR merged to `main` as of commit
`a4d68b7`; `flutter analyze` clean, 49 passed/0 failed/1 skipped independently re-verified; T025's
own end-to-end proof, initially self-skipped in the implementer's sandbox, was then run for real
against the hosted deployment and independently confirmed via a direct `GET /approvals/pending`
check — SC-003 holds).

**Lane change from Wave 3/4**: OpenCode hit its weekly usage limit during Wave 4 and is on a
user-directed pause until 2026-09-14. **This wave uses Agy (Google Antigravity CLI) for the
mobile-lane track instead of OpenCode** — a direct user instruction, not an orchestrator judgment
call. Wave 3's own plan noted "Agy is scoped to the existing Angular UI" as this project's
*convention* (routing `apps/web/src/**` changes through it) — that was never a technical
limitation of the tool, so using it for `apps/mobile/` Dart/Flutter work this wave is a scope
extension, not a contradiction. Everything else about the review protocol (re-run gates yourself,
read the diff, don't trust the self-report) applies identically regardless of which CLI wrote the
code.

**Audience**: shared verbatim with both implementers. Read the whole thing, then act only on your
own section.

---

## 0. Repo state right now

- `main` @ `a4d68b7`. The mobile app now has working `core/` (auth, i18n, offline-queue primitive),
  `features/auth/` (sign-in, biometric, sign-out), `features/home/` (role-aware home, wired
  "Request items" button), and `features/requests/` (create/submit a request, list, read-only
  decision detail). Three Dart API clients exist: `MobileApiClient` (`/devices`,
  `/low-stock-reports`), `ApprovalsApiClient` (`GET /approvals/pending`), `RequestsApiClient`
  (`/requests` CRUD + `/organisation/branches`, `/organisation/cost-centres`, `GET /products`
  catalogue search).
- **This wave covers only Phase 5 of `specs/009-mobile-app-mvp/tasks.md`: User Story 3
  (T028-T032) — one-tap low-stock reporting.** Nothing from Phase 6 onward (push notifications,
  offline queue wiring) starts here.
- **Unlike Phase 4, this phase has real backend work.** `POST/GET /low-stock-reports` does not
  exist yet in `apps/api` — only the schema/RLS (`low_stock_report` table,
  `supabase/migrations/20260912000002_low_stock_report.sql`, live since Wave 2) and the Pydantic
  shapes (`LowStockReport`/`LowStockReportCreate` in
  `apps/api/src/procurepilot_api/modules/requests/schemas.py`, also live since Wave 2) exist.
  **T031 (the actual endpoint implementation) is built by Claude in-house, not delegated** — see
  §2 for why, matching this project's standing carve-out for idempotency-key/offline-retry
  correctness logic (the same carve-out that kept T002, T017, T042, T037 in-house in earlier
  waves). It lands on `main` *before* Codex's track starts, so Codex's integration tests run
  against a real implementation, not a stub.
- **The mobile side needs no new API client.** `MobileApiClient.createLowStockReport()` and
  `.listLowStockReports()` already exist (built in Wave 2, Track C) and already match the contract
  exactly (`branchId`, `workspaceProductId`, `countRemaining`, `idempotencyKey`). T032's screen is
  pure UI wiring an already-correct client — no `apps/mobile/lib/core/api/**` changes expected.
- **Known, deliberately out-of-scope-here defects** (do not go looking for these; flag if you
  happen to hit them, don't fix them as part of this wave): the raw branch/product UUID display
  issues on web; the WCAG 2.1 AA color-contrast violations in
  `apps/web/tests/e2e/requests-a11y.spec.ts`; T020's documented FR-014 test-coverage gap.

---

## 1. Non-negotiables (unchanged from Wave 1-4)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied (`tasks.md` reviewed and merged).
2. **Tenant isolation is enforced in the database.** The `low_stock_report` table's RLS
   (`ENABLE`+`FORCE`, tenant-isolation policy, branch-scoped-visibility policy) is already live
   from Wave 2 — T031 must not touch or duplicate it, only query/insert through it. If either
   implementer finds themselves needing a new table or RLS policy, **stop and hand it to Claude.**
3. **No autonomous purchasing (FR-009) still applies, transitively.** Low-stock reporting is
   informational only — **FR-006 requires it to never create, modify, or reference any
   `purchase_request` row, in either direction.** T029's integration tests must prove this
   directly (create a low-stock report, assert every existing `purchase_request` row for that
   tenant is byte-for-byte unchanged), not just assume it from the schema having no FK.
4. **Idempotent replay is a real, enforced guarantee here, not a decoration.** `low_stock_report`
   has a genuine partial unique index on `(tenant_id, idempotency_key) where idempotency_key is
   not null` — this is this chunk's own fix for a systemic, separately-tracked gap (Idempotency-Key
   is accepted but not actually enforced anywhere else in this codebase yet). A replayed
   `POST /low-stock-reports` with the same key must return the **original row** with **200**, not
   a new row with **201**. Getting the status-code distinction right is part of the contract
   (`specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`), not a nice-to-have.
5. **Every user-facing string comes from `packages/i18n`.** Check `lowStock.*` first (added in
   Wave 2's i18n scaffolding per T005) before adding anything new — it likely already has the
   screen copy and confirmation-state strings T032 needs.
6. **Every monetary value carries an explicit currency** — not directly relevant here, no money is
   shown on this screen.
7. **Secrets never enter the repo.**
8. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report.**
   Every prior wave found something real this way (Wave 2: a missing-test gap and a wrong-base-URL
   bug; Wave 4: three validators showing the wrong error message, and a self-reported test count
   that was off by 14). Same discipline here, for both tracks.

---

## 2. Wave 5 scope — Phase 5 (User Story 3), T028-T032

### Track: Claude (in-house) — T031

**Why in-house**: per this project's own delegation-lanes convention (`specs/009-mobile-app-mvp/
tasks.md`'s "Delegation lanes" section), idempotency-key/offline-retry dedup logic is a standing
carve-out — the same reasoning that kept the push-outbox wiring (T037), the retry-sweep task
(T012), and the offline-queue primitive (T002, T017, T042) in-house rather than delegated. T031 is
this chunk's version of that: it's the one place in this whole feature where getting the dedup
logic subtly wrong (e.g. losing the 200-vs-201 distinction, or a race between the conflict check
and the insert) directly produces either a duplicated report or a client left showing a fake
failure for a report that actually landed.

**Implementation**: `POST/GET /low-stock-reports` in
`apps/api/src/procurepilot_api/modules/requests/service.py`, exposed in
`apps/api/src/procurepilot_api/modules/requests/router.py`:
- `GET`: list reports visible to the caller (owner sees all; branch-scoped member sees their
  branch's plus anything they personally raised — RLS already enforces this, the query just needs
  to run as the authenticated member), filterable by `branch_id`/`workspace_product_id`, cursor
  paginated.
- `POST`: insert-only. This codebase's established idiom for a unique-constraint conflict (see
  `catalogue/service.py`'s `canonical_product` insert, `_api_error_code(exc) == "23505"`) is
  try/except around `.insert(...).execute()` via the `supabase-py` `Client` from
  `authenticated_client()` (`members/service.py`) — **not** `psycopg` directly (that's the
  `devices` module's separate pattern; `requests/service.py` already uses `authenticated_client`
  throughout, stay consistent with the file you're editing). When an `Idempotency-Key` is
  supplied: attempt the insert; on a `23505` conflict against the partial unique index, re-query
  `low_stock_report` by `(tenant_id, idempotency_key)` and return that existing row with **200**
  (inject `response: Response` and set `response.status_code = status.HTTP_200_OK` — the route
  decorator's default stays `201` for the normal-insert path). When no key is supplied (or it's
  supplied but doesn't conflict), a plain insert always creates a new row with **201** — two
  omitted-key reports are both legitimate signals, not duplicates to collapse.

**Land as**: its own commit directly on `main` (small, in-house, no separate PR/branch review
needed — consistent with how T031-shaped work has landed in prior waves), *before* dispatching
Codex, so T028-T029 run against a real implementation.

---

### Track: Codex — T028, T029

**File scope**: `apps/api/tests/contract/test_low_stock_contract.py` (new),
`apps/api/tests/integration/test_low_stock_reports.py` (new). No production code changes — tests
only, against T031's already-landed implementation.

**Tasks**:
1. **(T028) Contract tests** in `test_low_stock_contract.py`: verify implemented `/low-stock-reports`
   GET/POST against `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml` — request/response
   shapes, the 200-vs-201 idempotent-replay distinction (§1.4 — this is the one behavior most
   worth a dedicated, explicit assertion), and 404/422 envelopes.
2. **(T029) Integration tests** in `test_low_stock_reports.py`, using this codebase's standard
   disposable-Postgres integration-test pattern (see `test_devices.py` for the shape to mirror —
   `make_workspace()`/`act_as()`/shared-`conn`-fixture):
   - Report creation succeeds with and without `count_remaining`.
   - Branch-scoped visibility: a branch-scoped member sees only their branch's reports plus any
     they personally raised (data-model.md RLS Summary) — mirror `test_branch_scoped_visibility.py`'s
     existing pattern for `purchase_request` rather than inventing a new one.
   - **FR-006, the most important assertion in this track**: creating a low-stock report leaves
     every existing `purchase_request` row for that tenant completely unchanged — snapshot the
     rows before, create the report, assert byte-for-byte equality after. Not "no error was
     raised" — actual row-level equality.
   - **Idempotent replay (FR-011)**: two `POST /low-stock-reports` calls with the same
     `Idempotency-Key` return the same row (same `id`), the second with status 200; the database
     ends up with exactly one row for that key, not two — assert the row count directly, don't
     infer it from the response alone.

**If T031 (already landed) turns out to have a real bug** (not a test-authoring question): report
it precisely rather than patching `service.py`/`router.py` yourself — that file is Claude's
in-house track for this wave, per §2 above; a delta fix goes back to Claude, not into this track's
diff.

**Land as**: one branch, e.g. `backend/009-low-stock-tests`.

---

### Track: Agy — T030, T032

**File scope**: `apps/mobile/lib/features/low_stock/**` (new),
`apps/mobile/test/features/low_stock/low_stock_report_test.dart` (new). No changes expected
anywhere in `apps/mobile/lib/core/**` — the API client this screen needs already exists
(`MobileApiClient.createLowStockReport()`/`.listLowStockReports()`, live since Wave 2); if you find
yourself wanting to add or change a client method, stop and check `mobile_api_client.dart` again
first, since it's very likely already there.

**Tasks**:
1. **(T032) Low-stock report screen** in `apps/mobile/lib/features/low_stock/`: reachable from a
   product in the catalogue-search picker already built for US2
   (`apps/mobile/lib/features/requests/request_form_screen.dart`'s `_LineItemEditor` — look at how
   it calls `RequestsApiClient.searchCatalogue()` and renders `CatalogueProduct` results; this
   screen needs the same kind of product-search entry point, or can be reached from a product
   result's own row via a secondary action — your call on the exact navigation trigger, as long as
   it starts from a real, already-searchable product rather than a hand-typed ID). The report
   itself: a "running low" confirmation with an *optional* count (`countRemaining`), calling
   `MobileApiClient.createLowStockReport(branchId:, workspaceProductId:, countRemaining:,
   idempotencyKey:)`. Stamp the `Idempotency-Key` **client-side, once, at the moment the user taps
   the report action** — not regenerated on retry — following the exact pattern the offline-queue
   primitive (`apps/mobile/lib/core/offline_queue/offline_queue_service.dart`) already uses for
   its own `idempotencyKey` (creation-time stamping, `uuid.v4()`), even though this screen isn't
   wiring into the offline queue yet (that's Phase 7). A confirmation state shows once the call
   succeeds. **Debounce a rapid double-tap client-side** so it produces exactly one HTTP call, not
   two racing calls both without a key (spec.md's own double-tap edge case) — a `Timer` or a
   simple "already submitting" boolean guard both work; look at how
   `request_form_screen.dart`'s `_searchDebounce` is used for the pattern already established in
   this codebase, though this is a tap-debounce not a search-debounce, so the mechanism will look
   different even if the *idea* (don't fire twice for one user action) is the same.
2. **(T030) Widget tests** in `low_stock_report_test.dart`: the one-tap submit with a count, the
   one-tap submit without a count, the confirmation state rendering after a successful call, and
   — the one every prior wave's FR-009-adjacent test discipline would insist on — a rapid
   double-tap producing **exactly one** call into a fake `MobileApiClient` (assert the fake's call
   list has length 1, not just that the UI didn't visibly break). Fake `MobileApiClient` the same
   way `apps/mobile/test/test_helpers.dart` already fakes it elsewhere in this test suite — extend
   that file's existing fake rather than writing a second, divergent one.

**A note on scope discipline** (carried over from Wave 4's review finding): stay inside
`features/low_stock/` and its own test file. Wave 4's implementer touched five already-landed
Wave 2 `core/` files with pure `dart format` reformatting that had to be reverted before landing —
harmless in that case, but avoidable. If your tool reformats a file it opens just to read it,
revert that file before finishing, or flag it in your report so Claude can check it during review.

**Land as**: one branch, e.g. `mobile/009-low-stock-screen`.

---

## 3. Review protocol (unchanged pattern from Wave 1-4)

| Track | Implementer | Reviewer |
|---|---|---|
| T031 | **Claude** (in-house) | — (self-verified via the same gate re-run discipline applied to every other track) |
| T028, T029 | **Codex** | **Claude** |
| T030, T032 | **Agy** | **Claude** |

Sequencing: T031 lands on `main` first. Codex is dispatched next (its tests need T031 live).
**Agy is dispatched after Codex, not in parallel with it** — per Wave 1/2's own finding that
running two implementer dispatches at once got both externally SIGTERM'd on this machine twice in
a row; there is no logical dependency between the two tracks here (different files entirely), but
the resource-contention lesson still applies regardless of whether the tracks are related.

For Agy specifically: this is the first wave using it for `apps/mobile/` Dart code rather than
`apps/web/` Angular/TypeScript. Read its diff with the same "did it actually do what was asked,
nothing more" scrutiny as any other track — a CLI switch changes nothing about the review
standard.

---

## 4. Wave 6 — blocked until Phase 5's Checkpoint is reviewed

Per `tasks.md`'s own Phase 5 Checkpoint: *"US3 is independently testable and fully additive —
US1/US2's request loop already works completely without it; its own offline-retry safety no longer
depends on an unenforced header."* Once that's independently confirmed, Claude issues a Wave 6 plan
for Phase 6 — User Story 4, durable push notifications on decision (T033-T038). Phase 6 needs the
already-built push-send/retry-sweep job pair (Wave 2) wired into the approve/reject decision path
(T037, another in-house-carve-out task per the same idempotency/correctness reasoning as T031),
plus backend unit tests with zero UI dependency (T033-T035, Codex) and mobile permission/deep-link
handling (T036, T038 — Agy or OpenCode depending on the pause status by then: 2026-09-14 is before
this wave would plausibly start, so OpenCode may be available again).

---

## 5. Cautions

- **Don't let Agy re-derive Wave 4's `features/requests/` work.** The only expected interaction
  with that code is *reading* `request_form_screen.dart`'s catalogue-search pattern for reference
  (§2) — not modifying it. If the diff touches `apps/mobile/lib/features/requests/**` or
  `apps/mobile/lib/features/home/**` at all, that's scope creep into already-reviewed work.
- **T031 landing before Codex's dispatch is load-bearing for this wave's sequencing** — don't
  dispatch Codex against a `main` that doesn't have it yet, or T028-T029 will be testing a 404.
- **Resource pressure**: per Wave 1/2's own finding, stagger dispatches (§3) rather than running
  Codex and Agy at once.
- **This is Agy's first `apps/mobile/` (Dart/Flutter) dispatch this session** — it has an
  established track record on `apps/web/` Angular work, but zero track record on Flutter in this
  project. Read its diff and gate results with correspondingly less assumed trust than a track
  with a clean history, not more.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

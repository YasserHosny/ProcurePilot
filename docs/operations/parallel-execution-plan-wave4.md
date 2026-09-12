# ProcurePilot — Wave 4 Execution Plan (OpenCode)

**Written**: 2026-09-12, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave3.md` ("Wave 3"). That document's §4 promised this one
once Phase 3's Checkpoint was independently confirmed — it now is (PRs #18, #19 merged to `main` as
of commit `4d21495`; Flutter 36/36 tests via the JSON-reporter parsing method, `analyze` clean;
T019's FR-009 proof manually verified by injecting and reverting a throwaway violation).

**Audience**: shared verbatim with the implementer. Read the whole thing, then act only on your own
section. If you are OpenCode reading this cold: everything you need is below.

---

## 0. Repo state right now

- `main` @ `61019cf`. `apps/mobile/` has a working `core/` (auth, i18n, offline-queue primitive,
  `MobileApiClient` for `/devices` + `/low-stock-reports`, `ApprovalsApiClient` for
  `GET /approvals/pending`) and a working `features/auth/` + `features/home/` — sign-in, biometric
  enable/unlock, sign-out, and a role-aware home screen with a **disabled** "Request items" button
  (`Key('homeRequestItemsButton')`, `onPressed: null`, in
  `apps/mobile/lib/features/home/home_screen.dart`) that this wave wires up for real.
- Also since Wave 3: `docs/user/user-documentation.md`, `docs/user/user-flows.md`, and a new
  `docs/user/mobile-app-user-documentation.md` were updated/added (merge commit `61019cf`) — no
  code impact, mentioned only so nobody is surprised by unrelated docs history on `main`.
- **This wave covers only Phase 4 of `specs/009-mobile-app-mvp/tasks.md`: User Story 2
  (T023-T027) — submit a purchase request from mobile, and view its status/decision once made.**
  Nothing from Phase 5 onward (low-stock report, push, offline queue) starts here.
- **The backend endpoints this wave calls are already complete and UNCHANGED** — they are 008's own
  `/requests` surface (`specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml`),
  live on `main` since R2.1 and exercised daily by the web app
  (`apps/web/src/app/features/requests/`). This wave is **pure mobile UI**: zero backend code,
  zero migrations, zero new endpoints. If the implementer finds themselves wanting to add or change
  anything under `apps/api/`, that's a sign of scope creep — stop and flag it.
- **One addition this wave needs that isn't yet in `apps/mobile/lib/core/api/`**: T026/T027 call
  `GET/POST /requests`, `GET/PATCH /requests/{request_id}`, and `POST /requests/{request_id}/submit`
  (008's contract). The current Dart clients only cover `/devices` + `/low-stock-reports`
  (`MobileApiClient`) and `GET /approvals/pending` (`ApprovalsApiClient`) — neither covers `/requests`
  CRUD. Adding a client for it is in scope for this wave (see §2, file scope). Mirror the web app's
  own split: `apps/web/src/app/features/requests/requests-api.ts` (`RequestsApiService`, the CRUD
  surface) is a separate class from `apps/web/src/app/features/approvals/approvals-api.ts`
  (`ApprovalsApiService`, the approver-facing surface) even though both live in the same OpenAPI
  file — do the same on mobile: a new `RequestsApiClient` in
  `apps/mobile/lib/core/api/requests_api_client.dart`, separate from the existing
  `ApprovalsApiClient`. This is not a new backend surface, just a new typed caller of an existing
  one — same framing as Wave 3's `GET /approvals/pending` addition.
- **The catalogue-search line-item picker (T023/T026) has a real, existing backend endpoint to use**:
  `GET /products?q=<text>&limit=...` in `apps/api/src/procurepilot_api/modules/catalogue/router.py`
  (unchanged, pre-existing) supports name search with cursor pagination. **Important scope note**:
  the web app's own request form does *not* have a catalogue-search picker yet — it's a plain text
  field bound to `workspace_product_id` (see `docs/user/user-documentation.md` §17's "Current display
  limitation" and Known Issue #2). `tasks.md`'s T023/T026 describe a real search-driven picker for
  mobile, which is a **step ahead of web's own current UI**, not a mismatch to "fix" — build the
  search picker as written in tasks.md using `GET /products`, but don't feel compelled to also
  retrofit web to match; that's out of scope here.
- **Branches and cost centres for the form's selectors** come from the existing, unchanged
  `GET /organisation/branches` and `GET /organisation/cost-centres` — reuse the same client-fetch
  pattern the web `RequestFormComponent` already uses (`apps/web/src/app/features/requests/
  request-form/request-form.component.ts`), just under the new `RequestsApiClient` or a small
  sibling method group — implementer's call, as long as it doesn't blur into the devices/low-stock
  or approvals client identities per the note above.
- **Known, deliberately out-of-scope-here defects** (do not go looking for these; flag if you happen
  to hit them, don't fix them as part of this wave): the raw branch/product UUID display issues on
  web (`docs/user/user-documentation.md` §23, items 1-2); the pre-existing WCAG 2.1 AA color-contrast
  violations in `apps/web/tests/e2e/requests-a11y.spec.ts`'s approval-queue screen; T020's
  documented FR-014 test-coverage gap (`apps/api/tests/integration/test_session_revocation.py`).

---

## 1. Non-negotiables (unchanged from Wave 1-3)

Restated for any agent reading cold:

1. **Specification precedes code** — already satisfied (`tasks.md` reviewed and merged).
2. **Tenant isolation is enforced in the database**, not app code. This wave adds no table, no RLS
   policy, and no new endpoint — it only calls existing, already-isolated `/requests` endpoints. If
   the implementer finds themselves needing any backend change at all, **stop and hand it to
   Claude** per this project's standing rule that tenancy/migration work is not delegated by default.
3. **No autonomous purchasing — FR-009, still this project's single most load-bearing rule.**
   This wave adds a *requester-side* screen (create/submit/view your own request), not an
   *approver-side* one — it must not add, wire, or even reference `POST /requests/{id}/approve` or
   `/reject` anywhere, including in the new `RequestsApiClient`. Wave 3's
   `apps/mobile/test/core/no_approval_surface_test.dart` already statically greps every API client
   file and the route table for `/approve`/`/reject` patterns — **extend its scanned-file list to
   include the new `requests_api_client.dart`** (see §2) so this wave's new client is covered by the
   same proof, not left outside it. Do not treat this extension as optional.
4. **Every user-facing string comes from `packages/i18n`.** Before adding any new key, check
   `packages/i18n/en.json`'s existing `requests.*` and `approvals.*` namespaces for one that already
   says what you need — the web app already has status labels (`requests.status.*`), form field
   labels (`requests.form.*`), and approval-step copy (`requests.approval.*`) for exactly this
   domain. Wave 3's sign-in screen got this right by reusing `auth.signin.*` verbatim rather than
   duplicating it; do the same here. Only genuinely new mobile-only copy (e.g. the catalogue-search
   placeholder, an empty-request-list state) needs a new key, under a `mobileRequests.*` namespace
   to mirror `mobileHome.*`'s existing convention.
5. **Every monetary value carries an explicit currency.** `PurchaseRequest.estimated_total` and
   `PurchaseRequestLine.estimated_unit_price` are both `{amount, currency}` objects (never a bare
   number) per the OpenAPI contract — add a `Money` Dart class to
   `apps/mobile/lib/core/api/models.dart` if one doesn't already exist, decimal-string `amount`
   (matching T013's original "decimal strings for money-shaped fields" instruction), and render
   every amount on screen with its currency, exactly like the web app's `formatMoney`/
   `formatLinePrice` helpers in `apps/web/src/app/features/requests/**` do.
6. **Secrets never enter the repo.**
7. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report** —
   restated because every prior wave found real, meaningful issues this way (a missing-test gap and
   a wrong-base-URL bug in Wave 2; nothing wrong in Wave 3, but only because the same discipline was
   applied). Same here, especially for T025's integration test (see caution below).

---

## 2. Wave 4 scope — Phase 4 (User Story 2), T023-T027

### Track: OpenCode (single track — no Codex this wave)

**File scope**:
- New: `apps/mobile/lib/features/requests/**`
- New: `apps/mobile/lib/core/api/requests_api_client.dart`
- Additive only: `apps/mobile/lib/core/api/models.dart` (new `Money`, `PurchaseRequest`,
  `PurchaseRequestLine`, `PurchaseRequestLineInput`, `ApprovalStep` classes — do not touch existing
  `DeviceRegistration`/`LowStockReport` classes)
- Additive only: `apps/mobile/lib/main.dart` (register the new request-form/list/detail routes and
  wire `RequestsApiClient` into `ServiceProvider`, same pattern as the existing
  `ApprovalsApiClient` wiring)
- One targeted change: `apps/mobile/lib/features/home/home_screen.dart` — flip the "Request items"
  button from `onPressed: null` to actually navigate to the new request-form screen. This is the
  ONLY change expected in `features/home/` or `features/auth/`; if the diff touches anything else
  there, that's scope creep into Wave 3's already-reviewed work.
- New: `apps/mobile/test/features/requests/request_form_test.dart`,
  `apps/mobile/test/features/requests/request_list_test.dart`,
  `apps/mobile/test/integration/mobile_request_submission_test.dart`
- Extend (do not rewrite): `apps/mobile/test/core/no_approval_surface_test.dart` — add
  `requests_api_client.dart` to its scanned client files (§1.3)
- Additive only: `packages/i18n/en.json` / `packages/i18n/ar.json` (new `mobileRequests.*` keys
  only for copy with no existing `requests.*`/`approvals.*` equivalent — see §1.4)

**Tasks**: T023-T027 — full task text is in `specs/009-mobile-app-mvp/tasks.md` Phase 4; summarized
precisely here, but that file is the source of truth if anything conflicts:

1. **(T026) Request form screen** in `apps/mobile/lib/features/requests/`:
   - Branch selector (from `GET /organisation/branches`) and optional cost-centre selector (from
     `GET /organisation/cost-centres`); required-by date.
   - Line items: a catalogue-search picker backed by `GET /products?q=...` (see §0), quantity, and
     an optional note per line — matching `PurchaseRequestLineInput`'s shape
     (`workspace_product_id`, `quantity` as a decimal string, `note`).
   - Draft persistence: `POST /requests` creates a draft; further edits before submission use
     `PATCH /requests/{id}` (requester-only, draft-only per the contract — a 409 on anything else
     is an expected, handleable response, not a bug).
   - Submit via `POST /requests/{id}/submit`; refuse submission client-side when there are zero
     lines (FR-004 — mirror the web form's `lines.length === 0` guard in
     `apps/web/src/app/features/requests/request-form/request-form.component.html`).
   - No new backend logic — this screen is a new caller of an existing surface (FR-003).

2. **(T027) Request list/detail screens** in `apps/mobile/lib/features/requests/`:
   - List via `GET /requests` (a requester always sees their own regardless of branch scoping, per
     the contract) with status filtering/display.
   - Detail view renders `approval_step`'s status, comment, and `decided_at` **exactly as**
     `request-form.component.html`'s existing web equivalent already does (section 17 of
     `docs/user/user-documentation.md` documents the exact fields and their behavior:
     a status chip, "assigned to," and — once decided — the approver's comment and decision
     timestamp). This is a read-only view — no approve/reject control, per §1.3.

3. **(T023) Request form widget tests** in
   `apps/mobile/test/features/requests/request_form_test.dart`: catalogue search, line add/remove,
   required-by date, draft persistence on navigating away, submit, and the zero-lines refusal
   (FR-004). Fake the new `RequestsApiClient` and the catalogue-search client the same way Wave 3's
   `test_helpers.dart` fakes `AuthService`/`DeviceRegistrar`/`BiometricAuth` — don't hit a real
   network.

4. **(T024) Request list/detail widget tests** in
   `apps/mobile/test/features/requests/request_list_test.dart`: status display, and — once
   decided — the approver's comment rendering identically to web's shape (FR-005).

5. **(T025) End-to-end mobile-submission proof** in
   `apps/mobile/test/integration/mobile_request_submission_test.dart`: a request created via the
   new `RequestsApiClient` (real HTTP call, not a fake) appears correctly routed in
   `GET /approvals/pending`, against the same disposable-Postgres `apps/api` recipe used everywhere
   else this session (pgvector/pg17 container + the `backend-tests` CI job's schema-prep steps +
   every `supabase/migrations/*.sql` file in order). This directly proves SC-003's "no
   channel-specific behaviour gap" — that mobile submission is not a second, divergent code path
   from web's. **If your sandbox has no Docker/network access to stand up that Postgres yourself**
   (this has been true for Codex every time this session; unconfirmed either way for OpenCode),
   write the test correctly and completely, then say so plainly in your final report rather than
   claiming it passed — Claude will independently stand up the same recipe and run it as part of
   review, exactly as established practice this session (see §3).

**Land as**: one branch, e.g. `mobile/009-request-submission`.

---

## 3. Review protocol (unchanged pattern from Wave 1-3)

| Implementer | Reviewer |
|---|---|
| **OpenCode** (T023-T027) | **Claude** |

No Codex track this wave — Phase 4 has zero backend work (§0), so there is nothing for Codex's lane
to do. Claude's role is entirely review: re-run `flutter analyze`/`flutter test` (via the JSON-
reporter parsing method established in Wave 3, not raw scrollback), independently stand up the
disposable-Postgres recipe to actually execute T025's end-to-end test regardless of what OpenCode's
own sandbox could or couldn't run, read the diff against this brief's file scope, and re-verify
§1.3's FR-009 extension actually covers the new client rather than trusting a self-report that it
does.

---

## 4. Wave 5 — blocked until Phase 4's Checkpoint is reviewed

Per `tasks.md`'s own Phase 4 Checkpoint: *"US2 is independently testable — a request can be created
and submitted from mobile and observed correctly routed on web, on top of US1's working sign-in."*
Once that's independently confirmed, Claude issues a Wave 5 plan for Phase 5 — User Story 3, one-tap
low-stock reporting (T028-T032). Phase 5 needs a schema/idempotency backend piece
(`POST/GET /low-stock-reports` in `apps/api/src/procurepilot_api/modules/requests/service.py`,
T031) alongside mobile UI (T032) reusing US2's catalogue-search entry point — expect a two-track
wave (Codex for T031, OpenCode for the mobile screen + tests), more similar in shape to Wave 2 than
to this single-track wave.

---

## 5. Cautions

- **Don't let OpenCode re-derive Wave 2/3's `core/` or `features/auth/`/`features/home/` work.**
  The only expected change in `features/home/` is the one-line wiring described in §2; if the diff
  touches `apps/mobile/lib/core/**` beyond the new `requests_api_client.dart` and the additive
  `models.dart` classes, that's scope creep into already-reviewed work — flag it rather than
  accepting it.
- **T025 is the wave's highest-risk task**, structurally similar to T020's FR-014 proof in Wave 3
  which turned out to be undeliverable in `apps/api`'s own bare-Postgres harness for a documented,
  legitimate reason (Supabase-Auth-internal behavior). T025 is different in kind — it only needs
  `apps/api` and Postgres, both of which this session's own disposable-Postgres recipe already
  covers — so there is no expected structural blocker here; treat a reported failure as something to
  actually investigate and re-run yourself before accepting either a "works" or a "can't be proven"
  claim at face value.
- **Resource pressure**: per Wave 1/2's own finding, avoid running Flutter's toolchain and a
  disposable Postgres container at the same time on this machine if you can sequence them instead.
- **`/tmp` instability** (Wave 3's finding): use a persistent worktree path under
  `/home/yasserhosny/.config/superpowers/worktrees/ProcurePilot/` and a brief file outside `/tmp`
  from the start of this wave, rather than discovering the same failure mode again mid-dispatch.
- **Constitution non-negotiables** (§1): unchanged, still apply to every task.

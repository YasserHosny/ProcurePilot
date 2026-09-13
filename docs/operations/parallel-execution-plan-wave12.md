# ProcurePilot — Wave 12 Execution Plan (dynamic pool)

**Written**: 2026-09-13, by Claude (orchestrator), continuing from
`docs/operations/parallel-execution-plan-wave11.md` ("Wave 11"), now fully landed (`main` @
`2edf497`): T017-T023 (confirm delivery) plus a concurrently-dispatched fix for an unrelated
branch-write-authorization gap.

**Orchestration model**: pool is **Claude (in-house), Codex, Agy** (OpenCode still paused per
standing memory until 2026-09-14 — today is 2026-09-13, one day early, so it stays out of this
wave's pool). Per explicit updated guidance from the user (2026-09-13, superseding the earlier
sequential-only caution), **this wave dispatches both tracks concurrently**, not sequentially.

---

## 0. Repo state right now

- `main` @ `2edf497`. Phases 1-4 of `specs/010-mobile-approvals-receipt/tasks.md` are complete.
  All schema this wave needs — `delivery_quality_issue`, `delivery_quality_issue_photo`, and the
  `quality-issue-photos` Storage bucket + RLS policy — was already built and reviewed in Wave 9
  (migrations `20260913000003/4/5`). **No new migration is expected in this wave either.**
- **This wave covers Phase 5 (User Story 3, T024-T032)** — reporting a delivery quality issue with
  optional camera-captured photo evidence, the last user-story phase (P2). Per tasks.md's own
  Independent Test framing, this story does NOT depend on Wave 11's mobile screen — it only needs a
  `delivered` row to exist (seeded directly in tests), so it does not block on anything except the
  schema, which is already there.
- **Two tracks, dispatched concurrently this time**: backend (T024-T028, Codex) and mobile
  (T029-T032, Agy). Unlike Wave 11, mobile is NOT sequenced after backend — both build against the
  already-fully-specified `contracts/mobile-approvals-receipt.openapi.yaml` (`QualityIssueCreate`,
  `QualityIssue`, `QualityIssuePhoto` schemas, already written in the original Speckit planning) and
  are reconciled against each other at review time rather than one waiting on the other's merge.
  This mirrors how a real team builds against an agreed contract in parallel; the orchestrator
  checks both diffs cross-reference the same shapes before landing either.

### Groundwork findings from this plan's own investigation (so implementers don't rediscover them)

1. **This test harness has no real Supabase Storage service** — only bare Postgres. A call like
   `client.storage.from_(bucket).create_signed_url(...)` or `.upload(...)` will fail here; there is
   no HTTP Storage endpoint to hit. This codebase already solved this exact problem for
   `quotation-documents`: `apps/api/tests/integration/test_tenant_isolation.py`'s
   `test_storage_object_from_another_workspace_is_invisible` (and its neighbors) test Storage
   tenant-isolation entirely at the **Postgres RLS level** — inserting rows directly into
   `storage.objects` via raw SQL, then role-switching and asserting a cross-tenant `SELECT` returns
   nothing. **T026's Storage-isolation test should follow this exact same pattern**, not attempt to
   call real Storage. **T025's contract test** (which exercises the actual FastAPI route) should
   monkeypatch/mock the Storage-touching calls inside `attach_quality_issue_photo()` specifically
   (verifying the DB row and response shape), the same way this module's other contract tests avoid
   hitting a live dependency they can't run in CI.
2. **Which client to use for the Storage write itself is a real design choice, not a copy-paste
   from `documents`.** `apps/api/src/procurepilot_api/modules/documents/service.py`'s
   `create_download_url()` uses a **service-role** client (bypasses RLS) to generate a signed URL,
   but that module's UPLOAD flow is a two-step **presigned-URL** dance (the client uploads directly
   to Storage, never through the API) — a different shape from this wave's contract, which is a
   **single multipart POST through the API** (`POST /quality-issues/{issue_id}/photos`, `file:
   binary` in the request body — the API receives the bytes itself). Given `quality-issue-photos`'
   RLS policy (`quality_issue_photos_tenant_isolation`, `for all to authenticated`) already permits
   the tenant-scoped `authenticated_client` to write and read its own tenant's objects (the path
   itself encodes `tenant_id`, which `current_tenant_id()` resolves from that same JWT), the
   tenant-scoped client should work for BOTH the upload and the signed-URL read-back here — try that
   first (it keeps tenant isolation enforced by the same mechanism as everywhere else in this
   codebase, rather than reaching for a service-role bypass); fall back to a service-role client
   only if a real test proves the tenant-scoped client can't generate a signed URL.
3. **`OfflineQueue`'s replay mechanism is a `switch` on `item.endpoint` string** in
   `apps/mobile/lib/core/offline_queue/offline_queue_replay.dart`'s private `_send()` method — read
   `_sendRequest()` there as the exact pattern for T031: it's a two-step replay (create, then a
   secondary action) already, calling `requestsApiClient.createRequest(...)` then
   `_submitTolerantly(created.id)`. Add a new `case 'quality-issues':` doing the same shape: call
   `reportQualityIssue(...)` to create the issue, then — only if the queued item's payload recorded
   a locally-cached photo path — call `uploadQualityIssuePhoto(issueId, file)` using the **newly
   created issue's ID**, not one computed client-side ahead of time (the server allocates the ID).
4. **`QueueItem.payload` is `Map<String, dynamic>`, JSON-serialized into a `Box<String>`** — it
   cannot hold raw photo bytes. Store the **local file path** as a string in the payload (e.g.
   `payload['photo_local_path']`), and the report screen must copy the captured photo into a
   **stable app-owned cache directory** at capture time (not just hold whatever transient path the
   camera plugin/stand-in returns) — a queued item may replay long after capture, potentially across
   an app restart, so a path into `path_provider`'s temp directory (which the OS can clear) is not
   safe to rely on unmodified. `null` (no photo) must remain a fully valid payload — FR-007 requires
   a submission with zero photos to succeed unconditionally.
5. **The camera integration stays behind the abstraction, no real plugin yet.** Wave 9's T008 built
   `CameraCapture`/`StandInCameraCapture` (`apps/mobile/lib/core/camera/camera_capture.dart`)
   specifically so this wave's screen could be built and tested against a real *shape* without
   picking a concrete camera/image-picker package — explicitly deferred to research.md R4. This
   sandbox has no real device/camera to test a live plugin against (mirrors the earlier
   no-Android-SDK finding that kept the mobile build-size gate `workflow_dispatch`-only rather than
   wired into CI) — so **T030 should NOT add a real camera plugin dependency this wave either.**
   Build the screen against the `CameraCapture` interface (inject `StandInCameraCapture` in
   production, same as today), and test it with the existing `FakeCameraCapture` test double (built
   in Wave 9's `test_helpers.dart` for exactly this purpose) proving both paths: a declined/
   unavailable camera never blocks submission (FR-007), and a captured photo shows a preview with a
   remove option before submit.
6. **`QualityIssue`'s response shape embeds `photos: [QualityIssuePhoto]`** (per the OpenAPI
   contract) — the service's row-mapper needs to join/fetch attached photos when building a
   `QualityIssue` response, not just return the bare issue row. A freshly created issue (no photos
   attached yet) returns `photos: []`, not null.
7. **A new `quality_issue_photos_bucket` setting** should be added to
   `apps/api/src/procurepilot_api/config.py`, mirroring `quotation_documents_bucket`'s exact
   `Field(default=..., validation_alias=...)` style, defaulting to `"quality-issue-photos"` (the
   bucket id from Wave 9's migration) — don't hardcode the bucket name string inline in the service.

---

## 1. Non-negotiables (unchanged from Wave 1-11)

1. **Tenant isolation is enforced in the database.** Already true for every table/bucket this wave
   touches (Wave 9). No new RLS policy expected.
2. **Tenancy comes from the verified JWT claim.** Every new service method uses
   `authenticated_client(self._settings, bearer_token)` — never a path/query tenant parameter, and
   (per finding #2) the tenant-scoped client should be tried for the Storage calls too, not a
   service-role bypass by default.
3. **A cross-tenant read returns "not found," never "forbidden."** A quality issue or photo from a
   different tenant must 404 via RLS's own SELECT policy (already built) — no service-layer branch
   check should be needed for this, since the schema already fully derives visibility.
4. **No secrets in the repo.**
5. **Every user-facing string comes from `packages/i18n`** (en + ar). T032 adds a full new
   `qualityIssue.*` block — no existing web screen to reuse from (same situation as Wave 11's
   `delivery.*`, unlike Wave 10's `approvals.*` reuse).
6. **Every monetary value carries an explicit currency.** Not implicated — this feature has no
   money field.
7. **`audit_event` is append-only.** `create_quality_issue()`/`attach_quality_issue_photo()` must
   each call `self._record(...)` with a new action string, matching every other mutating method in
   this file.
8. **No autonomous purchasing.** Not implicated (this is post-delivery quality reporting, not a
   purchasing or approval decision) — but the `delivered`-status precondition (FR-006) must be
   enforced server-side regardless of what the mobile client believes locally.
9. **Gate commands are re-run by the reviewer, not trusted from the implementer's self-report** —
   this project's standing discipline, reconfirmed twice already in this feature (Wave 11's both
   tracks each had a real, distinct verification gap the orchestrator caught independently).

---

## 2. Wave 12 scope

### Track A: backend (Codex) — T024-T028

**File scope**: `apps/api/tests/contract/test_quality_issues_contract.py` (new, covers both T024
and T025), `apps/api/tests/integration/test_quality_issues.py` (new),
`apps/api/src/procurepilot_api/modules/requests/service.py` (new methods + row mapper for
`QualityIssue`/`QualityIssuePhoto`), `apps/api/src/procurepilot_api/modules/requests/router.py` and
`schemas.py`, `apps/api/src/procurepilot_api/config.py` (one new bucket setting, finding #7). No
migration file — the schema already exists (Wave 9). If a migration genuinely seems needed, stop
and flag it rather than writing one.

1. **(T027)** `RequestsService.create_quality_issue()`: require the target `purchase_request` is
   `status == 'delivered'` (else `ConflictError(details={"reason": "not_delivered"})` per the
   contract), insert a `delivery_quality_issue` row, call `self._record(...)` with a new audit
   action, return a `QualityIssue` with `photos: []`.
   `RequestsService.attach_quality_issue_photo()`: receive the uploaded file bytes, allocate the
   path `tenants/{tenant_id}/quality-issues/{issue_id}/{filename}` server-side (never trust a
   client-supplied path — same discipline as `documents`' own `_storage_path` helper, which this
   method should mirror in shape, not import directly since the bucket differs), upload via the
   client per finding #2, insert a `delivery_quality_issue_photo` row with the resulting
   `storage_path`, generate a signed URL, call `self._record(...)`, return a `QualityIssuePhoto`.
2. **(T028)** `POST`/`GET /requests/{request_id}/quality-issues` and
   `POST /quality-issues/{issue_id}/photos` routes + `QualityIssueCreate`/`QualityIssue`/
   `QualityIssuePhoto` schemas, mirroring the contract exactly (finding #6 on the embedded `photos`
   list).
3. **(T024)** Contract test: both endpoints' shapes match the OpenAPI contract; `409 not_delivered`
   for a request not yet `delivered`. Mock the Storage-touching calls per finding #1.
4. **(T025)** Contract test for the photo-upload endpoint specifically: multipart accepted, returns
   a shape with a `url` field (mocked signed URL is fine), never a raw storage path in the response.
5. **(T026)** Integration test against real disposable Postgres: a quality issue with zero photos
   is valid; a quality issue against a non-`delivered` request refuses with `409 not_delivered`; the
   Storage-isolation half of this test follows `test_tenant_isolation.py`'s existing raw-SQL RLS
   pattern per finding #1 — do not attempt to call real Storage.

**Land as**: `backend/010-quality-issues`.

### Track B: mobile (Agy) — T029-T032, dispatched concurrently with Track A

**File scope**: `apps/mobile/lib/core/api/requests_api_client.dart` (new methods),
`apps/mobile/lib/features/delivery/quality_issue_screen.dart` (new),
`apps/mobile/lib/core/offline_queue/offline_queue_replay.dart` (new `case`, finding #3),
`apps/mobile/test/features/delivery/**` (new), `apps/mobile/test/core/offline_queue/**` (extend
existing replay tests with the new case), `packages/i18n/en.json`/`ar.json` (new `qualityIssue.*`
block). Built against the documented OpenAPI contract (request/response field names exactly as
written there) since Track A is running concurrently, not yet merged — the orchestrator
cross-checks both diffs against each other before landing either.

1. **(T029)** `reportQualityIssue(requestId, description)` → `POST
   /requests/{id}/quality-issues`, returning the created issue. `uploadQualityIssuePhoto(issueId,
   file)` → `POST /quality-issues/{id}/photos` (multipart), returning the photo (with its signed
   `url`). Mirror `RequestsApiClient`'s existing method style exactly (same as every prior wave).
2. **(T030)** New screen: description field (required, non-empty), camera capture via the
   `CameraCapture` abstraction (finding #5 — no real plugin, use the existing stand-in/fake),
   preview of a captured photo with a remove option before submit, submit calls T029. **Zero
   photos must submit successfully** — this is FR-007, test it explicitly, not just build it and
   assume. Reachable from wherever a `delivered` request is shown (mirror how Wave 11's delivery
   confirmation entry point was added to `RequestDetailScreen` when `status == 'ordered'` — do the
   same here for `status == 'delivered'`).
3. **(T031)** Wire into `OfflineQueue` per finding #3/#4: a report made offline queues via
   `createAndEnqueue(endpoint: 'quality-issues', payload: {...})`, and `offline_queue_replay.dart`
   gains the new `case 'quality-issues':` handling the two-step create-then-photo-upload sequence.
   A photo captured while offline must be copied to a stable local path before being queued (finding
   #4) — do not queue a reference to a transient camera-plugin temp path.
4. **(T032)** A full new `qualityIssue.*` i18n block (en + ar, exact parity) — there is no existing
   web screen for this to reuse copy from, same situation Wave 11's `delivery.*` was in.

**Land as**: `mobile/010-quality-issues`.

---

## 3. Review protocol

| Track | Implementer | Reviewer |
|---|---|---|
| T024-T028 (backend) | Codex | orchestrator, against real disposable Postgres |
| T029-T032 (mobile) | Agy | orchestrator, `flutter analyze` + full mobile suite |

**Because both tracks run concurrently this time, the orchestrator's review must explicitly
cross-check contract alignment** between them before landing either — read Track B's
`reportQualityIssue`/`uploadQualityIssuePhoto` request/response field assumptions against Track A's
actual final `schemas.py`, not just against the OpenAPI doc both started from. Land Track A first
regardless of which finishes first (mobile calling a not-yet-reviewed backend shape is the whole
reason Wave 11 sequenced them; concurrent dispatch changes when work happens, not the landing
order).

**T031 (offline-queue wiring) gets heightened scrutiny**, mirroring Wave 7's own history with this
exact subsystem (a major widget-test/real-Hive-I/O incompatibility was found and fixed there) — re-run
the full mobile suite specifically watching the existing `offline_queue`-related tests for any new
flakiness, not just the new quality-issue-specific tests.

---

## 4. What comes after

Once T024-T032 land, all three user stories (Wave 10, 11, 12) are independently functional and
integrated per tasks.md's own Phase 5 checkpoint. Wave 13 (Phase 6, Cross-cutting, T033-T037) closes
out this feature — mirroring 009-mobile-app-mvp's own final phase exactly (branch-scoped-visibility
test, mobile-audit test, accessibility tests, doc updates) — and is the last wave for
010-mobile-approvals-receipt.

---

## 5. Cautions

- **Don't call real Supabase Storage in any test** — this harness has no Storage service; mock it
  in contract tests, verify isolation at the raw-SQL RLS level in integration tests (finding #1).
- **Don't add a real camera plugin dependency** — stay behind the `CameraCapture` abstraction
  (finding #5); this environment cannot verify one against a real device.
- **Don't let a queued photo reference a transient file path** — copy to a stable local cache
  location at capture time (finding #4).
- **Don't skip the FR-007 zero-photos-succeeds test** — it's easy to build a screen that happens to
  work with a photo and never actually exercise the no-photo path.
- Constitution non-negotiables (§1): unchanged, still apply to every task.

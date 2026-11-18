# Tasks: In-App User Feedback

**Input**: `specs/025-user-feedback/` (plan.md, spec.md, research.md, data-model.md, contracts/feedback.openapi.yaml, quickstart.md)
**Jira**: PPS-223 (`[P-196]`)
**Tests**: Included. Tenant-isolation tests are mandatory under constitution Principle V, and the repo default is test-first: every `Tests` block is written and seen to **fail (red)** before the implementation tasks of its phase.

**Organization**: Grouped by user story (US1 to US5, priorities from spec.md) so each story is independently implementable and testable.

## Format: `- [ ] T### [P?] [US?] Description with file path`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[USn]**: user story the task serves (story phases only)
- Paths use these roots: `API` = `apps/api/src/procurepilot_api`, `TESTS` = `apps/api/tests`, `WEB` = `apps/web/src/app`, `MIG` = `supabase/migrations`

---

## Phase 1: Setup

**Purpose**: Settings, skeletons, and the decisions the owner accepted on 2026-11-18

- [ ] T001 Add feedback settings to `API/config.py` (`feedback_bucket`, `feedback_cooldown_seconds=30`, `rate_limit_feedback_submit`, `feedback_attachment_url_ttl_seconds=300`, `feedback_retention_months=12`, `feedback_digest_hour_utc`, `web_public_url` for the digest's triage link, image and audio size/count limits, `app_version`) and document each in `.env.example`
- [ ] T002 [P] Create the empty module and feature skeletons: `API/modules/feedback/__init__.py`, `API/modules/auth/operator.py`, `WEB/features/feedback/`, `WEB/features/platform/feedback-triage/`
- [x] T003 [P] Amend `specs/025-user-feedback/spec.md` for the accepted plan items, each with a Clarifications line:
  - FR-009 and story 1 scenario 5: the system sets workspace, submitter, role, demo flag, timestamp and app version; page address and language come from validated request headers, used for triage only.
  - FR-017, Assumptions ("granted and withdrawn… outside the workspace member system") and the Platform operator entity: an operator is an existing workspace member plus a live `platform_operator` record; drop the "dedicated verified credential" wording; any JWT claim is only a UI hint.
  - FR-014: operator labels are never shown to submitters or owners.
  - FR-018: status moves forward only (new to reviewed to resolved, or new to resolved).
  - FR-023: "delete or anonymise" becomes "delete".
  - Edge cases: a double-click on Send creates one submission.
  - Add a short justification that the read-only owner inbox is a support surface, not an insight dashboard (constitution Principle IV requires such features to be justified in the spec).
- [x] T003a [P] Record the owner's exception under constitution Governance ("Deviations are documented"; "explicit, recorded exception… by the project owner") for Principle V (platform-operator cross-workspace access) and Principle IV (read-only owner inbox): add an "Owner approval" line with date to `plan.md` Complexity Tracking and to ADR-027. No constitution amendment is proposed; if the owner prefers one, add a Principle V clause and bump to 1.1.0 instead.
- [x] T004 [P] Draft ADR-027 "Platform-operator access to feedback" in `docs/architecture/adrs.md` (context, decision from research.md D2, consequences, rejected alternatives, the owner approval from T003a)

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: Schema, RLS, storage, shared types. No story can start until T003, T003a and T058 are done and T015 is green.

### Tests (write first, expect red)

- [ ] T005 [P] Write `TESTS/integration/test_feedback_isolation.py`: both tables exist with RLS enabled and forced; workspace A cannot read, insert, update or delete workspace B's rows; a member cannot update any column; `platform_operator` and `is_platform_operator()` are unreachable by `authenticated` except the function's boolean result
- [ ] T006 [P] Extend `TESTS/integration/test_tenant_isolation.py`: add `feedback_submission` and `feedback_attachment` to the forced-RLS expected set, the `Workspace` dataclass and `make_workspace`; add a storage test that an object in another workspace's `feedback/` prefix is invisible
- [ ] T007 [P] Write `TESTS/unit/test_health_version.py`: `GET /api/v1/health` returns `app_version` from settings

### Implementation

- [ ] T008 `MIG/20261118000100_tenant_is_demo.sql`: `tenant.is_demo boolean not null default false`
- [ ] T009 (after T003a) `MIG/20261118000200_platform_operator.sql`: `platform_operator` table (forced RLS, no client grants, service_role only) and `is_platform_operator()` definer function (fixed `search_path`, execute for `authenticated` only) per data-model.md
- [ ] T010 `MIG/20261118000400_feedback.sql`: enums, `feedback_submission`, `feedback_attachment`, indexes, constraints, ENABLE + FORCE RLS with `USING` and `WITH CHECK` policies (own-or-owner select, operator select, member insert, operator update, own-and-new delete), forward-only status trigger, column-level update grant, table grants
- [ ] T011 `MIG/20261118000500_feedback_storage.sql`: private bucket `feedback-attachments` (10 MiB limit) and insert-only tenant-prefix policy on `storage.objects`
- [ ] T012 [P] `API/modules/feedback/schemas.py`: Pydantic models for `Submission`, `Attachment`, `Category`, `Status`, page wrappers; tenant-facing models never carry `labels`
- [ ] T013 [P] Add error types and codes in `API/errors.py` (`feedback.cooldown` with `retry_after_seconds`, `feedback.withdraw_refused`, `feedback.invalid_transition`) following the existing `AppError` pattern
- [ ] T014 [P] Expose `app_version` on `GET /api/v1/health` (`API/modules/health/router.py`) and pass `APP_VERSION` as a build arg in the API Dockerfile under `infra/docker/`
- [ ] T015 Apply with `pnpm db:migrate`; confirm T005, T006 and T007 are green and `pnpm db:check-privileges` passes
- [ ] T058 Gate spike (ID kept; runs after T015) `TESTS/integration/test_feedback_audit_cross_tenant.py`: can the audit writer's server-side form record an event for a tenant other than the caller's (research D2, D8)? If red, add `MIG/20261118000650_record_operator_audit_event.sql` (definer function executable only by operators) and use it. T066 depends on this result.

**Checkpoint**: schema, isolation and the audit approach proven; stories can start.

---

## Phase 3: User Story 1 - Submit text feedback from anywhere (P1) 🎯 MVP

**Goal**: any of the five roles sends text with an optional category from a persistent widget; context is captured; cooldown and idempotency hold.
**Independent test**: sign in as a `viewer`, send feedback, see it via `GET /feedback/mine` with status `new` and correct captured context; send again within 30 s and get a refusal.

### Tests (write first, expect red)

- [ ] T016 [P] [US1] `TESTS/contract/test_feedback_contract.py`: `POST /feedback` (text and category only) and `GET /feedback/mine` match `contracts/feedback.openapi.yaml`; add the OpenAPI drift entry
- [ ] T017 [US1] `TESTS/integration/test_feedback.py`: all five roles submit; empty and whitespace text give 422; 2000-character limit; client-sent tenant, role, user or demo values are ignored; `Referer` and `Accept-Language` are validated and normalised; `is_demo` and `app_version` are copied; name and email are snapshotted from `membership.display_name` and the token; `feedback.submitted` audit event written; category optional
- [ ] T018 [US1] `TESTS/integration/test_feedback.py` (cooldown section): second submit inside 30 s returns 429 `feedback.cooldown` with `retry_after_seconds`; same `Idempotency-Key` replay returns 200 with the original body and is exempt; abuse rate limit returns 429
- [ ] T019 [P] [US1] `TESTS/integration/test_feedback_rbac.py` (submit part): each of owner, buyer, branch_manager, approver, viewer can submit; a response to a member never contains `labels`
- [ ] T020 [P] [US1] `TESTS/unit/test_feedback_context.py`: same-origin `Referer` to path + query capped at 2000 chars, foreign-origin `Referer` rejected, `Accept-Language` normalised to `en`/`ar` with tenant-default fallback
- [ ] T021 [P] [US1] Karma specs `WEB/features/feedback/feedback-widget/feedback-widget.component.spec.ts` and `WEB/features/feedback/feedback-api.spec.ts`: open and close, empty-text block, counter at 2000, optional category, cooldown message with time left, draft kept on failure, notice visible, `Idempotency-Key` reused on retry, Send disabled while a request is in flight (double-click sends once), expired session prompts sign-in and keeps the draft

### Implementation

- [ ] T022 [US1] `API/modules/feedback/context.py`: derive page path from `Referer`, locale from `Accept-Language`, app version and demo flag, per research.md D3
- [ ] T023 [US1] `API/modules/feedback/service.py` `submit()` (text only): DB-timestamp cooldown (research D4), idempotency lookup on `(tenant_id, idempotency_key)`, insert through `procurepilot_api.db.connect` with `set local role authenticated` and synthesised claims, `feedback.submitted` audit event
- [ ] T024 [US1] `API/modules/feedback/router.py`: `POST /feedback` (multipart form, required `Idempotency-Key`, `mutation_limiter` keyed on `{tenant_id}:{sub}`) and `GET /feedback/mine` (cursor, limit up to 100); register in `API/main.py` under `/api/v1`
- [ ] T025 [P] [US1] i18n: add `feedback.widget.*`, `feedback.category.*`, `feedback.notice`, `feedback.errors.*` to `packages/i18n/en.json` and `packages/i18n/ar.json` (the notice names feedback, screenshots, name and email)
- [ ] T026 [P] [US1] `WEB/features/feedback/feedback-api.ts`: `submit()` using `FormData`, per-composition UUID `Idempotency-Key`, `Accept-Language` set from the active UI locale
- [ ] T027 [US1] `WEB/features/feedback/feedback-widget/` (standalone, signals): floating button and `MatDialog`; text with counter, optional category, notice, success state, cooldown countdown, offline error with draft kept; 360 px layout, CSS logical properties, focus trap and focus return, `aria-live` messages
- [ ] T028 [US1] Mount the widget in `WEB/layout/shell/shell.component.html` as a sibling inside `.shell-container` (not inside `main-content`); update `shell.component.spec.ts`

**Checkpoint**: text feedback works end to end. Demoable alone.

---

## Phase 4: User Story 2 - Attach screenshots (P2)

**Goal**: up to 5 screenshots by picker, drop or paste, validated by content, stored atomically with the submission.
**Independent test**: send feedback with several screenshots and confirm rows and objects exist; confirm bad files are rejected before upload and a mid-way failure stores nothing.

### Tests (write first, expect red)

- [ ] T029 [P] [US2] `TESTS/unit/test_feedback_validation.py`: content sniffing for JPEG, PNG, WEBP; renamed non-image rejected; 5 MiB limit; 6th image rejected
- [ ] T030 [US2] `TESTS/integration/test_feedback.py` (images): five images stored with attachment rows and tenant-prefixed paths; 6th gives 422; wrong type 415; oversize 413; injected failure on the 3rd upload leaves no rows and no objects; idempotent replay with files creates no second set
- [ ] T031 [P] [US2] `TESTS/integration/test_feedback_rbac.py` (attachment URL): own submitter gets a 300 s signed URL; another member in the workspace gets 404; another workspace gets 404; owner gets a URL
- [ ] T032 [P] [US2] Karma specs `WEB/features/feedback/attachment-rules.spec.ts` and widget image cases: type, size and count rules; picker, drop and paste add previews; remove works; paste with no image shows a message

### Implementation

- [ ] T033 [US2] `API/modules/feedback/validation.py`: python-magic allow-list for images (pattern: `API/modules/ingestion/capture_service.py:34-70`), size and count limits from settings, `UnsupportedMediaTypeError` and 413 mapping
- [ ] T034 [US2] `API/modules/feedback/storage.py`: upload with the user-JWT client (`upsert=false`), delete and signed-URL with the service-role client, path `tenants/{tenant_id}/feedback/{submission_id}/{uuid}/{safe_object_name}` via `shared/storage_keys.py`
- [ ] T035 [US2] Extend `service.submit()` and `router.py` for `images[]`: validate all, upload, insert in one transaction, delete uploaded objects on any failure
- [ ] T036 [US2] `GET /feedback/{id}/attachments/{attachment_id}/url` in `router.py` and `service.py`: RLS row check first, then 300 s signed URL
- [x] T037 [P] [US2] `infra/nginx/nginx.conf`: route-specific `client_max_body_size 40m` for `POST /api/v1/feedback` (global limit stays 30m)
- [ ] T038 [P] [US2] i18n: `feedback.attachments.*` in `en.json` and `ar.json` (add, remove, limits, paste hint, errors)
- [ ] T039 [P] [US2] `WEB/features/feedback/attachment-rules.ts`: client-side type, size and count checks run before any upload
- [ ] T040 [US2] Widget: image picker, drag and drop, clipboard paste on the dialog, thumbnails with remove, per-file errors; extend `feedback-api.ts` to send `images`

**Checkpoint**: US1 and US2 work together; each still passes alone.

---

## Phase 5: User Story 3 - Attach a voice message (P3)

**Goal**: record up to 2 minutes in the browser or upload an audio file, preview, send with the text.
**Independent test**: record or upload audio, play it back, send, and confirm one audio attachment is stored.

### Tests (write first, expect red)

- [ ] T041 [P] [US3] Create fixtures in `TESTS/fixtures/feedback/` (WebM/Opus, MP4/AAC, MP3, M4A, WAV, and a renamed fake) from real recorder output where possible; record libmagic's reported type for each in a comment (research.md verify item 2)
- [ ] T042 [US3] `TESTS/unit/test_feedback_validation.py` and `TESTS/integration/test_feedback.py` (audio): every fixture accepted or rejected as expected; second audio gives 422; over 10 MiB gives 413; audio stored with `kind = 'audio'`
- [ ] T043 [P] [US3] Karma specs `WEB/features/feedback/audio-recorder.service.spec.ts` and widget audio cases: feature detection hides recording; permission denied explained; 120 s auto-stop with fake timers; re-record and discard; file upload path

### Implementation

- [ ] T044 [US3] Extend `API/modules/feedback/validation.py` with the audio allow-list, mapping container types libmagic reports for audio-only WebM and M4A (per T041 findings; fallback: extension plus magic prefix)
- [ ] T045 [US3] Extend `service.submit()` and `router.py` for the optional `audio` part (one, 10 MiB) using the same atomic path as T035
- [ ] T046 [P] [US3] `WEB/features/feedback/audio-recorder.service.ts`: MediaRecorder wrapper with feature detection, 120 s cap, preview blob, MIME fallback for Safari
- [ ] T047 [US3] Widget audio UI: record, stop, playback, re-record, discard, upload file, hidden or disabled with explanation when unsupported
- [ ] T048 [P] [US3] i18n: `feedback.audio.*` in `en.json` and `ar.json`

**Checkpoint**: full submit experience (text, category, screenshots, audio).

---

## Phase 6: User Story 4 - Follow my feedback, owner inbox, withdraw (P4)

**Goal**: every member lists their own submissions with status; the owner has a read-only workspace inbox; a submitter can withdraw while `new`.
**Independent test**: two members and an owner in one workspace plus a member of another; verify visibility, withdraw rules and 404s.

### Tests (write first, expect red)

- [ ] T049 [P] [US4] `TESTS/integration/test_feedback_isolation.py` and `test_feedback_rbac.py`: member sees only own; owner sees all workspace rows; `GET /feedback` by a non-owner returns 404; cross-tenant id returns 404; owner cannot withdraw another member's item (404); no tenant payload contains `labels`; after the submitter's membership is removed the owner and operators still see the item and the former member gets 404
- [ ] T050 [P] [US4] `TESTS/integration/test_feedback.py` (withdraw): own `new` item returns 204, row and objects gone, `feedback.withdrawn` audit event without content; after status `reviewed` returns 409 `feedback.withdraw_refused`; concurrent operator status change and withdraw: exactly one wins
- [ ] T051 [P] [US4] Karma specs for `my-feedback`, `workspace-feedback` and the owner route guard; withdraw offered only when `can_withdraw`

### Implementation

- [ ] T052 [US4] `service.py` and `router.py`: `GET /feedback` (owner inbox, 404 for others), `GET /feedback/{id}`, `DELETE /feedback/{id}` using `delete ... where id = $1 and status = 'new'`; cursor pagination capped at 100
- [ ] T053 [US4] `storage.py`: delete a submission's stored objects after withdrawal (service role); failure leaves objects for the sweep in T075
- [ ] T054 [P] [US4] Extend `WEB/features/feedback/feedback-api.ts`: list mine, list workspace, get, withdraw, attachment URL
- [ ] T055 [US4] `WEB/features/feedback/my-feedback/`: own list with text, category, status, screenshot previews and audio playback via signed URLs, withdraw with confirmation
- [ ] T056 [US4] `WEB/features/feedback/workspace-feedback/` read-only owner inbox; routes `/feedback` and `/feedback/workspace` in `WEB/app.routes.ts` (`roleGuard('owner')` on the latter); shell navigation entries
- [ ] T057 [P] [US4] i18n: `feedback.list.*`, `feedback.status.*`, `feedback.withdraw.*` in `en.json` and `ar.json`

**Checkpoint**: members and owners can follow feedback; withdrawal safe against races.

---

## Phase 7: User Story 5 - ProcurePilot team triages across workspaces (P5)

**Goal**: platform operators list, open, filter, status-change and label feedback from all workspaces, with audit and an optional daily digest. Highest-risk story.
**Independent test**: with operator access read feedback from two workspaces, change status and labels, confirm audit records; with a workspace owner confirm none of it is possible.

### Tests (write first, expect red; the audit spike T058 ran in Phase 2)

- [ ] T059 [P] [US5] `TESTS/integration/test_feedback_operator.py`: operator reads across workspaces; cannot read any other tenant table; update limited to status, labels and trigger columns; backward status move refused; no insert or delete; revoking takes effect on the next request; non-operator gets 404 on `/platform/*`; list writes one aggregate `feedback.operator_listed` event; detail writes `feedback.operator_viewed` tagged with the submission's tenant; label limits (10 labels, 1 to 40 characters)
- [ ] T060 [P] [US5] `TESTS/integration/test_platform_operator_cli.py`: grant, revoke and list work and write `platform_operator.granted` and `platform_operator.revoked` audit events; revoke is idempotent
- [ ] T061 [P] [US5] `TESTS/integration/test_feedback_worker.py` (digest) and `TESTS/unit/test_feedback_digest_renderer.py`: only opted-in operators; only items newer than `digest_last_sent_at`; no email on empty days; at most one per day; body has workspace, category, excerpt and link and never an email address or attachment; English and Arabic; uses `FakeMailer`
- [ ] T062 [P] [US5] Karma specs for the triage list, detail, status and label controls, operator guard and digest toggle

### Implementation

- [ ] T063 [US5] `MIG/20261118000700_auth_hook_operator_claim.sql`: stamp a `platform_operator` claim in the access-token hook as a UI hint only (separable; fallback is `GET /platform/feedback/me`); add a claims test
- [ ] T064 [US5] `API/modules/auth/operator.py` `current_operator`: verify JWT, then live `platform_operator` check on every request (mirrors `API/deps.py:54`); operator DB access uses the direct-psycopg-with-claims path, never `service_role`
- [ ] T065 [US5] `MIG/20261118000600_platform_operator_digest_pref.sql`: definer functions that read and write only the caller's own digest preference row
- [ ] T066 [US5] `API/modules/feedback/operator_service.py` and `operator_router.py` under `/platform/feedback`: list with status, category, tenant and demo filters, detail with submitter name and email, `PATCH` status and labels, attachment signed URL, `me`, digest preference; audit actions per research D8; register in `API/main.py`
- [ ] T067 [P] [US5] `API/workers/platform_operator_cli.py`: `grant <email>`, `revoke <email>`, `list`; service role; requires an existing membership; audited
- [ ] T068 [P] [US5] `API/modules/feedback/digest_renderer.py` plus `emails.feedbackDigest.*` keys in `en.json` and `ar.json`, rendered through `shared/i18n.py` `t()`
- [ ] T069 [US5] `API/workers/feedback_worker.py`: loop with `--interval` and `--once`; digest job through `shared/mailer.py`, updating `digest_last_sent_at`
- [ ] T070 [P] [US5] i18n: `platform.feedback.*` (filters, columns, status actions, labels, digest toggle) in `en.json` and `ar.json`
- [ ] T071 [P] [US5] `WEB/features/platform/feedback-triage/platform-feedback-api.ts`
- [ ] T072 [US5] `WEB/core/auth/operator.guard.ts` (UX guard only; server is the authority) and route `/platform/feedback` in `WEB/app.routes.ts`; show the nav entry only when the claim or `me` endpoint says operator
- [ ] T073 [US5] `WEB/features/platform/feedback-triage/`: list with filters, detail with name and email, screenshots and audio via signed URLs, forward-only status control, label editor, digest toggle

**Checkpoint**: feedback reaches the team. All five stories complete.

---

## Phase 8: Polish and cross-cutting

- [ ] T074 [P] `TESTS/integration/test_feedback_retention.py` (write first): submissions older than 12 months are deleted with their objects, one aggregate `feedback.retention_purged` event, orphan objects older than 1 h swept, newer ones kept
- [ ] T075 Implement retention purge and orphan sweep in `API/workers/feedback_worker.py` (service-role connection)
- [x] T076 [P] Add a `feedback-worker` service to `docker-compose.yml`
- [ ] T077 Confirm how production runs workers (`infra/terraform`, bunny Magic Containers) and record the answer and any needed change in `docs/operations/`
- [ ] T078 [P] Playwright e2e `apps/web/tests/e2e/feedback.spec.ts`: submit, own list, owner inbox, operator triage, withdraw
- [ ] T079 [P] axe-core scans for widget, lists and triage in English and Arabic, plus manual 360 px check in both directions
- [ ] T080 Run `pnpm --filter web docs:screenshots` and `python scripts/docs_screenshots_diff.py`; regenerate and commit `docs/user/screenshots/` if the widget exceeds the 1% threshold
- [ ] T081 [P] Docs: `docs/architecture/data-dictionary.md` (three tables), finalise ADR-027, `docs/quality/test-strategy.md`, `docs/architecture/api-specification.md`, `docs/user/user-documentation.md`, `docs/gtm/demo-tenant/README.md` (flag the two demo workspaces with `tenant.is_demo`), `GLOSSARY.md` ("platform operator"), `CLAUDE.md` current-phase paragraph
- [ ] T082 Run `pnpm test`, `pnpm test:isolation`, `pnpm test:a11y`, `pnpm lint` and gitleaks; all green
- [ ] T083 Walk through `specs/025-user-feedback/quickstart.md` end to end and fix any drift
- [ ] T084 Run `debate-review --local` and fix real findings; write the PR body with `mattpocock-skills:pr`; move PPS-223 to In Review with a Progress comment; after merge apply migrations to hosted with `pnpm db:migrate`, flag the demo workspaces, and grant the first operators

---

## Dependencies and execution order

**Phase order**: Setup (1) then Foundational (2) then stories then Polish (8). T015 gates every story.

**Story dependencies**
- US1: needs Phase 2 only.
- US2: needs US1 (extends the same endpoint). US3: needs US2 (shares validation, storage and the multipart path).
- US4: needs US1; attachment display and withdrawal cleanup use US2's storage (T034, T036), so run US2 first or stub storage for the first pass.
- US5: needs US1 (data to triage). The operator digest and audit are independent of US2 to US4. Attachment viewing in the triage UI uses US2's storage helpers.
- Retention (T074 to T075) needs US2 (objects exist) and the worker from T069.

**Inside a story**: tests (red) then migrations or schemas, services, endpoints, then web. T058 (Phase 2 gate) must finish before T066. Migration timestamps only increase: `…000600` (T065), `…000650` (T058 if needed), `…000700` (T063), so nothing sorts before an already-applied file. T063 can be dropped without affecting security.

## Parallel opportunities

- **Phase 2**: T005, T006, T007 together; later T012, T013, T014 together.
- **US1**: T016 to T021 together; then T025 and T026 together while T022 to T024 proceed.
- **US2**: T029 to T032 together; T037, T038, T039 together.
- **US3**: T041 to T043 together; T046 and T048 together.
- **US4**: T049 to T051 together; T054 and T057 together.
- **US5**: T059 to T062 together; T067, T068, T070, T071 together.
- **Across stories**: after Phase 2 one developer can take the API and tests of US1 while another prepares the US5 spike (T058) and operator tests (T059).

## Implementation strategy

- **MVP (spec order)**: Phase 1, Phase 2, US1. Text feedback with category, cooldown and idempotency, demoable alone.
- **Recommended pilot MVP**: US1 plus US5. Without triage, submissions reach nobody on the team, so text-only feedback is invisible to you during the pilots. Then US2 (screenshots), US4 (own list, owner inbox, withdraw), US3 (audio). This reorders delivery only; priorities in the spec stay as written.
- **Incremental delivery**: each story ends at a checkpoint and can ship behind the existing shell without the later stories.
- **Risks front-loaded**: the audit cross-tenant spike (T058) and the audio fixtures (T041) resolve two assumptions early; both have written fallbacks in research.md.
- **Hard gates before PR**: T006 and T059 (isolation and operator boundaries), T082 (full suites), T084 (`debate-review --local`).

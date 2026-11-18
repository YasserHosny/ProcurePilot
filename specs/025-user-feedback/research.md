# Research: In-App User Feedback

Phase 0 decisions for spec 025. Each entry: decision, rationale, alternatives rejected. Code references are
from a read-only survey of the repository on 2026-11-18. Items marked **verify** are assumptions to confirm
in the first implementation task, each with a stated fallback.

## D1. One atomic multipart submit, not upload-then-submit

**Decision**: `POST /api/v1/feedback` takes `multipart/form-data` (text, category, up to 5 `images`, one
`audio`) plus a required `Idempotency-Key`. The API validates everything, uploads objects, then inserts the
submission and attachment rows in one transaction. On any failure it deletes objects it uploaded.

**Rationale**: FR-008 requires all-or-nothing and no duplicates. A single request makes atomicity and
idempotency simple. FormCraft's separate `/upload/*` endpoints followed by a submit leave orphaned files and
need cleanup logic. Photo upload in `requests/router.py:353-381` already uses multipart through the API, so
this follows precedent.

**Alternatives**: signed upload URLs straight to Storage (more client logic, partial-upload states, no
server-side content check before the file lands); per-file endpoints (orphans).

**Consequences**: Body can reach 35 MB; `infra/nginx/nginx.conf:83` sets `client_max_body_size 30m`, so a
route-specific `40m` is required for `POST /api/v1/feedback`. A backstop sweep removes storage objects with
no row (see D10).

## D2. Platform operator: live table check is the authority, claim is a hint

**Decision**:
- New table `platform_operator(user_id pk -> auth.users, email, granted_at, granted_by, revoked_at,
  digest_opt_in, digest_locale, digest_last_sent_at)`. RLS enabled and forced, **no grants to client roles**.
- `is_platform_operator()` is a `SECURITY DEFINER` function with a fixed `search_path`. It returns true if the
  caller's `sub` has a row with `revoked_at is null`. It is evaluated on every request, so revocation takes
  effect on the next request (FR-021).
- Operator RLS policies exist on `feedback_submission` (select; update limited to status/labels by a column
  grant) and `feedback_attachment` (select), and nowhere else. No operator policy exists on any other table.
- API dependency `current_operator` (new, `modules/auth/operator.py`) verifies the JWT, then checks
  `platform_operator` live, mirroring how `current_member` live-checks membership (`deps.py:54`).
- Operator reads and writes run on the direct-psycopg path with `set local role authenticated` and synthesised
  claims (precedent `offers/service.py:280`, `analyst/service.py:279`), **not** the `service_role` path.
- Grant and revoke by CLI `workers/platform_operator_cli.py` (service role, audited). No grant UI in v1.
- Optional: a dedicated `platform_operator` claim stamped by the auth hook, used only so the web app can show
  the triage nav. Separate migration (`20261118000700`) so it can be dropped without affecting security. If
  the hook change proves risky, fallback is a `GET /platform/feedback/me` call from the web app.

**Rationale**: No platform-operator concept exists today (grep of API, migrations, web, docs found none; the
only "platform" table, `platform_invitation`, is an invite-token store). A claim alone cannot be revoked
before the token expires. Keeping the operator off the service-role path confines the blast radius to two
tables, so a bug in an operator route cannot read quotations or orders.

**Alternatives**: service-role client in operator routes (whole-database blast radius); a separate Supabase
project or database for feedback (cross-system consistency, a second deployable, contradicts Principle VI);
a tenant "platform" workspace whose owner can read all tenants (a tenant role with cross-tenant reach, which
violates Principle V in spirit).

**Constraint found**: `SupabaseClaims` requires `tenant_id` and `member_role` (`auth/jwt.py:44-49`), and the
auth hook strips both when no active membership exists. So an operator must also be a workspace member.
Documented as a v1 limitation in plan.md.

**Verify**: that the audit writer's server-side form (no bearer token, over `DATABASE_URL`) can write an
`audit_event` for a tenant other than the caller's. Migration `20261018000004_definer_caller_tenant_guard.sql`
suggests the definer function checks the caller's tenant. Fallback: a dedicated
`record_operator_audit_event` definer function that only operators can execute.

## D3. Captured context

| Field | Source | Notes |
|---|---|---|
| tenant, submitter user and membership, member role | verified JWT + live membership (`current_member`) | server-set |
| submitter name | `membership.display_name` (migration `20261030000000`, PPS-125) | snapshotted at submit time |
| submitter email | `CurrentMember.email` | snapshotted at submit time |
| is_demo | new `tenant.is_demo` column | no marker exists today; ops step flags the two hosted demo workspaces |
| app version | new `APP_VERSION` setting (Docker build arg), exposed also on `/health` | nothing exposes a version today; web and API deploy together |
| page address | `Referer` header, same-origin only, stored as path + query, capped at 2000 chars | the SPA route is browser knowledge; validated, never trusted for security |
| language | `Accept-Language`, normalised to `en`/`ar`, fallback `tenant.default_locale` | web sets it from the active UI language on this request only |

**Spec tension**: FR-009 says client-supplied values for these are ignored. Page address and language can
only be browser-originated. Handled as in plan.md "Items for the owner" 1. Neither affects authorisation.

## D4. 30-second cooldown and rate limit

**Decision**: Cooldown is DB-timestamp based, as in `members/invitations.py:449-470`: reject if the same
submitter has a submission in this workspace newer than `feedback_cooldown_seconds` (30), returning 429 with
code `feedback.cooldown` and `details.retry_after_seconds`. Add `mutation_limiter` with a new setting
`rate_limit_feedback_submit` (for example `10/minute`) as an abuse backstop (key `"{tenant_id}:{sub}"`,
`key_style="endpoint"`).

**Rationale**: The cooldown must survive restarts and multiple API instances, which an in-memory limiter does
not. An idempotent replay (same `Idempotency-Key`) returns the stored result and is exempt from the cooldown.

## D5. Storage and signed URLs

**Decision**: Private bucket `feedback-attachments`, `file_size_limit` 10 MiB, path
`tenants/{tenant_id}/feedback/{submission_id}/{uuid}/{safe_object_name}`. Storage policy follows the
`quality-issue-photos` shape with `(storage.foldername(name))[2] = current_tenant_id()::text`, but grants
`INSERT` only to `authenticated`. Reads, deletes and signing go through the API using the service-role client
**after** the RLS-governed row check (precedent `documents/service.py:133`). Signed URL TTL 300 s from a new
setting `feedback_attachment_url_ttl_seconds`.

**Rationale**: Members and owners only ever reach attachments through an API access check, so a leaked path is
useless. Operators likewise: operator access is checked by the operator RLS policy on the attachment row
before a URL is signed.

**Content validation**: `python-magic` against allow-lists, as in `ingestion/capture_service.py:34-70`.
Images: JPEG, PNG, WEBP, 5 MB. Audio: MP3, M4A, WAV, WebM, 10 MB. **Verify** libmagic's reported types for
audio-only WebM (often `video/webm`) and M4A (`audio/x-m4a` or `video/mp4`) with real fixtures from Chrome,
Safari and Firefox MediaRecorder output; the allow-list must map those containers. Fallback: accept the
container type and validate by extension plus magic prefix.

## D6. Withdrawal

**Decision**: `DELETE /feedback/{id}`: a `DELETE` RLS policy allows only the submitter and only when
`status = 'new'`. The statement is `delete ... where id = $1 and status = 'new'` (atomic, so a concurrent
operator status change makes it match zero rows, and the API returns 409 `feedback.withdraw_refused`). After
the row is gone the service-role client deletes the stored objects. An audit record keeps the identifier but
not the content (FR-020). Attachment rows go by `ON DELETE CASCADE`.

**Rationale**: Hard delete satisfies "removed from every view" and the privacy intent. Orphan objects, if the
second step fails, are removed by the sweep (D10).

## D7. Status machine and labels

**Decision**: Status `new -> reviewed -> resolved` or `new -> resolved`, no backward moves, enforced by a
`BEFORE UPDATE` trigger (not only by the API) so the rule holds for any path. Backward moves are refused
because they would reopen withdrawal. `status_changed_at` and `status_changed_by` are set by the trigger.
Operator labels are a `text[]` on the submission (at most 10, each 1 to 40 characters), updatable only by
operators, hidden from tenants. Operator `UPDATE` is limited by a column-level grant to
`status, labels, status_changed_at, status_changed_by`.

**Alternatives**: a labels lookup table with a join (more tables and policies for a pilot-scale tag list).

## D8. Audit

**Decision**: Reuse `shared/audit.py` `AuditWriter` and the dotted action naming. Actions:
`feedback.submitted`, `feedback.withdrawn`, `feedback.operator_listed` (one event per list request with
filters and result count, no tenant), `feedback.operator_viewed` (one per detail open, tenant = the
submission's tenant), `feedback.operator_attachment_url_issued`, `feedback.operator_status_changed`,
`feedback.operator_labels_changed`, `feedback.retention_purged`, `platform_operator.granted`,
`platform_operator.revoked`, `feedback.digest_preference_changed`. A per-row event for list views would write
dozens of events per page and bury the trail, so list access is one aggregate event.

**Note**: audit rows tagged with the submission's tenant are readable under the existing tenant audit read
policy, which gives tenants visibility of operator access to their feedback. Treated as a feature. **Verify**
who can read `audit_event` in the web app today.

## D9. Operator daily digest and worker deployment

**Decision**: One worker module `workers/feedback_worker.py`, loop with `--interval` and `--once` like
`digest_worker.py`, running three jobs: operator digest, retention purge, orphan sweep. The digest uses the
shared `Mailer` adapter (`shared/mailer.py`, `FakeMailer` in tests), not the digest module's raw SMTP path.
Strings come from `packages/i18n` through `shared/i18n.py` `t()` (new `emails.feedbackDigest.*` keys). It sends
at most one email per opted-in operator per day, only if there is feedback newer than
`digest_last_sent_at`, containing workspace, category and a short excerpt (never email address or
attachments), with a link to the triage view.

**Why not reuse `digest_subscription`**: it is tenant-scoped, member-bound and weekly
(`MIG/20260915000003_digest_subscription.sql`). An operator is not a tenant membership.

**Deployment**: `workers/digest_worker.py` has no service in `docker-compose.yml`, while
`export_worker`, `webhook_worker`, `offer_refresh_scheduler` and `catalogue_refresh_worker` do. Add a
`feedback-worker` service. **Verify** how production runs workers (`infra/terraform`, bunny) before go-live.

## D10. Retention (12 months) and orphan sweep

**Decision**: The worker deletes submissions older than `feedback_retention_months` (12) by `created_at`
regardless of status, removing stored objects, writing one aggregate `feedback.retention_purged` audit event
per run. It also deletes storage objects under `feedback/` with no matching attachment row older than one
hour (failed-submit and failed-withdraw leftovers). Service-role connection, as other workers.

## D11. Web

- **Placement**: mount the widget as a sibling of `mat-sidenav-container` inside `.shell-container` in
  `layout/shell/shell.component.html`, so it persists across routes and is not inside the scrolling
  `main-content`. Standalone component, signals for local state.
- **Screenshots**: images by file picker, drag and drop, and clipboard paste on the dialog (`paste` event,
  `clipboardData.files`). There is no existing paste component; the ingestion capture dropzone
  (`features/ingestion/capture`) is the pattern to follow for drop handling.
- **Audio**: new `audio-recorder.service.ts` over MediaRecorder with feature detection, a 120 s cap, and
  re-record. Chrome and Firefox produce WebM/Opus; Safari produces MP4/AAC, so both containers must pass D5.
  No audio component exists today.
- **Idempotency**: generate a UUID per composition, keep it until success, reuse on retry. `ApiService`
  passes the header per call; there is no interceptor.
- **Docs screenshots**: `apps/web/src/app/**` changes trigger «Regenerate and diff» (fails above 1% pixels
  changed per image). A small collapsed button is probably under the threshold. **Verify** by running
  `pnpm --filter web docs:screenshots` locally; if it fails, regenerate and commit the images.
- **Guards**: `roleGuard('owner')` for `/feedback/workspace`; `operator.guard.ts` for `/platform/feedback`
  is a UX guard only (the existing guard comments say as much); the server is the authority.
- **a11y/i18n**: dialog focus trap and return focus, `aria-live` for validation and status, keys under
  `feedback.*` in both catalogues, parity enforced by `i18n-completeness.spec.ts` and
  `check-i18n-keys.mjs`, CSS logical properties, verified at 360 px in both directions.

## D12. Test strategy (test-first per task)

- **Isolation** (`test_feedback_isolation.py` + additions to `test_tenant_isolation.py`): workspace A cannot
  read, write, enumerate or withdraw workspace B's submissions or attachments; cross-tenant id returns no row
  (API 404); the forced-RLS expected set includes both new tables; storage object from another workspace is
  invisible.
- **RBAC** (`test_feedback_rbac.py`): all five roles can submit and read their own; only owner reads the
  workspace inbox; no role can change status or labels; non-owner cannot withdraw another's.
- **Operator** (`test_feedback_operator.py`): operator reads across workspaces; cannot read or write any
  other table; update limited to status and labels; backward status move refused by trigger; revoking takes
  effect on the next request; non-operator gets 404 on `/platform/*`.
- **Behaviour**: validation by content (renamed file rejected), 5-image and 1-audio limits, atomic rollback
  and object cleanup on failure, idempotent replay, cooldown, withdrawal race, retention and orphan sweep,
  digest only when new items and never containing email or attachments.
- **Platform**: `pnpm db:check-privileges` (new tables forced-RLS, no truncate or audit mutation grants,
  `platform_operator` unreachable by client roles), contract/OpenAPI drift, Karma specs, Playwright e2e
  (submit, own list, owner inbox, operator triage, withdraw), axe in en and ar.

## Items to verify first (order of the first implementation tasks)

1. Audit writer can record an event for a tenant other than the caller's (D2, D8); fallback stated.
2. libmagic types for real recorded audio (D5); fallback stated.
3. Docs-screenshot drift with the collapsed widget (D11).
4. Who can read `audit_event` in the web app (D8).
5. Production worker hosting (D9).

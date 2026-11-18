# Data Model: In-App User Feedback

Forward-only migrations, one concern each, RLS in the same migration as each table. Table definitions below
are design intent; exact SQL is written in the migrations.

## Migrations

| File | Contents |
|---|---|
| `20261118000100_tenant_is_demo.sql` | `alter table tenant add column is_demo boolean not null default false` |
| `20261118000200_platform_operator.sql` | `platform_operator` table, `is_platform_operator()` |
| `20261118000300_auth_hook_operator_claim.sql` | Optional UI-hint claim in the access-token hook (separable) |
| `20261118000400_feedback.sql` | enums, `feedback_submission`, `feedback_attachment`, RLS, triggers, grants |
| `20261118000500_feedback_storage.sql` | private bucket and insert-only storage policy |

## `tenant` (change)

`is_demo boolean not null default false`. Set by an ops step for the hosted demo workspaces. Copied onto each
submission at submit time so later changes do not rewrite history.

## `platform_operator`

| Column | Type | Notes |
|---|---|---|
| `user_id` | uuid pk, references `auth.users` | identifies the operator |
| `email` | text not null | snapshot for audit and digest |
| `granted_at` | timestamptz not null default now() | |
| `granted_by` | text not null | CLI operator identity |
| `revoked_at` | timestamptz null | set on revoke; a row with a value is inactive |
| `digest_opt_in` | boolean not null default false | FR-024, default off |
| `digest_locale` | text not null default 'en' check in ('en','ar') | |
| `digest_last_sent_at` | timestamptz null | watermark: only items newer than this are included |

RLS enabled and forced. `revoke all ... from public, anon, authenticated`; `grant ... to service_role`.
Clients never touch it directly. The digest preference is read and written by the API on the operator's
behalf using a definer function restricted to the caller's own row.

`is_platform_operator()`: `SECURITY DEFINER`, `set search_path = public`, returns
`exists (select 1 from platform_operator where user_id = (current_setting('request.jwt.claims', true)::jsonb ->> 'sub')::uuid and revoked_at is null)`.
`revoke execute from public, anon; grant execute to authenticated`.

## Enums

- `feedback_status`: `new`, `reviewed`, `resolved`
- `feedback_category`: `bug`, `idea`, `question`, `other`
- `feedback_attachment_kind`: `image`, `audio`

## `feedback_submission`

| Column | Type | Rule |
|---|---|---|
| `id` | uuid pk default gen_random_uuid() | |
| `tenant_id` | uuid not null references `tenant` on delete cascade | `unique (tenant_id, id)` |
| `submitter_user_id` | uuid not null | RLS identity of the submitter |
| `submitter_membership_id` | uuid null references `membership` on delete set null | |
| `submitter_name` | text not null | snapshot of `membership.display_name` |
| `submitter_email` | text not null | snapshot |
| `member_role` | text not null | owner, buyer, branch_manager, approver or viewer, at submit time |
| `text_content` | text not null | `char_length between 1 and 2000`, and not blank after trim |
| `category` | feedback_category null | optional (FR-002a) |
| `status` | feedback_status not null default 'new' | |
| `labels` | text[] not null default '{}' | operator-only, at most 10, each 1 to 40 chars |
| `page_path` | text not null | path + query, at most 2000 chars |
| `app_version` | text not null | |
| `locale` | text not null | check in ('en','ar') |
| `is_demo` | boolean not null | |
| `idempotency_key` | uuid not null | `unique (tenant_id, idempotency_key)` |
| `created_at` | timestamptz not null default now() | |
| `status_changed_at` | timestamptz null | set by trigger |
| `status_changed_by` | uuid null | operator user id, set by trigger |

Indexes: `(tenant_id, created_at desc)`, `(tenant_id, submitter_user_id, created_at desc)` (own list and
cooldown), `(status, created_at desc)` and `(category)` (operator filters), `(created_at)` (retention).

### State machine

```text
new ──► reviewed ──► resolved
 └──────────────────────▲
```

No backward transitions. A `BEFORE UPDATE` trigger raises on any other transition, sets `status_changed_at`
and `status_changed_by`, and rejects changes to every column except `status`, `labels` and those two.

### RLS (`ENABLE` + `FORCE`; every policy has `USING` and, where it writes, `WITH CHECK`)

| Policy | Command | Rule |
|---|---|---|
| `feedback_select_own_or_owner` | select | `tenant_id = current_tenant_id() and (submitter_user_id = auth.uid() or current_member_role() = 'owner')` |
| `feedback_select_operator` | select | `is_platform_operator()` |
| `feedback_insert_member` | insert | `tenant_id = current_tenant_id() and submitter_user_id = auth.uid() and status = 'new' and labels = '{}'` (any of the five roles) |
| `feedback_update_operator` | update | `using (is_platform_operator()) with check (is_platform_operator())` |
| `feedback_delete_own_new` | delete | `tenant_id = current_tenant_id() and submitter_user_id = auth.uid() and status = 'new'` |

Grants to `authenticated`: `select`, `insert`, `delete`, and column-level `update (status, labels,
status_changed_at, status_changed_by)`. Members hold the column grant but no update policy, so their updates
change nothing. `service_role` has full access (workers, signed URLs). Hiding `labels` from tenants is done in
the API response model and, for defence in depth, a tenant-facing view or column list used by member reads.

## `feedback_attachment`

| Column | Type | Rule |
|---|---|---|
| `id` | uuid pk | |
| `tenant_id` | uuid not null | |
| `submission_id` | uuid not null | composite FK `(tenant_id, submission_id)` references `feedback_submission (tenant_id, id)` on delete cascade |
| `kind` | feedback_attachment_kind not null | |
| `storage_path` | text not null | `tenants/{tenant_id}/feedback/...` |
| `content_type` | text not null | sniffed server-side |
| `size_bytes` | integer not null | images at most 5 MiB, audio at most 10 MiB |
| `display_order` | smallint not null | images 0 to 4; audio 0 |
| `created_at` | timestamptz not null default now() | |

Constraints: `unique (submission_id, kind, display_order)`; at most one audio per submission via a partial
unique index `(submission_id) where kind = 'audio'`; `check` that `display_order between 0 and 4`; image count
cap by the order range. RLS enabled and forced: select follows the parent submission's visibility
(own or owner, or operator); insert only by the submission's submitter in the same tenant; no update; delete
only by cascade or service role.

## Storage

Bucket `feedback-attachments`, private, 10 MiB object limit. Policy `feedback_attachments_tenant_insert` on
`storage.objects` for `authenticated`: `insert` only, `bucket_id = 'feedback-attachments' and
current_tenant_id() is not null and (storage.foldername(name))[2] = current_tenant_id()::text`. No `select`,
`update` or `delete` policy for clients: reads, deletes and signed URLs run through the API with the
service-role client after the row-level access check.

## Audit actions (append-only `audit_event`)

`feedback.submitted`, `feedback.withdrawn`, `feedback.operator_listed`, `feedback.operator_viewed`,
`feedback.operator_attachment_url_issued`, `feedback.operator_status_changed`,
`feedback.operator_labels_changed`, `feedback.retention_purged`, `platform_operator.granted`,
`platform_operator.revoked`, `feedback.digest_preference_changed`. Withdrawal events carry the submission id
and workspace, never the content.

## Lifecycle and retention

Created on submit; may be withdrawn while `new`; moves forward under operator control; deleted by retention
12 months after `created_at`, together with its stored objects. Counts only, no content, go to the audit
trail on purge.

## Isolation test hooks

Add `feedback_submission` and `feedback_attachment` to the expected forced-RLS set and to the `Workspace`
fixture in `tests/integration/test_tenant_isolation.py`. `pnpm db:check-privileges` must still pass:
`platform_operator` has no client grants, and no client role can truncate or alter `audit_event`.

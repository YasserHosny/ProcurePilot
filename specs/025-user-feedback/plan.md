# Implementation Plan: In-App User Feedback

**Branch**: `025-user-feedback` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/025-user-feedback/spec.md` (clarified 2026-11-18, PPS-223 / P-196)

## Summary

Workspace members of every role submit feedback (text, optional category, up to 5 screenshots, one audio)
from a floating widget in the web shell. Each submission is one atomic multipart request: the API validates
files by content, uploads them to a private tenant-scoped bucket, then inserts the rows in one transaction,
guarded by an `Idempotency-Key`. Members read their own submissions and may withdraw while `new`; the
workspace owner gets a read-only inbox. The ProcurePilot team triages across workspaces through a separate
**platform-operator** path: an operator is an existing user (a member of an internal workspace) with a live
row in a service-role-only `platform_operator` table. A narrow RLS policy backed by `is_platform_operator()`
gives that user `SELECT` on feedback and a column-limited `UPDATE` (status, labels) and nothing else. A worker
sends the optional operator daily digest and enforces 12-month retention.

Approach is a new `modules/feedback` inside the existing API (no new service), one new worker module in the
existing API image, one new web feature folder, five forward-only migrations, and ADR-027 for the operator
access exception. See [research.md](research.md) for decisions and rejected alternatives.

## Technical Context

**Language/Version**: Python 3.12 (API, worker); TypeScript 6.0 / Angular 22 (web)
**Primary Dependencies**: FastAPI, Pydantic v2, psycopg via `procurepilot_api.db.connect`, supabase-py (Storage signed URLs), python-magic (content sniffing, already used by `ingestion/capture_service.py`), SlowAPI, Angular Material + CDK, @ngx-translate, browser MediaRecorder API
**Storage**: Supabase Postgres 17 (RLS), Supabase Storage (new private bucket `feedback-attachments`)
**Testing**: pytest (unit, contract, integration incl. `test_tenant_isolation.py`), Karma/Jasmine, Playwright, axe-core, `pnpm db:check-privileges`
**Target Platform**: Hosted web (Angular SPA behind Nginx); Flutter mobile explicitly out of scope
**Project Type**: Web application (modular-monolith API + SPA) plus one background worker
**Performance Goals**: Submit with 5 images + audio completes in under 10 s on a typical connection; triage list p95 under 500 ms at 10k rows
**Constraints**: Max request body 35 MB (5 x 5 MB images + 10 MB audio) so Nginx needs a route-specific limit above its global 30m; 30 s cooldown per user; all-or-nothing writes; 360 px width; en + ar, RTL; no secrets in repo
**Scale/Scope**: Pilot scale (tens of workspaces, low hundreds of submissions per month); ~25 API/worker files, ~20 web files, 5 migrations

No `NEEDS CLARIFICATION` remains. Items verified against the code are listed in research.md; items still to
confirm at implementation time are flagged there as **verify** with a stated fallback.

## Constitution Check

*GATE: passed before Phase 0; re-checked after Phase 1 design (below).*

| Principle / rule | Result | Notes |
|---|---|---|
| I. Evidence over assertion | N/A | Feedback derives no values, savings or recommendations. |
| II. Deterministic, replayable | N/A | No normalisation or cost computation. Audit stays append-only. |
| III. Human authority | Pass | FR-022: feedback triggers no business action; nothing is automated beyond a digest email. |
| IV. Every insight ends in an action | **Justified exception** | The owner inbox is read-only by spec decision. It is a support channel, not an insight surface: see Complexity Tracking. The operator triage view carries actions (status, labels). |
| V. Tenant isolation by construction | **Pass with documented, owner-approved deviation** (Governance: "Deviations are documented"; task T003a records the approval) | `tenant_id` + ENABLE/FORCE RLS, `USING` and `WITH CHECK`, `tenant_id` from the verified JWT, cross-tenant read returns not found, isolation tests included. The operator path is a deliberate, narrow, audited cross-tenant exception: see Complexity Tracking and ADR-027. |
| VI. Modular monolith | Pass | New module in `apps/api`, new worker module in the existing image; no new service. |
| VII. Money, tax, language | Pass | en + ar catalogue, RTL logical properties, 360 px. No monetary values. |
| Phase and stage gates | Pass | Pilot-readiness work in the current phase; no Phase N+1 functionality. |
| CLAUDE.md 1-8 | Pass | 1 RLS in DB; 2 JWT tenancy (operator `tenant` filter is a filter inside the operator's authorised scope, not tenancy); 3 404 on cross-tenant; 4 no secrets; 5 i18n; 6 N/A; 7 audit append-only; 8 no autonomous purchasing. |

**Post-design re-check**: unchanged. Design adds no new service, keeps every tenant-scoped table under forced
RLS, and confines the operator exception to feedback tables.

## Project Structure

### Documentation (this feature)

```text
specs/025-user-feedback/
├── plan.md              # This file
├── research.md          # Phase 0: decisions, rationale, alternatives, items to verify
├── data-model.md        # Phase 1: tables, RLS, state machine, retention
├── quickstart.md        # Phase 1: run and verify locally
├── contracts/
│   └── feedback.openapi.yaml   # Member and operator endpoints
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit.tasks) — not created here
```

### Source Code (repository root)

```text
supabase/migrations/
├── 20261118000100_tenant_is_demo.sql
├── 20261118000200_platform_operator.sql          # table, is_platform_operator(), revoke all from clients
├── 20261118000400_feedback.sql                   # tables, enums, RLS, triggers, grants
├── 20261118000500_feedback_storage.sql           # private bucket + insert-only policy
├── 20261118000600_platform_operator_digest_pref.sql
├── 20261118000650_record_operator_audit_event.sql # only if the T058 spike needs it
└── 20261118000700_auth_hook_operator_claim.sql   # optional UI hint claim; separable (see research D2)

apps/api/src/procurepilot_api/
├── modules/feedback/
│   ├── router.py              # member + owner endpoints, prefix /feedback
│   ├── operator_router.py     # operator endpoints, prefix /platform/feedback
│   ├── schemas.py
│   ├── service.py             # submit, list, get, withdraw, signed URLs
│   ├── operator_service.py    # triage list/detail, status, labels, digest preference
│   ├── validation.py          # content sniffing, size/count rules
│   ├── storage.py             # upload, delete, signed URL (service-role only for delete/sign)
│   └── digest_renderer.py     # operator digest (reuses shared/i18n t())
├── modules/auth/operator.py   # current_operator dependency (JWT + live platform_operator check)
├── workers/feedback_worker.py # operator digest + retention purge + orphan sweep, loop with --once
├── workers/platform_operator_cli.py  # grant / revoke / list; service role; audited
├── config.py                  # feedback_* settings, app_version
└── main.py                    # include both routers

apps/api/tests/
├── unit/        test_feedback_validation.py, test_feedback_digest_renderer.py, test_feedback_status_machine.py
├── contract/    test_feedback_contract.py (+ openapi drift entry)
└── integration/ test_feedback.py, test_feedback_rbac.py, test_feedback_isolation.py,
                 test_feedback_operator.py, test_feedback_retention.py, test_feedback_worker.py
                 (+ test_tenant_isolation.py: add tables to the forced-RLS expected set and workspace fixture)

apps/web/src/app/
├── features/feedback/
│   ├── feedback-api.ts
│   ├── feedback-widget/       # FAB + dialog: text, category, images (pick/drop/paste), audio, notice
│   ├── audio-recorder.service.ts
│   ├── attachment-rules.ts    # client-side type/size/count checks
│   ├── my-feedback/           # own list + withdraw
│   └── workspace-feedback/    # owner read-only inbox (roleGuard('owner'))
├── features/platform/feedback-triage/   # operator list, detail, status, labels, digest toggle
├── core/auth/operator.guard.ts          # UX guard only; server is the authority
├── layout/shell/                        # mount widget as sibling inside .shell-container
├── app.routes.ts                        # /feedback, /feedback/workspace, /platform/feedback
packages/i18n/{en,ar}.json               # feedback.* and emails.feedbackDigest.* keys

infra/nginx/nginx.conf                   # route-specific client_max_body_size 40m for POST /api/v1/feedback
docker-compose.yml                       # feedback-worker service
docs/                                    # ADR-027, data-dictionary, test-strategy, api-specification, user docs
```

**Structure Decision**: Option 2 (web application) as it already exists in this monorepo: API module +
Angular feature + one worker module, following the `alerts` module shape and the `offers`/`analyst`
direct-psycopg-with-claims pattern for RLS-governed reads and writes. No new deployable service.

## Complexity Tracking

| Deviation | Why needed | Simpler alternative rejected because |
|---|---|---|
| **Operator cross-tenant access** (Principle V). `platform_operator` table, `is_platform_operator()` definer function, operator RLS policies on feedback tables, `/platform/feedback` routes, ADR-027. | The ProcurePilot team must read pilot feedback from every workspace; that is the point of the feature (user decision 2026-11-18). | (a) A tenant-owner-only inbox never reaches the team. (b) Service-role in the request path gives an operator route blast radius over every table; RLS policies scoped to two tables do not. (c) A JWT claim alone cannot be revoked before token expiry, so authority is the live table lookup and the claim is only a UI hint. |
| **Read-only owner inbox** (Principle IV). | Owners need to see whether their team's issues are heard; the spec decided owners cannot act. | Letting owners triage would give tenants write access to a ProcurePilot-internal queue and a second status authority. It is a support surface, not an insight dashboard: it surfaces no derived value, saving or recommendation. |
| **Client-originated request context** (spec FR-009). Page address (from `Referer`) and UI language (from `Accept-Language`) originate in the browser; the server validates and normalises them. | The server cannot know the SPA route or the UI language toggle on its own. | Ignoring them would drop the most useful triage context. All security-relevant context (tenant, user, role, demo flag, timestamp, app version) is set server-side. Spec wording should be adjusted: see below. |

**Owner approval (2026-11-18):** the owner approved the two constitutional deviations above (Principle V platform-operator access, Principle IV read-only owner inbox) as recorded exceptions under Governance. See ADR-027 in `docs/architecture/adrs.md`. No constitution amendment is proposed.

## Items for the owner

1. **Spec wording (FR-009, story 1 scenario 5)** says client-supplied context values are ignored. Page address and language can only come from the request. Proposed amendment: "tenant, submitter, role, demo flag, timestamp and app version are set by the system; page address and language are taken from standard request headers, validated, and used for triage context only."
2. **Operators must be workspace members.** The JWT parser requires `tenant_id` and `member_role`, and the shell requires a membership. An operator is an existing user, typically a member of an internal ProcurePilot workspace, plus a `platform_operator` row. Operators without any membership are not supported in v1.
3. **Labels are internal.** Operator labels are not shown to submitters or owners (the spec shows them status and category only).
4. **Status moves forward only** (new → reviewed → resolved, or new → resolved). No move back to `new`, which would reopen withdrawal.
5. **Worker deployment.** `workers/digest_worker.py` is not a service in `docker-compose.yml`; the plan adds `feedback-worker` there. How production (bunny Magic Containers / Terraform) runs workers must be confirmed before go-live.
6. **Demo flag** does not exist yet: the plan adds `tenant.is_demo`; the two hosted demo workspaces must be flagged by an ops step documented in `docs/gtm/demo-tenant/README.md`.

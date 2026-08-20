---
description: "Task list for Platform Foundation implementation"
---

# Tasks: Platform Foundation

**Input**: Design documents from `/specs/001-platform-foundation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/auth-tenant.openapi.yaml

**Tests**: Test tasks ARE included. The specification requires them explicitly — FR-030 (isolation
test on every change), SC-004 (role enforcement per role), SC-006 (axe-core), SC-009 (secret scan) —
and the constitution's Quality Gates make them release conditions rather than preferences.

**Organization**: grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelisable — different files, no dependency on an incomplete task
- **[Story]**: US1–US4 from spec.md
- Every task names its exact file path

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: an empty but correct monorepo that builds and starts.

- [ ] T001 Create the monorepo tree per plan.md Structure Decision: `apps/{api,web,mobile}`, `packages/{domain-types,ui,validation,i18n}`, `services/{extraction-worker,matching-worker,optimiser}`, `ml/{benchmarks,evals,notebooks}`, `infra/{docker,nginx,terraform}`, `.github/workflows/`
- [ ] T002 [P] Add `package.json`, `pnpm-workspace.yaml`, and `turbo.json` at the repo root declaring the workspace globs and the `test`, `lint`, `build`, `db:migrate`, `db:seed` pipelines
- [ ] T003 [P] Initialise the Python backend project in `apps/api/pyproject.toml` with uv, pinning FastAPI 0.115.6, Uvicorn 0.34.0, Pydantic v2, pydantic-settings, python-jose 3.3.0, httpx 0.28.1, SlowAPI 0.1.9, supabase-py 2.11.0
- [ ] T004 [P] Scaffold the Angular 19 app in `apps/web/` with Angular Material, the CDK, strict TypeScript, and SCSS
- [ ] T005 [P] Configure ruff in `apps/api/pyproject.toml` and Angular CLI lint in `apps/web/eslint.config.js`
- [ ] T006 [P] Add placeholder `README.md` to each of `apps/mobile/`, `services/extraction-worker/`, `services/matching-worker/`, `services/optimiser/`, `ml/benchmarks/`, `ml/evals/`, `ml/notebooks/`, each stating which chunk populates it
- [ ] T007 [P] Write `.env.example` at the repo root with every configuration key and safe local defaults, and add `.env` to `.gitignore`
- [ ] T008 Write `docker-compose.yml` running api, web-nginx, and the pinned local Supabase stack (Postgres, GoTrue, PostgREST, Storage, Kong) per research R5, with explicit image tags
- [ ] T009 [P] Write `infra/docker/api.Dockerfile` and `infra/docker/web.Dockerfile` (multi-stage: Angular build → Nginx serve)
- [ ] T010 [P] Write `infra/nginx/nginx.conf` with SPA fallback, `/api/` proxy, and the security headers from tech-stack-blueprint §7 (`X-Content-Type-Options`, `X-Frame-Options DENY`, HSTS, CSP, `Referrer-Policy`)

**Checkpoint**: `docker compose up --build` starts all containers, even with no routes yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: the tenancy, identity, and error primitives every user story sits on. **No user story
can start until this phase is complete.**

⚠️ **Highest-risk phase in the chunk.** T013 and T017 are where a mistake becomes a silent
cross-tenant leak.

### Database

- [ ] T011 Write migration `apps/api/migrations/0001_extensions.sql` enabling `pgvector` and `pg_trgm` (unused until chunks 4.3/4.4 — justified in plan.md Complexity Tracking)
- [ ] T012 Write migration `apps/api/migrations/0002_reference_tables.sql` creating `supported_region`, `supported_currency`, `supported_tax_model` with `code`, `label_en`, `label_ar`, `is_enabled`
- [ ] T013 Write migration `apps/api/migrations/0003_tenancy.sql` creating `tenant`, `membership`, `platform_invitation`, `member_invitation`, and `audit_event` exactly per data-model.md, including every constraint
- [ ] T014 Write migration `apps/api/migrations/0004_rls.sql` applying `ENABLE ROW LEVEL SECURITY` **and** `FORCE ROW LEVEL SECURITY` to every tenant-scoped table, with policies supplying both `USING` and `WITH CHECK` against `(auth.jwt() ->> 'tenant_id')::uuid` per research R4
- [ ] T015 Add to `apps/api/migrations/0004_rls.sql` the `audit_event` policy set granting `INSERT`/`SELECT` and granting no `UPDATE` or `DELETE` to any role, making the table append-only
- [ ] T016 Write migration `apps/api/migrations/0005_owner_guard.sql` with a trigger refusing any update or delete that would leave a tenant with no active owner (FR-012)
- [ ] T017 Write migration `apps/api/migrations/0006_auth_hook.sql` defining the Supabase custom access token hook that injects `tenant_id` and `role` from the caller's active membership, per research R1
- [ ] T018 [P] Write `apps/api/scripts/seed.py` inserting enabled reference rows and minting one platform invitation, printing its plaintext token once

### Backend primitives

- [ ] T019 [P] Implement settings in `apps/api/src/procurepilot_api/config.py` using pydantic-settings, reading every value from the environment with no hardcoded fallback for any secret
- [ ] T020 [P] Implement the error envelope `{code, message, details, trace_id}` and its exception handlers in `apps/api/src/procurepilot_api/errors.py`
- [ ] T021 [P] Implement structured JSON logging with trace-id propagation in `apps/api/src/procurepilot_api/shared/logging.py`
- [ ] T022 Implement Supabase JWT verification with python-jose in `apps/api/src/procurepilot_api/modules/auth/jwt.py`, rejecting tokens whose signature, expiry, audience, or issuer fails
- [ ] T023 Implement the `current_member` dependency in `apps/api/src/procurepilot_api/deps.py`, resolving exactly one workspace from the `tenant_id` claim, re-checking that the membership is still `active`, and refusing any request that resolves to none (FR-004, and the session-outlives-membership edge case)
- [ ] T024 Implement the `require_role(*roles)` dependency in `apps/api/src/procurepilot_api/modules/auth/rbac.py` per research R9
- [ ] T025 [P] Implement the append-only audit writer in `apps/api/src/procurepilot_api/shared/audit.py`, recording actor, workspace, action, target, outcome, and trace id, and never recording credentials
- [ ] T026 [P] Implement SlowAPI rate limiting in `apps/api/src/procurepilot_api/shared/rate_limit.py` using the in-process store (research R7), applied to auth endpoints
- [ ] T027 Implement the app factory in `apps/api/src/procurepilot_api/main.py` mounting routers at `/api/v1`, wiring middleware, CORS, and the exception handlers
- [ ] T028 Implement `GET /api/v1/health` in `apps/api/src/procurepilot_api/modules/health/router.py`, returning `{"status":"ok"}` only when a database round-trip succeeds and `503` otherwise (FR-024)

### Frontend primitives

- [ ] T029 [P] Configure routing in `apps/web/src/app/app.routes.ts` separating public routes from guarded ones
- [ ] T030 [P] Implement the auth interceptor and guard in `apps/web/src/app/core/auth/` attaching the bearer token and redirecting unauthenticated users
- [ ] T031 [P] Implement the session service in `apps/web/src/app/core/auth/session.service.ts` holding the current member, active workspace, and token refresh
- [ ] T032 [P] Implement the typed API client in `apps/web/src/app/core/api/` generated from `contracts/auth-tenant.openapi.yaml` into `packages/domain-types`

### Foundational tests

- [ ] T033 [P] Write `apps/api/tests/integration/test_health.py` asserting `200` when the database is reachable and `503` when it is not
- [ ] T034 [P] Write `apps/api/tests/unit/test_jwt.py` covering expired, wrong-signature, wrong-audience, and missing-claim tokens
- [ ] T035 [P] Write `apps/api/tests/unit/test_audit_append_only.py` asserting that `UPDATE` and `DELETE` on `audit_event` fail for every role including service

**Checkpoint**: migrations apply cleanly, health reports honestly, and a forged token is refused.

---

## Phase 3: User Story 1 — A business gets its own isolated workspace (P1) 🎯 MVP

**Goal**: an invited business creates a configured workspace, and no workspace can see another's data.

**Independent test**: create two workspaces, put a marker record in each, and confirm from the API
and from a direct database connection that neither can read, list, or detect the other's.

- [ ] T036 [P] [US1] Write `apps/api/tests/integration/test_tenant_isolation.py` — the FR-030 test: two workspaces, marker records, cross-reads via API and via a member's database connection, asserting "not found" rather than "forbidden" (FR-005)
- [ ] T037 [P] [US1] Write `apps/api/tests/contract/test_signup_contract.py` validating request and response shapes against `contracts/auth-tenant.openapi.yaml`
- [ ] T038 [US1] Implement the tenant, membership, and platform-invitation Pydantic models in `apps/api/src/procurepilot_api/modules/tenants/models.py` and `modules/members/models.py`
- [ ] T039 [US1] Implement platform-invitation validation in `apps/api/src/procurepilot_api/modules/tenants/invitations.py`: hash lookup, expiry and status checks, single-use marking (research R6, FR-033)
- [ ] T040 [US1] Implement workspace creation in `apps/api/src/procurepilot_api/modules/tenants/service.py`: validate the invitation, validate region/currency/tax_model against enabled reference rows, create the tenant, create the owner membership, mark the invitation spent, and write the audit event — all in one transaction (FR-001, FR-031, FR-032, FR-034)
- [ ] T041 [US1] Implement `POST /api/v1/auth/signup` in `apps/api/src/procurepilot_api/modules/tenants/router.py`
- [ ] T042 [P] [US1] Implement `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, and `POST /api/v1/auth/password-reset` in `apps/api/src/procurepilot_api/modules/auth/router.py`, with login failures indistinguishable from unknown accounts and reset always returning `202`
- [ ] T043 [P] [US1] Implement `GET /api/v1/reference/config-options` in `apps/api/src/procurepilot_api/modules/tenants/reference_router.py` returning enabled regions, currencies, and tax models
- [ ] T044 [P] [US1] Implement `GET /api/v1/me`, `PATCH /api/v1/me`, `GET /api/v1/tenant`, and `PATCH /api/v1/tenant` (owner-only; region, currency, and tax model immutable after creation) in `apps/api/src/procurepilot_api/modules/tenants/router.py` and `modules/members/router.py`
- [ ] T045 [US1] Implement `GET /api/v1/me/workspaces` and `PUT /api/v1/me/active-workspace` in `apps/api/src/procurepilot_api/modules/members/router.py`, re-issuing the session so the `tenant_id` claim follows the switch (research R3)
- [ ] T046 [P] [US1] Build the sign-up screen in `apps/web/src/app/features/onboarding/signup/` collecting the invitation token, business name, region, currency, and tax model, with no pre-selected default
- [ ] T047 [P] [US1] Build the sign-in, sign-out, and password-reset screens in `apps/web/src/app/features/auth/`
- [ ] T048 [US1] Build the authenticated shell in `apps/web/src/app/layout/` with navigation, workspace identity, workspace switcher, and account menu (FR-016)
- [ ] T049 [P] [US1] Write `apps/api/tests/integration/test_signup.py` covering a valid invitation, an expired one, a spent one, a revoked one, an absent one, and an unsupported currency
- [ ] T050 [P] [US1] Write `apps/web/tests/e2e/signup.spec.ts` (Playwright) driving invitation → sign-up → shell

**Checkpoint**: US1 is independently demonstrable. This is the MVP — isolation is proven with nothing else built.

---

## Phase 4: User Story 2 — A team works together with appropriate authority (P2)

**Goal**: owners invite colleagues under five roles, and role limits are enforced server-side.

**Independent test**: invite one member of each role, sign in as each, and confirm permitted and
refused actions match the role matrix.

- [ ] T051 [P] [US2] Write `apps/api/tests/integration/test_rbac_matrix.py` asserting, for every one of the five roles, which owner-only actions are refused (SC-004)
- [ ] T052 [P] [US2] Write `apps/api/tests/integration/test_last_owner_guard.py` asserting that self-demotion, self-removal, and demoting the final owner are all refused (FR-012)
- [ ] T053 [US2] Implement member-invitation issuing in `apps/api/src/procurepilot_api/modules/members/invitations.py`: hashed token, 7-day expiry, one pending invitation per address per workspace (FR-009, FR-010)
- [ ] T054 [US2] Implement idempotent invitation acceptance in `apps/api/src/procurepilot_api/modules/members/invitations.py` — a second acceptance returns the existing membership rather than creating a duplicate (concurrent-acceptance edge case)
- [ ] T055 [US2] Implement `POST /api/v1/invitations`, `GET /api/v1/invitations`, `DELETE /api/v1/invitations/{id}`, and `POST /api/v1/invitations/accept` in `apps/api/src/procurepilot_api/modules/members/router.py`
- [ ] T056 [US2] Implement `GET /api/v1/members`, `PATCH /api/v1/members/{id}`, and `DELETE /api/v1/members/{id}` with owner-only guards and the last-owner check, removal being a status change rather than a delete (FR-011, FR-014)
- [ ] T057 [P] [US2] Build the team management screen in `apps/web/src/app/features/team/` listing members with role, status, and actions
- [ ] T058 [P] [US2] Build the invite dialog in `apps/web/src/app/features/team/invite/` with email and role selection, per `docs/product/ui-mockup-prompts.md` §W settings
- [ ] T059 [P] [US2] Build the invitation acceptance screen in `apps/web/src/app/features/onboarding/accept-invitation/`, handling both existing and new accounts
- [ ] T060 [US2] Hide actions the active role may not perform in `apps/web/src/app/core/auth/role.directive.ts` — as a display concern **in addition to** server enforcement, never instead of it (FR-013)
- [ ] T061 [P] [US2] Write `apps/web/tests/e2e/team-management.spec.ts` covering invite → accept → role change → removal

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 — The product speaks the customer's language (P2)

**Goal**: full EN/AR parity with correct RTL layout and locale-safe formatting.

**Independent test**: switch language on the shell and confirm every string resolves, layout mirrors,
and no untranslated key appears.

- [ ] T062 [P] [US3] Create the `packages/i18n` catalogue package with `en.json` and `ar.json` and a shared loader
- [ ] T063 [US3] Configure @ngx-translate/core with http-loader in `apps/web/src/app/core/i18n/` per research R2, loading catalogues from `packages/i18n` at runtime, and register a `MissingTranslationHandler` that fails loudly in development
- [ ] T064 [US3] Wire the CDK `Directionality` service to the active language in `apps/web/src/app/core/i18n/direction.service.ts`, setting `dir` on the document root (FR-018)
- [ ] T065 [US3] Implement locale persistence: `PATCH /api/v1/me` writing `preferred_locale`, and restoration on sign-in (FR-019)
- [ ] T066 [P] [US3] Replace every hardcoded string in `apps/web/src/app/` with a catalogue key, and translate all of them into both catalogues
- [ ] T067 [P] [US3] Convert directional CSS to logical properties across `apps/web/src/app/` and `apps/web/src/styles/` (`margin-inline-start`, not `margin-left`)
- [ ] T068 [P] [US3] Add a missing-key check to `apps/web/tests/unit/i18n-completeness.spec.ts` failing the build on any key present in one catalogue and absent from the other (SC-005)
- [ ] T069 [P] [US3] Implement locale-aware currency and date formatting in `apps/web/src/app/core/format/`, always rendering an explicit currency (FR-020)
- [ ] T070 [P] [US3] Write `apps/api/tests/unit/test_locale_parsing.py` covering decimal-separator handling for both locales — the known leakage source named in the roadmap
- [ ] T071 [P] [US3] Write `apps/web/tests/e2e/rtl.spec.ts` asserting mirrored layout and Arabic strings after a language switch

**Checkpoint**: all three customer-facing stories work.

---

## Phase 6: User Story 4 — The team can build and release repeatably (P3)

**Goal**: one-command local start, blocking CI, and an automated release path.

**Independent test**: on a clean machine, follow quickstart.md and reach a healthy system; open a
trivial PR and see checks run.

- [ ] T072 [P] [US4] Write `.github/workflows/ci.yml` running ruff, Angular lint, pytest, Karma, and Playwright on every PR, with a required blocking verdict (FR-025)
- [ ] T073 [US4] Add the isolation test (T036) to `ci.yml` as a separately named required check, so its failure is never mistaken for an unrelated test failure (FR-030)
- [ ] T074 [P] [US4] Add a gitleaks step to `ci.yml` failing the build on any secret finding (FR-027, SC-009)
- [ ] T075 [P] [US4] Add an axe-core accessibility step to `ci.yml` asserting zero WCAG 2.1 AA violations on every shell screen (FR-022, SC-006)
- [ ] T076 [P] [US4] Write `.github/workflows/deploy-backend.yml` per deployment-plan §3: build, push to ghcr, test in container, update the Bunny backend container
- [ ] T077 [P] [US4] Write `.github/workflows/deploy-frontend.yml`: Angular production build, Nginx image, push, update the Bunny frontend container
- [ ] T078 [P] [US4] Write the Terraform skeleton in `infra/terraform/` for the bunny.net app, its two containers, and DNS
- [ ] T079 [P] [US4] Document required GitHub secrets (`BUNNY_API_KEY`, `BUNNY_BACKEND_APP_ID`, and the rest) in `infra/README.md`, with values held only in GitHub
- [ ] T080 [US4] Configure the staging and production environments with independent configuration and data, documented in `infra/README.md` (FR-028)
- [ ] T081 [P] [US4] Wire Sentry error reporting into both `apps/api/src/procurepilot_api/main.py` and `apps/web/src/main.ts` (FR-029)

**Checkpoint**: a change can go from PR to deployed artefact without manual assembly.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T082 [P] Apply design tokens from `packages/ui` — colour, typography, spacing — across the shell (FR-021)
- [ ] T083 [P] Verify `specs/001-platform-foundation/quickstart.md` end to end on a clean machine and correct anything that misleads (SC-007)
- [ ] T084 [P] Add the `Money` type (amount + currency, never a bare number) to `packages/domain-types` before chunk 4.2 stores its first price
- [ ] T085 [P] Fold the `[new]` fields from data-model.md back into `docs/architecture/data-dictionary.md`
- [ ] T086 [P] Add the `/auth`, `/me`, `/tenant`, `/members`, and `/invitations` surface to `docs/architecture/api-specification.md`
- [ ] T087 Confirm CI reports a verdict within 10 minutes and tune the slowest job in `.github/workflows/ci.yml` if not (SC-008)
- [ ] T089 [P] Assert the SC-001 timing budget in `apps/web/tests/e2e/signup.spec.ts` — invitation to workspace under 3 minutes unaided
- [ ] T090 [P] Assert the SC-003 timing budget in `apps/web/tests/e2e/team-management.spec.ts` — invite to active member under 2 minutes
- [ ] T091 [P] Record the Redis deferral (research R7) as a note in `docs/architecture/engineering-spec.md` §4, so the document and the build agree
- [ ] T088 Re-run the Constitution Check table from `specs/001-platform-foundation/plan.md` against the delivered code and record the result in the PR description

---

## Dependencies

```text
Phase 1 Setup
    ↓
Phase 2 Foundational  ← BLOCKS EVERYTHING; T013/T014/T017 are the critical path
    ↓
    ├── Phase 3 US1 (P1) ← MVP; must land before US2
    │       ↓
    │   Phase 4 US2 (P2) ← needs workspaces and memberships to exist
    │
    ├── Phase 5 US3 (P2) ← independent of US2; needs only the shell from T048
    │
    └── Phase 6 US4 (P3) ← CI can start early, but its story tests need US1-US3 code
            ↓
        Phase 7 Polish
```

**Story independence**: US3 and US4 can run concurrently with US2 once US1 lands. US2 depends on
US1 because roles are meaningless without a workspace to be scoped to.

---

## Delegation lanes

Task groups are shaped to be dispatched to separate implementer CLIs with minimal file overlap.

| Lane | Scope | Owner | Tasks |
|---|---|---|---|
| **A — Backend** | FastAPI modules, services, endpoints | lane `backend` → codex | T003, T019–T028, T038–T045, T053–T056, T065 |
| **B — Frontend** | Angular shell, screens, i18n | lane `frontend` → opencode | T004, T029–T032, T046–T048, T057–T061, T062–T069, T082 |
| **C — Infra & CI** | compose, Dockerfiles, workflows, Terraform | lane `infra` → agy | T001, T002, T005–T010, T072–T081 |
| **D — Tenancy & security** | migrations, RLS, auth hook, isolation tests | **not delegated** — orchestrator | T011–T018, T033–T037, T049, T051, T052 |

**Lane D is deliberately retained.** Principle V's failure mode is silent and unrecoverable: a
policy that is merely *present* but missing `WITH CHECK`, or a table with `ENABLE` but not
`FORCE`, passes a casual review and leaks quietly. That review burden is not delegated.

Lanes A, B, and C touch disjoint paths and can run concurrently once Phase 2 lands. Every
delegated diff is reviewed against spec.md, plan.md, and the constitution before it lands.

---

## Implementation strategy

**MVP first**: Phases 1–3 alone deliver a demonstrable product increment — an invited business
creates a configured workspace, and isolation is proven by an automated test. Everything after
that is additive.

**Suggested sequence**:

1. Phases 1–2 (T001–T035) — foundation, largely sequential, lane D leads.
2. Phase 3 (T036–T050) — the MVP; **stop and demo here**.
3. Phases 4–5 in parallel (T051–T071) — lanes A and B.
4. Phase 6 (T072–T081) — lane C, can begin during phase 4.
5. Phase 7 (T082–T088) — the closing pass.

**Task count**: 91 total — Setup 10 · Foundational 25 · US1 15 · US2 11 · US3 10 · US4 10 · Polish 10.

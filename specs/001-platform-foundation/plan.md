# Implementation Plan: Platform Foundation

**Branch**: `001-platform-foundation` | **Date**: 2026-08-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-platform-foundation/spec.md`

## Summary

Stand up the monorepo, environments, release path, and the isolation guarantee every later
chunk depends on. A pilot business admitted by platform invitation creates a workspace, states
its region/currency/tax model, invites colleagues under five roles, and uses a bilingual
(EN/AR, LTR/RTL) application shell. No procurement functionality ships here.

The technical approach instantiates decisions already made rather than making new ones: the
Angular 19 + FastAPI + Supabase + bunny.net stack is fixed by ADR-001 through ADR-008, and the
repository layout by engineering-spec §1. The two design questions this chunk genuinely owns
are **how `tenant_id` reaches the JWT** (the acceptance criterion for multi-tenancy) and **how
runtime language switching works in Angular** (the build-time default cannot satisfy FR-019).
Both are resolved in [research.md](./research.md).

Isolation is enforced at the database via row-level security reading a JWT claim, not by
application-layer filtering — so a forgotten `WHERE tenant_id = ...` cannot leak data. That
choice is what makes Constitution Principle V testable rather than aspirational.

## Technical Context

**Language/Version**: Python 3.12 (backend) · TypeScript 5.6 / Angular 19 (web) · Dart 3.x /
Flutter (mobile placeholder only) · SQL (versioned migrations)

**Primary Dependencies**: FastAPI 0.115.6 · Uvicorn 0.34.0 · Pydantic v2 + pydantic-settings ·
python-jose 3.3.0 (JWT verification) · httpx 0.28.1 · SlowAPI 0.1.9 (rate limiting) ·
supabase-py 2.11.0 · Angular Material + CDK · RxJS · Zod (shared validation) ·
@ngx-translate/core ^16 + http-loader (runtime i18n, blueprint-pinned — see research R2)

**Storage**: Supabase Postgres 17 with `pgvector` and `pg_trgm` extensions enabled at
migration time (unused until chunks 4.3/4.4) · Supabase Storage (bucket created, unused
here) · **no Redis in this chunk** — see research R7

**Testing**: pytest 8.3.4 + pytest-asyncio 0.25.2 · httpx TestClient · Karma 6.4 / Jasmine 5.4 ·
Playwright ^1.60 (E2E) · ruff + Angular CLI lint · axe-core (accessibility) · gitleaks (secrets)

**Target Platform**: Linux containers on bunny.net Magic Containers (ADR-005), fronted by
Nginx (ADR-006); evergreen browsers for the web client

**Project Type**: Web application — Angular SPA plus FastAPI modular monolith, in a Turborepo +
pnpm / uv monorepo (ADR-008)

**Performance Goals**: health check < 100 ms · authenticated request p95 < 300 ms · sign-up to
workspace under 3 minutes end-to-end (SC-001) · CI verdict within 10 minutes (SC-008)

**Constraints**: isolation enforced in the database, not the application · zero secrets in
version control (gitleaks-gated) · WCAG 2.1 AA, zero axe violations · every user-facing string
from the shared EN/AR catalogue · every monetary value stores an explicit currency

**Scale/Scope**: pilot-sized — tens of workspaces, low hundreds of users, single region.
Roughly 8 shell screens (sign-up, sign-in, password reset, workspace creation, home, team,
settings, profile). Staging and production provisioned as skeletons.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Principle | Applies? | Gate for this feature | Pre-design | Post-design |
|---|---|---|---|---|
| **I. Evidence Over Assertion** | Partially | No derived or extracted values exist yet. The applicable part is provenance on security-significant actions: every membership and authorisation event records actor, workspace, action, and time. | ✅ PASS | ✅ PASS |
| **II. Deterministic, Replayable Normalisation** | No | No normalisation, landed cost, or offer data in this chunk. Carried forward as a gate on chunk 4.4. The bitemporal and append-only requirements are *anticipated* in the audit table design (append-only, no updates) so the pattern is established, not retrofitted. | ✅ N/A | ✅ N/A |
| **III. Human Authority Over Automation** | No | No automation, recommendation, or purchasing path exists. Carried forward as a gate on chunks 4.3–4.5. | ✅ N/A | ✅ N/A |
| **IV. Every Insight Ends in an Action** | No | No insight surfaces. The shell deliberately ships without dashboards — consistent with the principle rather than an exception to it. | ✅ N/A | ✅ N/A |
| **V. Tenant Isolation by Construction** | **Yes — core** | Every tenant-scoped table carries `tenant_id` and is protected by RLS; every request resolves exactly one workspace; an automated cross-tenant test runs on every PR. | ✅ PASS | ✅ PASS — RLS policies in the first migration, `tenant_id` from a verified JWT claim, `tests/integration/test_tenant_isolation.py` wired into CI |
| **VI. Modular Monolith** | Yes | One deployable backend. No new services beyond the pre-authorised extraction/matching/optimiser, and those ship as empty placeholders only. | ✅ PASS | ⚠️ PASS with justification — see Complexity Tracking |
| **VII. Money, Tax, Language from the Schema Up** | **Yes — core** | Currency explicit on every monetary column; tax model stored as data; EN/AR catalogue with RTL; locale-sensitive parsing tested. | ✅ PASS | ✅ PASS — no monetary columns exist yet, so the gate lands on `Tenant.currency`/`tax_model` and on the shared money type defined in `packages/domain-types` before any amount is stored |

**Workflow gates** (Development Workflow section of the constitution):

- Specification precedes code — ✅ spec.md approved, clarifications resolved, 16/16 checklist items pass.
- Stage gates binding — ✅ this is Phase 1 work; G0 is the gate behind it. No Phase 2+ code is planned here.
- Delegated implementation reviewed — ✅ planned: every delegated diff is reviewed against this plan and the constitution before landing.

## Project Structure

### Documentation (this feature)

```text
specs/001-platform-foundation/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output — 8 resolved decisions
├── data-model.md        # Phase 1 output — entities, RLS, migrations
├── quickstart.md        # Phase 1 output — clean-machine setup
├── contracts/
│   └── auth-tenant.openapi.yaml   # Phase 1 output — API contract
├── checklists/
│   └── requirements.md  # Spec quality checklist (passing)
└── tasks.md             # Phase 2 output (/speckit.tasks — not created by /speckit.plan)
```

### Source Code (repository root)

```text
apps/
├── api/                          # FastAPI modular monolith — the only backend deployable
│   ├── src/procurepilot_api/
│   │   ├── main.py               # app factory, router mounting, middleware chain
│   │   ├── config.py             # pydantic-settings; all secrets from env
│   │   ├── deps.py               # shared dependencies (current member, workspace scope)
│   │   ├── errors.py             # {code, message, details, trace_id} envelope
│   │   ├── modules/
│   │   │   ├── auth/             # JWT verification, workspace resolution, RBAC
│   │   │   ├── tenants/          # workspace creation, configuration, platform invitations
│   │   │   ├── members/          # membership, roles, member invitations
│   │   │   └── health/           # health check incl. database reachability
│   │   └── shared/               # audit writer, logging, rate limiting
│   ├── migrations/               # versioned SQL, applied via Supabase CLI (ADR-007)
│   └── tests/{unit,integration,contract}/
├── web/                          # Angular 19 SPA
│   ├── src/app/
│   │   ├── core/                 # auth guard/interceptor, session, error handling
│   │   ├── layout/               # shell: nav, workspace switcher, account menu
│   │   ├── features/{auth,onboarding,team,settings}/
│   │   └── styles/               # design tokens, RTL support
│   └── tests/{unit,e2e}/
└── mobile/                       # Flutter placeholder — README only, no code (Phase 2)

packages/
├── domain-types/                 # OpenAPI-generated TS + Dart types; shared Money type
├── ui/                           # design tokens (colour, type, spacing)
├── validation/                   # shared Zod schemas
└── i18n/                         # en + ar catalogues

services/                         # placeholders only — no code, no deployables (chunks 4.3+)
├── extraction-worker/README.md
├── matching-worker/README.md
└── optimiser/README.md

ml/                               # placeholders only — populated from chunk 4.3
├── benchmarks/README.md
├── evals/README.md
└── notebooks/README.md

infra/
├── docker/                       # Dockerfiles for api and web-nginx
├── nginx/                        # SPA fallback, /api proxy, security headers
└── terraform/                    # bunny.net + DNS skeleton

.github/workflows/
├── ci.yml                        # lint, test, isolation test, axe, gitleaks — every PR
├── deploy-backend.yml            # ghcr build/push → Bunny container update
└── deploy-frontend.yml           # Angular build → Nginx image → Bunny container update

docker-compose.yml                # api + web + supabase local stack
```

**Structure Decision**: monorepo layout per ADR-008 and engineering-spec §1, instantiated
exactly as specified. Only `apps/api`, `apps/web`, `packages/*`, `infra/`, and the workflows
carry running code in this chunk; `apps/mobile`, `services/*`, and `ml/*` are created as
documented placeholders so that later chunks add files rather than restructure the tree.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Placeholder directories for three services and three ML folders that contain no code and deploy nothing (brushes against Principle VI's "no new services") | ADR-008 fixes the monorepo layout, and engineering-spec §1 specifies this exact tree. Creating empty, documented placeholders costs one README each and prevents a disruptive restructure when chunks 4.3–4.5 land. No service is built, containerised, deployed, or referenced by the running system. | Creating directories only when first needed would be simpler, but it defers a *layout* decision that is already made and would force import-path and CI-path churn across three later chunks. The constitutional concern is operating a distributed system prematurely — no process, container, or network hop is introduced here, so the substance of Principle VI is respected even though the tree anticipates future work. |
| Enabling `pgvector` and `pg_trgm` extensions in the first migration though nothing queries them until chunks 4.3–4.4 | Extension enablement is a privileged, environment-level operation. Doing it once in the foundation migration means later chunks ship plain table migrations. | Enabling them later is possible but concentrates privileged operations into a chunk already carrying the highest AI risk, and risks a staging/production drift that surfaces only under load. |


---

## Constitution Check — re-run against delivered code (T088)

Run at the close of Phase 1, against what was built rather than what was planned. Evidence is a
command that was executed, not a claim.

| Principle | Verdict | Evidence |
|---|---|---|
| **I. Evidence Over Assertion** | ✅ PASS | Every security- and membership-significant action writes an `audit_event` with actor, workspace, action, outcome and trace id. The table is append-only, proven by `test_audit_append_only.py`. No derived or extracted values exist yet, so the rest of the principle carries forward to chunk 4.3. |
| **II. Deterministic Normalisation** | ✅ N/A | No normalisation or landed cost in this chunk. The append-only `audit_event` establishes the pattern early, at no cost. Carried forward as a gate on chunk 4.4. |
| **III. Human Authority** | ✅ N/A | No automation, recommendation or purchasing path exists. Carried forward to chunks 4.3–4.5. |
| **IV. Every Insight Ends in an Action** | ✅ N/A | The shell ships with no dashboards, which is consistent with the principle rather than an exception to it. |
| **V. Tenant Isolation by Construction** | ✅ PASS | All five tenant-scoped tables have RLS both `ENABLED` and `FORCED` — verified by query, `5 | 5 | 5`. Twelve isolation tests run as the real `authenticated` role with a real JWT claim and are mutation-checked: removing `FORCE` from one table fails one test, dropping a policy fails two. CI runs them as their own named job. |
| **VI. Modular Monolith** | ⚠️ PASS with justification | One deployable backend. `services/*` and `ml/*` remain empty placeholders. The Supabase CLI now runs the local stack, which adds no ProcurePilot service. Complexity Tracking above still holds. |
| **VII. Money, Tax, Language from the Schema Up** | ✅ PASS | Region, currency and tax model are collected at sign-up, validated against data-held reference tables, and no default is inferred. EN/AR catalogues are at parity (233 keys) with a completeness check that fails the build on a gap. RTL verified by E2E. **Zero monetary columns exist yet** — confirmed by query — and the `Money` type (amount + currency, decimal string never a float) landed in `packages/domain-types` before chunk 4.2 can store the first price, which is the whole point of doing it now. |

### Standing exceptions, recorded rather than buried

**Four SECURITY DEFINER functions cross or precede the tenancy boundary** — `record_audit_event`
(0007), `list_my_workspaces` and `set_active_workspace` (0008), `accept_member_invitation` (0009),
`member_invitation_for_token` (0010). Each re-derives authority from something the caller must
already hold — the JWT `sub` claim, or an invitation token hash — rather than trusting a parameter.
They exist because RLS cannot express "an outsider becoming an insider", and the alternative was an
RLS bypass in application code. That is a deliberate, tested design, not a workaround.

**Four service-role call sites remain**, all in `modules/members/invitations.py`: the invitation
lookup and the mark-expired/mark-accepted back-office operations. These do not serve an
authenticated user's request. `find_membership` immediately after acceptance is the closest call:
the caller's token still names their previous workspace, so the new membership is not yet visible
to them. It is scoped to one tenant and one user id the RPC has already validated. **This is the
place a future reviewer should look first** if the service-role surface starts growing.

### Quality gates

| Gate | Threshold | Status |
|---|---|---|
| Accessibility | WCAG 2.1 AA, zero violations | ✅ 4 axe-core specs, all green. Two real defects found and fixed: 2.87:1 contrast, and a scrollable region unreachable by keyboard. |
| Cross-tenant isolation | Proven on every change | ✅ Own CI job, mutation-checked |
| Secrets in repo | Zero, verified | ✅ gitleaks job on every PR |
| i18n completeness | No key in one catalogue only | ✅ Unit test, mutation-checked |
| Sign-up time (SC-001) | Under 3 minutes | ✅ Asserted in `signup.spec.ts` |
| Invite time (SC-003) | Under 2 minutes | ✅ Asserted in `team-management.spec.ts` |
| CI verdict (SC-008) | Within 10 minutes | ✅ **5m29s**, measured on run 32375539305 of PR #1. All six jobs green on a real runner. |
| Extraction / matching accuracy | ≥90% / ≥92% | N/A — no AI in this chunk. Gates on chunks 4.3/4.4. |

### The honest gaps

- ~~No CI run has happened.~~ **Resolved.** Four runs on PR #1 took the pipeline from 3/6 to 6/6.
  Every failure was a real defect, not a flake: gitleaks lacking permission to report findings;
  `backend-tests` handed a database and `TEST_DATABASE_URL` but no schema, which made the
  database-backed tests stop skipping and start failing; uv's post-run cache save failing a job
  *after* all 14 E2E specs had passed; a high-entropy test fixture that looked exactly like an API
  key; and that fixture surviving in commit history after the file was fixed, because
  `gitleaks detect` scans history rather than the working tree.
- **The acceptance criterion in spec.md is now false.** `docker compose up --build` no longer
  starts Supabase. quickstart.md has been corrected; the spec's own wording still needs amending,
  which is a decision for the owner rather than a silent edit.
- **Deployment has never been exercised.** The deploy workflows and Terraform are validated but
  have never run against a real bunny.net account.

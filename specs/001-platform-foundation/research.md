# Phase 0 Research: Platform Foundation

**Feature**: 001-platform-foundation | **Date**: 2026-08-20

The stack is fixed by ADR-001 through ADR-008; this document does not revisit it. What follows
resolves the open questions that the ADRs do not answer and that the acceptance criteria force.

---

## R1 — How `tenant_id` reaches the JWT

**Decision**: a Supabase **custom access token auth hook** — a Postgres function invoked at
token issuance that reads the user's active membership and injects `tenant_id` and `role` as
claims into the access token.

**Rationale**: the acceptance criterion is literally "the JWT carries `tenant_id`", and RLS
policies need the claim to be *inside the token* — a policy cannot call back into application
code. The auth hook is the only mechanism that puts a server-controlled, per-issuance value in
the token. Because it runs at issuance, membership changes take effect on the next token
refresh rather than being frozen at sign-up.

**Alternatives considered**:
- *`app_metadata` written via the admin API at sign-up* — the claim goes stale the moment a
  membership or role changes, and correcting it requires an admin write on every membership
  mutation. A stale role claim is a privilege bug.
- *Backend looks up the tenant per request from the user id* — works for application code but
  leaves RLS with nothing to filter on, which forfeits Principle V's entire point: isolation
  must survive a forgotten application-level filter.
- *`tenant_id` in the URL path or a header* — client-supplied tenancy is a trivially forgeable
  isolation boundary. Explicitly rejected by engineering-spec §3 ("tenant resolved server-side
  from token").

**The claim is `member_role`, not `role`.** Discovered while reviewing the backend primitives:
Supabase and PostgREST use the `role` claim as the *Postgres role* to assume for the request
(`authenticated`, `anon`, `service_role`). Writing the member's role there makes PostgREST issue
`set role owner`, which fails with `role "owner" does not exist` — every request, not an edge
case. Verified directly against Postgres 17. The hook therefore injects `tenant_id` and
`member_role` and leaves `role` untouched.

**Verification required during implementation**: confirm the auth hook API shape against the
Supabase version pinned in `docker-compose.yml` before building on it — this is the single
highest-risk external dependency in the chunk, and the contract has moved between versions.

---

## R2 — Runtime language switching in Angular

**Decision**: **@ngx-translate/core ^16.0.0 with @ngx-translate/http-loader**, as pinned in
`docs/architecture/tech-stack-blueprint.md` §frontend, with catalogues living in `packages/i18n`
and served as JSON assets.

**Rationale**: FR-019 requires a member to switch language in-app and have the choice persist
across sessions. ngx-translate loads catalogues at runtime over HTTP and switches with
`translate.use(lang)`, which satisfies the requirement directly. The blueprint already pins the
library and its loader, and the install command in §3b lists it — this decision instantiates
that choice rather than revisiting it.

**Alternatives considered**:
- *`@angular/localize`* — first-party, but it compiles one bundle per locale and selects at
  *build* time. In-app switching would mean reloading against a different deployed bundle.
  Rejected on requirements: FR-019 cannot be met cleanly this way.
- *Transloco* — a capable alternative with a stricter typing story, and it was the initial
  choice in this document. **Rejected**: the blueprint pins ngx-translate, and the difference
  between the two is preference, not capability. Introducing a second i18n library into a
  stack that already names one is unjustified divergence, and the constitution requires
  deviations to be documented and justified rather than assumed.

**Consequence**: missing-key detection is not built into ngx-translate as strongly as
SC-005 requires, so a `MissingTranslationHandler` is registered to fail loudly in development
and a catalogue-completeness test (T068) enforces parity in CI. RTL is handled independently of
translation — `dir` on the document root plus CSS logical properties (`margin-inline-start`
rather than `margin-left`); Angular Material supports bidirectionality through the CDK's
`Directionality` service, which the shell wires to the active language.

## R3 — A person in several workspaces

**Decision**: one **active workspace per session**, carried as the `tenant_id` claim. Switching
workspace calls an endpoint that records the new active membership, then forces a token refresh
so the claim — and therefore RLS — follows.

**Rationale**: keeps exactly one tenant scope per request (FR-004) with no ambiguity about which
workspace a mutation lands in. Because the switch goes through token re-issuance, the database
enforcement and the application view can never disagree.

**Alternatives considered**:
- *All memberships as an array claim, workspace chosen per request by header* — puts scope
  selection back in the client's hands and makes every RLS policy a set-membership test. More
  moving parts, weaker guarantee.
- *One session per workspace in separate browser profiles* — no implementation cost, but an
  unacceptable experience for the multi-branch operators the product targets.

**Listing and switching need their own RPCs.** Found implementing the endpoints: membership RLS is
scoped to the active workspace, which makes "which workspaces do I belong to?" unanswerable by a
direct query — it can only ever return the one the token already names. The first implementation
reached past RLS with a privileged connection filtered by `user_id` in Python; not exploitable as
written, but an RLS bypass in the request path, and a precedent for later chunks. Migration 0008
adds `list_my_workspaces()` and `set_active_workspace()` as SECURITY DEFINER functions that read
the caller from the JWT's `sub` claim and take no user parameter, so neither can be pointed at
another person. Proven by test: a second user calling `list_my_workspaces` sees only their own.

**The backend must forward the caller's token.** PostgREST derives `request.jwt.claims` from the
bearer token it receives. A backend call made with the anon key alone carries no claims, so
`current_tenant_id()` is NULL and RLS denies — or, for the audit writer, silently files the event
with no tenant. Every on-behalf-of-user call therefore opens the client with the anon key and then
sets the caller's access token on it.

---

## R4 — RLS policy pattern

**Decision**: every tenant-scoped table gets `tenant_id uuid not null`, `ENABLE ROW LEVEL
SECURITY` **and** `FORCE ROW LEVEL SECURITY`, with policies comparing the column to the JWT
claim:

```sql
create policy tenant_isolation on <table>
  using (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid)
  with check (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
```

**Rationale**: `USING` governs reads and `WITH CHECK` governs writes; supplying only `USING`
leaves a hole where a member writes a row into another workspace. `FORCE` matters because table
owners bypass RLS by default — without it, the policy silently does nothing for the migration
role.

**Alternatives considered**:
- *Application-layer filtering only* — the failure mode is one missing `WHERE` clause in one
  query, and the leak is silent. Rejected by Principle V.
- *Schema-per-tenant* — strong isolation, but migrations become O(tenants) and cross-tenant
  benchmarking (a stated Year-3 asset) becomes impossible. Rejected by roadmap §10.1's shared
  canonical spine.

**Service-role handling**: the service role bypasses RLS and is therefore restricted to
migrations and the platform-invitation flow, which by definition runs before a workspace exists.
It is never used to serve an authenticated request. This restriction is itself a test.

**Writing audit events without a service role.** The audit insert policy requires
`tenant_id = current_tenant_id()`, which the two most security-relevant events cannot satisfy: a
failed sign-in has no tenant claim, and a refused workspace creation has no tenant yet. Both carry
`tenant_id` NULL, and `NULL = NULL` is not true — so the events most worth recording were the ones
that could not be written. Handing the backend a service-role key would have solved it and broken
the rule above; instead migration 0007 adds `record_audit_event`, a `SECURITY DEFINER` function
that is the only sanctioned write path. It is append-only by construction and validates the
target tenant against the caller's own claim, so elevated rights cannot be turned into
cross-tenant writes. Proven by test: a member of tenant A recording an event against tenant B is
refused.

---

## R5 — Single-command local stack

**Decision**: `docker-compose.yml` runs the API, the web app behind Nginx, and a pinned local
Supabase stack (Postgres, GoTrue, PostgREST, Storage, Kong) as services, so
`docker compose up --build` satisfies the acceptance criterion literally.

**Rationale**: the criterion is a single command bringing up backend, frontend, and Supabase.
Compose is already the documented local trigger in the deployment plan §1.

**Alternatives considered**:
- *`supabase start` (CLI) alongside a compose file for app services* — the CLI's managed stack
  is closer to hosted Supabase and is the officially supported path, but it makes the developer
  run two commands and turns the acceptance criterion into a lie. Kept as the documented
  fallback if version pinning against the local stack proves fragile.

**Consequence**: image versions are pinned explicitly and bumped deliberately. Unpinned Supabase
component images are the most likely source of "works on my machine" drift.

---

## R6 — The platform invitation gate

**Decision**: a `platform_invitation` table holding a single-use, hashed, expiring token issued
by the ProcurePilot team. Workspace creation requires a valid token; the invitation is marked
spent and retained, linked to the workspace it produced.

**Rationale**: the pilot is invitation-gated (spec Clarifications). Storing only a hash means a
database read cannot yield a usable invitation. Retaining spent invitations makes each workspace
attributable to a cohort (FR-034), which the Phase 0/1 pilot metrics depend on.

**Alternatives considered**:
- *A shared secret signup code* — trivial to implement, impossible to attribute or revoke
  individually, and one leak opens the gate entirely.
- *Manual workspace creation by the team* — safest, but every pilot onboarding becomes an
  engineering task, and the sign-up path stays untested until chunk 4.6 needs it working.

---

## R7 — No Redis in this chunk

**Decision**: **defer Redis** to chunk 4.3, when the extraction worker introduces the first
background job. Rate limiting in this chunk uses SlowAPI's in-process store.

**Rationale**: Principle VI — the foundation should carry no component that nothing uses. There
are no sessions to cache (JWTs are stateless), no queues, and no jobs. The one honest cost is
that in-process rate limiting counts per container rather than globally, which is immaterial at
pilot scale behind an invitation gate.

**Alternatives considered**:
- *Include Redis now because engineering-spec §4 lists it* — that section describes the Phase 1
  end state, not this chunk's slice. Adding an unused stateful service to compose, staging, and
  production means three environments to operate for zero delivered behaviour.

**Revisit when**: the first background job lands, or more than one backend container runs in
production — whichever comes first. Recorded so the deferral is a decision, not an oversight.

---

## R8 — Secrets and environment configuration

**Decision**: all configuration through environment variables via pydantic-settings, with
`.env.example` committed and `.env` ignored. GitHub Actions supplies deployment secrets. A
**gitleaks** scan runs on every PR and blocks the merge on any finding.

**Rationale**: FR-027 and SC-009 require *verified* absence of secrets, not a convention. A
scan in CI is the only form of that claim which stays true after the tenth contributor.

**Alternatives considered**:
- *Review discipline alone* — fails silently and exactly once.
- *A managed secrets service (Vault, Doppler)* — better at scale, disproportionate for a
  pilot-stage team already using GitHub Actions secrets, and reversible later.

---

## R9 — Where RBAC is enforced

**Decision**: **two layers**. The `role` claim in the JWT drives a FastAPI dependency that
authorises the endpoint; RLS independently enforces the workspace boundary. Roles govern *what
you may do*; RLS governs *whose data you may touch*.

**Rationale**: the two concerns fail differently. A role bug exposes an action to the wrong
person inside one workspace — bad. A tenancy bug exposes another business's commercial data —
fatal. Keeping the boundary in the database means a role bug cannot become a tenancy bug.

**Alternatives considered**:
- *Encoding roles into RLS policies too* — expressible, but every permission change becomes a
  migration, and policy logic grows combinatorially with the role/action matrix.
- *Frontend-only role gating* — a display concern mistaken for a security control. The frontend
  hides unavailable actions (FR-013) **in addition to**, never instead of, server enforcement.

---

## Summary of decisions

| # | Question | Decision |
|---|---|---|
| R1 | `tenant_id` into the JWT | Supabase custom access token auth hook |
| R2 | Runtime i18n | @ngx-translate/core ^16 + http-loader (blueprint-pinned), catalogues in `packages/i18n` |
| R3 | Multi-workspace membership | One active workspace per session; switch re-issues the token |
| R4 | Isolation enforcement | `FORCE` RLS with `USING` + `WITH CHECK` against the JWT claim |
| R5 | Local stack | Compose runs api + web + pinned Supabase stack |
| R6 | Pilot gate | Single-use hashed, expiring platform invitation |
| R7 | Redis | Deferred to chunk 4.3; in-process rate limiting for now |
| R8 | Secrets | Env-based config, `.env.example` committed, gitleaks gate in CI |
| R9 | RBAC | Role claim + FastAPI dependency for actions; RLS for tenancy |

**No NEEDS CLARIFICATION items remain.**

# Phase 1 Data Model: Platform Foundation

**Feature**: 001-platform-foundation | **Date**: 2026-08-20

Field names and types follow `docs/architecture/data-dictionary.md`. Where this chunk adds
fields the dictionary does not yet carry, they are marked **[new]** and should be folded back
into the dictionary when this feature lands.

---

## Entities

### `tenant` — the workspace and isolation boundary

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` | |
| `name` | text | not null, 1–200 chars | Business name |
| `slug` | text | not null, **unique**, lowercase, `[a-z0-9-]{3,63}` | Subdomain identifier |
| `region` | text | not null, FK → `supported_region.code` | Collected at sign-up (FR-031) |
| `currency` | text | not null, ISO 4217, FK → `supported_currency.code` | No default (FR-031) |
| `tax_model` | text | not null, FK → `supported_tax_model.code` | Data-driven (FR-032) |
| `default_locale` | text **[new]** | not null, `en` \| `ar` | Workspace fallback language |
| `platform_invitation_id` | uuid **[new]** | FK → `platform_invitation.id`, not null | Cohort attribution (FR-034) |
| `created_at` | timestamptz | not null, default `now()` | |

Not RLS-scoped by `tenant_id` — this *is* the tenant. Its policy compares `id` to the claim.

### `membership` — a person's participation in one workspace

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `tenant_id` | uuid | FK → `tenant.id`, not null | RLS key |
| `user_id` | uuid **[new]** | FK → `auth.users.id`, not null | Supabase Auth identity |
| `email` | text | not null | Denormalised for display and invitation matching |
| `role` | enum | not null — `owner`, `buyer`, `branch_manager`, `approver`, `viewer` | Exactly one (FR-008) |
| `mfa_enabled` | boolean | not null, default `false` | Modelled, not enforced (FR-015) |
| `preferred_locale` | text **[new]** | `en` \| `ar`, nullable | Falls back to `tenant.default_locale` (FR-019) |
| `is_active_workspace` | boolean **[new]** | not null, default `false` | Drives the JWT claim (R3) |
| `status` | enum **[new]** | `active` \| `removed`, default `active` | Removal is a state change, not a delete |
| `created_at` | timestamptz | not null, default `now()` | |

Constraints:
- **unique** `(tenant_id, user_id)` — one membership per person per workspace.
- **partial unique** `(user_id) where is_active_workspace` — exactly one active workspace per person.
- **partial unique** `(tenant_id) where role = 'owner' and status = 'active'` is *not* used; multiple owners are allowed. The last-owner rule (FR-012) is enforced by a trigger, because it is a cardinality-minimum rule that a unique constraint cannot express.

### `platform_invitation` — admits a business to the pilot

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `email` | text | not null | Intended recipient |
| `token_hash` | text | not null, unique | **Hash only** — never the token (R6) |
| `expires_at` | timestamptz | not null | Default 7 days |
| `status` | enum | `pending` \| `spent` \| `revoked` \| `expired` | |
| `spent_at` | timestamptz | nullable | |
| `created_at` | timestamptz | not null | |

Not tenant-scoped — it exists before any workspace does. Readable only by the service role.

### `member_invitation` — admits a person to an existing workspace

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK | |
| `tenant_id` | uuid | FK → `tenant.id`, not null | RLS key |
| `email` | text | not null | |
| `role` | enum | not null | Role on acceptance |
| `token_hash` | text | not null, unique | Hash only |
| `invited_by` | uuid | FK → `membership.id`, not null | |
| `expires_at` | timestamptz | not null | Default 7 days |
| `status` | enum | `pending` \| `accepted` \| `revoked` \| `expired` | |
| `created_at` | timestamptz | not null | |

Constraint: **partial unique** `(tenant_id, lower(email)) where status = 'pending'` — one open invitation per address per workspace.

### `audit_event` — append-only security and membership history

| Field | Type | Constraints | Notes |
|---|---|---|---|
| `id` | bigserial | PK | |
| `tenant_id` | uuid | FK → `tenant.id`, nullable | Null for pre-workspace events |
| `actor_membership_id` | uuid | nullable | Null for anonymous or system actors |
| `actor_email` | text | nullable | Preserved even if the membership is later removed |
| `action` | text | not null | e.g. `member.invited`, `auth.failed`, `tenant.created` |
| `target` | jsonb | nullable | What was acted on |
| `outcome` | enum | `success` \| `refused` | Refusals are evidence (FR-006) |
| `trace_id` | text | nullable | Correlates with the error envelope |
| `occurred_at` | timestamptz | not null, default `now()` | |

**Append-only by policy**: `INSERT` permitted, `UPDATE` and `DELETE` denied to every role
including service. This establishes the event-sourced pattern Principle II requires of outcome
data later, at zero cost now. Credentials are never written here (FR-006).

### Reference tables — `supported_region`, `supported_currency`, `supported_tax_model`

| Field | Type | Notes |
|---|---|---|
| `code` | text PK | e.g. `GB`, `GBP`, `uk_vat_standard` |
| `label_en` / `label_ar` | text | Display names |
| `is_enabled` | boolean | Widen the supported set by flipping a flag, not by migrating (FR-032) |

Global, not tenant-scoped: readable by any authenticated user, writable only by service role.

---

## Relationships

```text
platform_invitation 1──1 tenant          (a spent invitation produced exactly one workspace)
tenant              1──* membership      (a workspace has many members)
tenant              1──* member_invitation
tenant              1──* audit_event
auth.users          1──* membership      (one person, many workspaces, one active)
membership          1──* member_invitation  (as inviter)
supported_region    1──* tenant
supported_currency  1──* tenant
supported_tax_model 1──* tenant
```

---

## Row-Level Security

Every table above except `platform_invitation` and the reference tables carries RLS with both
`ENABLE` and `FORCE` (R4).

| Table | Policy |
|---|---|
| `tenant` | `id = (auth.jwt() ->> 'tenant_id')::uuid` |
| `membership` | `tenant_id = (auth.jwt() ->> 'tenant_id')::uuid` |
| `member_invitation` | `tenant_id = (auth.jwt() ->> 'tenant_id')::uuid` |
| `audit_event` | `SELECT`: same claim comparison. `INSERT`: same. `UPDATE`/`DELETE`: no policy — denied to all. |
| `platform_invitation` | No policy; service role only. Never reachable from an authenticated request. |
| `supported_*` | `SELECT` to `authenticated`; writes to service role only. |

Each policy supplies **both** `USING` and `WITH CHECK`. A `USING`-only policy would let a member
write a row into another workspace while being unable to read it back — a silent corruption path.

---

## State transitions

**`platform_invitation`**: `pending` → `spent` (workspace created) · `pending` → `revoked`
(team action) · `pending` → `expired` (time). Terminal states are final; a spent invitation
cannot create a second workspace.

**`member_invitation`**: `pending` → `accepted` · `pending` → `revoked` · `pending` → `expired`.
Acceptance is idempotent: a second acceptance of the same invitation is a no-op returning the
existing membership, never a duplicate (edge case: concurrent acceptance).

**`membership.status`**: `active` → `removed`. Reversal requires a fresh invitation, so
re-admission is always an auditable act. A removed membership must fail authorisation on the
next request, not at token expiry (edge case: session outliving membership) — enforced by
checking membership status on each request in addition to the JWT claim.

---

## Validation rules (traced to requirements)

| Rule | Source |
|---|---|
| `slug` unique across all workspaces, immutable after creation | FR-001 |
| Every tenant-scoped row carries a non-null `tenant_id` | FR-002 |
| `region`, `currency`, `tax_model` required at creation, no default applied | FR-031 |
| All three validated against `is_enabled` reference rows | FR-032 |
| Workspace creation requires a `pending`, unexpired platform invitation | FR-033 |
| Exactly one role per membership | FR-008 |
| A workspace always retains ≥1 active owner (trigger-enforced) | FR-012 |
| Invitations expire; expired ones cannot be accepted | FR-010 |
| Every monetary value stores an explicit currency | FR-020, Principle VII |
| Cross-workspace reads return "not found", never "forbidden" | FR-005 |

---

## Notes for later chunks

- No monetary columns exist yet. The shared `Money` type (amount + currency, never a bare
  number) belongs in `packages/domain-types` **before** chunk 4.2 stores its first price.
- `pgvector` and `pg_trgm` are enabled by the foundation migration but unused until 4.3/4.4.
- The bitemporal pattern Principle II requires (valid-time + record-time) does not apply to any
  table here; `audit_event`'s append-only policy is the pattern's first instance.

# ProcurePilot — Data Dictionary

> Field-level definitions for the core domain entities.

Foundation tables in this section reflect the SQL that is applied from
`supabase/migrations/`. Entities for later chunks are marked as planned and are not present in
the current foundation migrations.

---

## Implemented foundation entities

## `Tenant`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `name` | text | Business name; required, 1-200 characters |
| `slug` | text | Unique subdomain identifier; lowercase letters, digits, and hyphens |
| `region` | text | Required FK -> `supported_region.code`; collected at sign-up |
| `currency` | text | Required FK -> `supported_currency.code`; no default |
| `tax_model` | text | Required FK -> `supported_tax_model.code`; no default |
| `default_locale` | text | Required workspace fallback locale; `en` or `ar`, default `en` |
| `platform_invitation_id` | uuid | Required unique FK -> `platform_invitation.id`; invitation that produced the workspace |
| `created_at` | timestamptz | Audit field |

`Tenant` is protected by RLS, but it is not keyed by `tenant_id`; its policy compares `id` to the
verified JWT tenant claim.

## `User` / `Membership`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `user_id` | uuid | Required FK -> `auth.users.id`; Supabase Auth identity |
| `email` | text | Required denormalised email for display and invitation matching |
| `role` | enum | owner, buyer, branch_manager, approver, viewer |
| `mfa_enabled` | boolean | MFA status |
| `preferred_locale` | text | Optional user locale override; `en` or `ar` |
| `is_active_workspace` | boolean | Whether this membership supplies the active JWT tenant claim; default `false` |
| `status` | enum | `active` or `removed`; default `active` |
| `created_at` | timestamptz | Audit field |

Constraints:

- Unique `(tenant_id, user_id)`: one membership per person per workspace.
- Partial unique `(user_id) where is_active_workspace`: at most one active workspace flag per
  person.
- Multiple owners are allowed. The database trigger refuses updates/deletes that would leave a
  workspace with no active owner.

## `PlatformInvitation`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `email` | text | Required intended recipient |
| `token_hash` | text | Required, unique; only the token hash is stored |
| `expires_at` | timestamptz | Required expiry timestamp |
| `status` | enum | `pending`, `spent`, `revoked`, or `expired`; default `pending` |
| `spent_at` | timestamptz | Required exactly when `status = 'spent'`; otherwise null |
| `created_at` | timestamptz | Audit field |

`PlatformInvitation` is not tenant-scoped because it exists before a workspace exists. RLS is
enabled and forced with no authenticated policy; the service role is the operational path.

Indexes and checks:

- Unique `token_hash`.
- Index on `lower(email)`.
- Partial index on pending `status`.
- Check constraint keeps `spent_at` consistent with `status = 'spent'`.

## `MemberInvitation`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `email` | text | Required invited address |
| `role` | enum | Required role assigned on acceptance |
| `token_hash` | text | Required, unique; only the token hash is stored |
| `invited_by` | uuid | Required FK -> `membership.id` |
| `expires_at` | timestamptz | Required expiry timestamp |
| `status` | enum | `pending`, `accepted`, `revoked`, or `expired`; default `pending` |
| `created_at` | timestamptz | Audit field |

Constraints and access:

- Unique `token_hash`.
- Partial unique `(tenant_id, lower(email)) where status = 'pending'`: one open invitation per
  address per workspace.
- RLS is enabled and forced with tenant-claim `USING` and `WITH CHECK` policies.
- Acceptance and token lookup use security-definer functions because an invitee may not yet hold
  a tenant claim for the target workspace.

## `AuditEvent`

| Field | Type | Notes |
|---|---|---|
| `id` | bigint | PK, generated always as identity |
| `tenant_id` | uuid | Nullable FK -> Tenant; null for pre-workspace events |
| `actor_membership_id` | uuid | Nullable FK -> Membership; set null if membership is deleted |
| `actor_email` | text | Optional preserved actor email |
| `action` | text | Required action name, for example `member.invited`, `auth.failed`, `tenant.created` |
| `target` | jsonb | Optional target payload |
| `outcome` | enum | Required; `success` or `refused` |
| `trace_id` | text | Optional correlation id matching the error envelope |
| `occurred_at` | timestamptz | Required occurrence timestamp; default `now()` |

`AuditEvent` is append-only. Authenticated users can select and insert tenant-scoped rows through
RLS; no update or delete policy exists, update/delete privileges are revoked, and the service role
is granted only select/insert. Pre-authentication or refused events are written through the
`record_audit_event` security-definer function.

Indexes:

- `(tenant_id, occurred_at desc)` for workspace history.
- `(action)` for action filtering.

## Planned later domain entities

## `Branch` / `CostCentre`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `name` | text | |
| `code` | text | Short code for requests |
| `parent_id` | uuid | Optional hierarchy |

## `CanonicalProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `brand` | text | Normalised brand name |
| `name` | text | Base product name |
| `variant` | text | Variant (e.g., unscented) |
| `gtin` | text | Global trade item number |
| `base_unit` | text | e.g. litre, kg, each |
| `created_at` | timestamptz | |

## `TenantProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `canonical_product_id` | uuid | FK → CanonicalProduct |
| `tenant_name` | text | Name used inside this tenant |
| `preferred_supplier_id` | uuid | FK → Supplier |
| `substitute_ids` | uuid[] | Approved substitutes |

## `Unit` / `PackDefinition`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_product_id` | uuid | FK |
| `pack_count` | integer | e.g. 6 |
| `unit_size` | decimal | e.g. 5.0 |
| `base_quantity` | decimal | `pack_count × unit_size` |

## `Supplier`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `name` | text | |
| `payment_terms` | text | e.g. Net 30 |
| `lead_time_days` | integer | |
| `minimum_order_value` | money | |
| `delivery_fee` | money | |
| `reliability_score` | decimal | 0–1, computed |
| `status` | enum | active, blocked, preferred |

## `Document`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `storage_uri` | text | Supabase Storage path |
| `mime_type` | text | |
| `hash` | text | SHA-256 for caching |
| `source_channel` | enum | upload, email, api |
| `created_at` | timestamptz | |

## `Quotation`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `document_id` | uuid | FK → Document |
| `supplier_id` | uuid | FK → Supplier |
| `currency` | text | |
| `issue_date` | date | |
| `expiry_date` | date | |
| `status` | enum | pending, extracted, reviewed, accepted |

## `QuotationLine`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `quotation_id` | uuid | FK → Quotation |
| `original_text` | text | Raw extracted description |
| `supplier_sku` | text | |
| `quantity` | decimal | |
| `unit_price` | money | |
| `vat_rate` | decimal | |
| `delivery_fee` | money | |
| `discount` | money | |
| `confidence` | decimal | 0–1 per field aggregate |

## `SupplierOffer`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `tenant_product_id` | uuid | FK → TenantProduct |
| `quotation_line_id` | uuid | FK → QuotationLine |
| `landed_cost` | money | Computed total |
| `valid_from` | timestamptz | |
| `valid_to` | timestamptz | |
| `recorded_at` | timestamptz | Bitemporal record time |

## `SavingRecord`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `tenant_product_id` | uuid | FK |
| `baseline_policy` | text | e.g. last_paid, rolling_avg |
| `baseline_value` | money | |
| `actual_value` | money | |
| `delta` | money | Verified saving |
| `verified_at` | timestamptz | Immutable after verify |

## `PurchaseRequest`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `branch_id` | uuid | FK → Branch |
| `cost_centre_id` | uuid | FK → CostCentre |
| `requested_by` | uuid | FK → User |
| `required_by_date` | date | |
| `status` | enum | draft, submitted, approved, rejected, ordered |

## `ApprovalStep`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `request_id` | uuid | FK → PurchaseRequest |
| `approver_id` | uuid | FK → User |
| `threshold_rule_id` | uuid | FK → PolicyRule |
| `status` | enum | pending, approved, rejected, escalated |
| `comment` | text | |
| `decided_at` | timestamptz | |

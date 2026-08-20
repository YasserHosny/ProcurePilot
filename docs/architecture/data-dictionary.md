# ProcurePilot — Data Dictionary

> Field-level definitions for the core domain entities.

Implemented tables in this section reflect the SQL that is applied from `supabase/migrations/`.
Entities for later chunks are marked as planned and are not present in the current migrations.

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

## Implemented catalogue and supplier entities

## `SupportedBaseUnit`

| Field | Type | Notes |
|---|---|---|
| `code` | text | PK; one of `litre`, `millilitre`, `kilogram`, `gram`, or `each` |
| `label_en` | text | English display name |
| `label_ar` | text | Arabic display name |
| `dimension` | enum | `volume`, `mass`, or `count`; only same-dimension units are comparable |
| `is_enabled` | boolean | Whether the unit is available for product creation |

`supported_base_unit` is global reference data, not tenant-scoped. It is readable by authenticated
users and writable by the service role only.

## `CanonicalProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `brand` | text | Optional normalised brand name |
| `name` | text | Required base product name |
| `variant` | text | Optional variant, for example `unscented` |
| `gtin` | text | Optional global trade item number; unique where present and shape-validated |
| `base_unit` | text | Required FK -> `supported_base_unit.code` |
| `created_at` | timestamptz | Audit field |

`CanonicalProduct` is the deliberate asymmetry in this chunk: it has no `tenant_id` because it is
the shared product spine across workspaces. It must not contain workspace-specific names,
suppliers, substitutes, or preferences. RLS allows authenticated reads; application writes happen
through the product creation path that also creates the workspace-scoped overlay.

## `WorkspaceProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `canonical_product_id` | uuid | Required FK -> CanonicalProduct |
| `tenant_name` | text | Required name used inside this workspace |
| `preferred_supplier_id` | uuid | Optional FK -> Supplier |
| `status` | enum | `active` or `archived`; default `active` |
| `created_at` | timestamptz | Audit field |

Constraints:

- Unique `(tenant_id, canonical_product_id)`: one workspace view per canonical product.
- Duplicate `tenant_name` values are allowed inside a workspace; the application warns instead of
  refusing them.

## `PackDefinition`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key, denormalised so policies do not need a join |
| `workspace_product_id` | uuid | Required FK -> WorkspaceProduct |
| `pack_count` | integer | Required; check `> 0` |
| `unit_size` | numeric(18,6) | Required; check `> 0` |
| `base_quantity` | numeric(18,6) | Generated always as `pack_count * unit_size`, stored |
| `created_at` | timestamptz | Audit field |

`base_quantity` is generated by the database and cannot be written independently. Numeric types are
used instead of floating point because landed-cost comparison depends on exact pack arithmetic.

## `ProductSubstitute`

| Field | Type | Notes |
|---|---|---|
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `workspace_product_id` | uuid | Required FK -> WorkspaceProduct |
| `substitute_product_id` | uuid | Required FK -> WorkspaceProduct |

Constraints:

- PK `(tenant_id, workspace_product_id, substitute_product_id)`.
- Check `workspace_product_id <> substitute_product_id`: a product cannot be its own substitute.

## `Supplier`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `name` | text | Required supplier name |
| `payment_terms` | text | Optional terms, for example `Net 30` |
| `lead_time_days` | integer | Optional; check `>= 0` |
| `minimum_order_value_amount` | numeric(18,4) | Optional monetary amount |
| `minimum_order_value_currency` | text | Optional FK -> `supported_currency.code`; required exactly when amount is present |
| `delivery_fee_amount` | numeric(18,4) | Optional monetary amount |
| `delivery_fee_currency` | text | Optional FK -> `supported_currency.code`; required exactly when amount is present |
| `reliability_score` | numeric(4,3) | Optional 0-1 score; computed in a later chunk |
| `status` | enum | `active`, `preferred`, `blocked`, or `archived` |
| `created_at` | timestamptz | Audit field |

Money is stored as amount/currency pairs. Check constraints reject an amount without a currency and
a currency without an amount; no conversion is performed.

## `ProductAlias`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `workspace_product_id` | uuid | Required FK -> WorkspaceProduct |
| `supplier_id` | uuid | Optional FK -> Supplier; the supplier whose wording this is |
| `alias_text` | text | Required supplier or workspace wording |
| `created_by` | uuid | FK -> Membership; the human who confirmed the alias |
| `created_at` | timestamptz | Audit field |

Constraint: unique `(tenant_id, lower(alias_text))`, so one wording has one meaning inside a
workspace. Aliases are tenant-private.

## `ImportJob`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `kind` | enum | `products` or `suppliers` |
| `filename` | text | Required uploaded filename |
| `status` | enum | `validating`, `previewed`, `committed`, or `refused` |
| `row_count` | integer | Number of rows read |
| `error_report` | jsonb | `{errors, duplicates, file_error, validated_report}` — see below |
| `created_by` | uuid | FK -> Membership |
| `created_at` | timestamptz | Audit field |

Import jobs are retained after validation and commit so a bulk catalogue change can be explained
after the fact, including the line numbers that were refused.

`error_report` also holds the validated report (`validated_report`) between preview and commit, not
just errors — there is no separate column for it, so the application layer persists it here rather
than in an in-process cache, which would not survive a restart or a second worker process handling
the commit request. `errors` is the row-level list shaped as `[{line, column, reason}]`; `duplicates`
and `file_error` are the corresponding pieces of `ImportValidationReport`.

All tenant-scoped catalogue tables have RLS enabled and forced with tenant-claim `USING` and
`WITH CHECK` policies. Owner and buyer may mutate catalogue data; branch manager, approver, and
viewer are read-only.

## Planned later domain entities

## `Branch` / `CostCentre`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK -> Tenant |
| `name` | text | |
| `code` | text | Short code for requests |
| `parent_id` | uuid | Optional hierarchy |

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

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
| `canonical_embedding` | vector(256) | Optional semantic vector built only from `brand`, `name`, and `variant` |
| `canonical_embedding_model` | text | Optional model identifier for `canonical_embedding`, for example `stub-hash-v1` |
| `created_at` | timestamptz | Audit field |

`CanonicalProduct` is the deliberate asymmetry in this chunk: it has no `tenant_id` because it is
the shared product spine across workspaces. It must not contain workspace-specific names,
suppliers, substitutes, or preferences. RLS allows authenticated reads; application writes happen
through the product creation path that also creates the workspace-scoped overlay.

`canonical_embedding` is safe to store on the shared spine only because it is derived exclusively
from canonical fields already present on this table. It must not include `tenant_name`, supplier
wording, aliases, preferences, or any other workspace-specific text.

## `WorkspaceProduct`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `canonical_product_id` | uuid | Required FK -> CanonicalProduct |
| `tenant_name` | text | Required name used inside this workspace |
| `preferred_supplier_id` | uuid | Optional FK -> Supplier |
| `status` | enum | `active` or `archived`; default `active` |
| `tenant_name_embedding` | vector(256) | Optional tenant-scoped semantic vector built only from `tenant_name` |
| `tenant_name_embedding_model` | text | Optional model identifier for `tenant_name_embedding`, for example `stub-hash-v1` |
| `created_at` | timestamptz | Audit field |

Constraints:

- Unique `(tenant_id, canonical_product_id)`: one workspace view per canonical product.
- Duplicate `tenant_name` values are allowed inside a workspace; the application warns instead of
  refusing them.

The two embedding columns deliberately stay split. `canonical_product.canonical_embedding` carries
shareable brand/name/variant meaning, while `workspace_product.tenant_name_embedding` carries
workspace vocabulary and remains tenant-scoped under `workspace_product` RLS. Matching combines the
two similarities at query time rather than merging tenant-specific text into the shared
`CanonicalProduct` spine.

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

## Implemented quotation inbox and extraction entities

## `Document`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `storage_bucket` | text | Required Supabase Storage bucket, for example `quotation-documents` |
| `storage_path` | text | Required tenant-prefixed Supabase Storage path; unique |
| `mime_type` | text | Required accepted PDF, image, Excel, or CSV MIME type |
| `content_hash` | text | Optional SHA-256 hash; nullable until upload completes |
| `source_channel` | enum | `upload`; enum leaves room for future `email` and `api` ingestion |
| `status` | enum | `uploaded` or `failed_to_read` |
| `created_at` | timestamptz | Audit field |
| `created_by` | uuid | Required FK -> Membership |

`Document` stores metadata only. The file bytes live in a private Supabase Storage bucket and are
protected by both Postgres RLS on this row and Storage bucket policy on `storage_path`; a readable
row never implies a public object URL.

Constraints:

- Unique `storage_path`, plus unique `(tenant_id, storage_path)` for defensive lookup.
- Check `storage_path like 'tenants/%/quotations/%'`; the path is allocated from the verified
  tenant claim, not client input.
- Duplicate `content_hash` values are allowed in this chunk. Duplicate detection and merging are
  explicitly out of scope.

## `Quotation`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `document_id` | uuid | Required FK -> Document |
| `supplier_id` | uuid | Optional FK -> Supplier; reviewer confirms before final review |
| `currency` | text | Optional FK -> `supported_currency.code`; nullable until extracted or reviewed |
| `issue_date` | date | Optional quotation issue date |
| `expiry_date` | date | Optional quotation expiry date |
| `status` | enum | `pending`, `extracting`, `extracted`, `in_review`, `reviewed`, or `refused` |
| `previous_quotation_id` | uuid | Optional FK -> Quotation; links a supplier re-quote without replacing history |
| `stated_total_amount` | numeric(18,4) | Optional stated quotation total amount |
| `stated_total_currency` | text | Optional FK -> `supported_currency.code`; required exactly when amount is present |
| `arithmetic_status` | enum | Optional `not_applicable`, `reconciled`, or `mismatch` |
| `created_at` | timestamptz | Audit field |
| `reviewed_by` | uuid | Optional FK -> Membership |
| `reviewed_at` | timestamptz | Optional review timestamp |

`reviewed` is the only trusted state for downstream commercial data. `extracted` means automation
completed; it does not mean the quotation may be used for matching, comparison, or savings.

Constraints:

- Check `expiry_date is null or issue_date is null or expiry_date >= issue_date`.
- Check `previous_quotation_id is null or previous_quotation_id <> id`.
- Check `(stated_total_amount is null) = (stated_total_currency is null)`.
- `supplier_id` may remain null until review; confirmation refuses while it is null.
- `reviewed_by` and `reviewed_at` are both present or both absent.

State transitions:

```text
pending -> extracting -> extracted -> in_review -> reviewed
pending -> extracting -> refused
pending -> refused
extracted -> reviewed
```

## `QuotationLine`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_id` | uuid | Required FK -> Quotation |
| `line_number` | integer | Required line number; check `> 0` |
| `original_text` | text | Required raw extracted line description |
| `quantity` | numeric(18,6) | Optional until extracted or corrected; check `> 0` when present |
| `pack_count` | integer | Optional pack count; check `> 0` when present |
| `unit_size` | numeric(18,6) | Optional pack unit size; check `> 0` when present |
| `pack_unit` | text | Optional FK -> `supported_base_unit.code` where applicable |
| `unit_price_amount` | numeric(18,4) | Optional unit price amount |
| `unit_price_currency` | text | Optional FK -> `supported_currency.code`; required exactly when amount is present |
| `vat_rate` | numeric(5,4) | Optional VAT rate; check between 0 and 1 |
| `delivery_fee_amount` | numeric(18,4) | Optional delivery fee amount |
| `delivery_fee_currency` | text | Optional FK -> `supported_currency.code`; required exactly when amount is present |
| `discount_amount` | numeric(18,4) | Optional discount amount |
| `discount_currency` | text | Optional FK -> `supported_currency.code`; required exactly when amount is present |
| `created_at` | timestamptz | Audit field |

Money is stored as amount/currency pairs and exposed by the API as `Money { amount, currency }`.
Check constraints reject an amount without a currency and a currency without an amount; no money
field is a bare number.

Constraints:

- Unique `(tenant_id, quotation_id, line_number)`.
- Check `(unit_price_amount is null) = (unit_price_currency is null)`.
- Check `(delivery_fee_amount is null) = (delivery_fee_currency is null)`.
- Check `(discount_amount is null) = (discount_currency is null)`.
- Check `(pack_count is null) = (unit_size is null)`.
- `pack_unit` may be null for free-text pack descriptions the reviewer has not normalised yet.

## `FieldExtraction`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_id` | uuid | Required FK -> Quotation |
| `entity_type` | enum | `quotation` or `quotation_line` |
| `entity_id` | uuid | Required polymorphic target id for the quoted `entity_type` |
| `field_name` | text | Required extracted field name, for example `supplier_id`, `currency`, `unit_price`, or `quantity` |
| `extracted_value` | jsonb | Required original machine/structured value |
| `confidence` | numeric(5,4) | Required confidence score; check `0 <= confidence <= 1` |
| `source_page` | integer | Optional source page; check `> 0` when present |
| `source_region` | jsonb | Optional page-relative bounding box or polygon |
| `extraction_method` | enum | `structured_parse`, `bedrock`, or `azure_di` |
| `model_version` | text | Required parser/rule/model version |
| `corrected_value` | jsonb | Optional human-corrected value |
| `corrected_by` | uuid | Optional FK -> Membership |
| `corrected_at` | timestamptz | Optional correction timestamp |
| `created_at` | timestamptz | Audit field |

`FieldExtraction` is the constitutional evidence record for this chunk. Confidence and source
location are deliberately stored per field, not per line and not per quotation, so each extracted
commercial value can be audited independently under Constitution Principle I. Human correction is
distinct from `extracted_value`; review records the decision without overwriting the evidence.

Constraints:

- Unique `(tenant_id, entity_type, entity_id, field_name)`.
- Check `source_region` is null or contains a supported shape (`bbox` or `polygon`) in
  implementation validation.
- Check `corrected_by` and `corrected_at` are both present or both absent.
- `entity_id` cannot be protected by a simple FK because it is polymorphic; writes validate that
  the target entity belongs to the same tenant and quotation in the same transaction.

## `ExtractionJob`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_id` | uuid | Required FK -> Quotation |
| `status` | enum | `queued`, `running`, `succeeded`, or `failed` |
| `attempted_provider` | enum | Optional `structured_parse`, `bedrock`, or `azure_di` |
| `error` | jsonb | Optional tenant-safe code, message, and details |
| `created_at` | timestamptz | Audit field |
| `started_at` | timestamptz | Optional start timestamp |
| `completed_at` | timestamptz | Optional completion timestamp |

`ExtractionJob` is the persisted job resource behind `/jobs/{job_id}`. Redis may deliver work to
the worker, but it is not the source of truth for user-visible state.

Constraints:

- Partial unique `(tenant_id, quotation_id) where status in ('queued', 'running')`: one active
  extraction per quotation.
- `completed_at` is present only for terminal states.

## `ReviewTask`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_id` | uuid | Required FK -> Quotation |
| `status` | enum | `open`, `in_progress`, or `resolved` |
| `priority` | enum | `low`, `normal`, or `high` |
| `reason` | enum | `low_confidence`, `arithmetic_mismatch`, `read_failure`, or `review_required` |
| `created_at` | timestamptz | Audit field |
| `resolved_at` | timestamptz | Optional resolution timestamp |

`ReviewTask` is a standalone review queue resource, not a view over quotations. It exists because
human review has its own state machine, SLA, and metrics under Constitution Principle III.

Constraints:

- Partial unique `(tenant_id, quotation_id) where status in ('open', 'in_progress')`: one
  outstanding task per quotation.
- `resolved_at` is present only when `status = 'resolved'`.

All tenant-scoped quotation inbox tables have RLS enabled and forced with tenant-claim `USING` and
`WITH CHECK` policies. Owner and buyer may upload, extract, correct, and confirm; branch manager,
approver, and viewer are read-only. Cross-tenant reads return not found, never forbidden. `Document`
also requires private Supabase Storage policies that compare the path tenant segment and related
document row to the caller's JWT tenant claim.

## Implemented matching and normalisation entities

## `MatchCandidate`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_line_id` | uuid | Required FK -> QuotationLine |
| `candidate_workspace_product_id` | uuid | Required FK -> WorkspaceProduct proposed for the line |
| `confidence` | numeric(5,4) | Required calibrated confidence score; check `0 <= confidence <= 1` |
| `reasons` | jsonb | Required structured evidence breakdown, not free prose |
| `rank` | integer | Required candidate rank within the line and scoring version; check `> 0` |
| `scoring_version` | text | Required scoring rule identifier, for example `matching-score-v1` |
| `embedding_model` | text | Optional embedding model identifier used for semantic evidence |
| `created_at` | timestamptz | Audit field |

`MatchCandidate` records evidence for a proposed product match. Deterministic matches still create
a candidate row so the system can show confidence and reasons for the result.

Constraints:

- Unique `(tenant_id, quotation_line_id, candidate_workspace_product_id, scoring_version)`: one
  candidate per product per scoring run.
- Unique `(tenant_id, quotation_line_id, scoring_version, rank)`: stable ranks within a line and
  scoring version.
- `reasons` contains deterministic, lexical, semantic, and feature-score signals such as
  `alias_hit`, `gtin_match`, `supplier_code_match`, `lexical_similarity`,
  `semantic_similarity`, and `feature_score`.

## `MatchTask`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_line_id` | uuid | Required FK -> QuotationLine needing human resolution |
| `status` | enum | `open`, `in_progress`, or `resolved`; default `open` |
| `priority` | enum | `low`, `normal`, or `high`; default `normal` |
| `reason` | enum | `low_confidence`, `close_candidates`, `no_candidate`, or `alias_conflict` |
| `created_at` | timestamptz | Audit field |
| `resolved_at` | timestamptz | Optional resolution timestamp |

`MatchTask` is the standalone queue resource for human match resolution. It is not a view over
candidates; task state is separate from candidate evidence and immutable match decisions.

Constraints:

- Partial unique `(tenant_id, quotation_line_id) where status in ('open', 'in_progress')`: one
  outstanding match task per line.
- `resolved_at` is present only when `status = 'resolved'`.

## `MatchDecision`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_line_id` | uuid | Required FK -> QuotationLine |
| `matched_workspace_product_id` | uuid | Required FK -> WorkspaceProduct that the line resolved to |
| `selected_match_candidate_id` | uuid | Optional FK -> MatchCandidate; required unless outcome is `no_match_new_product` |
| `outcome` | enum | `same_product`, `different_pack`, `different_variant`, `compatible_alternative`, or `no_match_new_product` |
| `is_automatic` | boolean | Required; true when the system accepted the match without a human |
| `decided_by` | uuid | Optional FK -> Membership; required for human decisions and null for automatic decisions |
| `decided_at` | timestamptz | Required decision timestamp; default `now()` |
| `confidence` | numeric(5,4) | Required accepted confidence score; check `0 <= confidence <= 1` |
| `alias_id` | uuid | Optional FK -> ProductAlias learned or reused by the decision |
| `created_at` | timestamptz | Audit field |

One decision resolves one quotation line. `no_match_new_product` means no existing product fit and
the newly created workspace product is the match; the line is not left unmatched.

Constraints:

- Unique `(tenant_id, quotation_line_id)`: one final decision per line in this chunk.
- Automatic decisions have no `decided_by`; human decisions must name the deciding membership.
- `selected_match_candidate_id` is null exactly when `outcome = 'no_match_new_product'`.

`MatchDecision` is append-only outcome history for this chunk. Correcting a previously confirmed
match is out of scope and requires a future supersession model, not an update to this row.

Human decisions create or reuse `product_alias` from the exact `quotation_line.original_text`. If
the lowercased wording already exists for the same product, the alias is reused. If it exists for a
different product, the alias write is refused with a conflict and the existing alias is not
overwritten.

## `LandedCost`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `quotation_line_id` | uuid | Required FK -> QuotationLine |
| `match_decision_id` | uuid | Required FK -> MatchDecision |
| `quantity` | numeric(18,6) | Required source line quantity used by the rule; check `> 0` |
| `normalised_base_quantity` | numeric(18,6) | Required quantity normalised to the product base unit; check `> 0` |
| `base_unit` | text | Required FK -> `supported_base_unit.code` |
| `unit_price_amount` | numeric(18,4) | Required unit price amount |
| `unit_price_currency` | text | Required FK -> `supported_currency.code` |
| `vat_amount` | numeric(18,4) | Required VAT amount derived from unit price, quantity, and VAT rate |
| `vat_currency` | text | Required FK -> `supported_currency.code` |
| `delivery_fee_amount` | numeric(18,4) | Required delivery fee amount |
| `delivery_fee_currency` | text | Required FK -> `supported_currency.code` |
| `discount_amount` | numeric(18,4) | Required discount amount |
| `discount_currency` | text | Required FK -> `supported_currency.code` |
| `other_charges_amount` | numeric(18,4) | Required other-charges amount; default `0` in this chunk |
| `other_charges_currency` | text | Required FK -> `supported_currency.code` |
| `total_amount` | numeric(18,4) | Required computed landed-cost total |
| `total_currency` | text | Required FK -> `supported_currency.code` |
| `raw_inputs` | jsonb | Required complete replay snapshot used by the pinned rule version |
| `rule_version` | text | Required landed-cost rule identifier, for example `landed-cost-v1` |
| `valid_from` | timestamptz | Required valid-time start: when the price or cost applies |
| `valid_to` | timestamptz | Optional valid-time end |
| `recorded_at` | timestamptz | Required record-time: when the workspace learned or stored this cost |
| `created_at` | timestamptz | Audit field |

Money follows the established amount/currency pair rule. The API exposes these fields as
`Money { amount, currency }` with amount as a decimal string; there are no bare money numbers.

Constraints:

- Unique `(tenant_id, match_decision_id, rule_version)`: one stored computation per decision and
  rule version in this chunk.
- All currency columns must equal `total_currency`; this chunk performs no currency conversion.
- Check `valid_to is null or valid_to >= valid_from`.

`landed-cost-v1` computes `vat_amount = unit_price_amount * quantity * vat_rate`, then
`total_amount = (unit_price_amount * quantity) + vat_amount + delivery_fee_amount -
discount_amount + 0 other_charges`. Missing `vat_rate` is treated as zero. `other_charges` is
stored as zero because quotation lines do not model it in this chunk.

All tenant-scoped matching and landed-cost tables have RLS enabled and forced with tenant-claim
`USING` and `WITH CHECK` policies. Owner and buyer may resolve matches and create products from
no-match decisions; branch manager, approver, and viewer are read-only. Cross-tenant reads return
not found, never forbidden.

## Planned later domain entities

## `Branch` / `CostCentre`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK -> Tenant |
| `name` | text | |
| `code` | text | Short code for requests |
| `parent_id` | uuid | Optional hierarchy |

## `SupplierOffer`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK → Tenant |
| `workspace_product_id` | uuid | FK → WorkspaceProduct |
| `quotation_line_id` | uuid | FK → QuotationLine |
| `landed_cost_amount` | numeric(18,4) | Computed total amount |
| `landed_cost_currency` | text | FK -> `supported_currency.code`; explicit currency for the computed total |
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

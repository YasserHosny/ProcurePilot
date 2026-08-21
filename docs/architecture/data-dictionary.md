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

## Implemented smart compare and intelligence entities

Smart compare reuses chunk 4.2 catalogue/supplier rows and chunk 4.4 match and landed-cost rows.
It does not introduce a second offer, recommendation, price-history, or alert-condition source of
truth.

## `basket_split_job`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `requested_by` | uuid | Required FK -> Membership that submitted the solve |
| `supplier_ids` | uuid[] | Required exactly two distinct supplier ids |
| `items` | jsonb | Required request snapshot: array of `{workspace_product_id, quantity}` |
| `status` | enum | `queued`, `running`, `completed`, or `failed`; default `queued` |
| `result` | jsonb | Optional completed allocation or infeasible result |
| `error` | jsonb | Optional worker/system failure payload |
| `created_at` | timestamptz | Audit field; default `now()` |
| `started_at` | timestamptz | Optional worker start timestamp |
| `completed_at` | timestamptz | Required exactly for terminal `completed` or `failed` jobs |

Constraints and indexes:

- Check `cardinality(supplier_ids) = 2 and supplier_ids[1] <> supplier_ids[2]`: this chunk is
  exactly a two-supplier solve, and the two ids must be distinct.
- Check `(status in ('completed', 'failed')) = (completed_at is not null)`: terminal jobs carry a
  completion timestamp; queued/running jobs do not.
- Indexes on `tenant_id` and `requested_by`.
- Postgres cannot enforce an FK over `supplier_ids`; the application validates both suppliers are
  visible in the caller's tenant before insert.

`result` uses JSON because the optimiser returns a structured solve snapshot rather than a single
scalar. The completed shape is:

- `feasible`: boolean.
- `allocation`: array of per-supplier allocation objects.
- `total_landed_cost`: `Money { amount, currency }` or null.
- `single_supplier_baselines`: array comparing all-items-with-one-supplier totals where available.
- `infeasible_items`: array of `{workspace_product_id, requested_quantity, reason,
  missing_supplier_ids}` blockers.
- `solver_version`: optimiser version string.
- `computed_at`: solve timestamp.

An infeasible commercial outcome is `status = 'completed'` with `result.feasible = false`.
`status = 'failed'` is reserved for worker, database, queue, or unexpected solver failures and is
described by `error`.

## `alert_dismissal`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `alert_fingerprint` | text | Required deterministic alert id from the live condition |
| `kind` | text | Required alert kind at dismissal time |
| `workspace_product_id` | uuid | Required FK -> WorkspaceProduct concerned by the alert |
| `supplier_id` | uuid | Optional FK -> Supplier concerned by the alert |
| `dismissed_by` | uuid | Required FK -> Membership that dismissed the alert |
| `dismissed_at` | timestamptz | Audit field; default `now()` |

Constraints and indexes:

- Unique `(tenant_id, alert_fingerprint)`: one dismissal per exact live-computed alert recurrence.
- Index `(tenant_id, kind, workspace_product_id)`.

`alert_dismissal` stores only the dismissal fingerprint. Alert conditions themselves are never
persisted: `GET /alerts` recomputes conditions from current `workspace_product`, `supplier`,
`match_decision`, and `landed_cost` data on every request, then filters out matching dismissed
fingerprints. If the underlying condition changes, its fingerprint changes and the alert can appear
again.

All tenant-scoped smart compare tables have RLS enabled and forced with tenant-claim `USING` and
`WITH CHECK` policies. Owner and buyer may submit basket split jobs and dismiss alerts; branch
manager, approver, and viewer are read-only. Cross-tenant reads return not found, never forbidden.

## Response-only smart compare entities

These entities are API response shapes only. They are computed at request time from existing
chunk 4.2/4.4 data, especially `workspace_product`, `supplier`, `match_decision`, and
`landed_cost`; they are not tables and must not be treated as a new source of truth.

## `Offer`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Stable response id; current `landed_cost.id` |
| `workspace_product_id` | uuid | Matched product id from `match_decision.matched_workspace_product_id` |
| `supplier_id` | uuid | Supplier reached through `quotation_line` -> `quotation` |
| `supplier_name` | text | Supplier display name |
| `quotation_line_id` | uuid | Source quotation line |
| `match_decision_id` | uuid | Source accepted match decision |
| `landed_cost` | Money | Projected total for the requested quantity, using chunk 4.4 replay inputs and rule version |
| `normalised_unit_price` | Money | Projected total divided by requested base quantity |
| `requested_quantity` | decimal string | Caller-supplied quantity |
| `base_unit` | text | Product base unit from landed-cost normalisation |
| `lead_time_days` | integer | Optional supplier-level lead time |
| `reliability_score` | decimal string | Optional supplier-level 0-1 reliability score |
| `stock_signal` | enum | Nullable; always null in this chunk because no stock source exists |
| `match_confidence` | decimal string | Accepted `match_decision.confidence` |
| `valid_from` | timestamptz | Source landed-cost validity start |
| `valid_to` | timestamptz | Optional source landed-cost validity end |
| `is_expired` | boolean | True when `valid_to` is before request time |
| `rule_version` | text | Source landed-cost rule version |
| `recorded_at` | timestamptz | Source landed-cost record time |

`Offer` reuses reviewed quotations, accepted match decisions, and stored landed-cost replay inputs.
It does not persist a second landed-cost row and does not reimplement landed-cost rules.

## `Recommendation`

| Field | Type | Notes |
|---|---|---|
| `recommended_offer_id` | uuid | Selected offer id from the same response |
| `score` | decimal string | Weighted deterministic score rounded to 4 decimals |
| `confidence` | enum | `high`, `medium`, or `low` |
| `valid_from` | timestamptz | Recommended offer validity start |
| `valid_to` | timestamptz | Optional recommended offer validity end |
| `risk_notes` | text[] | Fixed risk codes such as `price_expiring_soon` |
| `evidence` | json object | Score weights, score components, winning margin, and tie-break evidence |

`Recommendation` is computed for one product and requested quantity. It is not stored as a buyer
decision; durable outcome and savings records are a later chunk.

## `PriceHistoryPoint`

| Field | Type | Notes |
|---|---|---|
| `landed_cost_id` | uuid | Source landed-cost row |
| `workspace_product_id` | uuid | Matched product id |
| `supplier_id` | uuid | Supplier reached through quotation joins |
| `supplier_name` | text | Supplier display name |
| `recorded_at` | timestamptz | Record-time x-axis |
| `valid_from` | timestamptz | Price valid-time start |
| `valid_to` | timestamptz | Optional price valid-time end |
| `normalised_unit_price` | Money | `landed_cost.total_amount / landed_cost.normalised_base_quantity` |
| `landed_cost_total` | Money | Source `landed_cost.total_amount/total_currency` |
| `quantity` | decimal string | Source landed-cost quantity |
| `base_unit` | text | Source landed-cost base unit |

`PriceHistoryPoint` is derived entirely from historical `landed_cost` rows and related joins.
It is not a separate purchase ledger.

## `Alert`

| Field | Type | Notes |
|---|---|---|
| `id` | text | Deterministic alert fingerprint |
| `kind` | enum | `recommended_price_expiring`, `preferred_supplier_offer_disappeared`, or `price_swing` |
| `workspace_product_id` | uuid | Product concerned |
| `supplier_id` | uuid | Optional supplier concerned |
| `severity` | enum | `info`, `warning`, or `critical` |
| `evidence` | json object | Current condition facts only |
| `action` | enum | `compare_product`, `review_supplier`, or `view_price_history` |
| `created_from_current_data_at` | timestamptz | Request evaluation timestamp, not a persisted condition timestamp |
| `dismissed` | boolean | False in alert listings; dismissal responses identify the dismissed fingerprint |

`Alert` conditions are live-computed and suppressed by `alert_dismissal` fingerprints. The
conditions themselves are not persisted, so resolved or changed conditions do not leave stale inbox
rows behind.

## Implemented value proof and launch-readiness entities

## `PurchaseRecord`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `workspace_product_id` | uuid | Required FK -> WorkspaceProduct |
| `supplier_id` | uuid | Optional FK -> Supplier; nullable when no supplier row exists |
| `quotation_line_id` | uuid | Optional FK -> QuotationLine; evidence link when the purchase followed a quoted line |
| `match_decision_id` | uuid | Optional FK -> MatchDecision; evidence link when the purchase followed a confirmed match |
| `landed_cost_id` | uuid | Optional FK -> LandedCost; evidence link to the compared offer when present |
| `recorded_by` | uuid | Required FK -> Membership; human who recorded the outcome |
| `quantity` | numeric(18,6) | Required actual ordered quantity; check `> 0` |
| `base_unit` | text | Required FK -> `supported_base_unit.code` |
| `unit_price_amount` | numeric(18,4) | Required actual paid unit price |
| `unit_price_currency` | text | Required FK -> `supported_currency.code` |
| `total_paid_amount` | numeric(18,4) | Required actual total paid |
| `total_paid_currency` | text | Required FK -> `supported_currency.code` |
| `delivery_result` | enum | `ordered`, `partially_delivered`, `delivered`, `cancelled`, or `disputed` |
| `ordered_at` | timestamptz | Optional real-world order time |
| `delivered_at` | timestamptz | Optional real-world delivery time |
| `recorded_at` | timestamptz | Required outcome record time; default `now()` |
| `notes` | text | Optional internal note; not a substitute for evidence links |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

Money is stored as amount/currency pairs. `unit_price_currency` must equal `total_paid_currency`;
Phase 1 performs no currency conversion. `delivered_at` cannot be before `ordered_at` when both are
known.

`PurchaseRecord` is tenant-scoped with forced RLS. Owner and buyer may record outcomes through the
API; branch manager, approver, and viewer are read-only. After the paired `SavingRecord` is
verified, the database trigger `purchase_record_locked_by_verified_saving` refuses update or delete
of the purchase evidence row.

## `SavingRecord`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `purchase_record_id` | uuid | Required unique FK -> PurchaseRecord |
| `workspace_product_id` | uuid | Required FK -> WorkspaceProduct; copied for filtering and ledger display |
| `supplier_id` | uuid | Optional FK -> Supplier; copied from the purchase record |
| `status` | enum | `pending` or `verified`; default `pending` |
| `baseline_policy` | enum | `last_paid`, `rolling_average_6m`, or `none_available`; actual policy used at record time |
| `baseline_source_landed_cost_ids` | uuid[] | Source landed-cost rows from the price-history summary; empty only when no baseline exists |
| `baseline_unit_price_amount` | numeric(18,4) | Optional normalised unit baseline amount |
| `baseline_unit_price_currency` | text | Optional FK -> `supported_currency.code`; required with `baseline_unit_price_amount` |
| `baseline_value_amount` | numeric(18,4) | Optional baseline unit price multiplied by recorded quantity |
| `baseline_value_currency` | text | Optional FK -> `supported_currency.code`; required with `baseline_value_amount` |
| `actual_value_amount` | numeric(18,4) | Required copied `purchase_record.total_paid_amount` |
| `actual_value_currency` | text | Required FK -> `supported_currency.code` |
| `delta_amount` | numeric(18,4) | Optional signed saving, `baseline_value - actual_value`; positive, zero, and negative values are valid |
| `delta_currency` | text | Optional FK -> `supported_currency.code`; required with `delta_amount` |
| `calculation_version` | text | Required calculation identifier, for example `saving-baseline-v1` |
| `calculation_inputs` | jsonb | Required replay snapshot: quantity, selected policy, source point ids, window months, and actual total |
| `recorded_by` | uuid | Required FK -> Membership; copied from the purchase record |
| `recorded_at` | timestamptz | Required time the baseline, actual, and delta were captured |
| `verified_by` | uuid | Optional FK -> Membership; set only by explicit verification |
| `verified_at` | timestamptz | Optional verification timestamp; set only by explicit verification |
| `created_at` | timestamptz | Audit field |

`SavingRecord` captures `baseline_policy`, baseline money, actual money, delta money, and calculation
inputs at purchase-record time from chunk 4.5's price-history read model. Verification is a later
explicit human action and does not re-read price history or recompute any money value.

Baseline and delta money fields are nullable only when `baseline_policy = 'none_available'`.
Whenever a baseline exists, baseline, actual, and delta currencies must match. Verified metadata is
consistent by constraint: `status = 'verified'` exactly when both `verified_at` and `verified_by`
are present.

`SavingRecord` is tenant-scoped with forced RLS. Active roles may read; owner and buyer may create
pending rows and verify them through the API. The database trigger
`saving_record_verified_immutability` refuses update or delete once `status = 'verified'`, for any
role. Verification is the final allowed mutation and changes only `status`, `verified_at`, and
`verified_by`.

## `ExportJob`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `requested_by` | uuid | Required FK -> Membership |
| `kind` | text | Const-like value `savings_ledger` for chunk 4.6 |
| `format` | enum | `xlsx` or `pdf` |
| `filters` | jsonb | Required export filters: `period_start`, `period_end`, optional `supplier_id`, optional `branch_id` |
| `status` | enum | `queued`, `running`, `completed`, or `failed`; default `queued` |
| `storage_bucket` | text | Optional storage bucket set when completed |
| `storage_path` | text | Optional storage path set when completed |
| `download_url` | text | Optional signed URL or API download URL |
| `row_count` | integer | Optional number of verified savings rendered; zero is valid |
| `error` | jsonb | Optional structured failure details for failed jobs |
| `created_at` | timestamptz | Job creation time |
| `started_at` | timestamptz | Optional worker start time |
| `completed_at` | timestamptz | Required for completed or failed jobs |

`ExportJob` is the durable polling resource for savings-ledger exports. Only verified savings are
rendered; an empty export is represented by `row_count = 0`, not a failed job. Completed jobs must
carry storage metadata and `row_count`; failed jobs must carry structured `error` details.

`ExportJob` is tenant-scoped with forced RLS. Owner and buyer may request exports through the API;
active workspace roles may read export status for jobs in their workspace.

## `Plan`

| Field | Type | Notes |
|---|---|---|
| `code` | text | PK, for example `starter` or `growth` |
| `name` | text | Plan name source value; UI strings still come from `packages/i18n` |
| `status` | enum | `active` or `archived`; default `active` |
| `monthly_price_amount` | numeric(18,4) | Required monthly price amount; seeded as `0.0000` for stub plans |
| `monthly_price_currency` | text | Required FK -> `supported_currency.code` |
| `limits` | jsonb | Required plan limits, including `active_catalogue_products` |
| `features` | jsonb | Required feature flags or included capabilities for display |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

Seeded plans are `starter` with `active_catalogue_products = 100` and `growth` with
`active_catalogue_products = 1000`; both are `0.0000 GBP` while the stub billing provider is in
use.

`Plan` is a deliberate shared reference table exception. It has no `tenant_id` because it contains
only global product-tier definitions and no workspace-specific data. It mirrors
`CanonicalProduct`: authenticated users may select rows, authenticated users have no insert,
update, or delete policy, and the service role seeds and updates plan definitions.

## `BillingAccount`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required unique FK -> Tenant; RLS key |
| `plan_code` | text | Required FK -> Plan |
| `provider` | text | Required billing provider; constrained to `stub` in chunk 4.6 |
| `provider_customer_id` | text | Required provider customer reference, for example `stub_customer:{tenant_id}` |
| `provider_subscription_id` | text | Optional provider subscription reference, for example `stub_subscription:{tenant_id}:starter` |
| `status` | enum | `active`, `past_due`, or `cancelled`; default `active` |
| `current_period_start` | timestamptz | Optional current billing period start; nullable for stub |
| `current_period_end` | timestamptz | Optional current billing period end; nullable for stub |
| `assigned_at` | timestamptz | Required plan assignment time; default `now()` |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

`BillingAccount` is the tenant-scoped assignment from a workspace to a shared plan through the
billing-provider abstraction. In chunk 4.6 the provider is stub-only; no real Stripe SDK,
credentials, payment collection, or financial transaction exists.

`BillingAccount` is tenant-scoped with forced RLS. Active roles may read their workspace's billing
account and plan. Plan assignment normally happens during workspace creation through the provider
abstraction; future provider changes should populate this table without changing plan-gating reads.

## Planned later domain entities

## `Branch` / `CostCentre`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | FK -> Tenant |
| `name` | text | |
| `code` | text | Short code for requests |
| `parent_id` | uuid | Optional hierarchy |

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

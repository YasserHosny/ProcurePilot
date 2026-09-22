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
| `reporting_timezone` | text | Chunk R2.5. IANA timezone name (e.g. `Africa/Cairo`, `UTC`); every scheduled-report window, digest window, and next-run instant for the workspace derives from this. Default `UTC`; owner-only write via `PATCH /api/v1/tenant`, validated as a real IANA name by the API |
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
| `confidence` | numeric(5,4) | Required heuristic match score; check `0 <= confidence <= 1` |
| `reasons` | jsonb | Required structured evidence breakdown, not free prose |
| `rank` | integer | Required candidate rank within the line and scoring version; check `> 0` |
| `scoring_version` | text | Required scoring rule identifier, for example `matching-score-v1` |
| `embedding_model` | text | Optional embedding model identifier used for semantic evidence |
| `created_at` | timestamptz | Audit field |

`MatchCandidate` records evidence for a proposed product match. Deterministic matches still create
a candidate row so the system can show score and reasons for the result; the score ranks and routes
candidates, but is not yet a calibrated statistical probability.

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

## `MatchResolutionIdempotency`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `idempotency_key` | uuid | Required client retry key |
| `quotation_line_id` | uuid | Required FK -> QuotationLine |
| `request_fingerprint` | text | Required SHA-256 hex digest of the canonical request body |
| `match_decision_id` | uuid | Required FK -> MatchDecision created by the original request |
| `created_at` | timestamptz | Audit field |

This append-only mapping backs `POST /quotation-lines/{line_id}/match`. A repeated key with the
same line and request body returns the original match decision. Reusing the key with another line
or request body is a conflict.

Constraints:

- Unique `(tenant_id, idempotency_key)`: one replay result per key in a workspace.
- Unique `(tenant_id, match_decision_id)`: one replay mapping per decision.
- `request_fingerprint` is a 64-character lowercase hexadecimal SHA-256 digest.

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
| `items` | jsonb | Required request snapshot: array of `{workspace_product_id, quantity}`; `quantity` is denominated in the product's normalised base unit, never a count of the supplier's original pack/case (same convention as `Offer.requested_quantity`) |
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
| `requested_quantity` | decimal string | Caller-supplied quantity, denominated in `base_unit` (the product's normalised base unit) — never a supplier pack/case count |
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
| `kind` | text | `savings_ledger`, `spend_by_supplier`, or `alerts_summary` (widened chunk R2.5) |
| `format` | enum | `xlsx`, `pdf`, or `csv` (csv added chunk R2.5) |
| `filters` | jsonb | Required export filters: `period_start`, `period_end`, optional `supplier_id`, optional `branch_id` |
| `status` | enum | `queued`, `running`, `completed`, `failed`, or `expired` (expired added chunk R2.5); default `queued` |
| `storage_bucket` | text | Optional storage bucket set when completed; nulled on purge |
| `storage_path` | text | Optional storage path set when completed; nulled on purge |
| `download_url` | text | Optional signed URL or API download URL; nulled on purge |
| `row_count` | integer | Optional number of rows rendered; zero is valid |
| `error` | jsonb | Optional structured failure details for failed jobs |
| `schedule_id` | uuid | Chunk R2.5. Composite FK -> ReportSchedule `(tenant_id, id)`. Null for on-demand jobs |
| `locale` | text | Chunk R2.5. `en` or `ar`; default `en` |
| `rule_version` | text | Chunk R2.5. Renderer rule version, for replay; default `''` |
| `schedule_snapshot` | jsonb | Chunk R2.5. Immutable copy of the schedule definition (kind, format, filters, weekday, locale, rule version) taken at enqueue time, so replay survives later schedule edits or deletion |
| `expires_at` | timestamptz | Chunk R2.5. Set at completion (`completed_at` + retention window); the purge pass flips `status` to `expired` and clears storage after this instant |
| `created_at` | timestamptz | Job creation time |
| `started_at` | timestamptz | Optional worker start time |
| `completed_at` | timestamptz | Required for completed or failed jobs |

`ExportJob` is the single durable job-and-artifact record for both on-demand exports and
scheduled report runs (chunk R2.5 widened it rather than adding a second table — see
`ReportSchedule` below). An empty export is represented by `row_count = 0`, not a failed job.
Completed jobs must carry storage metadata and `row_count`; failed jobs must carry structured
`error` details; expired jobs have had their storage metadata nulled by the purge pass and are
terminal for downloads.

A partial unique index (`export_job_schedule_period_uidx`) enforces one artifact per
`(tenant_id, schedule_id, filters->>'period_start')` for scheduled jobs only — on-demand jobs
(`schedule_id` null) are excluded on purpose; concurrent equivalent on-demand requests are not
de-duplicated.

`ExportJob` is tenant-scoped with forced RLS. Owner and buyer may request exports through the API;
active workspace roles may read export status for jobs in their workspace. Rendered artifacts land
in the `exports` Supabase Storage bucket (`public = false`), with a `storage.objects` tenant-
isolation policy mirroring the `quotation-documents`/`quality-issue-photos` pattern — see
`docs/quality/r2.5-security-review-record.md` §4.

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

## Implemented organisation model entities (chunk R2.0)

## `Branch`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `name` | text | Required |
| `address` | text | Optional |
| `region` | text | Optional FK -> `supported_region.code` |
| `is_active` | boolean | Required; default `true` |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

Also carries `unique (tenant_id, id)`, enabling composite tenant-scoped FK references from
`CostCentre`, `Budget`, and `BranchRoleAssignment`. No hard-delete path: `is_active = false` is the
only retirement path, permitted even with dependents attached (FR-009) — the API surfaces an
explicit confirmation naming what is still attached rather than blocking the deactivation.

`Branch` is tenant-scoped with forced RLS, plus a second, RESTRICTIVE visibility layer within the
tenant (research.md R1, `007-organisation-model`): an owner sees every branch; a member holding a
branch-scoped role (`branch_manager`, `approver`) sees only the branch(es) named in their own
`BranchRoleAssignment` rows; a member with no assignment at all (unscoped) sees every branch, same
as owner. Owner-only writes.

## `CostCentre`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `name` | text | Required |
| `code` | text | Required; unique per tenant (FR-003) |
| `budget_owner_membership_id` | uuid | Optional FK -> Membership; kept pointing at the row even after removal, since member removal is a soft delete |
| `branch_id` | uuid | Optional FK -> Branch; null = organisation-wide cost centre |
| `is_orphaned` | boolean | Required; default `false`; set by application logic when the linked branch is deactivated or the budget owner is removed (FR-010) |
| `is_archived` | boolean | Required; default `false` |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

`is_orphaned` is a real, persisted flag; the API additionally exposes a computed, never-stored
`orphan_reason` (`branch_deactivated` or `owner_removed`) on read, derived live from the linked
branch's `is_active` / the budget owner's membership `status` — a second stored cause column would
just be a second source of truth to keep in sync with facts already recoverable through the
existing FKs. No hard-delete path: archival is the only retirement path.

`CostCentre` is tenant-scoped with forced RLS, plus the same RESTRICTIVE branch-scoped visibility
as `Branch`, evaluated against `branch_id` (a `null` branch_id — organisation-wide — is always
visible regardless of scoping). Owner-only writes.

## `Budget`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `amount` | numeric(18,4) | Required; check `>= 0` |
| `currency` | text | Required FK -> `supported_currency.code`; never inferred from `tenant.currency` (research.md R3) |
| `period` | enum | `monthly`, `quarterly`, or `annual` |
| `period_start` | date | Required |
| `scope` | enum | `organisation`, `branch`, or `cost_centre` |
| `branch_id` | uuid | Required iff `scope = 'branch'`; FK -> Branch |
| `cost_centre_id` | uuid | Required iff `scope = 'cost_centre'`; FK -> CostCentre |
| `created_by` | uuid | Required FK -> Membership |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

The `budget_scope_target` check constraint enforces the scope/reference pairing at the database
level (exactly one of branch_id/cost_centre_id populated, matching scope; neither for
`organisation`). Deliberately no uniqueness constraint preventing overlapping periods for the same
scope (spec.md User Story 3, Acceptance Scenario 3: a running annual budget plus a supplementary
quarterly top-up may legitimately coexist) — the API computes an `overlap_warning` flag by
comparing each budget's `[period_start, period_start + period)` range against existing budgets for
the same scope/target, and surfaces it as a warning, never a rejection. This chunk defines and
stores budgets only; checking real spend against them is R2.1's job.

`Budget` is tenant-scoped with forced RLS, plus the same RESTRICTIVE branch-scoped visibility as
`Branch`/`CostCentre`, evaluated against `branch_id`/`cost_centre_id` depending on `scope`
(`organisation`-scoped budgets are always visible once tenant matches). Owner-only writes; no
update/delete endpoint in this chunk.

## `BranchRoleAssignment`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `membership_id` | uuid | Required FK -> Membership |
| `branch_id` | uuid | Required FK -> Branch |
| `created_at` | timestamptz | Audit field |

Composite `(tenant_id, id)` FKs throughout this chunk's schema (including this table's own
references to `Membership`/`Branch`) close the class of gap where a tenant-A row could reference a
tenant-B row while still passing its own table's tenant_id RLS check. `unique (tenant_id,
membership_id, branch_id)`: a member cannot be assigned to the same branch twice, but IS supported
scoped to multiple branches as separate rows (research.md R2). No soft-delete column: removing an
assignment is a real row delete — the historical record of the change lives in `audit_event`, not
here. Creating a row requires the target membership to already hold `branch_manager` or `approver`
(422 otherwise) — this extends the existing role, it does not itself change what role a member
holds.

`BranchRoleAssignment` is tenant-scoped with forced RLS, plus its own RESTRICTIVE visibility: an
owner sees every assignment in the tenant; a non-owner sees only their own row(s). Owner-only
writes.

## Implemented requests and approvals entities (chunk R2.1, `008-requests-approvals`)

Purchase requests and the single approval decision each one routes to at submission time.
Requests reuse R2.0's branch-scoped visibility mechanism verbatim (research.md R1) — an owner
sees every request; a branch-scoped member sees only their assigned branch(es); the requester
always sees their own request regardless of branch scope; a same-tenant, different-branch
reference resolves `not_found`, never forbidden. Write authorization (who may create, edit,
withdraw, or decide) lives in the service layer, not a write-narrowing RLS policy, matching the
R2.0 branch/cost-centre/budget pattern. Full contract:
`specs/008-requests-approvals/contracts/requests-approvals.openapi.yaml`.

## `PurchaseRequest`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `branch_id` | uuid | Required; composite FK -> Branch `(tenant_id, id)` |
| `cost_centre_id` | uuid | Optional; composite FK -> CostCentre `(tenant_id, id)` |
| `requested_by_membership_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `required_by_date` | date | Required |
| `status` | enum | `draft` \| `submitted` \| `approved` \| `rejected` \| `withdrawn` \| `ordered` \| `delivered`; default `draft` |
| `estimated_total_amount` | numeric(18,4) | Sum of line estimates; null when lines span >1 currency or no line has an estimate |
| `estimated_total_currency` | text | FK -> `supported_currency(code)`; paired with `estimated_total_amount` (both null or both set) |
| `has_incomplete_estimate` | boolean | Default `false`; `true` when any line's product has no reachable price history |
| `submitted_at` | timestamptz | Stamped on `draft -> submitted` |
| `withdrawn_at` | timestamptz | Stamped on `submitted -> withdrawn` |
| `delivered_at` | timestamptz | Stamped on `ordered -> delivered` (chunk R2.3); null before then. `purchase_request_delivered_at_pairing` check: set exactly when `status = 'delivered'` |
| `delivery_confirmed_by_membership_id` | uuid | Composite FK -> Membership `(tenant_id, id)`; who confirmed delivery (chunk R2.3) — the requester or a branch-scoped-write member, not necessarily the decider |
| `has_delivery_discrepancy` | boolean | Default `false` (chunk R2.3); `true` when any line's `quantity_received` came in short of `quantity` — a derived summary flag, not the source of truth (each line's own shortfall is computed at read time) |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

State machine: `draft -> submitted -> (approved | rejected | withdrawn)`. As of chunk R2.3
(`010-mobile-approvals-receipt`), an `approved` decision lands the request directly on `ordered`
— there is no separate "place the order" human action this release, so `approved` itself is now a
transient value the row never actually stops at (`RequestsService._decide_and_notify` maps
`decision == "approved"` to `status = "ordered"` before writing; `approval_step.status` still
records the human's real decision as `"approved"`, unchanged). From `ordered`, a delivery
confirmation (`POST /requests/{id}/confirm-delivery`) moves it to `delivered`, the current
terminal state. A `draft` may be hard-deleted by its own requester; once `submitted`, `withdraw`
(FR-004) is the only requester-initiated retirement and there is no hard-delete path. No edits
after submission (FR-004); submit requires at least one line (FR-003, `422 no_lines`). Line
estimates are recomputed live while the request is `draft` and frozen on submit (`estimated_at`
stamped, never updated again — research.md R2). `purchase_request_scoped_visibility` is a
RESTRICTIVE SELECT-only policy adding the requester-always-sees-own clause to R2.0's shape;
`purchase_request_tenant_isolation` is the permissive `ENABLE`+`FORCE` `for all` policy with
`USING` and `WITH CHECK`.

## `PurchaseRequestLine`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `purchase_request_id` | uuid | Required; composite FK -> PurchaseRequest `(tenant_id, id)`, `on delete cascade` |
| `workspace_product_id` | uuid | Required; composite FK -> WorkspaceProduct `(tenant_id, id)` |
| `quantity` | numeric(18,6) | Required, `> 0` |
| `note` | text | Optional |
| `estimated_unit_price_amount` | numeric(18,4) | Live while parent is `draft`, frozen on submit; null when the product has no reachable price history |
| `estimated_unit_price_currency` | text | FK -> `supported_currency(code)` |
| `estimated_unit_price_source_landed_cost_id` | uuid | Composite FK -> LandedCost `(tenant_id, id)` |
| `estimated_at` | timestamptz | Stamped when the estimate is frozen at submit |
| `quantity_received` | numeric(18,6) | Chunk R2.3; null until the parent request is `delivered`. `check (quantity_received is null or quantity_received >= 0)` |

A line's own delivery shortfall is `quantity_received < quantity` once both are set — computed at
read time (mirroring how `has_incomplete_estimate` is a computed-and-cached flag at the parent
level while the per-line comparison itself is not separately stored), not a second stored boolean
per line. The three `estimated_unit_price_*` columns are null together or populated together
(`purchase_request_line_estimate_paired` check — null exactly when the product has no reachable
`landed_cost` row; the parent request is then flagged `has_incomplete_estimate`). Visibility is
inherited from the parent request: `purchase_request_line_scoped_visibility` (RESTRICTIVE,
SELECT-only) re-derives the parent's visibility clause via an `EXISTS` join rather than
duplicating `branch_id` onto this table. `T002` added `unique (tenant_id, id)` to
`workspace_product` and `landed_cost` so those composite FKs are possible.

## `ApprovalStep`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `purchase_request_id` | uuid | Required; composite FK -> PurchaseRequest `(tenant_id, id)`, `on delete cascade`. `unique (tenant_id, purchase_request_id)` — one step per request |
| `assigned_membership_id` | uuid | Composite FK -> Membership `(tenant_id, id)`; who the request routed to |
| `source` | enum | `threshold_match` \| `delegate` \| `owner_fallback` — how `assigned_membership_id` was resolved (informational) |
| `status` | enum | `pending` \| `approved` \| `rejected`; default `pending` |
| `comment` | text | Optional decision comment |
| `decided_by_membership_id` | uuid | Composite FK -> Membership `(tenant_id, id)`; null while pending |
| `decided_at` | timestamptz | Null while pending |
| `created_at` | timestamptz | Audit field |

One resolved step per request in this release — a single decision, not a multi-stage chain
(`approval_step_one_per_request`). The `check (status = 'pending') = (decided_by_membership_id
is null and decided_at is null)` constraint encodes FR-006 ("no request becomes approved without
a recorded human decision") at the database level. `decided_by_membership_id` may legitimately
differ from `assigned_membership_id` — FR-007 lets an owner decide as a standing override; the
"only the assignee or an owner" rule is a service-layer RBAC guard, not a check constraint.
Produced by `resolve_approver()` at submission time and never silently re-resolved; the one
exception is member removal, which re-routes a still-`pending` step to the owner
(`source = 'owner_fallback'`, audited `requests.approval_step_escalated`, FR-009).
`approval_step_scoped_visibility` (RESTRICTIVE, SELECT-only): owner sees all; the assignee sees
their own step; the requester sees the step on their own request.

## `ThresholdRule`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `branch_id` | uuid | Optional; composite FK -> Branch `(tenant_id, id)`. Null = tenant-wide default rule |
| `min_amount` | numeric(18,4) | Required; inclusive lower bound (`0` for the lowest tier) |
| `max_amount` | numeric(18,4) | Optional; exclusive upper bound. Null = top tier (no ceiling) |
| `currency` | text | Required FK -> `supported_currency(code)`; a rule only matches a request whose estimated total shares this currency |
| `approver_membership_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `created_by` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `created_at` | timestamptz | Audit field |
| `updated_at` | timestamptz | Audit field |

`check (max_amount is null or max_amount > min_amount)`. Tenant-wide configuration: unlike
branch/cost-centre/budget, `threshold_rule` gets **no** branch-scoped RESTRICTIVE visibility
policy — every member may read the rules that determine routing (research.md R1), only an owner
may write them (service-layer RBAC). No uniqueness constraint on overlapping ranges;
`resolve_approver()` resolves a genuine overlap deterministically — a branch-scoped rule beats a
tenant-wide one, then the narrowest matching range wins. A rule pointing at a member who has
been removed from the workspace is skipped, so resolution falls through to owner-fallback.

## `ApprovalDelegation`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `delegator_membership_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `delegate_membership_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `starts_on` | date | Required; inclusive |
| `ends_on` | date | Required; inclusive |
| `created_at` | timestamptz | Audit field |

`check (delegator_membership_id <> delegate_membership_id)` and `check (ends_on >= starts_on)`.
Tenant-wide read (a delegation is not per-branch secret data); write restricted to the delegator
themselves or an owner (service-layer). Applied **after** threshold resolution at submission
time, not instead of it (research.md R3): once an approver is resolved, an active delegation
covering the request date redirects the step to the delegate (`source = 'delegate'`),
single-hop only. No uniqueness constraint on overlapping windows; routing prefers the
most-recently-created delegation covering the date. A delegation whose delegate has since been
removed from the workspace is ignored, and resolution falls back to the original assignee.

## Implemented mobile MVP entities (chunk R2.2, `009-mobile-app-mvp`)

The Flutter app's own three tables: a member's registered device (for push delivery), a
fast unlinked "shelf is running low" signal, and a durable record of one decision-triggered push
send attempt. Full contract: `specs/009-mobile-app-mvp/contracts/mobile.openapi.yaml`.

## `DeviceRegistration`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `member_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `platform` | enum | `ios` \| `android` |
| `push_token` | text | Required |
| `last_seen_at` | timestamptz | Default `now()`; passive staleness marker for a reinstall or token rotation |
| `created_at` | timestamptz | Audit field |

`unique (tenant_id, member_id, push_token)` makes registration a plain upsert at sign-in and
whenever the OS reissues a token, so a reinstall never accumulates duplicate rows. Sign-out is
**not** passive: the mobile app calls `DELETE /devices/{id}` for its own current registration,
which deletes the row outright, so a signed-out but still-installed device stops being eligible
for push immediately rather than waiting on `last_seen_at` staleness. Unlike every
branch-scoped table in this project, there is no owner-read-all clause here —
`device_registration_own_rows_only` is a RESTRICTIVE `for all` (not SELECT-only) policy narrowing
every operation to `member_id = current_membership_id()`, since an owner has no operational need
to browse another member's push tokens.

## `LowStockReport`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `branch_id` | uuid | Required; composite FK -> Branch `(tenant_id, id)` |
| `member_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `workspace_product_id` | uuid | Required; composite FK -> WorkspaceProduct `(tenant_id, id)` |
| `count_remaining` | numeric(18,6) | Optional; `check (count_remaining is null or count_remaining >= 0)` |
| `idempotency_key` | uuid | Optional; `unique (tenant_id, idempotency_key) where idempotency_key is not null` |
| `created_at` | timestamptz | Audit field |

Insert-only (FR-006) — `authenticated` is granted `SELECT`/`INSERT` only, no `UPDATE`/`DELETE`
(narrowed by a review-fix migration after the original grant mistakenly included both). The
partial unique index on `idempotency_key` is a real, database-enforced idempotent-replay
guarantee: `POST /low-stock-reports` does `insert ... on conflict (tenant_id, idempotency_key) do
nothing returning *`, falling back to a plain read of the existing row on a zero-row insert, so a
client retry after a dropped response never creates a second report. `low_stock_report_
scoped_visibility` is the same shape as `PurchaseRequest`'s own RESTRICTIVE SELECT-only policy —
an owner sees everything; a member always sees a report they raised themselves regardless of
branch scope; an unassigned (not branch-scoped) member sees everything; a branch-scoped member
sees only their own branch's reports.

## `PushNotification`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `purchase_request_id` | uuid | Required; composite FK -> PurchaseRequest `(tenant_id, id)` |
| `member_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` — the **requester**, not the decider |
| `status` | enum | `queued` \| `sent` \| `failed`; default `queued` |
| `attempts` | integer | Default `0` |
| `created_at` | timestamptz | Audit field |
| `sent_at` | timestamptz | Null unless `status = 'sent'` (`push_notification_sent_at_pairing` check) |

Not client-facing this release — no endpoint reads or writes it directly, and `authenticated`
gets no grant at all (rather than a deny-all RESTRICTIVE policy, the simpler of the two ways to
express "nothing here for a member or owner to see"); only `service_role` may touch it. Written
in the **same transaction** as the triggering approve/reject decision (a single raw-`psycopg`
block in `RequestsService._decide_and_notify()`, not a second independent PostgREST write) so an
insert failure here cleanly fails the whole decision rather than leaving an ambiguous
half-applied state. `process_push_notification()` marks a row `sent` only if it had zero device
registrations to attempt (FR-008) or `failed` for one or more real registrations — there is no
real FCM/APNs provider configured in this codebase, so a real registration's send is an honest,
deliberate stub that always reports failure rather than a fabricated success. A retry-sweep task
re-enqueues rows still `queued`/`failed` past a threshold, but no periodic scheduler invokes it
yet in this codebase — a still-open operational gap, not something this table's own design leaves
unresolved.

## Implemented mobile approvals and receipt entities (chunk R2.3, `010-mobile-approvals-receipt`)

Extends `PurchaseRequest`'s own lifecycle (see the R2.1 section above) with delivery confirmation
and delivery-quality reporting, rather than reusing the pre-existing, unrelated `PurchaseRecord`
entity (value-proof evidence, a different actor and trigger with no existing FK to
`purchase_request` — research.md R1). Full contract:
`specs/010-mobile-approvals-receipt/contracts/mobile-approvals-receipt.openapi.yaml`.

## `DeliveryQualityIssue`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `purchase_request_id` | uuid | Required; composite FK -> PurchaseRequest `(tenant_id, id)`, `on delete cascade` |
| `reported_by_membership_id` | uuid | Required; composite FK -> Membership `(tenant_id, id)` |
| `description` | text | Required, `check (char_length(description) > 0)` |
| `created_at` | timestamptz | Audit field |

Insert-only (no `PATCH`/`DELETE` surface this release) — `authenticated` is granted
`SELECT`/`INSERT` only, the same posture `LowStockReport` established. The parent
`purchase_request` must be `delivered` at insert time; enforced at the service layer
(`409 not_delivered`), not a check constraint, mirroring `approval_step`'s own precedent for a
condition that depends on a sibling row's current state. `delivery_quality_issue_scoped_visibility`
(RESTRICTIVE, SELECT-only) re-derives visibility via an `EXISTS` join to the **parent request's**
own requester/branch, the same pattern `PurchaseRequestLine`'s own policy already established —
notably, this rides who requested the underlying order, not `reported_by_membership_id` on this
table; a member who can see the parent request can see every quality issue filed against it,
regardless of who filed it.

## `DeliveryQualityIssuePhoto`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `delivery_quality_issue_id` | uuid | Required; composite FK -> DeliveryQualityIssue `(tenant_id, id)`, `on delete cascade` |
| `storage_path` | text | Required, `check (char_length(storage_path) > 0)`; server-allocated, never client-supplied |
| `created_at` | timestamptz | Audit field |

One-to-many child of `DeliveryQualityIssue` (a report may carry zero or more photos, FR-007) —
not a single photo column on the issue itself. Insert-only, same grant shape as its parent.
`storage_path` is allocated under `tenants/{tenant_id}/quality-issues/{issue_id}/{filename}` and
mirrors `quotation-documents`' own tenant-isolation-by-object-path Storage pattern exactly
(research.md R3) — a **separate** Storage bucket (`quality-issue-photos`, 10MB file-size limit),
not a shared one, since these are an unrelated document type with an unrelated lifecycle to
quotation documents. `delivery_quality_issue_photo_scoped_visibility` re-derives visibility one
join level deeper than its parent's own policy (issue -> parent request), the same idiom repeated
again rather than a new one. A signed URL for a photo is generated fresh at read time via the
tenant-scoped client (the same client that wrote it — no service-role bypass needed, since the
bucket's own RLS policy already permits a tenant member to read/write their own tenant's objects)
— never cached or stored, since a signed URL is inherently time-limited.

## Implemented Optimisation and Supplier IQ entities (chunk R2.4, `011-optimisation-supplier-iq`)

Extends smart compare, multi-supplier basket optimisation, supplier intelligence, and anomaly
detection without autonomous purchasing side effects (binding constitution rule).
Full contract: `specs/011-optimisation-supplier-iq/contracts/optimisation-supplier-iq.openapi.yaml`.

## `SupplierCommercialTerm`

Versioned tenant-scoped commercial rules for one supplier, enforcing commercial constraints
(MOV, free-delivery thresholds, delivery fees, and quantity pricing tiers).

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `supplier_id` | uuid | Required composite FK -> Supplier `(tenant_id, id)` |
| `effective_from` | timestamptz | Required |
| `effective_to` | timestamptz | Nullable; null indicates term is active open-endedly until superseded |
| `minimum_order_value_amount` | numeric(18,4) | Nullable money amount; paired with currency |
| `minimum_order_value_currency` | text | Required exactly when MOV amount is set |
| `delivery_fee_amount` | numeric(18,4) | Nullable money amount; paired with currency |
| `delivery_fee_currency` | text | Required exactly when delivery fee amount is set |
| `free_delivery_threshold_amount` | numeric(18,4) | Nullable money amount; paired with currency |
| `free_delivery_threshold_currency` | text | Required exactly when threshold amount is set |
| `quantity_tiers` | jsonb | Array of `{workspace_product_id?, min_quantity, unit_price_amount, unit_price_currency}` |
| `rule_version` | text | Required rule version identifier, e.g. `supplier-commercial-terms-v1` |
| `created_by_membership_id` | uuid | Required composite FK -> Membership `(tenant_id, id)` |
| `created_at` | timestamptz | Audit field |

Constraints and RLS:
- Money pairings enforced in database checks (`check_mov_pairing`, `check_delivery_fee_pairing`, `check_free_delivery_threshold_pairing`).
- Check constraint: `effective_to IS NULL OR effective_to > effective_from`.
- RLS enabled and forced: `supplier_commercial_term_tenant_isolation_select` allows all active tenant members; `supplier_commercial_term_tenant_isolation_insert` restricted to workspace owners and buyers. Forward-only / append-only: updates and deletes are disallowed for client roles.

## `SupplierScorecardSnapshot`

Cached, deterministic Supplier IQ scorecard calculation for a supplier and metric window.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key. `unique (tenant_id, id)` for composite FKs |
| `supplier_id` | uuid | Required composite FK -> Supplier `(tenant_id, id)` |
| `window_start` | date | Required window start date |
| `window_end` | date | Required window end date |
| `rule_version` | text | Required, e.g. `supplier-risk-v1` |
| `metrics` | jsonb | Required map of metric definitions, scores, sample counts, source ids, and confidence |
| `risk_score` | jsonb | Required weighted risk score total, rule version, and component breakdown |
| `source_counts` | jsonb | Required counts across quotation lines, delivery confirmations, and quality issues |
| `computed_at` | timestamptz | Required computation timestamp |
| `computed_by_membership_id` | uuid | Optional composite FK -> Membership `(tenant_id, id)` for human-triggered recompute |

Constraints and RLS:
- Unique `(tenant_id, supplier_id, window_start, window_end, rule_version)`.
- Check constraint: `window_end >= window_start`.
- Snapshots are deterministic caches computed from seeded tenant records (quotations, deliveries, quality issues, purchase records).
- RLS enabled and forced: tenant members may select; owner/buyer may insert/recompute via service.

## Extended `BasketSplitJob` Request & Result Snapshots

The existing `basket_split_job` table persists advanced multi-supplier basket optimisation runs:
- Request snapshot payload additions:
  - `supplier_ids`: 2 to 10 selected supplier UUIDs.
  - `hard_constraints`: Minimum order values (MOV), free-delivery thresholds, delivery fees, quantity tiers, supplier exclusions, and delivery urgency level (`normal` | `urgent`).
  - `soft_weights`: Weights for price, preferred suppliers, risk tolerance, lead time, and quality.
  - `rule_version`: Versioned optimiser algorithm snapshot.
- Result payload additions:
  - `allocation`: Product-to-supplier allocations satisfying constraints.
  - `total_landed_cost`: Optimised total money amount and currency.
  - `single_supplier_baselines`: Comparison against single-supplier fulfilment.
  - `applied_constraints` & `violated_constraints`: Structured list of constraint evaluations.
  - `risk_notes` & `confidence`: Calibrated confidence levels and risk notices.

## Response-Only Entities

- **`SupplierScorecard`**: Returned by `GET /suppliers/{supplier_id}/scorecard` (`supplier`, `window_start`, `window_end`, `metrics`, `risk_score`, `source_counts`, `confidence`, `insufficient_evidence`, `computed_at`, `rule_version`).
- **`AnomalySignal`**: Live-computed commercial alert returned by `GET /alerts` with kinds `price_spike`, `likely_duplicate_quotation_line`, `decimal_or_quantity_anomaly`, `delivery_cost_anomaly`, and `supplier_quality_trend_change`. Includes confidence, severity, recurrence fingerprints, and scorecard action routing.

## Audit Events

Append-only audit trail logging for R2.4 operations:
- `optimisation.basket_split.submitted`: Human-triggered advanced multi-supplier basket optimisation.
- `supplier_iq.scorecard.viewed`: Inspection of supplier scorecard metrics and risk evidence.
- `alerts.anomaly.dismissed`: Dismissal of commercial anomaly alerts with deterministic recurrence keys.

## R4.1 Supplier IQ v2 and Negotiation Brief Entities

Migration: `supabase/migrations/20260920000009_supplier_iq_v2.sql`. Every new table below carries
`tenant_id`, composite tenant foreign keys, `ENABLE` and `FORCE` row-level security, tenant-scoped
`USING` and `WITH CHECK` policies, and no authenticated or service-role update/delete/truncate
grant. Existing v1 scorecard rows remain readable.

### Extended `SupplierScorecardSnapshot`

The existing snapshot header remains the compatibility source for v1 consumers. V2 adds nullable
`state`, `confidence`, `release_posture`, `valid_from`, `valid_until`, `source_fingerprint`, and
`observed_history_days`. V2 rows require a fingerprint and use a partial unique index on
`(tenant_id, source_fingerprint)`; legacy rows retain window uniqueness. All snapshot history is
append-only.

### `SupplierScorecardMetric`

Immutable normalized component or currency-bucket calculation linked to one snapshot.

| Field | Type | Notes |
|---|---|---|
| `id`, `tenant_id`, `snapshot_id` | uuid | Tenant-pinned identity and snapshot FK |
| `metric_kind`, `bucket_key` | text | Unique per snapshot/kind/bucket |
| `value`, `numerator`, `denominator` | numeric(18,8) | Decimal calculation inputs/results |
| `amount`, `currency` | numeric(18,4), text | Nullable paired money fields |
| `sample_count`, `confidence`, `is_sufficient` | integer, text, boolean | Evidence sufficiency |
| `window_start`, `window_end` | date | Exact calculation window |
| `calculation_version`, `created_at` | text, timestamptz | Replay/provenance metadata |

### `SupplierScorecardEvidence`

Immutable typed link from one metric to exactly one source. The database check requires exactly
one of `purchase_order_id`, `delivery_receipt_id`, `landed_cost_id`, `three_way_match_id`,
`synced_bill_id`, `workspace_product_id`, `delivery_quality_issue_id`, or
`supplier_commercial_term_id`; every target uses a composite tenant FK.

### `NegotiationBrief`

Immutable header linked to a supplier and scorecard snapshot. Stores `brief_version`,
`source_fingerprint`, fixed `g3_unmet` posture, validity, creator, and creation time. Unique on
`(tenant_id, supplier_id, snapshot_id, brief_version)` for deterministic replay.

### `NegotiationBriefItem`

Immutable ranked talking point. Stores item kind, rank, optional metric, decimal value, optional
paired money amount/currency, confidence, optional normalized risk, validity, shared i18n question
key, and calculation version. A deferred constraint trigger requires at least one linked evidence
row before transaction commit.

### `NegotiationBriefItemEvidence`

Immutable many-to-many link between a brief item and `SupplierScorecardEvidence`, keyed by
`(tenant_id, item_id, evidence_id)`.

### `NegotiationBriefAction`

Append-only human review event. `action` is `acknowledged` or `dismissed`; dismissal requires a
non-blank reason. `idempotency_key` is unique per tenant. Current brief status is derived from the
latest event rather than stored by updating the brief.

### Extended `SyncedBill`

Adds provider-derived `due_date`, `remaining_balance_amount`, and
`remaining_balance_currency`. Remaining balance is non-negative and amount/currency are required
as a pair. Null historical values never support an inferred overdue-payment claim.

R4.1 audit events are append-only: `supplier_iq.recomputed`, `negotiation_brief.prepared`,
`negotiation_brief.acknowledged`, and `negotiation_brief.dismissed`. The feature writes no supplier
message, purchase request, or purchase order.

## Implemented mobile approvals and receipt entities (chunk R2.3, `010-mobile-approvals-receipt`)

See `specs/010-mobile-approvals-receipt/data-model.md` for `PurchaseRequest`'s delivery-status
columns and the `DeliveryQualityIssue`/`DeliveryQualityIssuePhoto` entities above (T037 landed
these; the section marker exists so this file's own section list stays in feature order).

## Implemented reporting and hardening entities (chunk R2.5, `012-reporting-hardening`)

### `ReportSchedule`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `created_by_membership_id` | uuid | Required composite FK -> Membership `(tenant_id, id)` |
| `kind` | text | Required; `savings_ledger`, `spend_by_supplier`, or `alerts_summary` |
| `format` | enum | Required; `csv`, `xlsx`, or `pdf` (kind/format compatibility validated at the API — `spend_by_supplier` + `pdf` is refused) |
| `filters` | jsonb | Required; `{supplier_id?, branch_id?}` — the fixed filter part; the period itself is derived at run time from `weekday`/`tenant.reporting_timezone` |
| `filters_digest` | text | Required; sha256 of the canonical filters JSON, computed by the API |
| `weekday` | smallint | Required; 0-6 (Monday-based) for the weekly cadence |
| `status` | enum | `active` or `paused`; default `active` |
| `next_run_at` | timestamptz | Required; the next due instant in the tenant's reporting timezone |
| `last_run_at` | timestamptz | Optional |
| `rule_version` | text | Required; renderer rule version, for replay |
| `locale` | text | `en` or `ar`; default `en` (added `20260915000006_report_schedule_locale.sql`, forward-only after the table's own creation migration) |
| `created_at` / `updated_at` | timestamptz | Audit fields |

A member-owned recurring report definition — configuration, not outcome history: deleting a
schedule never deletes the artifacts it already produced (`export_job.schedule_snapshot` keeps
them self-describing). Unique on `(tenant_id, created_by_membership_id, kind, format,
filters_digest)` — one schedule per member per kind/format/filters combination, turning an
accidental duplicate create into an honest 409 rather than a silent second schedule.

RLS (enabled + forced): any tenant member may `SELECT` any schedule in the tenant (team
visibility, by design — see `docs/quality/r2.5-security-review-record.md` §1); owner/buyer may
insert/update/delete any schedule in the tenant, not only their own. A partial index
(`report_schedule_due_idx`) on `(next_run_at)` where `status = 'active'` backs the scheduler's
`FOR UPDATE SKIP LOCKED` due-list claim.

### `DigestSubscription`

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant; RLS key |
| `membership_id` | uuid | Required composite FK -> Membership `(tenant_id, id)` |
| `kind` | text | Fixed value `weekly_digest` |
| `locale` | text | `en` or `ar`; drives the digest's render language (FR-029) |
| `filters` | jsonb | `{branch_id?}` |
| `filters_digest` | text | sha256 of the canonical filters JSON |
| `channel` | enum | `in_app` or `email` |
| `status` | enum | `active` or `paused`; default `active` |
| `next_run_at` | timestamptz | Required; the next due weekly instant |
| `last_delivery_at` | timestamptz | Optional |
| `last_delivery_status` | text | Optional (`succeeded`, `failed`, `skipped`) |
| `created_at` / `updated_at` | timestamptz | Audit fields |

A per-member weekly digest definition. Unique on `(tenant_id, membership_id, kind,
filters_digest)`. Content (verified-savings hero, pending outcome verifications, pending
approvals, anomalies, expiring validity) is assembled fresh at delivery time from existing tables
via the same tenant-pinned reader functions exports use — no digest content is persisted as a
second source of truth.

RLS (enabled + forced): a member sees and mutates only their own subscription rows; owners may
additionally `SELECT` every row in the tenant for visibility (not control — they cannot
insert/update/delete another member's subscription). A partial index on `(next_run_at)` where
`status = 'active'` backs the digest worker's own due-list claim, mirroring `ReportSchedule`'s.

### Reporting reader functions

Three `security definer`, `stable` SQL functions (`supabase/migrations/
20260915000005_reporting_reader_functions.sql`), each taking `p_tenant_id` as an explicit,
API-supplied (never client-supplied) parameter and pinning every joined table to it — the same
"authorization inside the function, not just at the API layer" pattern R2.4's supplier-IQ
functions established:

- `reporting_savings_for_period(tenant_id, period_start, period_end, supplier_id?, branch_id?)` —
  verified-savings rows for the `savings_ledger` export/digest kind.
- `reporting_purchases_for_period(tenant_id, period_start, period_end, supplier_id?, branch_id?)`
  — purchase/spend aggregation source for `spend_by_supplier`.
- `reporting_alert_snapshot(tenant_id, period_start, period_end, branch_id?)` — live alert
  conditions for `alerts_summary`. By design (`spec.md`'s own stated assumption, consistent with
  R2.4's dismissal-only alert model), this one does **not** filter by the period or branch
  parameters it declares — alerts have no persisted history and no branch attribution in this
  data model; it always returns the current live snapshot. See
  `docs/quality/r2.5-security-review-record.md` §3 for the review that confirmed this is
  intentional rather than a missed filter.

### `ExportJob` extensions

See the updated `ExportJob` entity above (schedule linkage, locale, rule version, immutable
schedule snapshot, retention expiry, the widened `kind`/`format`/`status` value sets, and the
per-schedule-period idempotency index).

### Storage: `exports` bucket

A private (`public = false`) Supabase Storage bucket, added in `supabase/migrations/
20260916000001_exports_storage.sql` — see `docs/quality/r2.5-security-review-record.md` §4 for
why this migration exists (the bucket had no creation migration or `storage.objects`
tenant-isolation policy before this review). Object paths are
`{tenant_id}/savings/{job_id}.{format}` (no `tenants/` prefix, unlike the
`quotation-documents`/`quality-issue-photos` buckets), so the tenant-isolation policy pins
`storage.foldername(name)`'s first element rather than its second.

### New audit events (chunk R2.5)

- `reports.export_requested` — an on-demand export was queued.
- `reports.artifact_downloaded` — a signed download URL was minted for a completed artifact.
- `reports.artifact_purged` — a retention-expired artifact's storage object was deleted.
- `reports.schedule_created` / `reports.schedule_updated` / `reports.schedule_deleted`.
- `reports.run_enqueued` / `reports.run_started` / `reports.run_completed` / `reports.run_failed`
  — the scheduled-run lifecycle, recorded by the scheduler and the export worker.
- `digests.subscription_created` / `digests.subscription_updated` /
  `digests.subscription_active` / `digests.subscription_paused` (the two live values of a status
  toggle) / `digests.subscription_deleted` / `digests.subscription_provisioned` (default
  subscription created automatically on member accept).

## Implemented automated ingestion entities (chunk R3.0, `013-automated-ingestion`)

Adds multi-channel quotation ingestion (inbound email forwarding, mobile/desktop capture, and
bulk supplier catalogue imports) with automated supplier matching, deduplication, and
asynchronous processing queues.

### Schema design note: Composite foreign keys for cross-tenant isolation

Several foreign keys in this chunk (`ingestion_email_log.supplier_id`, `tenant_email_config.created_by`,
`catalogue_imports.supplier_id`, `catalogue_imports.created_by`, and the `quotation.ingestion_email_id`
extension) deliberately reference parent tables via their `(tenant_id, id)` composite unique keys
(`supplier(tenant_id, id)`, `membership(tenant_id, id)`, and `ingestion_email_log(tenant_id, id)`) rather
than a bare `references table(id)`.

As documented in `ingestion_email_log_supplier_fkey`'s migration comment, this provides critical
defense-in-depth: a cross-tenant reference can never be inserted even from a background worker,
asynchronous processor, or service-role execution path that bypasses PostgreSQL Row Level Security.
Conversely, references to `quotation` (such as `ingestion_email_log.quotation_id`) remain bare foreign keys
because `quotation` does not yet possess a `(tenant_id, id)` composite unique constraint in the foundational
schema; introducing one piecemeal here would create inconsistency with existing quotation foreign keys across
the codebase.

### `TenantEmailConfig`

Per-tenant email ingestion configuration and rate limit counters (table `tenant_email_config`). Stores the
dedicated workspace forwarding address, ingestion enablement state, optional sender domain allowlist,
daily quota, and current daily consumption counter.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id)` enforces one config per workspace |
| `forwarding_address` | text | Required, unique (`tenant_email_config_address_key`). Format validated by regex `check (forwarding_address ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$')` |
| `enabled` | boolean | Required, default `true`. Tenant owner toggle to enable or disable inbound email processing |
| `domain_allowlist` | text[] | Nullable. Optional array of allowed sender domains; if non-empty, emails from unlisted domains are rejected |
| `daily_limit` | integer | Required, default `100`, `check (daily_limit between 1 and 10000)`. Max inbound emails allowed per calendar day |
| `daily_count` | integer | Required, default `0`, `check (daily_count >= 0)`. Count of emails accepted on `daily_count_date` |
| `daily_count_date` | date | Required, default `current_date`. Anchor date for the daily rate limit counter |
| `spf_dkim_required` | boolean | Required, default `false`. When true, inbound emails lacking passing SPF/DKIM verification are rejected |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |
| `created_by` | uuid | Required composite FK -> Membership `(tenant_id, id)` (`tenant_email_config_created_by_fkey`) |

RLS (enabled + forced): all active tenant members may `SELECT` (`tenant_email_config_tenant_select` using
`tenant_id = current_tenant_id()`) to view settings and copy the workspace forwarding address. Mutation
(`INSERT`, `UPDATE`, `DELETE`) is strictly restricted to the `owner` role via `tenant_email_config_owner_insert`,
`tenant_email_config_owner_update`, and `tenant_email_config_owner_delete` (checking `tenant_id = current_tenant_id() and current_member_role() = 'owner'`).
A case-insensitive index on `lower(forwarding_address)` backs inbound webhook routing queries. The address format
check constrains email syntax only rather than hardcoding `@ingest.procurepilot.com` into the database, preserving
testability across local, CI, and staging environments where the domain is dynamically configured.

### `IngestionEmailLog`

Metadata and audit record for every inbound email processed for a workspace (table `ingestion_email_log`).
Enforces per-tenant RFC 5322 Message-ID deduplication, attachment counting, and records supplier identification
provenance.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` for composite FKs |
| `message_id` | text | Required. RFC 5322 Message-ID header value. Unique per tenant `(tenant_id, message_id)` for duplicate prevention |
| `from_address` | text | Required. Envelope sender email address |
| `from_domain` | text | Required. Extracted and normalized domain from sender address; indexed for supplier matching |
| `subject` | text | Nullable. Email subject line |
| `in_reply_to` | text | Nullable. In-Reply-To header used for threading correlation |
| `references_list` | text[] | Required, default `'{}'`. Array of Message-IDs from the References header |
| `received_at` | timestamptz | Required, default `now()`. Ingestion timestamp recorded by inbound webhook |
| `processed_at` | timestamptz | Nullable. Timestamp when pipeline execution finished |
| `status` | enum `ingestion_email_status` | Required, default `'received'`. Values: `received`, `processing`, `completed`, `failed`, `duplicate`, `rejected` |
| `error_message` | text | Nullable. Error description or rejection reason if status is `failed` or `rejected` |
| `attachment_count` | integer | Required, default `0`, `check (attachment_count >= 0)`. Total attachments found |
| `raw_email_ref` | text | Nullable. Supabase Storage path in the private `ingestion-raw` bucket (`{tenant_id}/raw-email/{message_id}`) for audit and replay |
| `quotation_id` | uuid | Nullable bare FK -> Quotation (`quotation.id`, `on delete set null`). Linked quotation created from primary attachment |
| `supplier_id` | uuid | Nullable composite FK -> Supplier `(tenant_id, id)` (`ingestion_email_log_supplier_fkey`, `on delete set null`) |
| `match_method` | text | Nullable `check (match_method is null or match_method in ('address', 'domain', 'thread', 'manual'))`. Supplier identification mechanism |
| `created_at` | timestamptz | Audit field, default `now()` |

RLS (enabled + forced): `ingestion_email_log_tenant_isolation` grants full CRUD (`SELECT`, `INSERT`, `UPDATE`, `DELETE`)
to `authenticated` users scoped to their current tenant (`tenant_id = current_tenant_id()`). Unique constraint
`(tenant_id, message_id)` guarantees strict deduplication per RFC 5322: duplicates are caught at insertion time and
short-circuited without re-extracting documents.

### `IngestionJob`

Asynchronous worker queue for background ingestion tasks (table `ingestion_jobs`), including inbound email processing,
mobile/desktop camera capture extraction, and bulk supplier catalogue imports.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `job_type` | enum `ingestion_job_type` | Required. Values: `email_ingest`, `capture_ingest`, `catalogue_import` |
| `status` | enum `ingestion_job_status` | Required, default `'pending'`. Values: `pending`, `processing`, `completed`, `failed` |
| `payload` | jsonb | Required, default `'{}'::jsonb`. Serialized job parameters (e.g. storage paths, message metadata) |
| `attempts` | integer | Required, default `0`, `check (attempts >= 0)`. Execution attempt counter |
| `max_attempts` | integer | Required, default `3`, `check (max_attempts > 0)`. Retry limit before transition to terminal failed status |
| `last_error` | text | Nullable. Error message from the most recent failed execution attempt |
| `locked_by` | text | Nullable. Worker instance identifier holding execution lease |
| `locked_at` | timestamptz | Nullable. Timestamp when worker acquired lock |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |
| `completed_at` | timestamptz | Nullable. Completion timestamp; `check (completed_at is null or completed_at >= created_at)` |

RLS (enabled + forced): `ingestion_jobs_tenant_isolation` grants full CRUD to `authenticated` users within their
workspace (`tenant_id = current_tenant_id()`). Polled by background workers using the `FOR UPDATE SKIP LOCKED`
pattern over partial index `ingestion_jobs_pending_worker_idx` on `(created_at) where status = 'pending'`, mirroring
the concurrency mechanics of `ReportSchedule` and `DigestSubscription`.

### `CatalogueImport`

Tracks supplier catalogue bulk price refresh operations and telemetry from uploaded spreadsheets (table `catalogue_imports`).
Persists storage references, parsing/import metrics, structured row validation errors, and resolved header mappings.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `supplier_id` | uuid | Required composite FK -> Supplier `(tenant_id, id)` (`catalogue_imports_supplier_fkey`, `on delete cascade`) |
| `file_name` | text | Required, `check (char_length(file_name) between 1 and 255)`. Original uploaded filename |
| `file_path` | text | Required. Storage path in Supabase Storage |
| `file_size_bytes` | bigint | Required, `check (file_size_bytes > 0)`. Source file byte count |
| `file_format` | text | Required, `check (file_format in ('csv', 'xlsx'))`. Supported spreadsheet format |
| `status` | enum `catalogue_import_status` | Required, default `'pending'`. Values: `pending`, `processing`, `completed`, `failed` |
| `total_rows` | integer | Nullable, `check (total_rows is null or total_rows >= 0)`. Total data rows in sheet (excluding header) |
| `imported_rows` | integer | Nullable, `check (imported_rows is null or imported_rows >= 0)`. Valid rows imported into quotation lines |
| `skipped_rows` | integer | Nullable, `check (skipped_rows is null or skipped_rows >= 0)`. Rows skipped during processing |
| `error_rows` | integer | Nullable, `check (error_rows is null or error_rows >= 0)`. Count of invalid/unparseable rows |
| `error_details` | jsonb | Required, default `'[]'::jsonb`. Array of `{row, column, error}` validation failure objects |
| `column_mapping` | jsonb | Required, default `'{}'::jsonb`. Resolved spreadsheet column to catalogue attribute mapping |
| `created_at` | timestamptz | Audit field, default `now()` |
| `completed_at` | timestamptz | Nullable. Completion timestamp; `check (completed_at is null or completed_at >= created_at)` |
| `created_by` | uuid | Required composite FK -> Membership `(tenant_id, id)` (`catalogue_imports_created_by_fkey`) |

RLS (enabled + forced): all active tenant members may `SELECT` (`catalogue_imports_tenant_select` using
`tenant_id = current_tenant_id()`) to view import status and error logs. Mutation (`INSERT`, `UPDATE`) is
restricted to `owner` and `buyer` roles via `catalogue_imports_owner_buyer_insert` and
`catalogue_imports_owner_buyer_update` (checking `tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer')`).

### Storage: `ingestion-raw` bucket

A private (`public = false`, 50MB file size limit) Supabase Storage bucket added in migration
`20260917000007_ingestion_storage.sql`. Stores unmodified incoming MIME emails under `{tenant_id}/raw-email/{message_id}`
for compliance, audit trails, and deterministic replay. Protected by `ingestion_raw_tenant_isolation` on `storage.objects`,
pinning `(storage.foldername(name))[1] = current_tenant_id()::text` to enforce tenant isolation.

### Quotation & Supplier Schema Extensions

- **`quotation.source`**: Text column tracking arrival channel with check constraint `check (source in ('upload', 'email', 'capture', 'catalogue_import'))`; default `'upload'`.
- **`quotation.ingestion_email_id`**: Composite FK to `ingestion_email_log(tenant_id, id)` on delete set null (`quotation_ingestion_email_fkey`).
- **`supplier.email_domains`**: `text[] not null default '{}'` column storing authorized sender domains for automated email attribution, indexed with GIN (`supplier_email_domains_gin_idx`).
- **`document_source_channel`**: Enum extended with `'email'`, `'capture'`, and `'catalogue_import'`.
- **`document.mime_type`**: Widened check constraint accepting `image/heic` (mobile photo captures) and `text/plain`.

### New audit events (chunk R3.0)

- `ingestion.email_config_updated` — tenant email ingestion settings (domain allowlist, daily limit, SPF/DKIM enforcement) were updated.
- `ingestion.email_config_enabled` — email ingestion was activated by a workspace owner.
- `ingestion.email_config_disabled` — email ingestion was deactivated by a workspace owner.
- `email_received` — inbound email was accepted, raw MIME payload stored in `ingestion-raw`, and primary document/quotation enqueued.
- `email_duplicate` — duplicate RFC 5322 Message-ID was detected for the tenant and skipped without reprocessing.
- `email_rejected` — inbound email was rejected during validation (SPF/DKIM failure, unsupported attachment type, or file size limits).
- `email_supplier_matched` — inbound email sender was successfully resolved to a known tenant supplier via address, domain, or thread correlation.
- `email_supplier_unmatched` — inbound email sender could not be matched; quotation was created and flagged for manual supplier review.
- `capture_uploaded` — quotation document or photo was successfully uploaded via mobile/desktop capture endpoint.
- `capture_rejected` — capture upload was rejected due to file size exceeding limit or unsupported media type.
- `catalogue_import_started` — supplier price catalogue spreadsheet upload was accepted and import parsing initiated.
- `catalogue_import_completed` — supplier catalogue spreadsheet was successfully parsed and quotation lines imported.
- `catalogue_import_failed` — supplier catalogue import failed due to parse error, schema validation errors, or zero valid rows.

## Implemented accounting integration entities (chunk R3.1, `014-accounting-integration`)

Adds external accounting system integration (QuickBooks Online in R3.1) with OAuth credential management,
automated vendor and supplier bill synchronization, automated purchase-to-bill matching, and 3-way
reconciliation discrepancy tracking.

### Schema design note: Composite foreign keys for cross-tenant isolation

All foreign keys introduced in this chunk pin to parent tables via `(tenant_id, id)` composite unique keys
rather than bare `id` references:
- `purchase_record_tenant_id_key` unique constraint added on `purchase_record(tenant_id, id)` in migration
  `20260918000001_purchase_record_composite_key.sql`. `purchase_record` predated the composite-key convention
  established across chunks 011/012/013 (`supplier_commercial_term`, `supplier_scorecard_snapshot`, `ingestion_email_log`,
  `report_schedule`). `purchase_bill_match` and `reconciliation_discrepancy` are the first tables to reference
  `purchase_record` from outside its originating module, closing this legacy gap.
- `accounting_connection.connected_by` references `membership(tenant_id, id)`.
- `synced_vendor.connection_id` references `accounting_connection(tenant_id, id)`.
- `synced_vendor.matched_supplier_id` references `supplier(tenant_id, id)`.
- `synced_bill.connection_id` references `accounting_connection(tenant_id, id)`.
- `synced_bill.vendor_id` references `synced_vendor(tenant_id, id)`.
- `synced_bill.matched_supplier_id` references `supplier(tenant_id, id)`.
- `purchase_bill_match.synced_bill_id` references `synced_bill(tenant_id, id)`.
- `purchase_bill_match.purchase_record_id` references `purchase_record(tenant_id, id)`.
- `purchase_bill_match.matched_by` references `membership(tenant_id, id)`.
- `reconciliation_discrepancy.synced_bill_id` references `synced_bill(tenant_id, id)`.
- `reconciliation_discrepancy.purchase_record_id` references `purchase_record(tenant_id, id)`.
- `reconciliation_discrepancy.resolved_by` references `membership(tenant_id, id)`.

This provides strict defense-in-depth: cross-tenant references cannot be persisted even from background workers,
system tasks, or service-role execution paths that bypass PostgreSQL Row Level Security.

### Schema design note: Worker session isolation vs. column-level credential privileges

An essential RLS architecture nuance in this chunk is the operational boundary between background worker writes
and OAuth credential privileges:
- **Worker/System-triggered session pattern**: Four of the five tables (`synced_vendor`, `synced_bill`,
  `purchase_bill_match`'s automatic path, and `reconciliation_discrepancy`), as well as background sync updates
  to `accounting_connection` (`last_synced_at` and `status = 'needs_reauth'`), are written by the background sync
  worker or on-demand sync pipeline. Instead of running as a global `service_role` connection (which lacks
  tenant guardrails and would introduce architectural inconsistency), the worker establishes a tenant-scoped session
  acting as Postgres role `authenticated` via `_act_as_tenant_sync`: executing `SET LOCAL ROLE authenticated` and
  setting `request.jwt.claims` to `{"tenant_id": "<uuid>", "role": "authenticated"}` with **no** `member_role` claim.
- **Distinguishing worker from member sessions via `current_member_role() IS NULL`**: Real member sessions always
  carry an explicit `member_role` claim (`owner`, `buyer`, `approver`, `viewer`). In contrast, worker sessions
  deliberately omit `member_role`. The database RLS policies exploit this exact difference:
  - `accounting_connection_worker_update`: allows updates with `tenant_id = current_tenant_id() and current_member_role() is null`.
    Real non-owner member sessions cannot satisfy this policy because their JWT always provides `member_role`.
  - `purchase_bill_match_automatic_insert` / `purchase_bill_match_automatic_delete`: allows inserts/deletes where
    `tenant_id = current_tenant_id() and match_method = 'automatic' and matched_by is null`. Workers can insert and delete
    stale automatic matches, but can never alter or delete manual matches created by owners or buyers.
  - `reconciliation_discrepancy_worker_insert` / `reconciliation_discrepancy_worker_update`: allows inserts and reopening
    updates where `tenant_id = current_tenant_id() and current_member_role() is null`.
- **OAuth token security (`access_token`/`refresh_token` as the sole `service_role` write path)**:
  `accounting_connection.access_token` and `refresh_token` store live third-party financial credentials. Because PostgreSQL
  RLS is row-scoped rather than column-scoped, normal `SELECT` on `accounting_connection` for `authenticated` would expose
  tokens to every workspace member reading the connection status. Column-level `GRANT`s eliminate this exposure:
  - `authenticated` is granted `SELECT` on non-secret columns only (`id`, `tenant_id`, `provider`, `realm_id`, `display_name`,
    `status`, `connected_by`, `connected_at`, `last_synced_at`, `disconnected_at`, `created_at`, `updated_at`).
  - `authenticated` is granted `INSERT` on all columns including tokens (allowing the owner connect callback to insert
    credentials directly without needing a service-role bypass).
  - `authenticated` is granted `UPDATE` only on non-secret fields (`status`, `disconnected_at`, `updated_at`, `last_synced_at`).
  - Token reading and token refresh updates (`UPDATE access_token, refresh_token`) are the **sole operations** in this feature
    that use a direct `service_role` connection (`_service_role_db`), explicitly constrained by
    `WHERE id = %(id)s AND tenant_id = %(tenant_id)s`.
- On `reconciliation_discrepancy`, column-level `GRANT`s similarly restrict `authenticated`'s `UPDATE` privileges strictly to
  resolution fields `(status, resolved_by, resolved_at, resolution_note)`. `detected_at` is set once at `INSERT` and is
  permanently immutable (even when a discrepancy is reopened on subsequent syncs).

### `AccountingConnection`

One workspace's authorized link to an external accounting account (table `accounting_connection`). Exactly one non-disconnected
connection per tenant is permitted at a time; disconnecting a connection leaves the row intact for audit history while freeing
the tenant to connect a new account.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `provider` | enum `accounting_provider` | Required. Provider type, currently `'quickbooks'` |
| `realm_id` | text | Required. Third-party realm/company identifier |
| `display_name` | text | Required. Connected company name retrieved from provider |
| `access_token` | text | Required. Live OAuth access token; `service_role`-only for SELECT/UPDATE; `authenticated` INSERT-only |
| `refresh_token` | text | Required. Live OAuth refresh token; `service_role`-only for SELECT/UPDATE; `authenticated` INSERT-only |
| `status` | enum `accounting_connection_status` | Required, default `'active'`. Values: `'active'`, `'needs_reauth'`, `'disconnected'` |
| `connected_by` | uuid | Required composite FK -> Membership `(tenant_id, id)` (`accounting_connection_membership_fkey`) |
| `connected_at` | timestamptz | Required, default `now()`. Authorization timestamp |
| `last_synced_at` | timestamptz | Nullable. Timestamp when last full sync completed |
| `disconnected_at` | timestamptz | Nullable. Timestamp when disconnected; check `((status = 'disconnected') = (disconnected_at is not null))` |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |

RLS (enabled + forced): All tenant members may `SELECT` (`accounting_connection_tenant_select` using `tenant_id = current_tenant_id()`)
to view connection status and display name; column-level grants withhold `access_token` and `refresh_token`. Mutation (`INSERT`, `UPDATE`)
is restricted to `owner` members via `accounting_connection_owner_insert` and `accounting_connection_owner_update`. The sync worker
updates `last_synced_at` and `status` via `accounting_connection_worker_update` (`current_member_role() IS NULL`). A partial unique index
`accounting_connection_one_active_per_tenant` on `(tenant_id) WHERE status <> 'disconnected'` enforces at most one active connection.

### `SyncedVendor`

Vendor entities synced from the external accounting system (table `synced_vendor`). Persists the vendor-to-supplier name match
so subsequent sync passes reuse the established linkage without re-evaluating fuzzy name heuristics.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `connection_id` | uuid | Required composite FK -> AccountingConnection `(tenant_id, id)` (`synced_vendor_connection_fkey`) |
| `provider_vendor_id` | text | Required. External provider vendor identifier (QuickBooks `Vendor.Id`) |
| `display_name` | text | Required. Vendor display name in accounting system |
| `matched_supplier_id` | uuid | Nullable composite FK -> Supplier `(tenant_id, id)` (`synced_vendor_supplier_fkey`, `on delete set null`) |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |

RLS (enabled + forced): All tenant members may `SELECT` (`synced_vendor_tenant_select`). Sync worker inserts and updates rows
under tenant-scoped `authenticated` sessions via `synced_vendor_tenant_insert` and `synced_vendor_tenant_update`. Unique constraint
`synced_vendor_provider_id_key` on `(tenant_id, connection_id, provider_vendor_id)` prevents duplicate vendor ingestion.

### `SyncedBill`

Supplier bills as recorded in the connected accounting system as of the most recent sync (table `synced_bill`). Stores total amount,
currency, bill date, and provider status (`open`, `paid`, `void`).

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `connection_id` | uuid | Required composite FK -> AccountingConnection `(tenant_id, id)` (`synced_bill_connection_fkey`) |
| `provider_bill_id` | text | Required. External provider bill identifier (QuickBooks `Bill.Id`) |
| `vendor_id` | uuid | Required composite FK -> SyncedVendor `(tenant_id, id)` (`synced_bill_vendor_fkey`) |
| `matched_supplier_id` | uuid | Nullable composite FK -> Supplier `(tenant_id, id)` (`synced_bill_supplier_fkey`, `on delete set null`). Denormalized from vendor |
| `amount` | numeric(18, 4) | Required. Total monetary amount; decimal precision |
| `currency` | text | Required FK -> SupportedCurrency (`supported_currency.code`) |
| `bill_date` | date | Required. Commercial transaction date (QuickBooks `TxnDate`) |
| `provider_status` | enum `synced_bill_status` | Required. Values: `'open'`, `'paid'`, `'void'` |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |

RLS (enabled + forced): All tenant members may `SELECT` (`synced_bill_tenant_select`). The sync worker inserts and updates bills
via `synced_bill_tenant_insert` and `synced_bill_tenant_update`. Unique constraint `synced_bill_provider_id_key` on
`(tenant_id, connection_id, provider_bill_id)` prevents duplicate bill creation. Indexed on `(tenant_id, connection_id, bill_date desc)`
for efficient paginated list queries.

### `PurchaseBillMatch`

Links a `synced_bill` to a `purchase_record` (table `purchase_bill_match`). Enforces a strict 1:1 relationship in both directions:
one bill matches at most one purchase record, and one purchase record matches at most one bill.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `synced_bill_id` | uuid | Required composite FK -> SyncedBill `(tenant_id, id)`. Unique `(tenant_id, synced_bill_id)` enforces 1:1 |
| `purchase_record_id` | uuid | Required composite FK -> PurchaseRecord `(tenant_id, id)`. Unique `(tenant_id, purchase_record_id)` enforces 1:1 |
| `match_method` | enum `match_method` | Required. Values: `'automatic'` (matching service algorithm) or `'manual'` (buyer/owner discrepancy resolution) |
| `matched_by` | uuid | Nullable composite FK -> Membership `(tenant_id, id)`. Check `((match_method = 'manual') = (matched_by is not null))` |
| `matched_at` | timestamptz | Required, default `now()` |

RLS (enabled + forced): All tenant members may `SELECT` (`purchase_bill_match_tenant_select`). There is **no UPDATE policy or grant**:
matches are superseded by inserting a new record and deleting the previous one. `INSERT` is split into two policies:
`purchase_bill_match_automatic_insert` (for the worker's tenant session: `match_method = 'automatic' and matched_by is null`) and
`purchase_bill_match_owner_buyer_insert` (for manual match resolution: `match_method = 'manual' and current_member_role() in ('owner', 'buyer')`).
`DELETE` follows the same symmetry: workers can only delete automatic matches (`purchase_bill_match_automatic_delete`), while manual
matches can only be deleted by an owner or buyer (`purchase_bill_match_owner_buyer_delete`).

### `ReconciliationDiscrepancy`

Flagged reconciliation exceptions requiring human review (table `reconciliation_discrepancy`). Re-evaluated dynamically on each sync:
resolved discrepancies reopen if underlying records are modified, while open discrepancies auto-resolve if conditions clear.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `discrepancy_type` | enum `discrepancy_type` | Required. Values: `'amount_mismatch'`, `'unmatched_bill'`, `'unmatched_purchase'` |
| `synced_bill_id` | uuid | Nullable composite FK -> SyncedBill `(tenant_id, id)` (`reconciliation_discrepancy_bill_fkey`) |
| `purchase_record_id` | uuid | Nullable composite FK -> PurchaseRecord `(tenant_id, id)` (`reconciliation_discrepancy_purchase_record_fkey`) |
| `status` | enum `discrepancy_status` | Required, default `'open'`. Values: `'open'`, `'resolved'` |
| `detected_at` | timestamptz | Required, default `now()`. Initial detection timestamp; immutable |
| `resolved_by` | uuid | Nullable composite FK -> Membership `(tenant_id, id)` (`reconciliation_discrepancy_resolved_by_fkey`) |
| `resolved_at` | timestamptz | Nullable. Timestamp of resolution |
| `resolution_note` | text | Nullable. Reviewer explanation or auto-resolution system note |

Check constraints:
- `reconciliation_discrepancy_shape`: enforces mutual exclusivity across the three discrepancy types:
  - `unmatched_bill`: `synced_bill_id is not null and purchase_record_id is null`
  - `unmatched_purchase`: `purchase_record_id is not null and synced_bill_id is null`
  - `amount_mismatch`: `synced_bill_id is not null and purchase_record_id is not null`
- `reconciliation_discrepancy_resolved_fields`: `check ((status = 'resolved') = (resolved_at is not null) and (resolved_by is null or status = 'resolved'))`.
  Allows `resolved_by` to be `null` when a discrepancy is automatically resolved by the sync worker.

RLS (enabled + forced): All tenant members may `SELECT` (`reconciliation_discrepancy_tenant_select`). Owners and buyers can resolve
discrepancies via `reconciliation_discrepancy_owner_buyer_update`, with column-level grants restricting `UPDATE` strictly to
`(status, resolved_by, resolved_at, resolution_note)`. The sync worker inserts new discrepancies via `reconciliation_discrepancy_worker_insert`
and updates/reopens existing ones via `reconciliation_discrepancy_worker_update` (`current_member_role() IS NULL`).

### Enumerations & Schema Types

- **`accounting_provider`**: `'quickbooks'`
- **`accounting_connection_status`**: `'active'`, `'needs_reauth'`, `'disconnected'`
- **`synced_bill_status`**: `'open'`, `'paid'`, `'void'`
- **`match_method`**: `'automatic'`, `'manual'`
- **`discrepancy_type`**: `'amount_mismatch'`, `'unmatched_bill'`, `'unmatched_purchase'`
- **`discrepancy_status`**: `'open'`, `'resolved'`

### New audit events (chunk R3.1)

- `accounting.connection_created` — external accounting connection was established and authorized by a workspace owner.
- `accounting.connection_disconnected` — external accounting connection was disconnected by a workspace owner (historical records preserved).
- `accounting.sync_started` — accounting synchronization pass was initiated for the tenant connection.
- `accounting.sync_completed` — accounting synchronization pass finished successfully, recording synced vendor count, bill count, and match count.
- `accounting.sync_failed` — accounting synchronization pass failed (e.g. token refresh failure, network exception).
- `accounting.discrepancy_resolved` — reconciliation discrepancy was reviewed and marked resolved by a workspace owner or buyer.

## POS & Inventory Integration (chunk R3.2, `015-pos-inventory-integration`)

This chunk adds a read-only Square POS/inventory connection and persists stock-on-hand plus sales-velocity signals for
matching to `workspace_product`. The connector boundary enforces read-only behavior in code: `PosConnector` exposes
OAuth, account metadata, `list_sales_transactions(since)`, and `list_inventory_levels()`; it has no provider write
method. The sync path consumes those reads, writes ProcurePilot tables, and never changes Smart Compare scoring.

### Schema design note: POS token security, worker writes, and reconnect identity

- **Credential columns**: `pos_connection.access_token` and `refresh_token` are stored encrypted. `authenticated` may
  insert them during owner-led connection creation, but column-level grants withhold token `SELECT` and token `UPDATE`.
  Token reads and refresh writes use a direct `service_role` path constrained by explicit `id` and `tenant_id` filters.
- **Worker/system write sessions**: POS sync writes to `synced_product_signal`, automatic `pos_product_match`, and
  `pos_connection.last_synced_at` through tenant-scoped database sessions. `pos_connection_worker_update` is explicitly
  gated by `current_member_role() is null`; `synced_product_signal` insert/update is tenant-scoped authenticated without
  that additional worker-only role check, matching the migration as shipped. No member-facing endpoint writes
  `synced_product_signal`.
- **Reconnect de-duplication**: `synced_product_signal` is unique on `(tenant_id, external_item_id)` alone. Its
  `pos_connection_id` is the "most recently synced via" pointer and is updated in place on every sync. Because reconnect
  always creates a new `pos_connection` row, including `pos_connection_id` in the signal uniqueness key would duplicate
  every known external item after reconnect and strand old `pos_product_match` records. The shipped design keeps signal
  identity stable across disconnect/reconnect cycles.
- **Provisional velocity disclosure**: `velocity_window_days_observed` records how many days of transaction history the
  current velocity figure reflects. `SyncService` sets it below `velocity_window_days` for partial windows so the UI can
  distinguish a provisional figure from a full-window 30-day average. As of the current FastAPI schema,
  `SyncedProductSignal` does not expose this field even though the database and frontend type/templates support it.

### `PosConnection`

One workspace's authorized link to an external POS/inventory account (table `pos_connection`). Exactly one
non-disconnected connection per tenant is allowed at a time; disconnecting marks the row and preserves history, while
reconnecting inserts a new row.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `provider` | enum `pos_provider` | Required. Provider type, currently `'square'` |
| `external_account_id` | text | Required. Provider merchant/account identifier |
| `external_account_name` | text | Required. Connected account display name; API exposes this as `display_name` |
| `access_token` | text | Required encrypted OAuth access token; not selectable/updatable by `authenticated` |
| `refresh_token` | text | Required encrypted OAuth refresh token; not selectable/updatable by `authenticated` |
| `status` | enum `pos_connection_status` | Required, default `'active'`. Values: `'active'`, `'needs_reauth'`, `'disconnected'` |
| `connected_by` | uuid | Required composite FK -> Membership `(tenant_id, id)` (`pos_connection_membership_fkey`) |
| `connected_at` | timestamptz | Required, default `now()` |
| `last_synced_at` | timestamptz | Nullable. Updated after a successful sync |
| `disconnected_at` | timestamptz | Nullable. Check `((status = 'disconnected') = (disconnected_at is not null))` |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |

RLS (enabled + forced): All tenant members may `SELECT` non-secret connection fields
(`pos_connection_tenant_select`). Owners may insert and update through `pos_connection_owner_insert` and
`pos_connection_owner_update`. The sync worker may update status/last-sync fields through `pos_connection_worker_update`
when `current_member_role() is null`. A partial unique index `pos_connection_one_active_per_tenant` on `(tenant_id)
where disconnected_at is null` enforces one non-disconnected connection per tenant.

### `SyncedProductSignal`

The latest stock-on-hand and/or sales-velocity signal for one external POS catalog item (table
`synced_product_signal`). Absence of a provider signal is stored as `null`, not zero.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `pos_connection_id` | uuid | Required composite FK -> PosConnection `(tenant_id, id)`; most recently synced via this connection |
| `external_item_id` | text | Required provider item identifier |
| `external_item_name` | text | Required provider item name, or the item id when no name is provided |
| `stock_on_hand` | numeric(18, 4) | Nullable. Current inventory quantity when tracked by provider |
| `stock_synced_at` | timestamptz | Nullable. Stamped when inventory data for the item is returned |
| `sales_velocity_per_day` | numeric(18, 4) | Nullable. Computed from transactions in the trailing 30-day sync window |
| `velocity_window_days` | integer | Required, default `30` |
| `velocity_window_days_observed` | integer | Nullable. Actual observed history window; check allows null or values >= 0 |
| `velocity_computed_at` | timestamptz | Nullable. Timestamp for the velocity computation |
| `created_at` / `updated_at` | timestamptz | Audit fields, default `now()` |

RLS (enabled + forced): All tenant members may `SELECT` (`synced_product_signal_tenant_select`). Insert and update are
allowed for `authenticated` sessions scoped to the tenant (`synced_product_signal_tenant_insert` and
`synced_product_signal_tenant_update`). Unique constraint `synced_product_signal_external_item_key` on
`(tenant_id, external_item_id)` is the reconnect-dedup key; `pos_connection_id` is deliberately not part of it.

### `PosProductMatch`

Links a synced POS signal to a `workspace_product` (table `pos_product_match`). Enforces a strict 1:1 relationship in
both directions: one signal matches at most one product, and one product matches at most one signal.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | PK, default `gen_random_uuid()` |
| `tenant_id` | uuid | Required FK -> Tenant (`tenant.id`, `on delete cascade`); RLS key. Unique `(tenant_id, id)` |
| `synced_product_signal_id` | uuid | Required composite FK -> SyncedProductSignal `(tenant_id, id)`. Unique `(tenant_id, synced_product_signal_id)` enforces 1:1 |
| `workspace_product_id` | uuid | Required composite FK -> WorkspaceProduct `(tenant_id, id)`. Unique `(tenant_id, workspace_product_id)` enforces 1:1 |
| `match_method` | enum `match_method` | Required. Values: `'automatic'` or `'manual'` |
| `matched_by` | uuid | Nullable composite FK -> Membership `(tenant_id, id)`. Check `((match_method = 'manual') = (matched_by is not null))` |
| `matched_at` | timestamptz | Required, default `now()` |
| `confidence` | numeric(5, 4) | Nullable; automatic matcher confidence, constrained between 0 and 1 when present |

RLS (enabled + forced): All tenant members may `SELECT` (`pos_product_match_tenant_select`). There is no `UPDATE` policy
or grant. `INSERT` is split between automatic matches (`match_method = 'automatic' and matched_by is null`) and manual
owner/buyer matches (`match_method = 'manual'`, `matched_by = current_membership_id()`, and role in `owner`/`buyer`).
`DELETE` is also split: automatic matches can be deleted when `tenant_id` matches and `match_method = 'automatic'`;
owners and buyers can delete tenant matches through `pos_product_match_owner_buyer_delete`.

### Enumerations & Schema Types

- **`pos_provider`**: `'square'`
- **`pos_connection_status`**: `'active'`, `'needs_reauth'`, `'disconnected'`
- **`match_method`**: reused from chunk R3.1: `'automatic'`, `'manual'`

### New audit events (chunk R3.2)

- `pos.connection_created` — external POS connection was established and authorized by a workspace owner.
- `pos.connection_disconnected` — external POS connection was disconnected by a workspace owner (historical signals preserved).
- `pos.sync_started` — POS synchronization pass acquired its advisory lock and began.
- `pos.sync_completed` — POS synchronization pass finished successfully, recording synced signal count and match count.
- `pos.sync_failed` — POS synchronization pass failed after the advisory lock was acquired.

## R4.0 Forecasting and Reorder Proposals

### `DemandForecast`

Immutable tenant-scoped evidence snapshot in `demand_forecast`. It is keyed by a deterministic
source fingerprint so recomputing the same POS signal does not create duplicate snapshots.

| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Primary key; unique with `tenant_id` |
| `tenant_id` | uuid | Required tenant FK; RLS key |
| `workspace_product_id` | uuid | Composite FK to the matched workspace product |
| `synced_product_signal_id` | uuid | Composite FK to the POS signal used as evidence |
| `source_fingerprint` | text | Unique per tenant and input/model version |
| `model_version` | text | Pinned calculation version, currently `forecast-v1` |
| `horizon_days` | integer | Forecast horizon, currently 14 |
| `source_window_start/end` | date | Evidence interval used by the calculation |
| `observed_history_days` | integer | Actual history disclosed to the reviewer |
| `expected_daily_demand` | numeric(18,4) | Derived quantity in the product base unit |
| `expected_demand` | numeric(18,4) | Expected quantity over the horizon |
| `uncertainty_lower/upper` | numeric(18,4) | Quantity interval, never omitted for a numeric forecast |
| `stock_on_hand` | numeric(18,4) | Stock evidence at forecast time |
| `suggested_quantity` | numeric(18,4) | Non-negative draft quantity; null for insufficient evidence |
| `confidence` | text | `high`, `medium`, or `low` |
| `state` | text | `ready`, `provisional`, or `insufficient_data` |
| `release_posture` | text | Currently constrained to `g3_unmet` |
| `valid_from/valid_until` | timestamptz | Explicit forecast validity period |

RLS is enabled and forced. Authenticated owners/buyers may insert; no update or delete policy
exists, preserving replayable evidence.

### `ReorderProposal`

Tenant-scoped human workflow row in `reorder_proposal` linking one forecast to a draft request.
Statuses are `open`, `prepared`, `dismissed`, and `expired`. Preparation stores the selected
branch and `purchase_request_id`; it does not create a purchase order or bypass approvals.

RLS is enabled and forced. All tenant members may read. Owners and buyers may insert or update,
and every preparation is appended to `audit_event`.

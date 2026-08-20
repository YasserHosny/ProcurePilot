# Phase 1 Data Model: Quotation Inbox and Extraction Review

**Feature**: 003-quotation-inbox-extraction | **Date**: 2026-08-21

Field names follow `docs/architecture/data-dictionary.md` where it is already specific. Where this
chunk adds fields the dictionary lacks, they are marked **[new]** and should be folded back when
the feature lands.

---

## Entities

### `document`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `storage_bucket` **[new]** | text | not null, e.g. `quotation-documents` |
| `storage_path` **[new]** | text | not null, unique, tenant-prefixed |
| `mime_type` | text | not null; accepted PDF, image, Excel or CSV MIME types only |
| `content_hash` | text | nullable until upload completes; sha256 when known |
| `source_channel` **[new]** | enum | `upload`; enum leaves room for future `email`, `api` |
| `status` **[new]** | enum | `uploaded` \| `failed_to_read` |
| `created_at` | timestamptz | not null |
| `created_by` | uuid | not null, FK -> `membership.id` |

`document` stores metadata only. The source file is in Supabase Storage and is protected twice:
Postgres RLS on this row and Storage bucket policy on `storage_path`. A readable `document` row must
not imply a public object URL.

Constraints:
- **unique** `(tenant_id, storage_path)` in addition to global path uniqueness for defensive
  lookup.
- **check** `storage_path like 'tenants/%/quotations/%'`; implementation should additionally
  allocate the path from the verified tenant claim, never client input.
- Duplicate `content_hash` values are allowed in this chunk. Duplicate detection and merging are
  explicitly out of scope.

### `quotation`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `document_id` | uuid | not null, FK -> `document.id` |
| `supplier_id` | uuid | nullable, FK -> `supplier.id`; reviewer confirms per FR-015 |
| `currency` | text | nullable until extracted or reviewed, FK -> `supported_currency.code` |
| `issue_date` | date | nullable |
| `expiry_date` | date | nullable |
| `status` **[new]** | enum | `pending` \| `extracting` \| `extracted` \| `in_review` \| `reviewed` \| `refused` |
| `previous_quotation_id` **[new]** | uuid | nullable, FK -> `quotation.id` |
| `stated_total_amount` **[new]** | numeric(18,4) | nullable |
| `stated_total_currency` **[new]** | text | nullable, FK -> `supported_currency.code` |
| `arithmetic_status` **[new]** | enum | nullable: `not_applicable` \| `reconciled` \| `mismatch` |
| `created_at` | timestamptz | not null |
| `reviewed_by` | uuid | nullable, FK -> `membership.id` |
| `reviewed_at` | timestamptz | nullable |

Constraints:
- **check** `expiry_date is null or issue_date is null or expiry_date >= issue_date`.
- **check** `previous_quotation_id is null or previous_quotation_id <> id`.
- **check** `(stated_total_amount is null) = (stated_total_currency is null)`.
- `supplier_id` may remain null until review. `confirm` refuses if it is still null.
- `reviewed_by` and `reviewed_at` are both present or both absent.

State transitions:

```text
pending -> extracting -> extracted -> in_review -> reviewed
pending -> extracting -> refused
pending -> refused
extracted -> reviewed  (only if all fields pass validation and a human confirms)
```

`reviewed` is the only trusted state. `extracted` means automation completed; it does not mean
downstream commercial data may use the quotation.

### `quotation_line`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_id` | uuid | not null, FK -> `quotation.id` |
| `line_number` | integer | not null, check > 0 |
| `original_text` | text | not null |
| `quantity` | numeric(18,6) | nullable until extracted or corrected, check > 0 when present |
| `pack_count` **[new]** | integer | nullable, check > 0 when present |
| `unit_size` **[new]** | numeric(18,6) | nullable, check > 0 when present |
| `pack_unit` **[new]** | text | nullable, FK -> `supported_base_unit.code` where applicable |
| `unit_price_amount` | numeric(18,4) | nullable |
| `unit_price_currency` | text | nullable, FK -> `supported_currency.code` |
| `vat_rate` **[new]** | numeric(5,4) | nullable, check between 0 and 1 |
| `delivery_fee_amount` | numeric(18,4) | nullable |
| `delivery_fee_currency` | text | nullable, FK -> `supported_currency.code` |
| `discount_amount` | numeric(18,4) | nullable |
| `discount_currency` | text | nullable, FK -> `supported_currency.code` |
| `created_at` | timestamptz | not null |

Money follows chunk 4.2's exact convention: every amount is paired with `<name>_currency`, and both
halves are present or both absent. The API exposes these as `Money { amount, currency }`; the
database stores `numeric(18,4)` plus ISO currency text. No money field is a bare number.

Constraints:
- **unique** `(tenant_id, quotation_id, line_number)`.
- **check** `(unit_price_amount is null) = (unit_price_currency is null)`.
- **check** `(delivery_fee_amount is null) = (delivery_fee_currency is null)`.
- **check** `(discount_amount is null) = (discount_currency is null)`.
- **check** `(pack_count is null) = (unit_size is null)`; `pack_unit` may be null for free-text pack
  descriptions the reviewer has not normalized yet.

### `field_extraction`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_id` | uuid | not null, FK -> `quotation.id` |
| `entity_type` **[new]** | enum | `quotation` \| `quotation_line` |
| `entity_id` **[new]** | uuid | not null; points to `quotation.id` or `quotation_line.id` by `entity_type` |
| `field_name` **[new]** | text | not null, e.g. `supplier_id`, `currency`, `unit_price`, `quantity` |
| `extracted_value` **[new]** | jsonb | not null; original machine/structured value |
| `confidence` | numeric(5,4) | not null, check 0 <= confidence <= 1 |
| `source_page` **[new]** | integer | nullable, check > 0 |
| `source_region` **[new]** | jsonb | nullable; page-relative bounding polygon/box |
| `extraction_method` **[new]** | enum | `structured_parse` \| `bedrock` \| `azure_di` |
| `model_version` **[new]** | text | not null; parser/rule version for `structured_parse` |
| `corrected_value` **[new]** | jsonb | nullable |
| `corrected_by` **[new]** | uuid | nullable, FK -> `membership.id` |
| `corrected_at` **[new]** | timestamptz | nullable |
| `created_at` | timestamptz | not null |

This is the constitutional evidence record. Confidence and source region are per field, not per
line and not per quotation. Human correction is distinct from the original extracted value: review
does not overwrite the evidence it is reviewing.

Constraints:
- **unique** `(tenant_id, entity_type, entity_id, field_name)`.
- **check** `source_region` is null or contains a supported shape (`bbox` or `polygon`) in
  implementation validation.
- **check** `corrected_by` and `corrected_at` are both present or both absent.
- `entity_id` cannot be protected by a simple FK because it is polymorphic; writes must validate
  that the target entity belongs to the same tenant and quotation in the same transaction.

### `extraction_job`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_id` | uuid | not null, FK -> `quotation.id` |
| `status` **[new]** | enum | `queued` \| `running` \| `succeeded` \| `failed` |
| `attempted_provider` **[new]** | enum | nullable: `structured_parse` \| `bedrock` \| `azure_di` |
| `error` **[new]** | jsonb | nullable; code/message/details safe for tenant display |
| `created_at` | timestamptz | not null |
| `started_at` **[new]** | timestamptz | nullable |
| `completed_at` | timestamptz | nullable |

`extraction_job` is the persisted job resource behind `/jobs/{job_id}`. Redis is not the source of
truth for user-visible state; it only delivers work to the worker.

Constraints:
- **unique partial** `(tenant_id, quotation_id) where status in ('queued', 'running')` - one active
  extraction per quotation.
- `completed_at` is present only for terminal states.

### `review_task`

| Field | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `tenant_id` | uuid | not null, FK -> `tenant.id` - RLS key |
| `quotation_id` | uuid | not null, FK -> `quotation.id` |
| `status` **[new]** | enum | `open` \| `in_progress` \| `resolved` |
| `priority` **[new]** | enum | `low` \| `normal` \| `high` |
| `reason` **[new]** | enum | `low_confidence` \| `arithmetic_mismatch` \| `read_failure` \| `review_required` |
| `created_at` | timestamptz | not null |
| `resolved_at` | timestamptz | nullable |

`review_task` is not a view over quotations. It is the standalone review queue resource required by
FR-019 and Constitution Principle III.

Constraints:
- **unique partial** `(tenant_id, quotation_id) where status in ('open', 'in_progress')` - one
  outstanding task per quotation.
- `resolved_at` is present only when `status = 'resolved'`.

---

## Relationships

```text
tenant        1--* document
tenant        1--* quotation
document      1--* quotation          (usually one in this chunk, but not constrained)
supplier      1--* quotation          (nullable until review)
quotation     1--* quotation_line
quotation     1--* field_extraction
quotation     1--* extraction_job
quotation     1--* review_task
quotation     0..1 -- 0..* quotation  (previous_quotation_id version link)
membership    1--* document           (created_by)
membership    1--* quotation          (reviewed_by)
membership    1--* field_extraction   (corrected_by)
```

---

## Row-level security

Every table in this chunk carries `tenant_id` and gets the same pattern:

```sql
alter table <t> enable row level security;
alter table <t> force  row level security;
create policy tenant_isolation on <t>
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());
```

This applies to `document`, `quotation`, `quotation_line`, `field_extraction`, `extraction_job` and
`review_task`. `USING` and `WITH CHECK` are both required; `FORCE` is required because table owners
otherwise bypass RLS.

**Storage enforcement**: `document` has a second isolation boundary. The underlying Supabase
Storage object must be in a private quotation-documents bucket, under a tenant-prefixed path, with
Storage policies that compare the path tenant segment and related document row to the caller's JWT
tenant claim. Postgres RLS alone does not protect file bytes.

**Role gate**: owner and buyer may upload, extract, correct and confirm. Branch manager, approver
and viewer may read only unless a later spec grants more. Cross-tenant reads return 404-style "not
found", not 403.

---

## Migration sketch

Latest existing migration is `supabase/migrations/20260819000016_catalogue_rls.sql`; this chunk
continues sequentially. These files are sketches only; implementation creates the SQL later.

| File | Contents |
|---|---|
| `20260819000017_quotation_reference.sql` | enums for document source/status, quotation status, extraction method, job status, review status/priority/reason and arithmetic status; no tenant data |
| `20260819000018_documents_quotations.sql` | `document`, `quotation`, `quotation_line`; FKs to `tenant`, `membership`, `supplier`, `supported_currency`, `supported_base_unit`; money pair checks |
| `20260819000019_extraction_review_jobs.sql` | `field_extraction`, `extraction_job`, `review_task`; uniqueness constraints; correction metadata checks |
| `20260819000020_quotation_storage.sql` | Supabase Storage bucket and policies for tenant-scoped quotation document objects |
| `20260819000021_quotation_rls.sql` | `ENABLE` + `FORCE` RLS and tenant-isolation policies for all chunk 4.3 tenant tables in one file |

The RLS migration is last, matching chunk 4.2's approach: tables and constraints first, then all
tenant policies together for review.

---

## Validation rules traced to requirements

| Rule | Source |
|---|---|
| Accepted document MIME types only; refused before extraction | FR-001, FR-004 |
| Document stores storage path, MIME type, content hash and source channel | FR-002 |
| Quotation lifecycle includes pending, extracting, extracted, in_review, reviewed, refused | FR-003 |
| Structured CSV/Excel records still get per-field extraction records | FR-006, FR-008, FR-009 |
| Every extracted field has confidence, source location, method and model version | FR-008, FR-009 |
| Corrections are distinct from original extracted values | FR-013 |
| Supplier must be confirmed before quotation can become reviewed | FR-015 |
| Only `reviewed` quotations are trusted downstream | FR-016 |
| Reviewer identity and timestamp recorded | FR-017 |
| Extraction runs as a pollable async job | FR-018 |
| Review queue is a standalone `review_task` table | FR-019 |
| Re-quotes link through `previous_quotation_id` and never replace history | FR-020 |
| Monetary fields use amount+currency pairs | FR-021 |
| Unreadable documents are `failed_to_read` / `refused`, not pending review | FR-022 |

---

## Notes for later chunks

- No product matching here. `quotation_line` intentionally has no `workspace_product_id`.
- No landed-cost computation, offer comparison, basket building or savings ledger here.
- Email/API ingestion is reserved for later. `source_channel` only leaves enum room.
- Duplicate-document detection is absent by design.
- Matching may later consume only `quotation.status = 'reviewed'` rows.

-- 20260819000018_documents_quotations.sql — task T008
--
-- Document metadata, the quotation lifecycle, and its line items.

-- ---------------------------------------------------------------------------
-- document — metadata only. The file itself lives in Supabase Storage and is
-- protected twice: this row's RLS, and the Storage bucket policy added in
-- migration 20260819000020. A readable row must not imply a public object URL.
-- ---------------------------------------------------------------------------
create table if not exists document (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenant(id) on delete cascade,

  storage_bucket text not null,
  storage_path   text not null,
  mime_type      text not null check (mime_type in (
    'application/pdf', 'image/png', 'image/jpeg', 'image/tiff',
    'text/csv', 'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  )),
  -- Nullable until the client's direct-to-storage upload completes and the hash is known.
  content_hash   text,
  source_channel document_source_channel not null default 'upload',
  status         document_status not null default 'uploaded',

  created_at     timestamptz not null default now(),
  created_by     uuid not null references membership(id),

  constraint document_storage_path_tenant_prefixed
    check (storage_path like 'tenants/%/quotations/%')
);

-- Duplicate content_hash values are allowed in this chunk — duplicate detection and merging are
-- explicitly out of scope (see spec.md Edge Cases).
create unique index if not exists document_tenant_storage_path_idx
  on document (tenant_id, storage_path);
create index if not exists document_tenant_idx on document (tenant_id);

-- ---------------------------------------------------------------------------
-- quotation — one supplier's offer, tied to the document it came from.
-- `reviewed` is the only trusted state; `extracted` means automation completed, nothing more.
-- ---------------------------------------------------------------------------
create table if not exists quotation (
  id                     uuid primary key default gen_random_uuid(),
  tenant_id              uuid not null references tenant(id) on delete cascade,
  document_id            uuid not null references document(id) on delete cascade,
  -- Nullable until the reviewer confirms it (FR-015). Confirm refuses while still null.
  supplier_id            uuid references supplier(id),
  currency               text references supported_currency(code),
  issue_date             date,
  expiry_date            date,
  status                 quotation_status not null default 'pending',
  previous_quotation_id  uuid references quotation(id),
  stated_total_amount    numeric(18, 4),
  stated_total_currency  text references supported_currency(code),
  arithmetic_status      arithmetic_status,

  created_at             timestamptz not null default now(),
  reviewed_by            uuid references membership(id),
  reviewed_at            timestamptz,

  constraint quotation_expiry_after_issue
    check (expiry_date is null or issue_date is null or expiry_date >= issue_date),
  constraint quotation_previous_not_self
    check (previous_quotation_id is null or previous_quotation_id <> id),
  constraint quotation_stated_total_has_currency
    check ((stated_total_amount is null) = (stated_total_currency is null)),
  constraint quotation_reviewed_fields_together
    check ((reviewed_by is null) = (reviewed_at is null))
);

create index if not exists quotation_tenant_idx on quotation (tenant_id);
create index if not exists quotation_document_idx on quotation (document_id);
create index if not exists quotation_previous_idx on quotation (previous_quotation_id);

comment on column quotation.status is
  'reviewed is the ONLY trusted state (FR-016, Constitution Principle III). extracted means
   automation finished, not that a human authorised anything.';

-- ---------------------------------------------------------------------------
-- quotation_line — one line item, as extracted, plus whatever a reviewer corrected.
-- Money follows chunk 4.2''s exact convention: amount + explicit currency, both or neither.
-- ---------------------------------------------------------------------------
create table if not exists quotation_line (
  id                     uuid primary key default gen_random_uuid(),
  tenant_id              uuid not null references tenant(id) on delete cascade,
  quotation_id           uuid not null references quotation(id) on delete cascade,

  line_number            integer not null check (line_number > 0),
  original_text          text not null,

  quantity               numeric(18, 6) check (quantity is null or quantity > 0),
  pack_count             integer check (pack_count is null or pack_count > 0),
  unit_size              numeric(18, 6) check (unit_size is null or unit_size > 0),
  pack_unit              text references supported_base_unit(code),

  unit_price_amount      numeric(18, 4),
  unit_price_currency    text references supported_currency(code),
  vat_rate               numeric(5, 4) check (vat_rate is null or (vat_rate between 0 and 1)),
  delivery_fee_amount    numeric(18, 4),
  delivery_fee_currency  text references supported_currency(code),
  discount_amount        numeric(18, 4),
  discount_currency      text references supported_currency(code),

  created_at             timestamptz not null default now(),

  constraint quotation_line_unit_price_has_currency
    check ((unit_price_amount is null) = (unit_price_currency is null)),
  constraint quotation_line_delivery_fee_has_currency
    check ((delivery_fee_amount is null) = (delivery_fee_currency is null)),
  constraint quotation_line_discount_has_currency
    check ((discount_amount is null) = (discount_currency is null)),
  constraint quotation_line_pack_fields_together
    check ((pack_count is null) = (unit_size is null))
);

create unique index if not exists quotation_line_unique_number
  on quotation_line (tenant_id, quotation_id, line_number);
create index if not exists quotation_line_tenant_idx on quotation_line (tenant_id);
create index if not exists quotation_line_quotation_idx on quotation_line (quotation_id);

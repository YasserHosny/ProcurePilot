-- 20260821000031_purchase_saving_records.sql
--
-- purchase_record — the factual outcome capture: what was ordered, from whom, at what price, and
-- with what delivery result. saving_record — the computed, eventually-verified savings-ledger row
-- paired one-to-one with it. Together these are the product's second append-only entity (after
-- audit_event), and the whole reason every prior chunk exists: proof of money saved.
--
-- See specs/006-value-proof-launch/data-model.md and research.md R1 for the exact semantics:
-- baseline/actual/delta are captured at RECORD time from chunk 4.5's existing price-history read
-- model (no second baseline computation); verification (0035) later changes only status metadata,
-- never recomputes anything.

create table if not exists purchase_record (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  workspace_product_id  uuid not null references workspace_product(id),
  supplier_id           uuid references supplier(id),
  quotation_line_id     uuid references quotation_line(id),
  match_decision_id     uuid references match_decision(id),
  landed_cost_id        uuid references landed_cost(id),
  recorded_by           uuid not null references membership(id),

  quantity              numeric(18, 6) not null check (quantity > 0),
  base_unit             text not null references supported_base_unit(code),

  unit_price_amount     numeric(18, 4) not null,
  unit_price_currency   text not null references supported_currency(code),
  total_paid_amount     numeric(18, 4) not null,
  total_paid_currency   text not null references supported_currency(code),

  delivery_result       purchase_delivery_result not null,
  ordered_at            timestamptz,
  delivered_at          timestamptz,
  recorded_at           timestamptz not null default now(),
  notes                 text,

  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  constraint purchase_record_single_currency
    check (unit_price_currency = total_paid_currency),
  constraint purchase_record_delivery_after_order
    check (delivered_at is null or ordered_at is null or delivered_at >= ordered_at)
);

create index if not exists purchase_record_tenant_product_idx
  on purchase_record (tenant_id, workspace_product_id, recorded_at desc);
create index if not exists purchase_record_tenant_supplier_idx
  on purchase_record (tenant_id, supplier_id, recorded_at desc);

comment on table purchase_record is
  'What was actually ordered, delivered, and paid (FR-001). Editable only while its paired
   saving_record is pending — enforced by 20260821000035_saving_record_immutability.sql''s second
   trigger, not by this table alone. See data-model.md.';

create table if not exists saving_record (
  id                              uuid primary key default gen_random_uuid(),
  tenant_id                       uuid not null references tenant(id) on delete cascade,
  purchase_record_id              uuid not null references purchase_record(id) on delete cascade,
  workspace_product_id            uuid not null references workspace_product(id),
  supplier_id                     uuid references supplier(id),

  status                          saving_record_status not null default 'pending',

  baseline_policy                 baseline_policy not null,
  baseline_source_landed_cost_ids uuid[] not null default '{}',
  baseline_unit_price_amount      numeric(18, 4),
  baseline_unit_price_currency    text references supported_currency(code),
  baseline_value_amount           numeric(18, 4),
  baseline_value_currency         text references supported_currency(code),

  actual_value_amount             numeric(18, 4) not null,
  actual_value_currency           text not null references supported_currency(code),

  delta_amount                    numeric(18, 4),
  delta_currency                  text references supported_currency(code),

  calculation_version             text not null,
  calculation_inputs               jsonb not null,

  recorded_by                     uuid not null references membership(id),
  recorded_at                     timestamptz not null default now(),
  verified_by                     uuid references membership(id),
  verified_at                     timestamptz,

  created_at                      timestamptz not null default now(),

  constraint saving_record_unique_purchase unique (tenant_id, purchase_record_id),
  constraint saving_record_verified_metadata_together
    check ((status = 'verified') = (verified_at is not null and verified_by is not null)),
  constraint saving_record_baseline_amount_has_currency
    check ((baseline_unit_price_amount is null) = (baseline_unit_price_currency is null)),
  constraint saving_record_baseline_value_has_currency
    check ((baseline_value_amount is null) = (baseline_value_currency is null)),
  constraint saving_record_delta_has_currency
    check ((delta_amount is null) = (delta_currency is null)),
  constraint saving_record_none_available_has_no_baseline
    check (
      (baseline_policy <> 'none_available')
      or (baseline_value_amount is null and delta_amount is null)
    ),
  constraint saving_record_currencies_match
    check (
      baseline_value_currency is null
      or (baseline_value_currency = actual_value_currency
          and (delta_currency is null or delta_currency = actual_value_currency))
    )
);

create index if not exists saving_record_tenant_status_idx
  on saving_record (tenant_id, status, recorded_at desc);
create index if not exists saving_record_tenant_supplier_idx
  on saving_record (tenant_id, supplier_id, recorded_at desc);
create index if not exists saving_record_tenant_product_idx
  on saving_record (tenant_id, workspace_product_id, recorded_at desc);

comment on table saving_record is
  'The literal proof of money saved (FR-002-FR-006). baseline/actual/delta are captured once, at
   record time, from chunk 4.5''s existing price-history read model — never recomputed on
   verification. Immutable once verified: see 20260821000035_saving_record_immutability.sql.
   See research.md R1 and R7.';

-- 20260914000001_supplier_commercial_term.sql
--
-- R2.4 supplier commercial terms. This is versioned supplier data used by the advisory basket
-- optimiser: minimum order value, delivery fee, free-delivery threshold, and quantity tiers.
-- It extends supplier data without overwriting the earlier simple supplier money columns.

alter table supplier add constraint supplier_tenant_id_key unique (tenant_id, id);

create table if not exists supplier_commercial_term (
  id                              uuid primary key default gen_random_uuid(),
  tenant_id                       uuid not null references tenant(id) on delete cascade,
  supplier_id                     uuid not null,
  effective_from                  timestamptz not null default now(),
  effective_to                    timestamptz,

  minimum_order_value_amount      numeric(18, 4),
  minimum_order_value_currency    text references supported_currency(code),
  delivery_fee_amount             numeric(18, 4),
  delivery_fee_currency           text references supported_currency(code),
  free_delivery_threshold_amount  numeric(18, 4),
  free_delivery_threshold_currency text references supported_currency(code),

  quantity_tiers                  jsonb not null default '[]'::jsonb,
  rule_version                    text not null default 'supplier-commercial-terms-v1',
  created_by_membership_id        uuid not null,
  created_at                      timestamptz not null default now(),

  constraint supplier_commercial_term_tenant_id_key unique (tenant_id, id),
  constraint supplier_commercial_term_supplier_fkey
    foreign key (tenant_id, supplier_id) references supplier (tenant_id, id) on delete cascade,
  constraint supplier_commercial_term_created_by_fkey
    foreign key (tenant_id, created_by_membership_id) references membership (tenant_id, id),
  constraint supplier_commercial_term_effective_window
    check (effective_to is null or effective_to > effective_from),
  constraint supplier_commercial_term_mov_money_pair
    check ((minimum_order_value_amount is null) = (minimum_order_value_currency is null)),
  constraint supplier_commercial_term_delivery_fee_money_pair
    check ((delivery_fee_amount is null) = (delivery_fee_currency is null)),
  constraint supplier_commercial_term_free_delivery_money_pair
    check ((free_delivery_threshold_amount is null) = (free_delivery_threshold_currency is null)),
  constraint supplier_commercial_term_quantity_tiers_array
    check (jsonb_typeof(quantity_tiers) = 'array')
);

create index if not exists supplier_commercial_term_tenant_supplier_idx
  on supplier_commercial_term (tenant_id, supplier_id, effective_from desc);

comment on table supplier_commercial_term is
  'Versioned supplier commercial terms for R2.4 advisory optimisation. Money values are paired
   with currency; quantity tiers are JSON snapshots validated by the API and replayed by the
   optimiser.';

alter table supplier_commercial_term enable row level security;
alter table supplier_commercial_term force  row level security;

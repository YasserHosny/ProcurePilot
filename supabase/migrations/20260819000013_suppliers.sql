-- 20260819000013_suppliers.sql — task T003
--
-- Suppliers, and the first money in the product.

do $$ begin
  create type supplier_status as enum ('active', 'preferred', 'blocked', 'archived');
exception when duplicate_object then null; end $$;

create table if not exists supplier (
  id             uuid primary key default gen_random_uuid(),
  tenant_id      uuid not null references tenant(id) on delete cascade,
  name           text not null check (char_length(name) between 1 and 200),
  payment_terms  text,
  lead_time_days integer check (lead_time_days is null or lead_time_days >= 0),

  -- MONEY: an amount and its currency, always together, never a bare number.
  --
  -- Constitution Principle VII, and the reason it exists. These are the first monetary columns in
  -- the product, and retrofitting a currency onto stored amounts means a migration over financial
  -- data — the most expensive kind and the easiest to get wrong under pressure.
  --
  -- numeric(18,4), not float: the same exactness argument as pack quantities, with more at stake.
  minimum_order_value_amount   numeric(18, 4),
  minimum_order_value_currency text references supported_currency(code),
  delivery_fee_amount          numeric(18, 4),
  delivery_fee_currency        text references supported_currency(code),

  -- Populated from recorded outcomes in a later chunk. Null here, and honestly null rather than
  -- defaulted to something flattering.
  reliability_score numeric(4, 3) check (reliability_score is null or (reliability_score between 0 and 1)),

  status     supplier_status not null default 'active',
  created_at timestamptz not null default now(),

  -- The constraints that carry Principle VII. Both halves of a money value or neither.
  --
  -- Without these, a nullable currency column eventually holds nulls, and something downstream
  -- infers a default — which is how a supplier's GBP 500 minimum silently becomes a plausible,
  -- wrong SAR 500. There is no default currency in this product and inferring one is the failure
  -- mode, not the convenience.
  constraint supplier_mov_has_currency
    check ((minimum_order_value_amount is null) = (minimum_order_value_currency is null)),
  constraint supplier_delivery_fee_has_currency
    check ((delivery_fee_amount is null) = (delivery_fee_currency is null))
);

create index if not exists supplier_tenant_idx on supplier (tenant_id);
create index if not exists supplier_status_idx on supplier (tenant_id, status) where status <> 'archived';

-- Now that supplier exists, close the forward reference left in the products migration.
alter table workspace_product
  drop constraint if exists workspace_product_preferred_supplier_fkey;
alter table workspace_product
  add constraint workspace_product_preferred_supplier_fkey
  foreign key (preferred_supplier_id) references supplier(id) on delete set null;

comment on constraint supplier_mov_has_currency on supplier is
  'An amount without a currency is not a price, it is a number. Refused outright (FR-011, SC-006).';

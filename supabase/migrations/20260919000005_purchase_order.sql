-- 20260919000005_purchase_order.sql — R3.3 internal order evidence foundation
--
-- Purchase orders are internal evidence only.  No column or policy in this migration permits
-- an order to be sent to, changed in, or cancelled through an external provider.

create type purchase_order_status as enum (
  'draft', 'submitted', 'confirmed', 'partially_received', 'received', 'cancelled', 'closed'
);

create table if not exists purchase_order (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  order_number               text not null check (char_length(order_number) between 1 and 100),
  supplier_id                uuid not null,
  status                     purchase_order_status not null default 'draft',
  order_date                 date not null,
  expected_delivery_date     date,

  total_amount               numeric(18, 4) not null default 0 check (total_amount >= 0),
  total_currency             text not null references supported_currency(code),
  tax_amount                 numeric(18, 4) not null default 0 check (tax_amount >= 0),
  tax_currency               text not null references supported_currency(code),

  source_kind                text not null default 'manual'
    check (source_kind in ('manual', 'import', 'provider')),
  source_reference           text not null check (char_length(source_reference) between 1 and 500),
  source_hash                text,
  created_by                 uuid not null,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint purchase_order_supplier_fkey
    foreign key (tenant_id, supplier_id) references supplier (tenant_id, id),
  constraint purchase_order_created_by_fkey
    foreign key (tenant_id, created_by) references membership (tenant_id, id),
  constraint purchase_order_tenant_id_key unique (tenant_id, id),
  constraint purchase_order_number_key unique (tenant_id, order_number),
  constraint purchase_order_tax_currency_consistent
    check (tax_amount = 0 or tax_currency = total_currency),
  constraint purchase_order_expected_delivery_after_order
    check (expected_delivery_date is null or expected_delivery_date >= order_date)
);

create table if not exists purchase_order_line (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  purchase_order_id         uuid not null,
  line_number                integer not null check (line_number > 0),
  workspace_product_id      uuid,
  description                text not null check (char_length(description) between 1 and 500),

  ordered_quantity           numeric(18, 6) not null check (ordered_quantity >= 0),
  base_unit                  text not null references supported_base_unit(code),
  unit_price_amount          numeric(18, 4) not null check (unit_price_amount >= 0),
  unit_price_currency        text not null references supported_currency(code),
  tax_amount                 numeric(18, 4) not null default 0 check (tax_amount >= 0),
  tax_currency               text not null references supported_currency(code),
  line_total_amount          numeric(18, 4) not null default 0 check (line_total_amount >= 0),
  line_total_currency        text not null references supported_currency(code),

  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint purchase_order_line_order_fkey
    foreign key (tenant_id, purchase_order_id) references purchase_order (tenant_id, id)
    on delete cascade,
  constraint purchase_order_line_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id),
  constraint purchase_order_line_tenant_id_key unique (tenant_id, id),
  constraint purchase_order_line_order_id_key unique (tenant_id, purchase_order_id, id),
  constraint purchase_order_line_number_key unique (tenant_id, purchase_order_id, line_number),
  constraint purchase_order_line_tax_currency_consistent
    check (tax_amount = 0 or tax_currency = line_total_currency),
  constraint purchase_order_line_total_currency_consistent
    check (line_total_currency = unit_price_currency)
);

create index if not exists purchase_order_tenant_status_idx
  on purchase_order (tenant_id, status, order_date desc);
create index if not exists purchase_order_supplier_idx
  on purchase_order (tenant_id, supplier_id, order_date desc);
create index if not exists purchase_order_line_order_idx
  on purchase_order_line (tenant_id, purchase_order_id, line_number);

comment on table purchase_order is
  'An internal, human-authorized purchase order and its immutable source reference (R3.3).';
comment on table purchase_order_line is
  'A tenant-pinned purchase-order line. Prices, tax, totals, and their currencies are explicit.';

alter table purchase_order enable row level security;
alter table purchase_order force row level security;
alter table purchase_order_line enable row level security;
alter table purchase_order_line force row level security;

create policy purchase_order_tenant_select on purchase_order
  for select to authenticated using (tenant_id = current_tenant_id());
create policy purchase_order_owner_buyer_insert on purchase_order
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
create policy purchase_order_owner_buyer_update on purchase_order
  for update to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'))
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

create policy purchase_order_line_tenant_select on purchase_order_line
  for select to authenticated using (tenant_id = current_tenant_id());
create policy purchase_order_line_owner_buyer_insert on purchase_order_line
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
create policy purchase_order_line_owner_buyer_update on purchase_order_line
  for update to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'))
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

grant select, insert, update on purchase_order, purchase_order_line to authenticated;
grant select, insert, update on purchase_order, purchase_order_line to service_role;

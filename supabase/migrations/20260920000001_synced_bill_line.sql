-- Persist normalized accounting bill evidence for R3.3 matching.

alter table synced_bill
  add column if not exists provider_order_reference text,
  add column if not exists document_references jsonb not null default '[]'::jsonb;

create table if not exists synced_bill_line (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  synced_bill_id             uuid not null,
  line_number                integer not null,
  provider_line_reference    text,
  provider_product_reference text,
  description                text not null,
  quantity                   numeric(18, 6) not null,
  unit_price_amount          numeric(18, 4) not null,
  unit_price_currency        text not null references supported_currency(code),
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint synced_bill_line_bill_fkey
    foreign key (tenant_id, synced_bill_id) references synced_bill (tenant_id, id)
    on delete cascade,
  constraint synced_bill_line_tenant_id_key unique (tenant_id, id),
  constraint synced_bill_line_number_positive check (line_number > 0),
  constraint synced_bill_line_quantity_non_negative check (quantity >= 0),
  constraint synced_bill_line_price_non_negative check (unit_price_amount >= 0),
  constraint synced_bill_line_unique_number unique (tenant_id, synced_bill_id, line_number)
);

create index if not exists synced_bill_line_bill_idx
  on synced_bill_line (tenant_id, synced_bill_id, line_number);

alter table synced_bill_line enable row level security;
alter table synced_bill_line force row level security;

create policy synced_bill_line_tenant_select on synced_bill_line
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy synced_bill_line_tenant_insert on synced_bill_line
  for insert to authenticated
  with check (tenant_id = current_tenant_id());

create policy synced_bill_line_tenant_update on synced_bill_line
  for update to authenticated
  using (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

create policy synced_bill_line_tenant_delete on synced_bill_line
  for delete to authenticated
  using (tenant_id = current_tenant_id());

grant select, insert, update, delete on synced_bill_line to authenticated;
grant select, insert, update, delete on synced_bill_line to service_role;

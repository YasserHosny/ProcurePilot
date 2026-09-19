-- 20260919000006_supplier_confirmation_delivery_receipt.sql — R3.3 receipt evidence
--
-- Confirmations and receipts are append-only evidence from the application perspective.  There is
-- deliberately no authenticated UPDATE or DELETE grant: later confirmations/receipts add history
-- rather than overwriting what was previously observed.

create table if not exists supplier_confirmation (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  purchase_order_id         uuid not null,
  supplier_reference         text not null check (char_length(supplier_reference) between 1 and 200),
  confirmed_at               timestamptz not null,
  expected_delivery_date     date,
  source_kind                text not null default 'manual'
    check (source_kind in ('manual', 'import', 'provider')),
  source_reference           text not null check (char_length(source_reference) between 1 and 500),
  source_hash                text,
  recorded_by                uuid not null,
  created_at                 timestamptz not null default now(),

  constraint supplier_confirmation_order_fkey
    foreign key (tenant_id, purchase_order_id) references purchase_order (tenant_id, id),
  constraint supplier_confirmation_recorded_by_fkey
    foreign key (tenant_id, recorded_by) references membership (tenant_id, id),
  constraint supplier_confirmation_tenant_id_key unique (tenant_id, id),
  constraint supplier_confirmation_order_id_key unique (tenant_id, id, purchase_order_id)
);

create table if not exists supplier_confirmation_line (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  supplier_confirmation_id  uuid not null,
  purchase_order_id         uuid not null,
  purchase_order_line_id    uuid not null,
  confirmed_quantity         numeric(18, 6) not null check (confirmed_quantity >= 0),
  confirmed_unit_price_amount numeric(18, 4),
  confirmed_unit_price_currency text references supported_currency(code),
  created_at                 timestamptz not null default now(),

  constraint supplier_confirmation_line_confirmation_fkey
    foreign key (tenant_id, supplier_confirmation_id)
    references supplier_confirmation (tenant_id, id) on delete cascade,
  constraint supplier_confirmation_line_confirmation_order_fkey
    foreign key (tenant_id, supplier_confirmation_id, purchase_order_id)
    references supplier_confirmation (tenant_id, id, purchase_order_id) on delete cascade,
  constraint supplier_confirmation_line_order_line_fkey
    foreign key (tenant_id, purchase_order_id, purchase_order_line_id)
    references purchase_order_line (tenant_id, purchase_order_id, id),
  constraint supplier_confirmation_line_tenant_id_key unique (tenant_id, id),
  constraint supplier_confirmation_line_one_line_per_confirmation
    unique (tenant_id, supplier_confirmation_id, purchase_order_line_id),
  constraint supplier_confirmation_line_price_currency_pair
    check ((confirmed_unit_price_amount is null) = (confirmed_unit_price_currency is null)),
  constraint supplier_confirmation_line_price_non_negative
    check (confirmed_unit_price_amount is null or confirmed_unit_price_amount >= 0)
);

create table if not exists delivery_receipt (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  purchase_order_id         uuid not null,
  receipt_reference          text not null check (char_length(receipt_reference) between 1 and 200),
  receipt_date               date not null,
  received_by                uuid not null,
  source_kind                text not null default 'manual'
    check (source_kind in ('manual', 'import', 'provider')),
  source_reference           text not null check (char_length(source_reference) between 1 and 500),
  source_hash                text,
  created_at                 timestamptz not null default now(),

  constraint delivery_receipt_order_fkey
    foreign key (tenant_id, purchase_order_id) references purchase_order (tenant_id, id),
  constraint delivery_receipt_received_by_fkey
    foreign key (tenant_id, received_by) references membership (tenant_id, id),
  constraint delivery_receipt_tenant_id_key unique (tenant_id, id),
  constraint delivery_receipt_order_id_key unique (tenant_id, id, purchase_order_id),
  constraint delivery_receipt_reference_key unique (tenant_id, receipt_reference)
);

create table if not exists delivery_receipt_line (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  delivery_receipt_id       uuid not null,
  purchase_order_id         uuid not null,
  purchase_order_line_id    uuid not null,
  received_quantity           numeric(18, 6) not null check (received_quantity >= 0),
  created_at                 timestamptz not null default now(),

  constraint delivery_receipt_line_receipt_fkey
    foreign key (tenant_id, delivery_receipt_id) references delivery_receipt (tenant_id, id)
    on delete cascade,
  constraint delivery_receipt_line_receipt_order_fkey
    foreign key (tenant_id, delivery_receipt_id, purchase_order_id)
    references delivery_receipt (tenant_id, id, purchase_order_id) on delete cascade,
  constraint delivery_receipt_line_order_line_fkey
    foreign key (tenant_id, purchase_order_id, purchase_order_line_id)
    references purchase_order_line (tenant_id, purchase_order_id, id),
  constraint delivery_receipt_line_tenant_id_key unique (tenant_id, id),
  constraint delivery_receipt_line_one_line_per_receipt
    unique (tenant_id, delivery_receipt_id, purchase_order_line_id)
);

create index if not exists supplier_confirmation_order_idx
  on supplier_confirmation (tenant_id, purchase_order_id, confirmed_at desc);
create index if not exists supplier_confirmation_line_order_line_idx
  on supplier_confirmation_line (tenant_id, purchase_order_line_id, created_at desc);
create index if not exists delivery_receipt_order_idx
  on delivery_receipt (tenant_id, purchase_order_id, receipt_date desc);
create index if not exists delivery_receipt_line_order_line_idx
  on delivery_receipt_line (tenant_id, purchase_order_line_id, created_at desc);

comment on table delivery_receipt is
  'An append-only delivery observation. Multiple receipts preserve receipt history; absence is not zero.';

alter table supplier_confirmation enable row level security;
alter table supplier_confirmation force row level security;
alter table supplier_confirmation_line enable row level security;
alter table supplier_confirmation_line force row level security;
alter table delivery_receipt enable row level security;
alter table delivery_receipt force row level security;
alter table delivery_receipt_line enable row level security;
alter table delivery_receipt_line force row level security;

create policy supplier_confirmation_tenant_select on supplier_confirmation
  for select to authenticated using (tenant_id = current_tenant_id());
create policy supplier_confirmation_owner_buyer_insert on supplier_confirmation
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
create policy supplier_confirmation_line_tenant_select on supplier_confirmation_line
  for select to authenticated using (tenant_id = current_tenant_id());
create policy supplier_confirmation_line_owner_buyer_insert on supplier_confirmation_line
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
create policy delivery_receipt_tenant_select on delivery_receipt
  for select to authenticated using (tenant_id = current_tenant_id());
create policy delivery_receipt_owner_buyer_insert on delivery_receipt
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
create policy delivery_receipt_line_tenant_select on delivery_receipt_line
  for select to authenticated using (tenant_id = current_tenant_id());
create policy delivery_receipt_line_owner_buyer_insert on delivery_receipt_line
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

-- Evidence history is append-only for both normal members and the sync/service role.  Explicit
-- revokes make that contract survive default-role or future grant changes.
revoke update, delete, truncate on supplier_confirmation, supplier_confirmation_line,
  delivery_receipt, delivery_receipt_line from authenticated, service_role;

grant select, insert on supplier_confirmation, supplier_confirmation_line,
  delivery_receipt, delivery_receipt_line to authenticated;
grant select, insert on supplier_confirmation, supplier_confirmation_line,
  delivery_receipt, delivery_receipt_line to service_role;

-- 20260918000004_synced_bill.sql — task T006, chunk R3.1 (014-accounting-integration)
--
-- synced_bill — one supplier bill as recorded by the connected accounting system at the time of
-- the most recent sync (spec: "Synced Bill"). Sync-derived, same write split as synced_vendor.
-- matched_supplier_id is denormalized from vendor_id's own match (query convenience for the
-- reconciliation views) and kept in sync by the sync worker when the vendor's match changes.

create type synced_bill_status as enum ('open', 'paid', 'void');

create table if not exists synced_bill (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  connection_id         uuid not null,

  provider_bill_id      text not null,
  vendor_id             uuid not null,
  matched_supplier_id   uuid,

  amount                numeric(18, 4) not null,
  currency              text not null references supported_currency(code),
  bill_date             date not null,
  provider_status       synced_bill_status not null,

  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),

  constraint synced_bill_connection_fkey
    foreign key (tenant_id, connection_id) references accounting_connection (tenant_id, id),

  constraint synced_bill_vendor_fkey
    foreign key (tenant_id, vendor_id) references synced_vendor (tenant_id, id),

  constraint synced_bill_supplier_fkey
    foreign key (tenant_id, matched_supplier_id) references supplier (tenant_id, id)
    on delete set null (matched_supplier_id),

  constraint synced_bill_tenant_id_key unique (tenant_id, id),

  constraint synced_bill_provider_id_key
    unique (tenant_id, connection_id, provider_bill_id)
);

create index if not exists synced_bill_tenant_idx
  on synced_bill (tenant_id, connection_id, bill_date desc);

create index if not exists synced_bill_matched_supplier_idx
  on synced_bill (tenant_id, matched_supplier_id)
  where matched_supplier_id is not null;

comment on table synced_bill is
  'A supplier bill as recorded by the connected accounting system at the time of the most recent
   sync (R3.1). updated_at advances whenever a re-sync changes any field. Sync-derived: written
   only by the sync worker''s service-role path. See specs/014-accounting-integration/data-model.md.';

alter table synced_bill enable row level security;
alter table synced_bill force  row level security;

create policy synced_bill_tenant_select on synced_bill
  for select to authenticated
  using (tenant_id = current_tenant_id());

grant select on synced_bill to authenticated;
grant select, insert, update on synced_bill to service_role;

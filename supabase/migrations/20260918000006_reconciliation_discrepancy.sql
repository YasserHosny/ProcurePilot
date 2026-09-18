-- 20260918000006_reconciliation_discrepancy.sql — task T008, chunk R3.1 (014-accounting-integration)
--
-- reconciliation_discrepancy — a flagged exception needing human review (spec: "Reconciliation
-- Discrepancy"). The check constraint makes the three discrepancy shapes mutually exclusive by
-- construction, not just by convention (data-model.md).
--
-- Resolution is column-scoped: an owner/buyer may resolve a discrepancy, but RLS is row-scoped,
-- not column-scoped, so a plain UPDATE policy would let them silently rewrite detected_at or
-- discrepancy_type too. Column-level GRANTs restrict authenticated's UPDATE to exactly the
-- resolution columns (status, resolved_by, resolved_at, resolution_note) — the sync worker's
-- service-role path is the only writer of every other column, including re-opening a
-- previously-resolved row (see data-model.md's re-evaluation-on-sync note).

create type discrepancy_type as enum ('amount_mismatch', 'unmatched_bill', 'unmatched_purchase');
create type discrepancy_status as enum ('open', 'resolved');

create table if not exists reconciliation_discrepancy (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,

  discrepancy_type      discrepancy_type not null,
  synced_bill_id        uuid,
  purchase_record_id    uuid,

  status                discrepancy_status not null default 'open',
  detected_at           timestamptz not null default now(),
  resolved_by           uuid,
  resolved_at           timestamptz,
  resolution_note       text,

  constraint reconciliation_discrepancy_bill_fkey
    foreign key (tenant_id, synced_bill_id) references synced_bill (tenant_id, id),

  constraint reconciliation_discrepancy_purchase_record_fkey
    foreign key (tenant_id, purchase_record_id) references purchase_record (tenant_id, id),

  constraint reconciliation_discrepancy_resolved_by_fkey
    foreign key (tenant_id, resolved_by) references membership (tenant_id, id),

  constraint reconciliation_discrepancy_tenant_id_key unique (tenant_id, id),

  -- The three discrepancy shapes are mutually exclusive by construction (data-model.md).
  constraint reconciliation_discrepancy_shape check (
    (discrepancy_type = 'unmatched_bill'
      and synced_bill_id is not null and purchase_record_id is null)
    or (discrepancy_type = 'unmatched_purchase'
      and purchase_record_id is not null and synced_bill_id is null)
    or (discrepancy_type = 'amount_mismatch'
      and synced_bill_id is not null and purchase_record_id is not null)
  ),

  constraint reconciliation_discrepancy_resolved_fields check (
    (status = 'resolved') = (resolved_by is not null and resolved_at is not null)
  )
);

create index if not exists reconciliation_discrepancy_tenant_idx
  on reconciliation_discrepancy (tenant_id, status, detected_at desc);

comment on table reconciliation_discrepancy is
  'A flagged reconciliation exception needing human review (R3.1). Re-evaluated on every sync:
   a resolved row is reopened, not duplicated, if its underlying condition recurs against newer
   data. See specs/014-accounting-integration/data-model.md.';

alter table reconciliation_discrepancy enable row level security;
alter table reconciliation_discrepancy force  row level security;

create policy reconciliation_discrepancy_tenant_select on reconciliation_discrepancy
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy reconciliation_discrepancy_owner_buyer_update on reconciliation_discrepancy
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select on reconciliation_discrepancy to authenticated;

-- Column-level split (see file header): authenticated may only ever change the resolution
-- fields; discrepancy_type/synced_bill_id/purchase_record_id/detected_at are sync-worker-only.
grant update (status, resolved_by, resolved_at, resolution_note)
  on reconciliation_discrepancy to authenticated;

grant select, insert, update on reconciliation_discrepancy to service_role;

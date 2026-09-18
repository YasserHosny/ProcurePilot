-- 20260918000006_reconciliation_discrepancy.sql — task T008, chunk R3.1 (014-accounting-integration)
--
-- reconciliation_discrepancy — a flagged exception needing human review (spec: "Reconciliation
-- Discrepancy"). The check constraint makes the three discrepancy shapes mutually exclusive by
-- construction, not just by convention (data-model.md).
--
-- Resolution is column-scoped: an owner/buyer may resolve a discrepancy, but RLS is row-scoped,
-- not column-scoped, so a plain UPDATE policy would let them silently rewrite detected_at or
-- discrepancy_type too. Column-level GRANTs restrict authenticated's UPDATE to exactly the
-- resolution columns (status, resolved_by, resolved_at, resolution_note).
--
-- The sync worker is the writer of every other column, including detecting new discrepancies and
-- re-opening a previously-resolved row (data-model.md's re-evaluation-on-sync note) — via the
-- same tenant-scoped `authenticated` session as synced_vendor/synced_bill/purchase_bill_match
-- (see synced_vendor's migration header for why: no service_role write helper exists elsewhere
-- in this codebase, and this table has no secret column to warrant one). `current_member_role()
-- is null` distinguishes that worker session from a real owner/buyer's own session below, the
-- same idiom used on accounting_connection and purchase_bill_match.

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

-- Worker-triggered writes (see file header): detecting a new discrepancy (insert) and
-- re-opening a stale-resolved one (update) both run through this tenant-scoped, no-member-role
-- session — never a real owner/buyer's own session, which always carries member_role.
create policy reconciliation_discrepancy_worker_insert on reconciliation_discrepancy
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  );

create policy reconciliation_discrepancy_worker_update on reconciliation_discrepancy
  for update to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  )
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() is null
  );

grant select on reconciliation_discrepancy to authenticated;

-- Column-level split (see file header): authenticated may only ever change the resolution
-- fields via UPDATE — detected_at is set once, at INSERT, and never touched again, including on
-- reopen (data-model.md: reopening preserves the discrepancy's original identity/detected_at,
-- only clearing the resolution fields). GRANT is per-role, not per-policy, so this same column
-- set covers both a worker reopening a row and a real owner/buyer resolving one — which of the
-- two is actually happening is decided by which RLS policy the session satisfies, above, not by
-- the grant.
grant insert (
  tenant_id, discrepancy_type, synced_bill_id, purchase_record_id, status, detected_at
) on reconciliation_discrepancy to authenticated;

grant update (status, resolved_by, resolved_at, resolution_note)
  on reconciliation_discrepancy to authenticated;

grant select, insert, update on reconciliation_discrepancy to service_role;

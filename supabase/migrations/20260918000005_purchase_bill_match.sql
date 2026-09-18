-- 20260918000005_purchase_bill_match.sql — task T007, chunk R3.1 (014-accounting-integration)
--
-- purchase_bill_match — a link between a synced_bill and an existing purchase_record (spec:
-- "Purchase-Bill Match"). The two 1:1 uniqueness constraints enforce FR-007's "equally-qualifying
-- candidates are left unmatched" rule at the data layer: a bill or a purchase record can have at
-- most one match, so the relationship cannot silently become 1:many even from a buggy caller.
--
-- No UPDATE/DELETE grant at all: a match is superseded by inserting a new row and deleting the
-- old one inside the same transaction that changes it (service-layer responsibility), keeping
-- the "how was this decided" trail simple rather than allowing silent in-place correction.
-- Requires purchase_record's composite key (T003/20260918000001).

create type match_method as enum ('automatic', 'manual');

create table if not exists purchase_bill_match (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,

  synced_bill_id        uuid not null,
  purchase_record_id    uuid not null,
  match_method          match_method not null,
  matched_by            uuid,
  matched_at            timestamptz not null default now(),

  constraint purchase_bill_match_bill_fkey
    foreign key (tenant_id, synced_bill_id) references synced_bill (tenant_id, id),

  constraint purchase_bill_match_purchase_record_fkey
    foreign key (tenant_id, purchase_record_id) references purchase_record (tenant_id, id),

  constraint purchase_bill_match_membership_fkey
    foreign key (tenant_id, matched_by) references membership (tenant_id, id),

  constraint purchase_bill_match_tenant_id_key unique (tenant_id, id),

  constraint purchase_bill_match_bill_unique unique (tenant_id, synced_bill_id),
  constraint purchase_bill_match_purchase_record_unique unique (tenant_id, purchase_record_id),

  -- automatic matches have no human actor; manual matches (FR-011, a reviewer confirming a
  -- match while resolving a discrepancy) always record who.
  constraint purchase_bill_match_matched_by_manual_only
    check ((match_method = 'manual') = (matched_by is not null))
);

create index if not exists purchase_bill_match_tenant_idx
  on purchase_bill_match (tenant_id, matched_at desc);

comment on table purchase_bill_match is
  'A link between a synced_bill and a purchase_record (R3.1). 1:1 both directions, enforced by
   the two unique constraints. Superseded by insert-then-delete, never updated in place.
   See specs/014-accounting-integration/data-model.md.';

alter table purchase_bill_match enable row level security;
alter table purchase_bill_match force  row level security;

create policy purchase_bill_match_tenant_select on purchase_bill_match
  for select to authenticated
  using (tenant_id = current_tenant_id());

-- INSERT (automatic, via the sync worker's service-role path) and INSERT/DELETE (manual, an
-- owner/buyer resolving a discrepancy per FR-011) both need row-level access; no UPDATE policy
-- exists at all (see file header) and none is granted below.
create policy purchase_bill_match_owner_buyer_insert on purchase_bill_match
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and match_method = 'manual'
    and matched_by = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  );

create policy purchase_bill_match_owner_buyer_delete on purchase_bill_match
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert, delete on purchase_bill_match to authenticated;
grant select, insert, delete on purchase_bill_match to service_role;

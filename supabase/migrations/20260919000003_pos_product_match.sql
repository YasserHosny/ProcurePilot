-- 20260919000003_pos_product_match.sql — task T006, chunk R3.2 (015-pos-inventory-integration)
--
-- pos_product_match — a link between a synced_product_signal and an existing workspace_product
-- (spec: "Product Match"). Same shape as purchase_bill_match (014's own precedent,
-- 20260918000005): the two 1:1 uniqueness constraints enforce FR-006's "equally-qualifying
-- candidates are left unmatched" rule at the data layer, and there is no UPDATE grant at all — a
-- match is superseded by inserting a new row and deleting the old one inside the same
-- transaction, keeping the "how was this decided" trail simple rather than allowing silent
-- in-place correction (same Principle-I-adjacent rationale as purchase_bill_match).
--
-- Because synced_product_signal_id is stable across a disconnect/reconnect cycle (that table's
-- own uniqueness is keyed on the external item alone, not the connection — see its migration's
-- header, research.md R8), a match made before a disconnect remains valid, unmodified, after a
-- reconnect. No reconnect-specific handling is needed here.
--
-- match_method reuses the enum purchase_bill_match already created (014) — do not recreate it.

create table if not exists pos_product_match (
  id                        uuid primary key default gen_random_uuid(),
  tenant_id                 uuid not null references tenant(id) on delete cascade,

  synced_product_signal_id  uuid not null,
  workspace_product_id      uuid not null,
  match_method              match_method not null,
  matched_by                uuid,
  matched_at                timestamptz not null default now(),
  confidence                numeric(5, 4),

  constraint pos_product_match_signal_fkey
    foreign key (tenant_id, synced_product_signal_id)
    references synced_product_signal (tenant_id, id),

  constraint pos_product_match_workspace_product_fkey
    foreign key (tenant_id, workspace_product_id)
    references workspace_product (tenant_id, id),

  constraint pos_product_match_membership_fkey
    foreign key (tenant_id, matched_by) references membership (tenant_id, id),

  constraint pos_product_match_tenant_id_key unique (tenant_id, id),

  constraint pos_product_match_signal_unique unique (tenant_id, synced_product_signal_id),
  constraint pos_product_match_workspace_product_unique unique (tenant_id, workspace_product_id),

  -- automatic matches have no human actor; manual matches (FR-006's own resolution path) always
  -- record who — identical provenance rule to purchase_bill_match.
  constraint pos_product_match_matched_by_manual_only
    check ((match_method = 'manual') = (matched_by is not null)),

  constraint pos_product_match_confidence_range
    check (confidence is null or (confidence >= 0 and confidence <= 1))
);

create index if not exists pos_product_match_tenant_idx
  on pos_product_match (tenant_id, matched_at desc);

comment on table pos_product_match is
  'A link between a synced_product_signal and a workspace_product (R3.2). 1:1 both directions,
   enforced by the two unique constraints. Superseded by insert-then-delete, never updated in
   place. See specs/015-pos-inventory-integration/data-model.md.';

alter table pos_product_match enable row level security;
alter table pos_product_match force  row level security;

create policy pos_product_match_tenant_select on pos_product_match
  for select to authenticated
  using (tenant_id = current_tenant_id());

-- Two permissive INSERT policies (Postgres ORs them): automatic matches come from the sync
-- worker's tenant-scoped session (see synced_product_signal's migration header — same
-- _act_as_tenant-style write, no member_role/membership_id claim set, so this policy cannot and
-- must not require either); manual matches come from an owner/buyer resolving an unmatched
-- signal (FR-006). No UPDATE policy exists at all (see file header) and none is granted below.
create policy pos_product_match_automatic_insert on pos_product_match
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and match_method = 'automatic'
    and matched_by is null
  );

create policy pos_product_match_owner_buyer_insert on pos_product_match
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and match_method = 'manual'
    and matched_by = current_membership_id()
    and current_member_role() in ('owner', 'buyer')
  );

-- Mirrors the insert split above: the worker may only ever delete its own automatic matches (a
-- resync that finds a stale automatic match no longer qualifies) — it can never touch a manual
-- match, which only an owner/buyer may remove.
create policy pos_product_match_automatic_delete on pos_product_match
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and match_method = 'automatic'
  );

create policy pos_product_match_owner_buyer_delete on pos_product_match
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert, delete on pos_product_match to authenticated;
grant select, insert, delete on pos_product_match to service_role;

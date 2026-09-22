-- Durable request replay for Supplier IQ recompute mutations.

create table supplier_iq_recompute_idempotency (
  tenant_id          uuid not null references tenant(id) on delete cascade,
  idempotency_key    uuid not null,
  request_fingerprint text not null,
  generated_snapshots integer not null check (generated_snapshots >= 0),
  release_posture    text not null check (release_posture = 'g3_unmet'),
  created_at         timestamptz not null default now(),

  primary key (tenant_id, idempotency_key)
);

alter table supplier_iq_recompute_idempotency enable row level security;
alter table supplier_iq_recompute_idempotency force row level security;

create policy supplier_iq_recompute_idempotency_tenant_select
  on supplier_iq_recompute_idempotency
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy supplier_iq_recompute_idempotency_owner_buyer_insert
  on supplier_iq_recompute_idempotency
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert on supplier_iq_recompute_idempotency to authenticated;
grant select, insert on supplier_iq_recompute_idempotency to service_role;
revoke update, delete, truncate on supplier_iq_recompute_idempotency from authenticated, service_role;

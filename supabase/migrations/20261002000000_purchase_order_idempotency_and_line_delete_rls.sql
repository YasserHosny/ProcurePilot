-- US4 follow-up: durable draft-edit idempotency, dedicated create idempotency,
-- and draft-only direct deletion of purchase_order_line rows.

alter table purchase_order add column if not exists create_idempotency_key uuid;

create unique index if not exists purchase_order_tenant_create_idempotency_key
  on purchase_order (tenant_id, create_idempotency_key)
  where create_idempotency_key is not null;

create table if not exists purchase_order_edit_idempotency (
  tenant_id uuid not null,
  purchase_order_id uuid not null,
  idempotency_key uuid not null,
  created_at timestamptz not null default now(),

  primary key (tenant_id, idempotency_key),
  constraint purchase_order_edit_idempotency_order_fkey
    foreign key (tenant_id, purchase_order_id)
    references purchase_order (tenant_id, id)
    on delete cascade
);

alter table purchase_order_edit_idempotency enable row level security;
alter table purchase_order_edit_idempotency force row level security;

create policy purchase_order_edit_idempotency_owner_buyer_select
  on purchase_order_edit_idempotency
  for select to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

create policy purchase_order_edit_idempotency_owner_buyer_insert
  on purchase_order_edit_idempotency
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
  );

grant select, insert on purchase_order_edit_idempotency to authenticated;
grant select, insert on purchase_order_edit_idempotency to service_role;
revoke update, delete, truncate on purchase_order_edit_idempotency from authenticated, service_role;

drop policy if exists purchase_order_line_owner_buyer_delete on purchase_order_line;

create policy purchase_order_line_owner_buyer_delete on purchase_order_line
  for delete to authenticated
  using (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and exists (
      select 1
      from purchase_order po
      where po.tenant_id = purchase_order_line.tenant_id
        and po.id = purchase_order_line.purchase_order_id
        and po.status = 'draft'
    )
  );

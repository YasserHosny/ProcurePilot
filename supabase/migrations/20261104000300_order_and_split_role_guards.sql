-- 20261104000300_order_and_split_role_guards.sql
--
-- Table-level backstops for rules the API already enforces (PPS-210):
--
-- 1. basket_split_job: every member of a workspace could write rows. Reading stays open to
--    every member; starting, changing or removing a job needs the owner or buyer role, the same
--    as the API. The worker connects as a role that bypasses row-level security.
-- 2. purchase_order: only draft orders have an editable header or lines, an order moves
--    along the lifecycle the API uses, and cancelled and closed orders are final.
--
-- Tenant isolation is unchanged; every policy below still pins tenant_id.

-- 1. basket_split_job -------------------------------------------------------------------------

drop policy if exists tenant_isolation on basket_split_job;

create policy basket_split_job_member_select on basket_split_job
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy basket_split_job_owner_buyer_insert on basket_split_job
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

create policy basket_split_job_owner_buyer_update on basket_split_job
  for update to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'))
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

create policy basket_split_job_owner_buyer_delete on basket_split_job
  for delete to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

-- 2. purchase_order and its lines: orders start as drafts; lines change only on a draft order -----------------

drop policy if exists purchase_order_line_owner_buyer_insert on purchase_order_line;
drop policy if exists purchase_order_line_owner_buyer_update on purchase_order_line;

create policy purchase_order_line_owner_buyer_insert on purchase_order_line
  for insert to authenticated
  with check (
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

create policy purchase_order_line_owner_buyer_update on purchase_order_line
  for update to authenticated
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
  )
  with check (
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

-- Orders start as drafts: the API never sets a status on insert.
drop policy if exists purchase_order_owner_buyer_insert on purchase_order;

create policy purchase_order_owner_buyer_insert on purchase_order
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and current_member_role() in ('owner', 'buyer')
    and status = 'draft'
  );

-- 3. purchase_order: status transitions and a frozen header -----------------------------------

create or replace function purchase_order_lifecycle_guard() returns trigger
language plpgsql
as $$
begin
  if new.status is distinct from old.status and not (
    (old.status = 'draft' and new.status in ('submitted', 'cancelled'))
    or (old.status = 'submitted'
        and new.status in ('confirmed', 'partially_received', 'received', 'cancelled'))
    or (old.status = 'confirmed'
        and new.status in ('partially_received', 'received', 'cancelled'))
    or (old.status = 'partially_received' and new.status in ('received', 'cancelled'))
    or (old.status = 'received' and new.status = 'closed')
  ) then
    raise exception 'purchase order status cannot move from % to %', old.status, new.status
      using errcode = 'restrict_violation';
  end if;

  if old.status <> 'draft' and (
    new.order_number is distinct from old.order_number
    or new.supplier_id is distinct from old.supplier_id
    or new.order_date is distinct from old.order_date
    or new.expected_delivery_date is distinct from old.expected_delivery_date
    or new.total_amount is distinct from old.total_amount
    or new.total_currency is distinct from old.total_currency
    or new.tax_amount is distinct from old.tax_amount
    or new.tax_currency is distinct from old.tax_currency
    or new.source_kind is distinct from old.source_kind
    or new.source_reference is distinct from old.source_reference
    or new.source_hash is distinct from old.source_hash
    or new.source_request_id is distinct from old.source_request_id
    or new.created_by is distinct from old.created_by
  ) then
    raise exception 'only a draft purchase order header can be edited'
      using errcode = 'restrict_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists purchase_order_lifecycle_guard on purchase_order;
create trigger purchase_order_lifecycle_guard
  before update on purchase_order
  for each row execute function purchase_order_lifecycle_guard();

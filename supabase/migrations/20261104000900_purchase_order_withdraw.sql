-- 20261104000900_purchase_order_withdraw.sql
--
-- A submitted order can go back to a draft while no confirmation, receipt or purchase outcome
-- exists (PPS-205).
-- The lifecycle guard gains that one transition, with the evidence check at the table, and the
-- withdraw call keeps its idempotency key like submit, cancel and close.

alter table purchase_order add column if not exists withdraw_idempotency_key uuid;

create unique index if not exists purchase_order_tenant_withdraw_idempotency_key
  on purchase_order (tenant_id, withdraw_idempotency_key)
  where withdraw_idempotency_key is not null;

create or replace function purchase_order_lifecycle_guard() returns trigger
language plpgsql
as $$
begin
  if new.status is distinct from old.status and not (
    (old.status = 'draft' and new.status in ('submitted', 'cancelled'))
    or (old.status = 'submitted'
        and new.status in ('draft', 'confirmed', 'partially_received', 'received', 'cancelled'))
    or (old.status = 'confirmed'
        and new.status in ('partially_received', 'received', 'cancelled'))
    or (old.status = 'partially_received' and new.status in ('received', 'cancelled'))
    or (old.status = 'received' and new.status = 'closed')
  ) then
    raise exception 'purchase order status cannot move from % to %', old.status, new.status
      using errcode = 'restrict_violation';
  end if;

  if old.status = 'submitted' and new.status = 'draft' and (
    exists (
      select 1 from supplier_confirmation sc
      where sc.tenant_id = old.tenant_id and sc.purchase_order_id = old.id
    )
    or exists (
      select 1 from delivery_receipt dr
      where dr.tenant_id = old.tenant_id and dr.purchase_order_id = old.id
    )
    or exists (
      select 1
      from purchase_record pr
      join purchase_order_line pol
        on pol.tenant_id = pr.tenant_id and pol.id = pr.purchase_order_line_id
      where pol.tenant_id = old.tenant_id and pol.purchase_order_id = old.id
    )
  ) then
    raise exception 'a purchase order with recorded evidence cannot go back to a draft'
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

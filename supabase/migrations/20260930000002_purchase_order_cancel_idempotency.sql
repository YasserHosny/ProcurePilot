-- T008 Add cancel idempotency key to purchase orders
alter table purchase_order add column if not exists cancel_idempotency_key uuid;

create unique index if not exists purchase_order_tenant_cancel_idempotency_key
  on purchase_order (tenant_id, cancel_idempotency_key)
  where cancel_idempotency_key is not null;

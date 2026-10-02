-- T006 Add edit idempotency key to purchase orders
alter table purchase_order add column if not exists edit_idempotency_key uuid;

create unique index if not exists purchase_order_tenant_edit_idempotency_key
  on purchase_order (tenant_id, edit_idempotency_key)
  where edit_idempotency_key is not null;

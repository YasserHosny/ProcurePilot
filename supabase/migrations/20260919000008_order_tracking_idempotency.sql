-- R3.3 order workflow idempotency.  Keys are nullable for imported/provider evidence;
-- API mutations require one and use the tenant-scoped partial indexes below.
alter table purchase_order add column if not exists idempotency_key uuid;
alter table supplier_confirmation add column if not exists idempotency_key uuid;
alter table delivery_receipt add column if not exists idempotency_key uuid;
alter table purchase_order add column if not exists submit_idempotency_key uuid;

create unique index if not exists purchase_order_tenant_idempotency_key
  on purchase_order (tenant_id, idempotency_key)
  where idempotency_key is not null;
create unique index if not exists supplier_confirmation_tenant_idempotency_key
  on supplier_confirmation (tenant_id, idempotency_key)
  where idempotency_key is not null;
create unique index if not exists delivery_receipt_tenant_idempotency_key
  on delivery_receipt (tenant_id, idempotency_key)
  where idempotency_key is not null;
create unique index if not exists purchase_order_tenant_submit_idempotency_key
  on purchase_order (tenant_id, submit_idempotency_key)
  where submit_idempotency_key is not null;

-- 20261104000800_purchase_order_close_idempotency.sql
--
-- Closing a received order is retried safely: the key of the close call is kept on the order,
-- as for submit and cancel (PPS-205).

alter table purchase_order add column if not exists close_idempotency_key uuid;

create unique index if not exists purchase_order_tenant_close_idempotency_key
  on purchase_order (tenant_id, close_idempotency_key)
  where close_idempotency_key is not null;

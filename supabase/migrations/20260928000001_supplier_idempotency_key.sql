alter table supplier add column if not exists idempotency_key uuid;

create unique index if not exists supplier_idempotency_key_idx
  on supplier (tenant_id, idempotency_key)
  where idempotency_key is not null;

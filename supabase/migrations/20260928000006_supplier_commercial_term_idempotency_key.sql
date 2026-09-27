alter table supplier_commercial_term add column if not exists idempotency_key uuid;

create unique index if not exists supplier_commercial_term_idempotency_key_idx
  on supplier_commercial_term (tenant_id, idempotency_key)
  where idempotency_key is not null;

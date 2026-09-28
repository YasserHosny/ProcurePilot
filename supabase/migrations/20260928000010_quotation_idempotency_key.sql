alter table quotation add column if not exists idempotency_key uuid;

create unique index if not exists quotation_idempotency_key_idx
  on quotation (tenant_id, idempotency_key)
  where idempotency_key is not null;

alter table purchase_record add column if not exists idempotency_key uuid;

create unique index if not exists purchase_record_idempotency_key_idx
  on purchase_record (tenant_id, idempotency_key)
  where idempotency_key is not null;

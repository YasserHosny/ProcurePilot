alter table basket_split_job add column if not exists idempotency_key uuid;

create unique index if not exists basket_split_job_idempotency_key_idx
  on basket_split_job (tenant_id, idempotency_key)
  where idempotency_key is not null;

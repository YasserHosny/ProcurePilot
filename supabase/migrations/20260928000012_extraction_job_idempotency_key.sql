alter table extraction_job add column if not exists idempotency_key uuid;

create unique index if not exists extraction_job_idempotency_key_idx
  on extraction_job (tenant_id, idempotency_key)
  where idempotency_key is not null;

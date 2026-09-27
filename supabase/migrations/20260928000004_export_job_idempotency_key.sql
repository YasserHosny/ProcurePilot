alter table export_job add column if not exists idempotency_key uuid;

create unique index if not exists export_job_idempotency_key_idx
  on export_job (tenant_id, idempotency_key)
  where idempotency_key is not null;

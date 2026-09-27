alter table branch add column if not exists idempotency_key uuid;

create unique index if not exists branch_idempotency_key_idx
  on branch (tenant_id, idempotency_key)
  where idempotency_key is not null;

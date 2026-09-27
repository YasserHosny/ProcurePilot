alter table cost_centre add column if not exists idempotency_key uuid;

create unique index if not exists cost_centre_idempotency_key_idx
  on cost_centre (tenant_id, idempotency_key)
  where idempotency_key is not null;

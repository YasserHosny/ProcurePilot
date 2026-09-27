alter table budget add column if not exists idempotency_key uuid;

create unique index if not exists budget_idempotency_key_idx
  on budget (tenant_id, idempotency_key)
  where idempotency_key is not null;

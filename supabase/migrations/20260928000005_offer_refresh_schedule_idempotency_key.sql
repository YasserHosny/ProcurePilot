alter table offer_refresh_schedule add column if not exists idempotency_key uuid;

create unique index if not exists offer_refresh_schedule_idempotency_key_idx
  on offer_refresh_schedule (tenant_id, idempotency_key)
  where idempotency_key is not null;

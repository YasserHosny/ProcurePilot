alter table device_registration add column if not exists idempotency_key uuid;

create unique index if not exists device_registration_idempotency_key_idx
  on device_registration (tenant_id, idempotency_key)
  where idempotency_key is not null;

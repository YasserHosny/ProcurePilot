alter table digest_subscription add column if not exists idempotency_key uuid;

create unique index if not exists digest_subscription_idempotency_key_idx
  on digest_subscription (tenant_id, idempotency_key)
  where idempotency_key is not null;

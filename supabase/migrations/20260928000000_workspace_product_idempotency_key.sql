alter table workspace_product add column if not exists idempotency_key uuid;

create unique index if not exists workspace_product_idempotency_key_idx
  on workspace_product (tenant_id, idempotency_key)
  where idempotency_key is not null;

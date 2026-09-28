alter table quotation
  add column if not exists archive_idempotency_key uuid;

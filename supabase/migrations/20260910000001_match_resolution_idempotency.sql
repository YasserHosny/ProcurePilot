-- 20260910000001_match_resolution_idempotency.sql
--
-- Durable replay keys for POST /quotation-lines/{line_id}/match.
-- Append-only by design: a retry key records the one match decision it produced.

create table if not exists match_resolution_idempotency (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references tenant(id) on delete cascade,
  idempotency_key      uuid not null,
  quotation_line_id    uuid not null references quotation_line(id) on delete cascade,
  request_fingerprint  text not null check (request_fingerprint ~ '^[0-9a-f]{64}$'),
  match_decision_id    uuid not null references match_decision(id) on delete cascade,
  created_at           timestamptz not null default now(),

  constraint match_resolution_idempotency_key_unique
    unique (tenant_id, idempotency_key),
  constraint match_resolution_idempotency_decision_unique
    unique (tenant_id, match_decision_id)
);

create index if not exists match_resolution_idempotency_line_idx
  on match_resolution_idempotency (tenant_id, quotation_line_id);

alter table match_resolution_idempotency enable row level security;
alter table match_resolution_idempotency force row level security;

create policy match_resolution_idempotency_read on match_resolution_idempotency
  for select
  to authenticated
  using (tenant_id = current_tenant_id());

create policy match_resolution_idempotency_append on match_resolution_idempotency
  for insert
  to authenticated
  with check (tenant_id = current_tenant_id());

grant select, insert on match_resolution_idempotency to authenticated;
grant select, insert on match_resolution_idempotency to service_role;
revoke update, delete on match_resolution_idempotency from authenticated, anon, public;

comment on table match_resolution_idempotency is
  'Append-only replay mapping for human match-resolution retries. Reusing a key with a different line or payload is rejected.';

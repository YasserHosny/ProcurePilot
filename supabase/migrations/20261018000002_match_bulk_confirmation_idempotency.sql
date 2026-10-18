-- 20261018000002_match_bulk_confirmation_idempotency.sql
--
-- Durable replay record for POST /match-tasks/confirm-exact. The first call under an
-- Idempotency-Key freezes the batch (which lines, which candidates); a retry replays that exact
-- plan instead of re-selecting from a queue the first attempt may already have mutated.
-- Append-only: no UPDATE, no DELETE for any API role.

create table if not exists match_bulk_confirmation (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenant(id) on delete cascade,
  idempotency_key  uuid not null,
  plan             jsonb not null check (jsonb_typeof(plan) = 'array'),
  created_at       timestamptz not null default now(),

  constraint match_bulk_confirmation_key_unique unique (tenant_id, idempotency_key)
);

alter table match_bulk_confirmation enable row level security;
alter table match_bulk_confirmation force row level security;

create policy match_bulk_confirmation_read on match_bulk_confirmation
  for select
  to authenticated
  using (tenant_id = current_tenant_id());

create policy match_bulk_confirmation_append on match_bulk_confirmation
  for insert
  to authenticated
  with check (tenant_id = current_tenant_id());

grant select, insert on match_bulk_confirmation to authenticated;
grant select, insert on match_bulk_confirmation to service_role;
revoke update, delete on match_bulk_confirmation from authenticated, anon, public;

comment on table match_bulk_confirmation is
  'Append-only frozen plan for bulk exact-match confirmation retries (Idempotency-Key).';

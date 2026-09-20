-- R3.4 webhook subscriptions and durable outbound delivery.
-- Audit events remain append-only; this trigger creates delivery work without changing the event.

create type webhook_subscription_status as enum ('active', 'paused', 'revoked');
create type webhook_delivery_status as enum ('pending', 'processing', 'succeeded', 'failed');

create table if not exists webhook_subscription (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenant(id) on delete cascade,
  endpoint_url      text not null check (endpoint_url ~ '^https?://'),
  events            text[] not null default array['*']::text[],
  secret_encrypted  text not null,
  status            webhook_subscription_status not null default 'active',
  created_by        uuid not null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),

  constraint webhook_subscription_membership_fkey
    foreign key (tenant_id, created_by) references membership (tenant_id, id),
  constraint webhook_subscription_tenant_id_key unique (tenant_id, id),
  constraint webhook_subscription_events_nonempty
    check (cardinality(events) between 1 and 50)
);

create table if not exists webhook_delivery (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references tenant(id) on delete cascade,
  subscription_id  uuid not null,
  audit_event_id   bigint not null,
  event_type       text not null,
  payload          jsonb not null,
  status           webhook_delivery_status not null default 'pending',
  attempts         integer not null default 0 check (attempts >= 0),
  next_attempt_at  timestamptz not null default now(),
  locked_at        timestamptz,
  locked_by        text,
  delivered_at     timestamptz,
  last_error       text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),

  constraint webhook_delivery_subscription_fkey
    foreign key (tenant_id, subscription_id) references webhook_subscription (tenant_id, id)
    on delete cascade,
  constraint webhook_delivery_event_unique
    unique (tenant_id, subscription_id, audit_event_id)
);

create index if not exists webhook_subscription_tenant_idx
  on webhook_subscription (tenant_id, created_at desc);
create index if not exists webhook_delivery_due_idx
  on webhook_delivery (next_attempt_at, created_at)
  where status in ('pending', 'processing');
create index if not exists webhook_delivery_tenant_idx
  on webhook_delivery (tenant_id, created_at desc);

alter table webhook_subscription enable row level security;
alter table webhook_subscription force row level security;
alter table webhook_delivery enable row level security;
alter table webhook_delivery force row level security;

create policy webhook_subscription_owner_select on webhook_subscription
  for select to authenticated
  using (tenant_id = current_tenant_id());
create policy webhook_subscription_owner_insert on webhook_subscription
  for insert to authenticated
  with check (
    tenant_id = current_tenant_id()
    and created_by = current_membership_id()
    and current_member_role() = 'owner'
  );
create policy webhook_subscription_owner_update on webhook_subscription
  for update to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() = 'owner')
  with check (tenant_id = current_tenant_id() and current_member_role() = 'owner');

create policy webhook_delivery_owner_select on webhook_delivery
  for select to authenticated
  using (tenant_id = current_tenant_id());

grant select, insert, update on webhook_subscription to authenticated;
grant select on webhook_delivery to authenticated;
grant select, insert, update, delete on webhook_subscription, webhook_delivery to service_role;

create or replace function enqueue_webhook_delivery_for_audit()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.tenant_id is null then
    return new;
  end if;

  insert into webhook_delivery (
    tenant_id, subscription_id, audit_event_id, event_type, payload
  )
  select
    new.tenant_id,
    subscription.id,
    new.id,
    new.action,
    jsonb_build_object(
      'event_id', new.id,
      'event_type', new.action,
      'occurred_at', new.occurred_at,
      'outcome', new.outcome,
      'target', coalesce(new.target, '{}'::jsonb)
    )
  from webhook_subscription subscription
  where subscription.tenant_id = new.tenant_id
    and subscription.status = 'active'
    and ('*' = any(subscription.events) or new.action = any(subscription.events))
  on conflict (tenant_id, subscription_id, audit_event_id) do nothing;

  return new;
end;
$$;

drop trigger if exists audit_event_webhook_delivery on audit_event;
create trigger audit_event_webhook_delivery
  after insert on audit_event
  for each row execute function enqueue_webhook_delivery_for_audit();

grant execute on function enqueue_webhook_delivery_for_audit() to authenticated, service_role;

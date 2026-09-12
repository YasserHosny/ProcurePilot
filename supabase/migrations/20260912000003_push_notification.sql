-- 20260912000003_push_notification.sql — task T003, chunk R2.2 (Mobile MVP)
--
-- push_notification — a durable, internal record of one decision-triggered push send attempt
-- (specs/009-mobile-app-mvp/research.md R1, revised). Not client-facing this release: no
-- endpoint reads or writes it directly. It exists so an enqueue failure or a worker outage
-- leaves a visible, replayable row instead of a silently dropped job — the direct fix for a gap
-- Codex's review of the R2.2 plan caught (an in-memory-only RQ enqueue satisfies FR-008 but not
-- spec.md's SC-004, "100% of decisions... learns... without opening the app").
--
-- No client-facing read policy at all — service-role only. RLS is still ENABLE+FORCE per the
-- constitution's blanket requirement for every tenant-scoped table, even one with no client read
-- surface yet, but `authenticated` gets no grant at all rather than a deny-all RESTRICTIVE
-- policy — the simpler of the two ways to express "nothing here for a member or owner to see."

create table if not exists push_notification (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  purchase_request_id   uuid not null,
  member_id             uuid not null,
  status                text not null default 'queued',
  attempts              integer not null default 0,
  created_at            timestamptz not null default now(),
  sent_at               timestamptz,

  constraint push_notification_tenant_id_key unique (tenant_id, id),

  constraint push_notification_request_fkey
    foreign key (tenant_id, purchase_request_id) references purchase_request (tenant_id, id),
  constraint push_notification_member_fkey
    foreign key (tenant_id, member_id) references membership (tenant_id, id),

  constraint push_notification_status_check check (status in ('queued', 'sent', 'failed')),

  -- A step's decision fields pair mirrors approval_step's own discipline: sent_at is populated
  -- if and only if status has actually moved past queued/failed into a completed send.
  constraint push_notification_sent_at_pairing check (
    (status = 'sent') = (sent_at is not null)
  )
);

create index if not exists push_notification_tenant_idx on push_notification (tenant_id);
create index if not exists push_notification_sweep_idx
  on push_notification (tenant_id, status, created_at);

comment on table push_notification is
  'A durable outbox row for one decision-triggered push send attempt (chunk R2.2). Written in
   the same transaction as the triggering approve/reject decision (research.md R1 revised);
   updated by the send job to sent/failed; a retry-sweep task re-enqueues rows still
   queued/failed past a threshold. Service-role only — no client-facing read this release.';

alter table push_notification enable row level security;
alter table push_notification force  row level security;

create policy push_notification_tenant_isolation on push_notification
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- No grant to `authenticated` at all — service-role only, per the note above. The tenant
-- isolation policy above is still meaningful defense-in-depth even with no authenticated grant.
grant select, insert, update, delete on push_notification to service_role;

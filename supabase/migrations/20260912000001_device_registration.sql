-- 20260912000001_device_registration.sql — task T001, chunk R2.2 (Mobile MVP)
--
-- device_registration — a signed-in member's mobile device, registered to receive push
-- notifications (specs/009-mobile-app-mvp/research.md R1, revised). Registration is a plain
-- upsert on (tenant_id, member_id, push_token) at sign-in and whenever the OS reissues a token;
-- a reinstall or token rotation is left as passive staleness (last_seen_at). Sign-out is NOT
-- passive — the mobile app calls DELETE /devices/{id} for its own current registration, which
-- deletes the row outright, so a signed-out but still-installed device stops being eligible for
-- push immediately rather than eventually.
--
-- No owner read-all, unlike purchase_request/branch-scoped tables: a member manages only their
-- own device registrations, and an owner has no operational need to browse another member's
-- push tokens (data-model.md RLS Summary). The RESTRICTIVE policy below narrows every operation
-- (not only SELECT) to the row's own member_id, so a member can never read, upsert, or delete a
-- registration under someone else's member_id even at the application layer's own request.

create table if not exists device_registration (
  id                uuid primary key default gen_random_uuid(),
  tenant_id         uuid not null references tenant(id) on delete cascade,
  member_id         uuid not null,
  platform          text not null,
  push_token        text not null,
  last_seen_at      timestamptz not null default now(),
  created_at        timestamptz not null default now(),

  constraint device_registration_tenant_id_key unique (tenant_id, id),

  constraint device_registration_member_fkey
    foreign key (tenant_id, member_id) references membership (tenant_id, id),

  constraint device_registration_platform_check check (platform in ('ios', 'android')),

  constraint device_registration_upsert_key unique (tenant_id, member_id, push_token)
);

create index if not exists device_registration_tenant_idx on device_registration (tenant_id);
create index if not exists device_registration_member_idx on device_registration (member_id);

comment on table device_registration is
  'A signed-in member''s mobile device, registered to receive push notifications (chunk R2.2).
   Upsert on (tenant_id, member_id, push_token) keeps a reinstall/token-rotation from
   accumulating duplicate rows. Sign-out deletes the row outright via DELETE /devices/{id} —
   research.md R1 revised, distinct from passive last_seen_at staleness.';

alter table device_registration enable row level security;
alter table device_registration force  row level security;

create policy device_registration_tenant_isolation on device_registration
  for all to authenticated
  using      (tenant_id = current_tenant_id())
  with check  (tenant_id = current_tenant_id());

-- RESTRICTIVE, for ALL operations (not select-only) — a member manages only their own device
-- registrations; there is no owner-read-all clause here, unlike every branch-scoped table in
-- this project, because an owner has no operational need to browse another member's push tokens.
create policy device_registration_own_rows_only on device_registration
  as restrictive
  for all to authenticated
  using      (member_id = current_membership_id())
  with check  (member_id = current_membership_id());

grant select, insert, update, delete on device_registration to authenticated;
grant select, insert, update, delete on device_registration to service_role;

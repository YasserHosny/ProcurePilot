-- 20260919000002_synced_product_signal.sql — task T005, chunk R3.2 (015-pos-inventory-integration)
--
-- synced_product_signal — the most recent sales-velocity and/or stock-on-hand figures for one
-- external Square catalog item, as of the last successful sync (spec: "Synced Product Signal").
--
-- Reconnect-dedup design (research.md R8, a defect found and fixed during /speckit.analyze,
-- BEFORE this table was ever built — not a later patch): uniqueness is keyed on
-- (tenant_id, external_item_id) ALONE. pos_connection_id is a "most recently synced via" pointer,
-- updated in place on every sync — it is NOT part of the uniqueness key and must never become
-- part of it. If it were, a disconnect followed by a reconnect (pos_connection always inserts a
-- NEW row on reconnect, per that table's own header — the old row is never reactivated) would
-- cause the very next sync to insert a SECOND signal row for every external item already known
-- from before the disconnect, alongside the original row still pointing at the now-disconnected
-- connection. Keying on the external item alone makes a reconnect idempotent with respect to
-- signal identity, and lets any pos_product_match row (which points at synced_product_signal_id,
-- never at pos_connection_id) survive a reconnect with no re-matching required.
--
-- velocity_window_days_observed (FR-013, research.md R9): Constitution Principle I (NON-
-- NEGOTIABLE) forbids presenting insufficient data as if it were a complete figure. A product
-- matched only a few days ago would otherwise show a velocity computed from a handful of
-- transactions with no way to tell it apart from one backed by the full window. This column
-- records how many days of actual history the current figure reflects; the frontend renders it
-- as provisional whenever this is less than velocity_window_days.
--
-- Same write path as synced_bill (014's own precedent, see that migration's header): a
-- tenant-scoped `authenticated` session the sync worker acts through, RLS scoped by tenant_id
-- only rather than further restricted to a worker-only role check, because no member-facing
-- endpoint ever writes this table directly (only the worker syncs it; members only read it, or
-- write pos_product_match via the separate manual-match endpoint).

create table if not exists synced_product_signal (
  id                            uuid primary key default gen_random_uuid(),
  tenant_id                     uuid not null references tenant(id) on delete cascade,
  pos_connection_id             uuid not null,

  external_item_id              text not null,
  external_item_name            text not null,

  stock_on_hand                 numeric(18, 4),
  stock_synced_at               timestamptz,

  sales_velocity_per_day        numeric(18, 4),
  velocity_window_days          integer not null default 30,
  velocity_window_days_observed integer,
  velocity_computed_at          timestamptz,

  created_at                    timestamptz not null default now(),
  updated_at                    timestamptz not null default now(),

  constraint synced_product_signal_connection_fkey
    foreign key (tenant_id, pos_connection_id) references pos_connection (tenant_id, id),

  constraint synced_product_signal_tenant_id_key unique (tenant_id, id),

  -- The dedup key (see file header) — NOT (tenant_id, pos_connection_id, external_item_id).
  constraint synced_product_signal_external_item_key
    unique (tenant_id, external_item_id),

  constraint synced_product_signal_window_observed_not_negative
    check (velocity_window_days_observed is null or velocity_window_days_observed >= 0)
);

create index if not exists synced_product_signal_tenant_idx
  on synced_product_signal (tenant_id, pos_connection_id);

comment on table synced_product_signal is
  'The most recent sales-velocity and/or stock-on-hand figures for one external Square catalog
   item (R3.2). Unique on (tenant_id, external_item_id) ONLY — never add pos_connection_id to
   this key, see file header (research.md R8, SC-005). Written by the sync worker/service
   (system-triggered, acting as authenticated for the tenant), read by any member.
   See specs/015-pos-inventory-integration/data-model.md.';

alter table synced_product_signal enable row level security;
alter table synced_product_signal force  row level security;

create policy synced_product_signal_tenant_select on synced_product_signal
  for select to authenticated
  using (tenant_id = current_tenant_id());

create policy synced_product_signal_tenant_insert on synced_product_signal
  for insert to authenticated
  with check (tenant_id = current_tenant_id());

create policy synced_product_signal_tenant_update on synced_product_signal
  for update to authenticated
  using (tenant_id = current_tenant_id())
  with check (tenant_id = current_tenant_id());

grant select, insert, update on synced_product_signal to authenticated;
grant select, insert, update on synced_product_signal to service_role;

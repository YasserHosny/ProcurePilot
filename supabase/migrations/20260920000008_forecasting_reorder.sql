-- 20260920000008_forecasting_reorder.sql — R4.0 forecasting and reorder proposals
--
-- This release is intentionally running while G3 remains unmet.  Forecast rows carry the
-- release posture so a pre-G3 result cannot be mistaken for commercially validated evidence.

create table if not exists demand_forecast (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  workspace_product_id       uuid not null,
  synced_product_signal_id   uuid,
  source_fingerprint          text not null check (char_length(source_fingerprint) between 1 and 200),
  model_version              text not null check (char_length(model_version) between 1 and 100),
  horizon_days               integer not null check (horizon_days > 0),
  source_window_start        date not null,
  source_window_end          date not null,
  observed_history_days      integer check (observed_history_days is null or observed_history_days >= 0),
  expected_daily_demand      numeric(18, 4),
  expected_demand            numeric(18, 4),
  uncertainty_lower          numeric(18, 4),
  uncertainty_upper          numeric(18, 4),
  stock_on_hand              numeric(18, 4),
  suggested_quantity         numeric(18, 4),
  confidence                 text not null check (confidence in ('high', 'medium', 'low')),
  state                      text not null check (state in ('ready', 'provisional', 'insufficient_data')),
  release_posture            text not null default 'g3_unmet' check (release_posture = 'g3_unmet'),
  valid_from                 timestamptz not null,
  valid_until                timestamptz not null,
  created_at                 timestamptz not null default now(),

  constraint demand_forecast_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id),
  constraint demand_forecast_signal_fkey
    foreign key (tenant_id, synced_product_signal_id) references synced_product_signal (tenant_id, id),
  constraint demand_forecast_tenant_id_key unique (tenant_id, id),
  constraint demand_forecast_source_fingerprint_key unique (tenant_id, source_fingerprint),
  constraint demand_forecast_window_order check (source_window_end >= source_window_start),
  constraint demand_forecast_validity_order check (valid_until > valid_from),
  constraint demand_forecast_uncertainty_order check (
    uncertainty_lower is null or uncertainty_upper is null or uncertainty_upper >= uncertainty_lower
  )
);

create table if not exists reorder_proposal (
  id                   uuid primary key default gen_random_uuid(),
  tenant_id            uuid not null references tenant(id) on delete cascade,
  demand_forecast_id   uuid not null,
  workspace_product_id uuid not null,
  status               text not null default 'open'
    check (status in ('open', 'prepared', 'dismissed', 'expired')),
  purchase_request_id  uuid,
  prepared_branch_id   uuid,
  created_at           timestamptz not null default now(),
  prepared_at          timestamptz,
  dismissed_at         timestamptz,

  constraint reorder_proposal_forecast_fkey
    foreign key (tenant_id, demand_forecast_id) references demand_forecast (tenant_id, id),
  constraint reorder_proposal_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id),
  constraint reorder_proposal_request_fkey
    foreign key (tenant_id, purchase_request_id) references purchase_request (tenant_id, id),
  constraint reorder_proposal_branch_fkey
    foreign key (tenant_id, prepared_branch_id) references branch (tenant_id, id),
  constraint reorder_proposal_tenant_id_key unique (tenant_id, id),
  constraint reorder_proposal_forecast_key unique (tenant_id, demand_forecast_id),
  constraint reorder_proposal_request_key unique (tenant_id, purchase_request_id),
  constraint reorder_proposal_prepared_shape check (
    (status = 'prepared') = (purchase_request_id is not null and prepared_branch_id is not null and prepared_at is not null)
  )
);

create index if not exists demand_forecast_product_created_idx
  on demand_forecast (tenant_id, workspace_product_id, created_at desc);
create index if not exists reorder_proposal_status_idx
  on reorder_proposal (tenant_id, status, created_at desc);

comment on table demand_forecast is
  'Immutable R4.0 forecast evidence. Every row is explicitly marked g3_unmet until the G3 commercial gate passes.';
comment on table reorder_proposal is
  'Human workflow around one forecast. Preparation creates a draft purchase request only; it never executes a purchase order.';

alter table demand_forecast enable row level security;
alter table demand_forecast force row level security;
alter table reorder_proposal enable row level security;
alter table reorder_proposal force row level security;

create policy demand_forecast_tenant_select on demand_forecast
  for select to authenticated using (tenant_id = current_tenant_id());
create policy demand_forecast_owner_buyer_insert on demand_forecast
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

create policy reorder_proposal_tenant_select on reorder_proposal
  for select to authenticated using (tenant_id = current_tenant_id());
create policy reorder_proposal_owner_buyer_insert on reorder_proposal
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));
create policy reorder_proposal_owner_buyer_update on reorder_proposal
  for update to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'))
  with check (tenant_id = current_tenant_id() and current_member_role() in ('owner', 'buyer'));

grant select, insert on demand_forecast to authenticated;
grant select, insert, update on reorder_proposal to authenticated;
grant select, insert on demand_forecast to service_role;
grant select, insert, update on reorder_proposal to service_role;

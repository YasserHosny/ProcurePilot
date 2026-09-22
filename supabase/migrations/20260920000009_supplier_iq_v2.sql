-- R4.1 Supplier IQ v2: normalized, immutable evidence and negotiation briefs.

alter table supplier_scorecard_snapshot
  add column state text,
  add column confidence text,
  add column release_posture text,
  add column valid_from timestamptz,
  add column valid_until timestamptz,
  add column source_fingerprint text,
  add column observed_history_days integer;

alter table supplier_scorecard_snapshot
  add constraint supplier_scorecard_snapshot_v2_state_check
    check (state is null or state in ('ready', 'provisional', 'insufficient_data')),
  add constraint supplier_scorecard_snapshot_v2_confidence_check
    check (confidence is null or confidence in ('high', 'medium', 'low')),
  add constraint supplier_scorecard_snapshot_v2_release_posture_check
    check (release_posture is null or release_posture = 'g3_unmet'),
  add constraint supplier_scorecard_snapshot_v2_fingerprint_check
    check (rule_version <> 'supplier-scorecard-v2' or source_fingerprint is not null),
  add constraint supplier_scorecard_snapshot_v2_validity_check
    check (valid_until is null or valid_from is null or valid_until >= valid_from),
  add constraint supplier_scorecard_snapshot_v2_history_check
    check (observed_history_days is null or observed_history_days >= 0);

-- V1 snapshots remain one-per-window while fingerprinted V2 snapshots preserve recomputation history.
alter table supplier_scorecard_snapshot
  drop constraint supplier_scorecard_snapshot_unique_window;

create unique index supplier_scorecard_snapshot_legacy_window_key
  on supplier_scorecard_snapshot (tenant_id, supplier_id, window_start, window_end, rule_version)
  where rule_version <> 'supplier-scorecard-v2';

create unique index supplier_scorecard_snapshot_v2_fingerprint_key
  on supplier_scorecard_snapshot (tenant_id, source_fingerprint)
  where source_fingerprint is not null;

alter table synced_bill
  add column due_date date,
  add column remaining_balance_amount numeric(18, 4),
  add column remaining_balance_currency text references supported_currency(code),
  add constraint synced_bill_remaining_balance_non_negative
    check (remaining_balance_amount is null or remaining_balance_amount >= 0),
  add constraint synced_bill_remaining_balance_pair
    check ((remaining_balance_amount is null) = (remaining_balance_currency is null));

create table supplier_scorecard_metric (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  snapshot_id           uuid not null,
  metric_kind           text not null,
  bucket_key            text not null default 'default',
  value                 numeric(18, 8),
  numerator             numeric(18, 8),
  denominator           numeric(18, 8),
  amount                numeric(18, 4),
  currency              text references supported_currency(code),
  sample_count          integer check (sample_count is null or sample_count >= 0),
  confidence            text not null check (confidence in ('high', 'medium', 'low')),
  is_sufficient          boolean not null default true,
  window_start          date,
  window_end            date,
  calculation_version   text not null,
  created_at            timestamptz not null default now(),

  constraint supplier_scorecard_metric_tenant_id_key unique (tenant_id, id),
  constraint supplier_scorecard_metric_snapshot_fkey
    foreign key (tenant_id, snapshot_id)
    references supplier_scorecard_snapshot (tenant_id, id) on delete cascade,
  constraint supplier_scorecard_metric_bucket_key_nonempty check (char_length(bucket_key) > 0),
  constraint supplier_scorecard_metric_amount_currency_pair
    check ((amount is null) = (currency is null)),
  constraint supplier_scorecard_metric_window_valid
    check (window_end is null or window_start is null or window_end >= window_start),
  constraint supplier_scorecard_metric_unique_bucket
    unique (tenant_id, snapshot_id, metric_kind, bucket_key)
);

create index supplier_scorecard_metric_snapshot_idx
  on supplier_scorecard_metric (tenant_id, snapshot_id, metric_kind, bucket_key);

create table supplier_scorecard_evidence (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  metric_id                  uuid not null,
  purchase_order_id          uuid,
  delivery_receipt_id        uuid,
  landed_cost_id             uuid,
  three_way_match_id         uuid,
  synced_bill_id             uuid,
  workspace_product_id       uuid,
  delivery_quality_issue_id  uuid,
  supplier_commercial_term_id uuid,
  created_at                 timestamptz not null default now(),

  constraint supplier_scorecard_evidence_tenant_id_key unique (tenant_id, id),
  constraint supplier_scorecard_evidence_metric_fkey
    foreign key (tenant_id, metric_id)
    references supplier_scorecard_metric (tenant_id, id) on delete cascade,
  constraint supplier_scorecard_evidence_purchase_order_fkey
    foreign key (tenant_id, purchase_order_id) references purchase_order (tenant_id, id),
  constraint supplier_scorecard_evidence_delivery_receipt_fkey
    foreign key (tenant_id, delivery_receipt_id) references delivery_receipt (tenant_id, id),
  constraint supplier_scorecard_evidence_landed_cost_fkey
    foreign key (tenant_id, landed_cost_id) references landed_cost (tenant_id, id),
  constraint supplier_scorecard_evidence_three_way_match_fkey
    foreign key (tenant_id, three_way_match_id) references three_way_match (tenant_id, id),
  constraint supplier_scorecard_evidence_synced_bill_fkey
    foreign key (tenant_id, synced_bill_id) references synced_bill (tenant_id, id),
  constraint supplier_scorecard_evidence_workspace_product_fkey
    foreign key (tenant_id, workspace_product_id) references workspace_product (tenant_id, id),
  constraint supplier_scorecard_evidence_quality_issue_fkey
    foreign key (tenant_id, delivery_quality_issue_id)
    references delivery_quality_issue (tenant_id, id),
  constraint supplier_scorecard_evidence_commercial_term_fkey
    foreign key (tenant_id, supplier_commercial_term_id)
    references supplier_commercial_term (tenant_id, id),
  constraint supplier_scorecard_evidence_exactly_one_source check (
    num_nonnulls(
      purchase_order_id, delivery_receipt_id, landed_cost_id, three_way_match_id,
      synced_bill_id, workspace_product_id, delivery_quality_issue_id,
      supplier_commercial_term_id
    ) = 1
  )
);

create index supplier_scorecard_evidence_metric_idx
  on supplier_scorecard_evidence (tenant_id, metric_id);
create index supplier_scorecard_evidence_sources_idx
  on supplier_scorecard_evidence (tenant_id, purchase_order_id, delivery_receipt_id,
                                  landed_cost_id, three_way_match_id, synced_bill_id,
                                  workspace_product_id, delivery_quality_issue_id,
                                  supplier_commercial_term_id);

create table negotiation_brief (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  supplier_id           uuid not null,
  snapshot_id           uuid not null,
  brief_version         text not null,
  source_fingerprint    text not null,
  release_posture       text not null default 'g3_unmet' check (release_posture = 'g3_unmet'),
  valid_from            timestamptz not null,
  valid_until           timestamptz not null,
  created_by_membership_id uuid not null,
  created_at            timestamptz not null default now(),

  constraint negotiation_brief_tenant_id_key unique (tenant_id, id),
  constraint negotiation_brief_supplier_fkey
    foreign key (tenant_id, supplier_id) references supplier (tenant_id, id),
  constraint negotiation_brief_snapshot_fkey
    foreign key (tenant_id, snapshot_id) references supplier_scorecard_snapshot (tenant_id, id),
  constraint negotiation_brief_created_by_fkey
    foreign key (tenant_id, created_by_membership_id) references membership (tenant_id, id),
  constraint negotiation_brief_validity_check check (valid_until >= valid_from),
  constraint negotiation_brief_unique_version
    unique (tenant_id, supplier_id, snapshot_id, brief_version)
);

create index negotiation_brief_supplier_idx
  on negotiation_brief (tenant_id, supplier_id, created_at desc);

create table negotiation_brief_item (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  brief_id              uuid not null,
  metric_id             uuid,
  item_kind             text not null,
  rank                  integer not null check (rank > 0),
  value                 numeric(18, 8),
  amount                numeric(18, 4),
  currency              text references supported_currency(code),
  confidence            text not null check (confidence in ('high', 'medium', 'low')),
  risk                  numeric(18, 8) check (risk is null or risk between 0 and 1),
  valid_from            timestamptz not null,
  valid_until           timestamptz not null,
  question_i18n_key     text not null,
  calculation_version   text not null,
  created_at            timestamptz not null default now(),

  constraint negotiation_brief_item_tenant_id_key unique (tenant_id, id),
  constraint negotiation_brief_item_brief_fkey
    foreign key (tenant_id, brief_id) references negotiation_brief (tenant_id, id) on delete cascade,
  constraint negotiation_brief_item_metric_fkey
    foreign key (tenant_id, metric_id) references supplier_scorecard_metric (tenant_id, id),
  constraint negotiation_brief_item_amount_currency_pair
    check ((amount is null) = (currency is null)),
  constraint negotiation_brief_item_validity_check check (valid_until >= valid_from)
);

create index negotiation_brief_item_brief_idx
  on negotiation_brief_item (tenant_id, brief_id, rank);

create table negotiation_brief_item_evidence (
  tenant_id       uuid not null references tenant(id) on delete cascade,
  item_id         uuid not null,
  evidence_id     uuid not null,
  created_at      timestamptz not null default now(),

  primary key (tenant_id, item_id, evidence_id),
  constraint negotiation_brief_item_evidence_item_fkey
    foreign key (tenant_id, item_id) references negotiation_brief_item (tenant_id, id)
    on delete cascade,
  constraint negotiation_brief_item_evidence_evidence_fkey
    foreign key (tenant_id, evidence_id) references supplier_scorecard_evidence (tenant_id, id)
    on delete cascade
);

create index negotiation_brief_item_evidence_evidence_idx
  on negotiation_brief_item_evidence (tenant_id, evidence_id);

create table negotiation_brief_action (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,
  brief_id              uuid not null,
  action                 text not null check (action in ('acknowledged', 'dismissed')),
  reason                text,
  idempotency_key       text not null,
  acted_by_membership_id uuid not null,
  created_at            timestamptz not null default now(),

  constraint negotiation_brief_action_tenant_id_key unique (tenant_id, id),
  constraint negotiation_brief_action_brief_fkey
    foreign key (tenant_id, brief_id) references negotiation_brief (tenant_id, id),
  constraint negotiation_brief_action_actor_fkey
    foreign key (tenant_id, acted_by_membership_id) references membership (tenant_id, id),
  constraint negotiation_brief_action_dismiss_reason
    check (action <> 'dismissed' or nullif(btrim(reason), '') is not null),
  constraint negotiation_brief_action_idempotency_key unique (tenant_id, idempotency_key)
);

create index negotiation_brief_action_brief_idx
  on negotiation_brief_action (tenant_id, brief_id, created_at desc);

create or replace function ensure_negotiation_brief_item_evidence()
returns trigger language plpgsql as $$
begin
  if not exists (
    select 1 from negotiation_brief_item_evidence
    where tenant_id = new.tenant_id and item_id = new.id
  ) then
    raise exception 'negotiation brief item requires evidence';
  end if;
  return new;
end;
$$;

create constraint trigger negotiation_brief_item_requires_evidence
after insert on negotiation_brief_item
deferrable initially deferred
for each row execute function ensure_negotiation_brief_item_evidence();

do $$
declare
  table_name text;
begin
  foreach table_name in array array[
    'supplier_scorecard_metric', 'supplier_scorecard_evidence', 'negotiation_brief',
    'negotiation_brief_item', 'negotiation_brief_item_evidence', 'negotiation_brief_action'
  ] loop
    execute format('alter table %I enable row level security', table_name);
    execute format('alter table %I force row level security', table_name);
    execute format(
      'create policy %I on %I for select to authenticated using (tenant_id = current_tenant_id())',
      table_name || '_tenant_select', table_name
    );
    execute format(
      'create policy %I on %I for insert to authenticated with check (tenant_id = current_tenant_id() and current_member_role() in (''owner'', ''buyer''))',
      table_name || '_owner_buyer_insert', table_name
    );
    execute format('grant select, insert on %I to authenticated', table_name);
    execute format('grant select, insert on %I to service_role', table_name);
    execute format('revoke update, delete, truncate on %I from authenticated, service_role', table_name);
  end loop;
end;
$$;

-- v1 snapshot history is also append-only. Existing v1 rows remain untouched.
revoke update, delete, truncate on supplier_scorecard_snapshot from authenticated, service_role;

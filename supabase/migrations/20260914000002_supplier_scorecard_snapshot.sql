-- 20260914000002_supplier_scorecard_snapshot.sql
--
-- R2.4 Supplier IQ scorecard cache. This table stores deterministic, rule-versioned snapshots
-- for performance; the values remain recomputable from source records.

create table if not exists supplier_scorecard_snapshot (
  id                              uuid primary key default gen_random_uuid(),
  tenant_id                       uuid not null references tenant(id) on delete cascade,
  supplier_id                     uuid not null,
  window_start                    date not null,
  window_end                      date not null,
  rule_version                    text not null,
  metrics                         jsonb not null,
  risk_score                      jsonb not null,
  source_counts                   jsonb not null,
  computed_at                     timestamptz not null default now(),
  computed_by_membership_id       uuid,

  constraint supplier_scorecard_snapshot_tenant_id_key unique (tenant_id, id),
  constraint supplier_scorecard_snapshot_supplier_fkey
    foreign key (tenant_id, supplier_id) references supplier (tenant_id, id) on delete cascade,
  constraint supplier_scorecard_snapshot_computed_by_fkey
    foreign key (tenant_id, computed_by_membership_id) references membership (tenant_id, id),
  constraint supplier_scorecard_snapshot_window_valid
    check (window_end >= window_start),
  constraint supplier_scorecard_snapshot_unique_window
    unique (tenant_id, supplier_id, window_start, window_end, rule_version),
  constraint supplier_scorecard_snapshot_metrics_object
    check (jsonb_typeof(metrics) = 'object'),
  constraint supplier_scorecard_snapshot_risk_object
    check (jsonb_typeof(risk_score) = 'object'),
  constraint supplier_scorecard_snapshot_source_counts_object
    check (jsonb_typeof(source_counts) = 'object')
);

create index if not exists supplier_scorecard_snapshot_tenant_supplier_idx
  on supplier_scorecard_snapshot (tenant_id, supplier_id, window_end desc);

comment on table supplier_scorecard_snapshot is
  'Cached deterministic Supplier IQ snapshot for R2.4. It is a replayable cache, not a manual
   supplier review or marketplace rating.';

alter table supplier_scorecard_snapshot enable row level security;
alter table supplier_scorecard_snapshot force  row level security;

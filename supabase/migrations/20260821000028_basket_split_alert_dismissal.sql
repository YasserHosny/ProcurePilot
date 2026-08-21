-- 20260821000028_basket_split_alert_dismissal.sql
--
-- Chunk 4.5 (005-smart-compare-intelligence) introduces exactly two new tables. Offers,
-- recommendations, price history, and live alert conditions are all computed at request time from
-- existing chunk 4.2/4.4 data (workspace_product, supplier, match_decision, landed_cost) — this
-- migration does not touch any of those, and adds no second source of price or match truth.
--
-- basket_split_job is the durable, user-visible job resource behind POST /baskets/optimise and
-- GET /baskets/{id} — same shape as chunk 4.3's extraction_job: Redis/RQ only delivers work to
-- services/optimiser, this row is the source of truth the API polls against.
--
-- alert_dismissal stores only the fact that a human dismissed a specific, deterministically
-- fingerprinted alert condition — never the condition itself, which is always recomputed live on
-- each request (spec.md FR-014). If the underlying condition changes, its fingerprint changes and
-- a new alert can appear even though an earlier, different condition for the same product was
-- dismissed.

do $$ begin
  create type basket_split_job_status as enum ('queued', 'running', 'completed', 'failed');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- basket_split_job
-- ---------------------------------------------------------------------------
create table if not exists basket_split_job (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references tenant(id) on delete cascade,
  requested_by  uuid not null references membership(id),

  -- Exactly two named suppliers (spec.md FR-008, research.md R5) — the buyer chooses which two,
  -- this chunk does not choose for them. Postgres has no native array FK; application code must
  -- verify both ids resolve to suppliers visible in the caller's tenant before insert, the same
  -- discipline field_extraction's polymorphic entity_id already requires in this codebase.
  supplier_ids  uuid[] not null
    constraint basket_split_job_exactly_two_distinct_suppliers
      check (cardinality(supplier_ids) = 2 and supplier_ids[1] <> supplier_ids[2]),

  -- {workspace_product_id, quantity}[] — stored verbatim so a completed or failed solve stays
  -- replayable against exactly what was requested, the same replay discipline chunk 4.4's
  -- landed_cost.raw_inputs already established.
  items         jsonb not null,

  status        basket_split_job_status not null default 'queued',
  result        jsonb,
  error         jsonb,

  created_at    timestamptz not null default now(),
  started_at    timestamptz,
  completed_at  timestamptz,

  constraint basket_split_job_completed_at_only_terminal
    check ((status in ('completed', 'failed')) = (completed_at is not null))
);

create index if not exists basket_split_job_tenant_idx on basket_split_job (tenant_id);
create index if not exists basket_split_job_requested_by_idx on basket_split_job (requested_by);

comment on column basket_split_job.result is
  'Completed shape: {feasible, allocation[], total_landed_cost, single_supplier_baselines[],
   infeasible_items[], solver_version, computed_at}. An infeasible solve is still status=completed
   with result.feasible=false — status=failed is reserved for worker/system failure, never a normal
   commercial "no feasible allocation" outcome. See specs/005-smart-compare-intelligence/research.md R5.';

-- ---------------------------------------------------------------------------
-- alert_dismissal
-- ---------------------------------------------------------------------------
create table if not exists alert_dismissal (
  id                    uuid primary key default gen_random_uuid(),
  tenant_id             uuid not null references tenant(id) on delete cascade,

  alert_fingerprint     text not null,
  kind                  text not null,
  workspace_product_id  uuid not null references workspace_product(id) on delete cascade,
  supplier_id           uuid references supplier(id) on delete cascade,

  dismissed_by          uuid not null references membership(id),
  dismissed_at          timestamptz not null default now()
);

create unique index if not exists alert_dismissal_unique_fingerprint
  on alert_dismissal (tenant_id, alert_fingerprint);
create index if not exists alert_dismissal_tenant_kind_product_idx
  on alert_dismissal (tenant_id, kind, workspace_product_id);

comment on table alert_dismissal is
  'Only the dismissal is durable. Alert conditions are always recomputed live from current
   workspace_product/supplier/match_decision/landed_cost data on every GET /alerts — this table
   never stores a condition, only that a human already actioned one specific fingerprint of it.
   See specs/005-smart-compare-intelligence/research.md R7.';

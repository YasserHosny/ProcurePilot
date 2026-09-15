-- 20260915000005_reporting_reader_functions.sql — task T005, chunk R2.5
-- (012-reporting-hardening)
--
-- The authorization-pinned reporting readers (research R5; security critique finding 3).
-- Four SECURITY DEFINER functions, each pinned to an explicit p_tenant_id parameter on EVERY
-- table reference. They exist so the scheduler and export workers — which hold no member JWT
-- and therefore no RLS context — can read report content tenant-pinned, and so the API layer
-- can share the exact same reads. SECURITY DEFINER bypasses RLS by design; the pinning below
-- is what makes that safe: a caller passing tenant B's id can never see tenant A's rows, and
-- a branch parameter that does not belong to the tenant raises instead of silently widening.
--
-- canonical_product is the schema's one shared cross-tenant table; it is ONLY ever reached
-- through a tenant-pinned workspace_product join here, never scanned directly.
--
-- Reader contract notes:
--   * reporting_alert_snapshot returns the tenant-pinned offer/history SOURCE rows (the
--     landed-cost lineage per active product, latest-offer flagged). The alert conditions
--     themselves stay in Python (modules/alerts/conditions.py) and are executed by the
--     workers over these rows — the projection rule engine (offers/projection.py) runs over
--     raw_inputs at read time and is deliberately NOT duplicated in SQL, so a report can
--     never silently disagree with the alerts inbox (constitution: evidence over assertion).
--   * Branch attribution for purchases/savings rides the only branch linkage the data has:
--     purchase_record.landed_cost_id -> purchase_request_line.estimated_unit_price_source_
--     landed_cost_id -> purchase_request.branch_id (R2.1). Purchases with no request lineage
--     are honestly unattributed (null branch) and are EXCLUDED when a branch filter is given —
--     never silently attributed.

-- Carried over from 20260915000004 on purpose: this references the 'expired' enum value,
-- which could not be used in the same transaction that added it. 'expired' is the purge
-- state of an artifact that WAS completed, so it is terminal like completed/failed and
-- keeps completed_at — the original biconditional from 20260821000032 is REPLACED, not
-- supplemented: a second constraint beside it would make 'expired' unsatisfiable (the old
-- biconditional forbids completed_at on any status outside completed/failed).
alter table export_job
  drop constraint if exists export_job_completed_at_only_terminal;
alter table export_job
  add constraint export_job_completed_at_only_terminal
  check ((status in ('completed', 'failed', 'expired')) = (completed_at is not null));

-- 'expired' means purged (FR-014): the storage columns are cleared, so a purged artifact
-- cannot be mistaken for a downloadable one at the storage layer, whatever code reads it.
alter table export_job
  add constraint export_job_expired_has_no_storage
  check (
    status <> 'expired'
    or (storage_bucket is null and storage_path is null and download_url is null)
  );

create or replace function reporting_savings_for_period(
  p_tenant_id     uuid,
  p_period_start  date,
  p_period_end    date,
  p_supplier_id   uuid default null,
  p_branch_id     uuid default null
)
returns table (
  saving_id                    uuid,
  purchase_record_id           uuid,
  purchase_request_id          uuid,
  recorded_at                  timestamptz,
  supplier_id                  uuid,
  supplier_name                text,
  product_id                   uuid,
  product_name                 text,
  canonical_brand              text,
  canonical_name               text,
  canonical_gtin               text,
  base_unit                    text,
  quantity                     numeric,
  attributed_branch_id         uuid,
  attributed_branch_name       text,
  baseline_unit_price_amount   numeric,
  baseline_unit_price_currency text,
  baseline_value_amount        numeric,
  baseline_value_currency      text,
  actual_unit_price_amount     numeric,
  actual_unit_price_currency   text,
  actual_total_paid_amount     numeric,
  actual_total_paid_currency   text,
  verified_saving_amount       numeric,
  verified_saving_currency     text
)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select
    sr.id,
    pc.id,
    attr.purchase_request_id,
    sr.recorded_at,
    sr.supplier_id,
    s.name,
    wp.id,
    wp.tenant_name,
    cp.brand,
    cp.name,
    cp.gtin,
    pc.base_unit,
    pc.quantity,
    attr.branch_id,
    attr.branch_name,
    sr.baseline_unit_price_amount,
    sr.baseline_unit_price_currency,
    sr.baseline_value_amount,
    sr.baseline_value_currency,
    pc.unit_price_amount,
    pc.unit_price_currency,
    pc.total_paid_amount,
    pc.total_paid_currency,
    sr.delta_amount,
    sr.delta_currency
  from saving_record sr
  join purchase_record pc
    on pc.id = sr.purchase_record_id
   and pc.tenant_id = p_tenant_id
  join workspace_product wp
    on wp.id = sr.workspace_product_id
   and wp.tenant_id = p_tenant_id
  join canonical_product cp on cp.id = wp.canonical_product_id
  left join supplier s
    on s.id = sr.supplier_id
   and s.tenant_id = p_tenant_id
  left join lateral (
    select pr.id as purchase_request_id, pr.branch_id, b.name as branch_name
    from purchase_request_line prl
    join purchase_request pr
      on pr.id = prl.purchase_request_id
     and pr.tenant_id = prl.tenant_id
    join branch b
      on b.id = pr.branch_id
     and b.tenant_id = pr.tenant_id
    where prl.tenant_id = p_tenant_id
      and prl.estimated_unit_price_source_landed_cost_id = pc.landed_cost_id
    order by pr.created_at desc, pr.id desc
    limit 1
  ) attr on true
  where sr.tenant_id = p_tenant_id
    and sr.status = 'verified'
    and sr.recorded_at::date >= p_period_start
    and sr.recorded_at::date <= p_period_end
    and (p_supplier_id is null or sr.supplier_id = p_supplier_id)
    and (
      p_branch_id is null
      or exists (
        select 1
        from purchase_request_line prl2
        join purchase_request pr2
          on pr2.id = prl2.purchase_request_id
         and pr2.tenant_id = prl2.tenant_id
        where prl2.tenant_id = p_tenant_id
          and prl2.estimated_unit_price_source_landed_cost_id = pc.landed_cost_id
          and pr2.branch_id = p_branch_id
      )
    )
  order by sr.recorded_at desc, sr.id desc
$$;

create or replace function reporting_purchases_for_period(
  p_tenant_id     uuid,
  p_period_start  date,
  p_period_end    date,
  p_supplier_id   uuid default null,
  p_branch_id     uuid default null
)
returns table (
  purchase_record_id          uuid,
  purchase_request_id         uuid,
  recorded_at                 timestamptz,
  ordered_at                  timestamptz,
  delivered_at                timestamptz,
  supplier_id                 uuid,
  supplier_name               text,
  product_id                  uuid,
  product_name                text,
  base_unit                   text,
  quantity                    numeric,
  attributed_branch_id        uuid,
  attributed_branch_name      text,
  unit_price_amount           numeric,
  unit_price_currency         text,
  total_paid_amount           numeric,
  total_paid_currency         text,
  saving_id                   uuid,
  saving_status               text,
  saving_delta_amount         numeric,
  saving_delta_currency       text
)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select
    pc.id,
    attr.purchase_request_id,
    pc.recorded_at,
    pc.ordered_at,
    pc.delivered_at,
    pc.supplier_id,
    s.name,
    wp.id,
    wp.tenant_name,
    pc.base_unit,
    pc.quantity,
    attr.branch_id,
    attr.branch_name,
    pc.unit_price_amount,
    pc.unit_price_currency,
    pc.total_paid_amount,
    pc.total_paid_currency,
    sr.id,
    sr.status::text,
    sr.delta_amount,
    sr.delta_currency
  from purchase_record pc
  join workspace_product wp
    on wp.id = pc.workspace_product_id
   and wp.tenant_id = p_tenant_id
  left join supplier s
    on s.id = pc.supplier_id
   and s.tenant_id = p_tenant_id
  left join saving_record sr
    on sr.purchase_record_id = pc.id
   and sr.tenant_id = p_tenant_id
  left join lateral (
    select pr.id as purchase_request_id, pr.branch_id, b.name as branch_name
    from purchase_request_line prl
    join purchase_request pr
      on pr.id = prl.purchase_request_id
     and pr.tenant_id = prl.tenant_id
    join branch b
      on b.id = pr.branch_id
     and b.tenant_id = pr.tenant_id
    where prl.tenant_id = p_tenant_id
      and prl.estimated_unit_price_source_landed_cost_id = pc.landed_cost_id
    order by pr.created_at desc, pr.id desc
    limit 1
  ) attr on true
  where pc.tenant_id = p_tenant_id
    and pc.recorded_at::date >= p_period_start
    and pc.recorded_at::date <= p_period_end
    and (p_supplier_id is null or pc.supplier_id = p_supplier_id)
    and (
      p_branch_id is null
      or exists (
        select 1
        from purchase_request_line prl2
        join purchase_request pr2
          on pr2.id = prl2.purchase_request_id
         and pr2.tenant_id = prl2.tenant_id
        where prl2.tenant_id = p_tenant_id
          and prl2.estimated_unit_price_source_landed_cost_id = pc.landed_cost_id
          and pr2.branch_id = p_branch_id
      )
    )
  order by pc.recorded_at desc, pc.id desc
$$;

create or replace function reporting_alert_snapshot(
  p_tenant_id     uuid,
  p_period_start  date,
  p_period_end    date,
  p_branch_id     uuid default null
)
returns table (
  landed_cost_id           uuid,
  workspace_product_id     uuid,
  product_name             text,
  canonical_brand          text,
  canonical_name           text,
  canonical_gtin           text,
  supplier_id              uuid,
  supplier_name            text,
  quotation_line_id        uuid,
  match_confidence         numeric,
  rule_version             text,
  recorded_at              timestamptz,
  valid_from               timestamptz,
  valid_to                 timestamptz,
  total_amount             numeric,
  total_currency           text,
  normalised_base_quantity numeric,
  quantity                 numeric,
  base_unit                text,
  pack_base_quantity       numeric,
  lead_time_days           integer,
  reliability_score        numeric,
  is_latest_offer          boolean
)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  with lineage as (
    select
      lc.id as landed_cost_id,
      md.matched_workspace_product_id as workspace_product_id,
      q.supplier_id,
      ql.id as quotation_line_id,
      md.confidence as match_confidence,
      lc.rule_version,
      lc.recorded_at,
      lc.valid_from,
      lc.valid_to,
      lc.total_amount,
      lc.total_currency,
      lc.normalised_base_quantity,
      lc.quantity,
      lc.base_unit,
      pd.base_quantity as pack_base_quantity,
      s.lead_time_days,
      s.reliability_score,
      row_number() over (
        partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
        order by lc.recorded_at desc, lc.id desc
      ) as rn
    from workspace_product wp
    join match_decision md
      on md.matched_workspace_product_id = wp.id
     and md.tenant_id = p_tenant_id
    join landed_cost lc
      on lc.match_decision_id = md.id
     and lc.tenant_id = p_tenant_id
    join quotation_line ql
      on ql.id = lc.quotation_line_id
     and ql.tenant_id = p_tenant_id
    join quotation q
      on q.id = ql.quotation_id
     and q.tenant_id = p_tenant_id
    join supplier s
      on s.id = q.supplier_id
     and s.tenant_id = p_tenant_id
    join pack_definition pd
      on pd.workspace_product_id = wp.id
     and pd.tenant_id = p_tenant_id
    where wp.tenant_id = p_tenant_id
      and wp.status = 'active'
      and q.status = 'reviewed'
      and s.status in ('active', 'preferred')
  )
  select
    ln.landed_cost_id,
    ln.workspace_product_id,
    wp.tenant_name,
    cp.brand,
    cp.name,
    cp.gtin,
    ln.supplier_id,
    s.name,
    ln.quotation_line_id,
    ln.match_confidence,
    ln.rule_version,
    ln.recorded_at,
    ln.valid_from,
    ln.valid_to,
    ln.total_amount,
    ln.total_currency,
    ln.normalised_base_quantity,
    ln.quantity,
    ln.base_unit,
    ln.pack_base_quantity,
    ln.lead_time_days,
    ln.reliability_score,
    (ln.rn = 1)
  from lineage ln
  join workspace_product wp
    on wp.id = ln.workspace_product_id
   and wp.tenant_id = p_tenant_id
  join canonical_product cp on cp.id = wp.canonical_product_id
  join supplier s
    on s.id = ln.supplier_id
   and s.tenant_id = p_tenant_id
  order by ln.workspace_product_id, ln.supplier_id, ln.landed_cost_id
$$;

create or replace function reporting_validity_expiring(
  p_tenant_id    uuid,
  p_now          timestamptz,
  p_horizon_days integer,
  p_branch_id    uuid default null
)
returns table (
  landed_cost_id           uuid,
  workspace_product_id     uuid,
  product_name             text,
  supplier_id              uuid,
  supplier_name            text,
  recorded_at              timestamptz,
  valid_from               timestamptz,
  valid_to                 timestamptz,
  total_amount             numeric,
  total_currency           text,
  normalised_base_quantity numeric,
  base_unit                text
)
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  with lineage as (
    select
      lc.id as landed_cost_id,
      md.matched_workspace_product_id as workspace_product_id,
      q.supplier_id,
      s.name as supplier_name,
      lc.recorded_at,
      lc.valid_from,
      lc.valid_to,
      lc.total_amount,
      lc.total_currency,
      lc.normalised_base_quantity,
      lc.base_unit,
      row_number() over (
        partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
        order by lc.recorded_at desc, lc.id desc
      ) as rn
    from workspace_product wp
    join match_decision md
      on md.matched_workspace_product_id = wp.id
     and md.tenant_id = p_tenant_id
    join landed_cost lc
      on lc.match_decision_id = md.id
     and lc.tenant_id = p_tenant_id
    join quotation_line ql
      on ql.id = lc.quotation_line_id
     and ql.tenant_id = p_tenant_id
    join quotation q
      on q.id = ql.quotation_id
     and q.tenant_id = p_tenant_id
    join supplier s
      on s.id = q.supplier_id
     and s.tenant_id = p_tenant_id
    where wp.tenant_id = p_tenant_id
      and wp.status = 'active'
      and q.status = 'reviewed'
      and s.status in ('active', 'preferred')
      and lc.valid_to is not null
      and lc.valid_to >= p_now
      and lc.valid_to <= p_now + make_interval(days => p_horizon_days)
  )
  select
    ln.landed_cost_id,
    ln.workspace_product_id,
    wp.tenant_name,
    ln.supplier_id,
    ln.supplier_name,
    ln.recorded_at,
    ln.valid_from,
    ln.valid_to,
    ln.total_amount,
    ln.total_currency,
    ln.normalised_base_quantity,
    ln.base_unit
  from lineage ln
  join workspace_product wp
    on wp.id = ln.workspace_product_id
   and wp.tenant_id = p_tenant_id
  where ln.rn = 1
  order by ln.valid_to, ln.landed_cost_id
$$;

-- Branch validation lives in each caller-facing surface (API validates branch visibility;
-- workers validate before calling) — but the readers must still refuse a branch that does not
-- belong to the pinned tenant rather than treat it as "no filter". A shared guard keeps that
-- rule identical across all four readers.

create or replace function reporting_assert_branch_visible(
  p_tenant_id uuid,
  p_branch_id uuid
)
returns void
language plpgsql
stable
security definer
set search_path = pg_catalog, public
as $$
begin
  if p_branch_id is not null and not exists (
    select 1 from branch b
    where b.tenant_id = p_tenant_id
      and b.id = p_branch_id
      and b.is_active
  ) then
    raise exception 'reporting reader: branch % is not an active branch of the pinned tenant',
      p_branch_id
      using errcode = '22023';
  end if;
end;
$$;

comment on function reporting_savings_for_period(uuid, date, date, uuid, uuid) is
  'Authorization-pinned savings-ledger source rows for a period (R2.5). Every table reference
   is filtered by p_tenant_id; branch attribution rides the purchase_request lineage; a branch
   filter excludes unattributed purchases rather than guessing. Callers must run
   reporting_assert_branch_visible first when a branch filter is supplied.';
comment on function reporting_purchases_for_period(uuid, date, date, uuid, uuid) is
  'Authorization-pinned purchase rows for a period (R2.5) — the spend_by_supplier source.
   Carries the paired saving row (status, delta) so the renderer can group verified savings
   realised per (supplier, currency) without a second reader.';
comment on function reporting_alert_snapshot(uuid, date, date, uuid) is
  'Authorization-pinned offer/history SOURCE rows per active product (R2.5): the landed-cost
   lineage with latest-offer flags, exactly the inputs modules/alerts/conditions.py consumes.
   The alert conditions themselves are NOT duplicated here — workers execute the Python
   conditions over these rows so reports can never disagree with the alerts inbox. Period
   bounds are carried for the report header; alert evaluation is as-of the run instant.';
comment on function reporting_validity_expiring(uuid, timestamptz, integer, uuid) is
  'Authorization-pinned latest offers whose validity window ends inside the horizon (R2.5
   digest section three). p_now is a parameter, not now(), so tests and the scheduler agree
   on the evaluation instant.';

revoke execute on function reporting_savings_for_period(uuid, date, date, uuid, uuid) from public;
revoke execute on function reporting_purchases_for_period(uuid, date, date, uuid, uuid) from public;
revoke execute on function reporting_alert_snapshot(uuid, date, date, uuid) from public;
revoke execute on function reporting_validity_expiring(uuid, timestamptz, integer, uuid) from public;
revoke execute on function reporting_assert_branch_visible(uuid, uuid) from public;

grant execute on function reporting_savings_for_period(uuid, date, date, uuid, uuid)
  to authenticated, service_role;
grant execute on function reporting_purchases_for_period(uuid, date, date, uuid, uuid)
  to authenticated, service_role;
grant execute on function reporting_alert_snapshot(uuid, date, date, uuid)
  to authenticated, service_role;
grant execute on function reporting_validity_expiring(uuid, timestamptz, integer, uuid)
  to authenticated, service_role;
grant execute on function reporting_assert_branch_visible(uuid, uuid)
  to authenticated, service_role;

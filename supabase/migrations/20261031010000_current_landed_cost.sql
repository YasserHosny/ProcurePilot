-- 20261031010000_current_landed_cost.sql — one landed cost per match decision for readers (PPS-122,
-- ADR-021).
--
-- landed_cost is append-only and versioned: a rule change appends a row for an existing decision
-- (FR-016/017, landed_cost_one_per_decision_per_rule), so since landed-cost-v2 a decision can carry
-- a v1 and a v2 row. Readers that list offers or price history per decision counted such a decision
-- twice: a duplicate-line alert of a line against itself, a doubled rolling average, two rows in
-- the alerts digest and export.
--
--   * current_landed_cost: the latest row per match decision (recorded_at, then id). The
--     decision's cost is that row; the earlier rows stay as audit evidence. security_invoker so
--     the caller's RLS on landed_cost applies, as for current_match_decision.
--   * The two reporting readers read it. Bodies unchanged from 20261031000000 apart from that
--     join; CREATE OR REPLACE keeps SECURITY DEFINER, search_path and grants.

create view current_landed_cost
  with (security_invoker = true)
as
select distinct on (lc.match_decision_id) lc.*
from landed_cost lc
order by lc.match_decision_id, lc.recorded_at desc, lc.id desc;

comment on view current_landed_cost is
  'One row per match decision: its latest landed_cost row. Earlier rows (another rule version) '
  'remain in landed_cost as evidence (ADR-021).';

revoke all on current_landed_cost from public, anon, authenticated;
grant select on current_landed_cost to authenticated, service_role;

CREATE OR REPLACE FUNCTION public.reporting_validity_expiring_unguarded(p_tenant_id uuid, p_now timestamp with time zone, p_horizon_days integer, p_branch_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(landed_cost_id uuid, workspace_product_id uuid, product_name text, supplier_id uuid, supplier_name text, recorded_at timestamp with time zone, valid_from timestamp with time zone, valid_to timestamp with time zone, total_amount numeric, total_currency text, normalised_base_quantity numeric, base_unit text)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
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
        partition by md.matched_workspace_product_id, q.supplier_id
        order by lc.recorded_at desc, lc.id desc
      ) as rn
    from workspace_product wp
    join current_match_decision md
      on md.matched_workspace_product_id = wp.id
     and md.tenant_id = p_tenant_id
    join current_landed_cost lc
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
$function$;

CREATE OR REPLACE FUNCTION public.reporting_alert_snapshot_unguarded(p_tenant_id uuid, p_period_start date, p_period_end date, p_branch_id uuid DEFAULT NULL::uuid)
 RETURNS TABLE(landed_cost_id uuid, workspace_product_id uuid, product_name text, canonical_brand text, canonical_name text, canonical_gtin text, supplier_id uuid, supplier_name text, quotation_line_id uuid, match_confidence numeric, rule_version text, recorded_at timestamp with time zone, valid_from timestamp with time zone, valid_to timestamp with time zone, total_amount numeric, total_currency text, normalised_base_quantity numeric, quantity numeric, base_unit text, pack_base_quantity numeric, lead_time_days integer, reliability_score numeric, is_latest_offer boolean)
 LANGUAGE sql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'public'
AS $function$
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
        partition by md.matched_workspace_product_id, q.supplier_id
        order by lc.recorded_at desc, lc.id desc
      ) as rn
    from workspace_product wp
    join current_match_decision md
      on md.matched_workspace_product_id = wp.id
     and md.tenant_id = p_tenant_id
    join current_landed_cost lc
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
$function$;


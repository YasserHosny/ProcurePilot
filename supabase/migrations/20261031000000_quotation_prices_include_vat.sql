-- 20261031000000_quotation_prices_include_vat.sql — VAT-inclusive quotes keep their printed
-- prices (PPS-122, ADR-021).
--
-- Saudi suppliers print prices that already include 15% VAT («الأسعار شاملة ضريبة القيمة المضافة
-- 15%»). Landed-cost rule v1 adds VAT on top of the unit price, so recording the rate on such a
-- quote would count VAT twice. Quotes stay as printed and say which basis they use:
--
--   * quotation.prices_include_vat — true when the document states its prices include VAT. Set
--     by extraction from that statement and confirmed or changed by the reviewer. Existing rows
--     are false: nothing is reinterpreted retroactively. quotation is already tenant-scoped with
--     ENABLE + FORCE RLS; the new column is covered by its existing policies and grants.
--
-- Landed-cost rule v2 (application code) reads the column: on a VAT-inclusive quote it derives
-- the VAT from the gross price instead of adding it. v1 rows stay as they were (append-only).
--
-- Both rule versions put landed_cost.total on the same basis (what the line costs including
-- VAT, delivery and discount), so the latest offer per supplier no longer splits by
-- rule_version: without this, a supplier with a v1 row and a newer v2 row for the same product
-- would appear as two offers. The two reporting readers below are recreated with only that
-- window changed; their signatures, SECURITY DEFINER, search_path and grants are unchanged.

alter table quotation
  add column prices_include_vat boolean not null default false;

comment on column quotation.prices_include_vat is
  'True when the quote''s printed prices include VAT (ADR-021). Line vat_rate is then the rate '
  'already inside the price, and landed-cost rule v2 derives VAT rather than adding it.';

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
$function$;


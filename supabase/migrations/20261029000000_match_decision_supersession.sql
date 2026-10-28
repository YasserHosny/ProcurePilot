-- 20261029000000_match_decision_supersession.sql — correctable match decisions, still append-only
-- (spec 023 FR-005, research R5).
--
-- 20260819000024 made match_decision append-only with one decision per line and left correction
-- to "its own supersession model later". Spec 023 accepts an unambiguous RFQ fit automatically
-- (owner decision Q1, 2026-10-28), so a wrong automatic match must be correctable. A correction is
-- a NEW row naming the decision it supersedes; no row is ever updated (Constitution II).
--
--   * supersedes_decision_id — set only on a correction.
--   * learned_from_decision_id — set on a decision made because another decision taught the
--     wording (the alias sweep, FR-011), so correcting the teacher can list what it taught.
--
-- One chain per line, enforced here rather than in application code:
--   * one root per line: unique nulls not distinct (tenant_id, quotation_line_id,
--     supersedes_decision_id) — exactly one row per line may have a null supersedes_decision_id;
--   * each decision superseded at most once: unique (supersedes_decision_id);
--   * a correction supersedes a decision of the same line (trigger below); the composite FK keeps
--     it in the same tenant.
-- Together these make each line's decisions a single chain with one head. The view
-- current_match_decision serves the heads; readers that mean "the line's match" read the view.
--
-- Concurrency: two corrections of the same head both pass the trigger, and the unique index on
-- supersedes_decision_id rejects the second (23505), as the one-per-line constraint did for two
-- concurrent first decisions. A second root decision still raises 23505, so the existing
-- "a concurrent runner decided first" handling (unique_violation → re-read) is unchanged.

alter table match_decision
  add column supersedes_decision_id uuid,
  add column learned_from_decision_id uuid;

alter table match_decision
  add constraint match_decision_supersedes_fkey
    foreign key (tenant_id, supersedes_decision_id) references match_decision (tenant_id, id),
  add constraint match_decision_learned_from_fkey
    foreign key (tenant_id, learned_from_decision_id) references match_decision (tenant_id, id),
  add constraint match_decision_not_self_superseding
    check (supersedes_decision_id is null or supersedes_decision_id <> id);

alter table match_decision drop constraint match_decision_one_per_line;

alter table match_decision
  add constraint match_decision_one_root_per_line
    unique nulls not distinct (tenant_id, quotation_line_id, supersedes_decision_id),
  add constraint match_decision_superseded_once
    unique (supersedes_decision_id);

create index if not exists match_decision_learned_from_idx
  on match_decision (learned_from_decision_id)
  where learned_from_decision_id is not null;

create or replace function match_decision_supersession_same_line()
returns trigger
language plpgsql
set search_path = public
as $$
declare
  v_line uuid;
begin
  if new.supersedes_decision_id is null then
    return new;
  end if;
  -- Runs as the inserting role, so RLS applies: another tenant's decision is not visible and is
  -- reported the same way as a missing one (no existence leak).
  select quotation_line_id into v_line
  from match_decision
  where tenant_id = new.tenant_id and id = new.supersedes_decision_id;
  if v_line is null or v_line <> new.quotation_line_id then
    raise exception 'a correction must supersede a decision of the same quotation line'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

create trigger match_decision_supersession_same_line
  before insert on match_decision
  for each row execute function match_decision_supersession_same_line();

-- The head of each line's chain. security_invoker so the caller's RLS on match_decision applies.
create view current_match_decision
  with (security_invoker = true)
as
select md.*
from match_decision md
where not exists (
  select 1
  from match_decision successor
  where successor.supersedes_decision_id = md.id
);

comment on view current_match_decision is
  'One row per decided quotation line: the decision no other decision supersedes (spec 023 R5).';

revoke all on current_match_decision from public, anon, authenticated;
grant select on current_match_decision to authenticated, service_role;

-- The two reporting functions (20261018000004) price products through a decision; a superseded
-- decision attributed the price to the wrong product, so they read the current decision. The
-- bodies below are unchanged apart from that join. CREATE OR REPLACE keeps their grants.

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
        partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
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
$function$
;

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
        partition by md.matched_workspace_product_id, q.supplier_id, lc.rule_version
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
$function$
;

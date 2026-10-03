-- Keep latest-per-product selection and pagination in Postgres, before any row limit.
-- SECURITY INVOKER preserves reorder_proposal RLS under the caller's authenticated JWT.
create or replace function forecasting_latest_reorder_proposals(
  p_offset integer,
  p_limit integer
)
returns table (
  id uuid,
  tenant_id uuid,
  demand_forecast_id uuid,
  workspace_product_id uuid,
  status text,
  purchase_request_id uuid,
  prepared_branch_id uuid,
  created_at timestamptz,
  prepared_at timestamptz,
  dismissed_at timestamptz
)
language sql
stable
security invoker
set search_path = pg_catalog, public
as $$
  with ranked_proposals as (
    select
      rp.id,
      rp.tenant_id,
      rp.demand_forecast_id,
      rp.workspace_product_id,
      rp.status,
      rp.purchase_request_id,
      rp.prepared_branch_id,
      rp.created_at,
      rp.prepared_at,
      rp.dismissed_at,
      row_number() over (
        partition by rp.workspace_product_id
        order by rp.created_at desc, rp.id
      ) as product_rank
    from public.reorder_proposal rp
    where rp.status <> 'dismissed'
  )
  select
    rp.id,
    rp.tenant_id,
    rp.demand_forecast_id,
    rp.workspace_product_id,
    rp.status,
    rp.purchase_request_id,
    rp.prepared_branch_id,
    rp.created_at,
    rp.prepared_at,
    rp.dismissed_at
  from ranked_proposals rp
  where rp.product_rank = 1
  order by rp.created_at desc, rp.id
  offset greatest(p_offset, 0)
  limit greatest(p_limit, 0)
$$;

revoke all on function forecasting_latest_reorder_proposals(integer, integer) from public, anon;
grant execute on function forecasting_latest_reorder_proposals(integer, integer) to authenticated;

-- 20261029070000_match_decision_live_request.sql — which live purchase request prices a match
-- decision, whatever the caller can see (spec 023 FR-005).
--
-- A match decision may be corrected only while no live purchase request is priced from it (a
-- request line's estimated_unit_price_source_landed_cost_id → landed_cost.match_decision_id). The
-- check ran as the caller, and purchase_request RLS (purchase_request_scoped_visibility) hides
-- other branches' requests from a branch-assigned buyer, so such a buyer could correct a match a
-- request they cannot see is priced from.
--
-- This function answers the question for the caller's own tenant only: SECURITY DEFINER so branch
-- visibility does not hide the request, pinned to current_tenant_id() (the verified JWT claim) so
-- another workspace's decision id answers null, exactly like a decision with no request. It
-- returns only the request id, which the API reports so the buyer can ask for it to be withdrawn.

create or replace function match_decision_live_request(p_decision_id uuid)
returns uuid
language sql
stable
security definer
set search_path = pg_catalog, public
as $$
  select pr.id
  from landed_cost lc
  join purchase_request_line prl
    on prl.tenant_id = lc.tenant_id
   and prl.estimated_unit_price_source_landed_cost_id = lc.id
  join purchase_request pr
    on pr.tenant_id = prl.tenant_id
   and pr.id = prl.purchase_request_id
  where lc.tenant_id = current_tenant_id()
    and lc.match_decision_id = p_decision_id
    and pr.status not in ('withdrawn', 'rejected')
  order by pr.id
  limit 1
$$;

revoke all on function match_decision_live_request(uuid) from public, anon;
grant execute on function match_decision_live_request(uuid) to authenticated, service_role;

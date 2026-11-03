-- 20261104000300_rfq_definer_hardening.sql — hardening of the two RFQ status functions that run with
-- the definer's rights (PPS-213, review of 20261103120000_rfq_cancel.sql).
--
-- 1. mark_rfq_converted (20261019000001) converted any RFQ that was "neither a draft nor already
--    converted". Since 20261103120000 that also matched a cancelled RFQ, where setting
--    status = 'converted' would hit rfq_cancelled_at_check and raise instead of returning false. It
--    now converts only from sent, responded or expired, as intended; a cancelled RFQ returns false.
-- 2. cancel_rfq and mark_rfq_converted now pin search_path to pg_catalog, public, pg_temp and
--    schema-qualify every table and helper function they use (the style of 20261018000004), so a
--    caller cannot shadow them with objects in another schema.
--
-- Behaviour is otherwise unchanged: same callers allowed, same checks, same return values.
-- Forward-only; replaces both function bodies in place; grants are re-stated.

create or replace function cancel_rfq(p_rfq_id uuid)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
  v_tenant uuid := public.current_tenant_id();
  v_role text := public.current_membership_role();
  v_member uuid := public.current_membership_id();
begin
  if v_tenant is null or coalesce(v_role, '') not in ('owner', 'buyer') then
    raise exception 'only an owner or buyer can cancel an RFQ' using errcode = '42501';
  end if;

  update public.rfq
  set status = 'cancelled',
      cancelled_at = now()
  where tenant_id = v_tenant
    and id = p_rfq_id
    and status in ('draft', 'sent', 'responded')
    and (v_role = 'owner' or created_by_membership_id = v_member);

  return found;
end;
$$;

create or replace function mark_rfq_converted(p_rfq_id uuid, p_purchase_request_id uuid)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public, pg_temp
as $$
declare
  v_tenant uuid := public.current_tenant_id();
begin
  if v_tenant is null or coalesce(public.current_membership_role(), '') not in ('owner', 'buyer') then
    raise exception 'only an owner or buyer can convert an RFQ' using errcode = '42501';
  end if;

  if not exists (
    select 1
    from public.purchase_request pr
    join public.rfq_response resp
      on resp.tenant_id = pr.tenant_id and resp.id = pr.source_rfq_response_id
    join public.rfq_recipient rec
      on rec.tenant_id = resp.tenant_id and rec.id = resp.rfq_recipient_id
    where pr.tenant_id = v_tenant
      and pr.id = p_purchase_request_id
      and rec.rfq_id = p_rfq_id
  ) then
    return false;
  end if;

  update public.rfq
  set status = 'converted'
  where tenant_id = v_tenant
    and id = p_rfq_id
    and status in ('sent', 'responded', 'expired');

  return found;
end;
$$;

revoke all on function cancel_rfq(uuid) from public, anon;
grant execute on function cancel_rfq(uuid) to authenticated;
revoke all on function mark_rfq_converted(uuid, uuid) from public, anon;
grant execute on function mark_rfq_converted(uuid, uuid) to authenticated;

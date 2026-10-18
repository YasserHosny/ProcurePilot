-- 20261019000001_rfq_mark_converted.sql — any owner or buyer who prepares a request from an RFQ
-- closes that RFQ.
--
-- RfqService.prepare_request ends with `update rfq set status = 'converted'`. Since
-- 20261018000009 the rfq_update policy only matches the RFQ's creator, so when another owner or
-- buyer prepared the request the update matched no rows: the purchase request existed but the RFQ
-- stayed 'sent'/'responded', and a second preparation from it stayed possible.
--
-- Widening rfq_update would let any buyer edit any RFQ. Instead this SECURITY DEFINER function does
-- the one status change, and only when:
--   * the caller is an active owner or buyer (current_membership_role, live lookup);
--   * the purchase request is in the caller's workspace and was prepared from a response to this
--     RFQ (purchase_request.source_rfq_response_id);
--   * the RFQ is in the caller's workspace and is neither a draft nor already converted (one
--     purchase request per RFQ; RfqService.prepare_request also serialises preparations of one
--     RFQ and refuses a converted one).
-- Returns whether this call converted the RFQ.
--
-- It also converts the RFQs a request was already prepared from while the update was
-- creator-only (the backfill at the end).

create or replace function mark_rfq_converted(p_rfq_id uuid, p_purchase_request_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_tenant uuid := current_tenant_id();
begin
  if v_tenant is null or coalesce(current_membership_role(), '') not in ('owner', 'buyer') then
    raise exception 'only an owner or buyer can convert an RFQ' using errcode = '42501';
  end if;

  if not exists (
    select 1
    from purchase_request pr
    join rfq_response resp
      on resp.tenant_id = pr.tenant_id and resp.id = pr.source_rfq_response_id
    join rfq_recipient rec
      on rec.tenant_id = resp.tenant_id and rec.id = resp.rfq_recipient_id
    where pr.tenant_id = v_tenant
      and pr.id = p_purchase_request_id
      and rec.rfq_id = p_rfq_id
  ) then
    return false;
  end if;

  update rfq
  set status = 'converted'
  where tenant_id = v_tenant
    and id = p_rfq_id
    and status not in ('draft', 'converted');

  return found;
end;
$$;

comment on function mark_rfq_converted(uuid, uuid) is
  'Sets rfq.status = converted for an RFQ a purchase request was prepared from, for any active
   owner or buyer of the workspace (rfq_update only matches the creator). 20261019000001.';

revoke all on function mark_rfq_converted(uuid, uuid) from public, anon;
grant execute on function mark_rfq_converted(uuid, uuid) to authenticated;

-- Backfill: RFQs with a purchase request prepared from one of their responses, left
-- 'sent'/'responded'/'expired' by the creator-only update.
update rfq
set status = 'converted'
where status in ('sent', 'responded', 'expired')
  and exists (
    select 1
    from rfq_recipient rec
    join rfq_response resp
      on resp.tenant_id = rec.tenant_id and resp.rfq_recipient_id = rec.id
    join purchase_request pr
      on pr.tenant_id = resp.tenant_id and pr.source_rfq_response_id = resp.id
    where rec.tenant_id = rfq.tenant_id
      and rec.rfq_id = rfq.id
  );

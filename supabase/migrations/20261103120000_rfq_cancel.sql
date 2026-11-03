-- 20261103120000_rfq_cancel.sql — an RFQ can be cancelled (PPS-176).
--
-- A cancelled RFQ is terminal: nothing can be sent, split or prepared from it, and it stays in the
-- history with its lines, recipients and any replies. Cancelling emails nobody.
--
--   * rfq.status gains 'cancelled'; rfq.cancelled_at records when (set exactly when cancelled).
--   * rfq_update only matches the RFQ's creator (20261018000009), so an owner could not cancel a
--     buyer's RFQ. Widening that policy would let any owner edit any RFQ. Instead this SECURITY
--     DEFINER function does the one status change, like mark_rfq_converted (20261019000001), and
--     only when:
--       - the caller is an active owner or buyer (current_membership_role, live lookup);
--       - the RFQ is in the caller's workspace;
--       - the caller is an owner, or the RFQ's creator;
--       - the RFQ is a draft, sent or responded (never converted or already cancelled).
--     It returns whether this call cancelled the RFQ; the API reads the RFQ first (through RLS, so
--     another workspace's RFQ is "not found") and writes the audit event.
--
-- Forward-only, no data change: no existing row is cancelled.

alter table rfq drop constraint rfq_status_check;
alter table rfq add constraint rfq_status_check
  check (status in ('draft', 'sent', 'responded', 'expired', 'converted', 'cancelled'));

alter table rfq add column cancelled_at timestamptz;
alter table rfq add constraint rfq_cancelled_at_check
  check ((status = 'cancelled') = (cancelled_at is not null));

create or replace function cancel_rfq(p_rfq_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_tenant uuid := current_tenant_id();
  v_role text := current_membership_role();
  v_member uuid := current_membership_id();
begin
  if v_tenant is null or coalesce(v_role, '') not in ('owner', 'buyer') then
    raise exception 'only an owner or buyer can cancel an RFQ' using errcode = '42501';
  end if;

  update rfq
  set status = 'cancelled',
      cancelled_at = now()
  where tenant_id = v_tenant
    and id = p_rfq_id
    and status in ('draft', 'sent', 'responded')
    and (v_role = 'owner' or created_by_membership_id = v_member);

  return found;
end;
$$;

comment on function cancel_rfq(uuid) is
  'Sets rfq.status = cancelled for a draft, sent or responded RFQ: any active owner of the
   workspace, or an active buyer for an RFQ they created (rfq_update only matches the creator).
   20261103120000.';

revoke all on function cancel_rfq(uuid) from public, anon;
grant execute on function cancel_rfq(uuid) to authenticated;

-- 20261104000700_rfq_status_guard.sql — a client session can only edit a draft RFQ and send it
-- (PPS-213, P-190).
--
-- rfq_update (20261018000009, widened to an active owner by 20261104000200) matches the RFQ's
-- creator or an owner but does not say which status they may write, so one of them using the
-- database directly could re-open a cancelled RFQ or mark one converted without the API's checks
-- and audit event. A row policy sees only row values, not the
-- transition, so this BEFORE UPDATE trigger does.
--
-- It restricts the client roles only (`authenticated`, `anon`), and by current_user, so:
--   * the server-side functions that move the status keep working: cancel_rfq (20261103120000) and
--     mark_rfq_converted (20261019000001) are SECURITY DEFINER and run as their owner;
--   * the ingestion worker (which marks an RFQ 'responded' under service_role) and the table
--     owner are not restricted.
-- A client role may update only a draft RFQ, with the result a draft (an edit) or 'sent' (the send
-- the API performs under the sender's own session, the creator or an owner). Nothing else changes: the API already behaves
-- this way, so no API change is needed. (Creating an RFQ in another status is a separate gap; it
-- needs a wide test-fixture change and is tracked on PPS-213.)
--
-- Forward-only, no data change.

create or replace function rfq_guard_client_update()
returns trigger
language plpgsql
set search_path = pg_catalog, public, pg_temp
as $$
begin
  if current_user not in ('authenticated', 'anon') then
    return new;
  end if;

  if old.status <> 'draft' or new.status not in ('draft', 'sent') then
    raise exception 'an RFQ can only be edited while it is a draft and sent from there'
      using errcode = '42501';
  end if;

  return new;
end;
$$;

comment on function rfq_guard_client_update() is
  'BEFORE UPDATE guard on rfq: a client role (authenticated, anon) may only update a draft RFQ and
   leave it a draft or sent; every other status change goes through cancel_rfq,
   mark_rfq_converted or the ingestion worker. 20261104000700.';

create trigger rfq_guard_client_update
  before update on rfq
  for each row
  execute function rfq_guard_client_update();

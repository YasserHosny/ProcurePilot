-- 20261029060000_purchase_request_source_snapshot.sql — a request names its supplier to everyone who
-- can read the request (PPS-97, review finding on the round-1 fixes).
--
-- A request prepared from an RFQ response showed its supplier only to members who can read the RFQ
-- tables: rfq_response_select and rfq_recipient_select (20260924203650) pass the RFQ's creator,
-- owners and buyers. Approvers and branch managers, the people deciding the request, saw no
-- supplier at all.
--
-- The request now carries a snapshot of where it came from: source_rfq_id, source_quotation_id and
-- source_supplier_id, derived from source_rfq_response_id. Readers take the supplier from the
-- request itself (purchase_request RLS) and its name from supplier (tenant-wide read), so no RFQ
-- table needs to be readable by approvers.
--
-- The trigger is the only writer of the three columns: it recomputes them on every insert and
-- update from source_rfq_response_id, so a client can neither forge nor forget them. It runs as
-- SECURITY DEFINER because the member preparing the request may not be able to read the RFQ
-- tables either (the guardrail path runs as the worker). It only reads the response named by the
-- row, inside the row's own tenant; the composite FK on source_rfq_response_id already keeps that
-- response in the same tenant.

alter table purchase_request
  add column source_rfq_id uuid,
  add column source_quotation_id uuid,
  add column source_supplier_id uuid;

alter table purchase_request
  add constraint purchase_request_source_rfq_fkey
    foreign key (tenant_id, source_rfq_id) references rfq (tenant_id, id),
  add constraint purchase_request_source_quotation_fkey
    foreign key (tenant_id, source_quotation_id) references quotation (tenant_id, id),
  add constraint purchase_request_source_supplier_fkey
    foreign key (tenant_id, source_supplier_id) references supplier (tenant_id, id);

-- Existing requests (before the trigger exists, so nothing else fires).
update purchase_request pr
set source_rfq_id = rec.rfq_id,
    source_quotation_id = resp.quotation_id,
    source_supplier_id = rec.supplier_id
from rfq_response resp
join rfq_recipient rec
  on rec.tenant_id = resp.tenant_id and rec.id = resp.rfq_recipient_id
where resp.tenant_id = pr.tenant_id
  and resp.id = pr.source_rfq_response_id;

-- Only after the backfill: existing requests prepared from an RFQ would otherwise violate it.
alter table purchase_request
  add constraint purchase_request_source_snapshot_complete
    check (
      (source_rfq_response_id is null)
      = (source_rfq_id is null and source_quotation_id is null and source_supplier_id is null)
    );

create or replace function purchase_request_source_snapshot()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
begin
  if new.source_rfq_response_id is null then
    new.source_rfq_id := null;
    new.source_quotation_id := null;
    new.source_supplier_id := null;
    return new;
  end if;
  select rec.rfq_id, resp.quotation_id, rec.supplier_id
    into new.source_rfq_id, new.source_quotation_id, new.source_supplier_id
  from rfq_response resp
  join rfq_recipient rec
    on rec.tenant_id = resp.tenant_id and rec.id = resp.rfq_recipient_id
  where resp.tenant_id = new.tenant_id
    and resp.id = new.source_rfq_response_id;
  return new;
end;
$$;

revoke all on function purchase_request_source_snapshot() from public, anon, authenticated;

create trigger purchase_request_source_snapshot
  before insert or update on purchase_request
  for each row execute function purchase_request_source_snapshot();

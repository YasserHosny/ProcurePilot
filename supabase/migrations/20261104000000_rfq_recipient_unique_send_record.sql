-- 20261104000000_rfq_recipient_unique_send_record.sql — one recipient row per supplier per RFQ, and
-- a small send record on each recipient (PPS-178, PPS-174).
--
-- 1. rfq_recipient had no uniqueness on (tenant_id, rfq_id, supplier_id), so a repeated supplier id in
--    a request created two recipients and the supplier was emailed twice. The API now de-duplicates;
--    this makes the database refuse it too. Existing duplicates are cleaned first, conservatively:
--    for each duplicate group the row kept is the one that has a reply, else the earliest; only rows
--    that are still unsent ('draft' or 'failed') and have no reply are deleted. If a group still has
--    duplicates after that (for example two sent rows), the unique index fails and the migration
--    stops instead of guessing.
-- 2. The send record: why a delivery failed (a fixed set of reasons, no provider text), how many
--    attempts were made and when the last one was. The web shows the reason per supplier.
--
-- Forward-only.

delete from rfq_recipient d
using (
  select id
  from (
    select r.id,
           row_number() over (
             partition by r.tenant_id, r.rfq_id, r.supplier_id
             order by exists (
                        select 1 from rfq_response resp
                        where resp.tenant_id = r.tenant_id and resp.rfq_recipient_id = r.id
                      ) desc,
                      r.created_at, r.id
           ) as rn
    from rfq_recipient r
  ) ranked
  where ranked.rn > 1
) dup
where d.id = dup.id
  and d.status in ('draft', 'failed')
  and not exists (
    select 1 from rfq_response resp
    where resp.tenant_id = d.tenant_id and resp.rfq_recipient_id = d.id
  );

create unique index rfq_recipient_rfq_supplier_key
  on rfq_recipient (tenant_id, rfq_id, supplier_id);

alter table rfq_recipient
  add column failure_reason text,
  add column send_attempts integer not null default 0,
  add column last_attempt_at timestamptz;

alter table rfq_recipient
  add constraint rfq_recipient_failure_reason_check
    check (failure_reason is null or failure_reason in ('delivery_error', 'missing_contact_email')),
  add constraint rfq_recipient_send_attempts_check
    check (send_attempts >= 0);

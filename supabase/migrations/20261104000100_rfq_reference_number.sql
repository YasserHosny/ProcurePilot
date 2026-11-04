-- 20261104000100_rfq_reference_number.sql — every RFQ gets a per-workspace number (PPS-183).
--
-- RFQs had no human reference, so list rows and the detail page could not be told apart. This adds
-- rfq.reference_number (shown as RFQ-000123), unique per workspace.
--   * Existing RFQs are numbered per workspace in creation order (created_at, id).
--   * New RFQs are numbered by a BEFORE INSERT trigger under a per-workspace advisory lock, so two
--     concurrent creates cannot take the same number; the unique constraint is the backstop.
--   * The trigger function is SECURITY DEFINER with a fixed search_path and an explicit tenant
--     filter, so the max() sees the whole workspace whatever the inserting role can read; it cannot
--     be called directly (trigger functions are not callable) and execute is revoked anyway.
--
-- Forward-only.

alter table rfq add column reference_number bigint;

update rfq
set reference_number = numbered.n
from (
  select id, row_number() over (partition by tenant_id order by created_at, id) as n
  from rfq
) numbered
where rfq.id = numbered.id;

alter table rfq alter column reference_number set not null;
alter table rfq add constraint rfq_reference_number_check check (reference_number > 0);
alter table rfq add constraint rfq_tenant_reference_number_key unique (tenant_id, reference_number);

create or replace function rfq_assign_reference_number()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  if new.reference_number is null then
    perform pg_advisory_xact_lock(hashtextextended('rfq-reference:' || new.tenant_id::text, 0));
    select coalesce(max(reference_number), 0) + 1
      into new.reference_number
    from rfq
    where tenant_id = new.tenant_id;
  end if;
  return new;
end;
$$;

revoke all on function rfq_assign_reference_number() from public, anon, authenticated;

create trigger rfq_assign_reference_number_trg
  before insert on rfq
  for each row execute function rfq_assign_reference_number();

-- 20260919000007_three_way_match_discrepancy.sql — R3.3 normalized comparison evidence

alter type discrepancy_type add value if not exists 'missing_confirmation';
alter type discrepancy_type add value if not exists 'missing_receipt';
alter type discrepancy_type add value if not exists 'quantity_variance';
alter type discrepancy_type add value if not exists 'price_variance';
alter type discrepancy_type add value if not exists 'currency_mismatch';
alter type discrepancy_type add value if not exists 'invoice_without_order';
alter type discrepancy_type add value if not exists 'ambiguous_order';
alter type discrepancy_type add value if not exists 'over_billed_quantity';
alter type discrepancy_type add value if not exists 'over_billed_price';

create type three_way_match_result as enum (
  'matched', 'partial', 'needs_review', 'unmatched', 'unavailable'
);

create table if not exists three_way_match (
  id                         uuid primary key default gen_random_uuid(),
  tenant_id                  uuid not null references tenant(id) on delete cascade,
  purchase_order_id         uuid,
  delivery_receipt_id       uuid,
  synced_bill_id             uuid,
  result                     three_way_match_result not null,
  tolerance_ruleset_version text not null,

  ordered_quantity           numeric(18, 6),
  confirmed_quantity         numeric(18, 6),
  received_quantity          numeric(18, 6),
  invoiced_quantity          numeric(18, 6),
  ordered_unit_price_amount  numeric(18, 4),
  ordered_unit_price_currency text references supported_currency(code),
  invoiced_unit_price_amount numeric(18, 4),
  invoiced_unit_price_currency text references supported_currency(code),
  ordered_total_amount      numeric(18, 4),
  ordered_total_currency    text references supported_currency(code),
  invoiced_total_amount     numeric(18, 4),
  invoiced_total_currency   text references supported_currency(code),

  source_hash                text not null,
  evaluated_at               timestamptz not null default now(),
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now(),

  constraint three_way_match_order_fkey
    foreign key (tenant_id, purchase_order_id) references purchase_order (tenant_id, id),
  constraint three_way_match_receipt_fkey
    foreign key (tenant_id, delivery_receipt_id) references delivery_receipt (tenant_id, id),
  constraint three_way_match_receipt_order_fkey
    foreign key (tenant_id, delivery_receipt_id, purchase_order_id)
    references delivery_receipt (tenant_id, id, purchase_order_id),
  constraint three_way_match_bill_fkey
    foreign key (tenant_id, synced_bill_id) references synced_bill (tenant_id, id),
  constraint three_way_match_tenant_id_key unique (tenant_id, id),
  constraint three_way_match_source_present
    check (purchase_order_id is not null or delivery_receipt_id is not null or synced_bill_id is not null),
  constraint three_way_match_receipt_requires_order
    check (delivery_receipt_id is null or purchase_order_id is not null),
  constraint three_way_match_quantities_non_negative
    check (
      (ordered_quantity is null or ordered_quantity >= 0)
      and (confirmed_quantity is null or confirmed_quantity >= 0)
      and (received_quantity is null or received_quantity >= 0)
      and (invoiced_quantity is null or invoiced_quantity >= 0)
    ),
  constraint three_way_match_amounts_non_negative
    check (
      (ordered_unit_price_amount is null or ordered_unit_price_amount >= 0)
      and (invoiced_unit_price_amount is null or invoiced_unit_price_amount >= 0)
      and (ordered_total_amount is null or ordered_total_amount >= 0)
      and (invoiced_total_amount is null or invoiced_total_amount >= 0)
    ),
  constraint three_way_match_unit_price_currency_pair
    check ((ordered_unit_price_amount is null) = (ordered_unit_price_currency is null)
      and (invoiced_unit_price_amount is null) = (invoiced_unit_price_currency is null)),
  constraint three_way_match_total_currency_pair
    check ((ordered_total_amount is null) = (ordered_total_currency is null)
      and (invoiced_total_amount is null) = (invoiced_total_currency is null))
);

create unique index if not exists three_way_match_current_bill_idx
  on three_way_match (tenant_id, synced_bill_id) where synced_bill_id is not null;
create index if not exists three_way_match_order_idx
  on three_way_match (tenant_id, purchase_order_id, evaluated_at desc);
create index if not exists three_way_match_result_idx
  on three_way_match (tenant_id, result, evaluated_at desc);

comment on table three_way_match is
  'Current deterministic order/receipt/bill comparison. source_hash and ruleset version make the
   evidence replayable; unavailable evidence is represented explicitly, never as zero.';

alter table three_way_match enable row level security;
alter table three_way_match force row level security;

create policy three_way_match_tenant_select on three_way_match
  for select to authenticated using (tenant_id = current_tenant_id());
create policy three_way_match_worker_insert on three_way_match
  for insert to authenticated
  with check (tenant_id = current_tenant_id() and current_member_role() is null);
create policy three_way_match_worker_update on three_way_match
  for update to authenticated
  using (tenant_id = current_tenant_id() and current_member_role() is null)
  with check (tenant_id = current_tenant_id() and current_member_role() is null);

grant select on three_way_match to authenticated;
grant insert, update on three_way_match to authenticated;
grant select, insert, update on three_way_match to service_role;

alter table reconciliation_discrepancy
  add column if not exists three_way_match_id uuid,
  add column if not exists purchase_order_id uuid,
  add column if not exists evidence jsonb not null default '{}'::jsonb,
  add column if not exists source_hash text,
  add column if not exists source_updated_at timestamptz,
  add column if not exists reopened_at timestamptz;

alter table reconciliation_discrepancy
  add constraint reconciliation_discrepancy_three_way_match_fkey
    foreign key (tenant_id, three_way_match_id) references three_way_match (tenant_id, id),
  add constraint reconciliation_discrepancy_purchase_order_fkey
    foreign key (tenant_id, purchase_order_id) references purchase_order (tenant_id, id);

alter table reconciliation_discrepancy
  drop constraint if exists reconciliation_discrepancy_shape;

alter table reconciliation_discrepancy
  add constraint reconciliation_discrepancy_shape check (
    (discrepancy_type = 'unmatched_bill'
      and synced_bill_id is not null and purchase_record_id is null)
    or (discrepancy_type = 'unmatched_purchase'
      and purchase_record_id is not null and synced_bill_id is null)
    or (discrepancy_type = 'amount_mismatch'
      and synced_bill_id is not null and purchase_record_id is not null)
    or (discrepancy_type::text in (
      'missing_confirmation', 'missing_receipt', 'quantity_variance', 'price_variance',
      'currency_mismatch', 'invoice_without_order', 'ambiguous_order',
      'over_billed_quantity', 'over_billed_price'
    ) and three_way_match_id is not null)
  );

create index if not exists reconciliation_discrepancy_three_way_idx
  on reconciliation_discrepancy (tenant_id, three_way_match_id)
  where three_way_match_id is not null;
create index if not exists reconciliation_discrepancy_order_idx
  on reconciliation_discrepancy (tenant_id, purchase_order_id)
  where purchase_order_id is not null;

comment on column reconciliation_discrepancy.evidence is
  'Immutable-at-source comparison snapshot: ordered, confirmed, received, invoiced, tolerance,
   and currency evidence. Re-evaluation may replace the current snapshot and reopen the row.';

create or replace function prevent_member_r3_3_discrepancy_evidence_mutation()
returns trigger
language plpgsql
as $$
begin
  -- Owner/buyer sessions may still update only the legacy resolution columns granted by R3.1.
  -- A null member_role is the established tenant-scoped worker session; service_role is also
  -- intentionally allowed to preserve the sync worker's existing capability.
  if current_member_role() is not null and (
    new.three_way_match_id is distinct from old.three_way_match_id
    or new.purchase_order_id is distinct from old.purchase_order_id
    or new.evidence is distinct from old.evidence
    or new.source_hash is distinct from old.source_hash
    or new.source_updated_at is distinct from old.source_updated_at
    or new.reopened_at is distinct from old.reopened_at
  ) then
    raise exception
      'R3.3 discrepancy evidence and links may only be changed by the sync worker';
  end if;
  return new;
end;
$$;

drop trigger if exists reconciliation_discrepancy_r3_3_evidence_guard
  on reconciliation_discrepancy;
create trigger reconciliation_discrepancy_r3_3_evidence_guard
  before update on reconciliation_discrepancy
  for each row
  execute function prevent_member_r3_3_discrepancy_evidence_mutation();

-- Preserve the existing R3.1 resolution grant and add only the columns the tenant-scoped worker
-- needs to refresh R3.3 evidence. Existing API inserts remain valid because all new fields default
-- or remain nullable.
grant insert (
  tenant_id, discrepancy_type, synced_bill_id, purchase_record_id, status, detected_at,
  three_way_match_id, purchase_order_id, evidence, source_hash, source_updated_at, reopened_at
) on reconciliation_discrepancy to authenticated;

grant update (
  status, resolved_by, resolved_at, resolution_note, three_way_match_id, purchase_order_id,
  evidence, source_hash, source_updated_at, reopened_at
) on reconciliation_discrepancy to authenticated;

grant select, insert, update on reconciliation_discrepancy to service_role;
